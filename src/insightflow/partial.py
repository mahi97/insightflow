"""Partial-run monitoring.

Given an in-flight run's partial learning curve, recommend whether to
``continue``, ``pause``, ``stop``, ``promote``, ``add_seed``, or
``launch_baseline``. The guiding principle from the spec: decide on *decision
impact*, not on current performance alone. A run that is doing great but can no
longer change any claim is a candidate to stop; a mediocre run that sits on a
claim's decision boundary may be worth continuing.

This is a transparent heuristic stand-in for the freeze-thaw / learning-curve
extrapolation models on the v0.2 roadmap (see ``docs/roadmap.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import (
    ActionType,
    Experiment,
    PlanAction,
    Policy,
    RunResult,
    RunStatus,
    State,
)
from .scoring import ClaimEvidence
from .utils import mean


@dataclass
class PartialDecision:
    action_type: ActionType
    urgency: float
    reason: str
    factors: dict[str, float] = field(default_factory=dict)


def _trajectory(result: RunResult, metric: str) -> list[float]:
    return [float(p[metric]) for p in result.partial_history if metric in p]


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    # Average step-to-step change over the most recent half of the curve.
    half = values[len(values) // 2 :]
    if len(half) < 2:
        half = values[-2:]
    return (half[-1] - half[0]) / max(1, len(half) - 1)


def _baseline_value(state: State, exp: Experiment, metric: str) -> float | None:
    vals: list[float] = []
    for other in state.experiments:
        if other.is_baseline and other.cell_key == exp.cell_key:
            for r in state.results_for(other.id):
                if r.status == RunStatus.completed:
                    v = r.metric(metric)
                    if v is not None:
                        vals.append(v)
    return mean(vals) if vals else None


def monitor_partial(
    result: RunResult,
    exp: Experiment,
    state: State,
    evidence: dict[str, ClaimEvidence],
    policy: Policy,
) -> PartialDecision:
    """Recommend an action for one in-flight run."""
    linked = [evidence[c] for c in exp.claim_links if c in evidence]
    metric = next((ev.claim.target_metric for ev in linked), "accuracy")
    traj = _trajectory(result, metric)

    if not traj:
        return PartialDecision(ActionType.continue_, 0.2, "No partial metric yet; keep going.")

    current = traj[-1]
    slope = _slope(traj)
    factors = {"current": current, "slope": slope}

    # 1) Does this run still matter for any claim?
    any_near_boundary = any(ev.confidence.near_boundary for ev in linked)
    if linked and not any_near_boundary:
        return PartialDecision(
            ActionType.stop,
            0.7,
            "Linked claim(s) are already decided; this run can no longer change the "
            "decision, so stop it to free the worker.",
            factors,
        )

    direction_lower = bool(linked) and linked[0].claim.desired_direction.value == "lower"
    baseline = _baseline_value(state, exp, metric)

    def oriented(value: float) -> float:
        return -value if direction_lower else value

    improving = oriented(slope) > 0
    declining = oriented(slope) < -1e-9

    # 2) Baseline available: judge against it.
    if baseline is not None:
        gap = oriented(current - baseline)
        factors["gap_vs_baseline"] = gap
        if gap < 0 and not improving:
            return PartialDecision(
                ActionType.stop,
                0.6,
                "Trailing the baseline with no upward trend; unlikely to support the "
                "claim, so stop rather than spend more compute.",
                factors,
            )
        if gap > 0 and not declining:
            cell = exp.cell_key
            seeds = linked[0].seeds_per_cell.get(cell, 0) if linked else 0
            required = linked[0].claim.required_seeds if linked else 3
            if linked and linked[0].claim.importance >= 0.7 and seeds < required:
                return PartialDecision(
                    ActionType.continue_,
                    0.5,
                    "Beating the baseline on a claim-critical, under-seeded condition; "
                    "continue to lock in the result.",
                    factors,
                )
            return PartialDecision(
                ActionType.promote,
                0.5,
                "Clearly beats the baseline; promote this result and shift workers to "
                "uncovered conditions instead of more replication.",
                factors,
            )
        return PartialDecision(
            ActionType.continue_, 0.4, "Still informative near the decision boundary; continue.", factors
        )

    # 3) No baseline yet.
    if improving:
        return PartialDecision(
            ActionType.launch_baseline,
            0.6,
            "Method looks strong but there is no baseline to compare against; launch the "
            "baseline so the claim can actually be decided.",
            factors,
        )
    if declining:
        return PartialDecision(
            ActionType.pause,
            0.5,
            "Flat or declining early curve with low decision value; pause to reconsider "
            "before spending the full budget.",
            factors,
        )
    return PartialDecision(ActionType.continue_, 0.3, "Early but inconclusive; continue.", factors)


def monitor_all(
    state: State,
    evidence: dict[str, ClaimEvidence],
    policy: Policy,
) -> list[PlanAction]:
    """Produce PlanActions for every in-flight run that has a partial curve."""
    actions: list[PlanAction] = []
    for result in state.results:
        if result.status not in (RunStatus.running, RunStatus.partial):
            continue
        if not result.partial_history:
            continue
        exp = state.experiment(result.experiment_id)
        if exp is None:
            continue
        decision = monitor_partial(result, exp, state, evidence, policy)
        # Score for a partial action: urgency divided by remaining cost proxy.
        denom = max(1e-6, exp.expected_time + policy.lambda_cost * exp.expected_cost)
        score = round(decision.urgency / denom, 4)
        label = f"{exp.method} / {exp.dataset} / {exp.condition} / seed={exp.seed}"
        actions.append(
            PlanAction(
                experiment_id=exp.id,
                action_type=decision.action_type,
                score=score,
                affected_claims=list(exp.claim_links),
                rationale=decision.reason,
                expected_decision_value=round(decision.urgency, 4),
                expected_cost=exp.expected_cost,
                expected_time=exp.expected_time,
                risk=0.0,
                checkpoint=f"step={len(result.partial_history)}",
                factors={k: round(float(v), 4) for k, v in decision.factors.items()},
                label=label,
            )
        )
    return actions

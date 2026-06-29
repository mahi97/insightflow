"""Partial-run monitoring.

Given an in-flight run's partial learning curve, recommend whether to
``continue``, ``pause``, ``stop``, ``promote``, ``add_seed``, or
``launch_baseline``. The guiding principle from the spec: decide on *decision
impact*, not on current performance alone. A run that is doing great but can no
longer change any claim is a candidate to stop; a mediocre run that sits on a
claim's decision boundary may be worth continuing.

Decisions are made on the *projected final value* of the run, extrapolated from
its partial curve by a deterministic saturating-exponential fit (``curves.py``) —
a freeze-thaw-style judgement of where the run will end up, not just where it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .curves import fit_learning_curve
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


def _steps_and_values(result: RunResult, metric: str) -> tuple[list[float], list[float]]:
    steps, values = [], []
    for i, p in enumerate(result.partial_history):
        if metric in p:
            steps.append(float(p.get("step", i)))
            values.append(float(p[metric]))
    return steps, values


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
    """Recommend an action for one in-flight run, judged on the *projected* final
    value (freeze-thaw learning-curve extrapolation), not just the current value."""
    linked = [evidence[c] for c in exp.claim_links if c in evidence]
    metric = next((ev.claim.target_metric for ev in linked), "accuracy")
    steps, values = _steps_and_values(result, metric)

    if not values:
        return PartialDecision(ActionType.continue_, 0.2, "No partial metric yet; keep going.")

    current = values[-1]
    fit = fit_learning_curve(steps, values)
    projected = fit.projected_final
    factors = {
        "current": round(current, 4),
        "projected_final": round(projected, 4),
        "remaining": round(fit.trend, 4),
        "curve_fit": 1.0 if fit.ok else 0.0,
    }

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

    def oriented(value: float) -> float:
        return -value if direction_lower else value

    # "Improving" / "declining" use where the curve is *headed*, not just slope.
    improving = oriented(fit.trend) > 1e-4 or oriented(_slope(values)) > 0
    declining = oriented(fit.trend) < -1e-4

    # 2) Baseline available: judge the *projected* final against it.
    baseline = _baseline_value(state, exp, metric)
    if baseline is not None:
        gap = oriented(projected - baseline)
        factors["projected_gap_vs_baseline"] = round(gap, 4)
        if gap < 0:
            return PartialDecision(
                ActionType.stop,
                0.6,
                f"Projected final ({projected:.4f}) trails the baseline ({baseline:.4f}); "
                "the curve will not clear it, so stop rather than spend more compute.",
                factors,
            )
        cell = exp.cell_key
        seeds = linked[0].seeds_per_cell.get(cell, 0) if linked else 0
        required = linked[0].claim.required_seeds if linked else 3
        if linked and linked[0].claim.importance >= 0.7 and seeds < required and improving:
            return PartialDecision(
                ActionType.continue_,
                0.5,
                f"Projected to beat the baseline ({projected:.4f} vs {baseline:.4f}) on a "
                "claim-critical, under-seeded condition; continue to lock it in.",
                factors,
            )
        return PartialDecision(
            ActionType.promote,
            0.5,
            f"Projected to clearly beat the baseline ({projected:.4f} vs {baseline:.4f}); "
            "promote and shift workers to uncovered conditions instead of more replication.",
            factors,
        )

    # 3) No baseline yet.
    if improving:
        return PartialDecision(
            ActionType.launch_baseline,
            0.6,
            f"Projected final {projected:.4f} looks strong but there is no baseline to "
            "compare against; launch the baseline so the claim can be decided.",
            factors,
        )
    if declining:
        return PartialDecision(
            ActionType.pause,
            0.5,
            "Curve is flat or declining with low decision value; pause before spending "
            "the full budget.",
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

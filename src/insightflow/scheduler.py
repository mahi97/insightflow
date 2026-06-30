"""The deterministic scheduler.

Takes the current :class:`State`, scores every available action, and produces a
:class:`Plan` with an immediate queue, postponed actions, avoided actions,
warnings, a claim-confidence table, and a human-readable summary.

Action enumeration is where the "extra seed vs new condition" distinction is
made concrete: a pending experiment whose *cell* (dataset x condition) has not
been observed yet is a **new-condition launch**; one whose cell is already
observed is an **extra seed**, routed through the seed policy. The scoring terms
then make breadth outrank premature replication.
"""

from __future__ import annotations

from .actions import generate_research_actions, score_research_action
from .errors import SchedulerError
from .partial import monitor_all
from .schemas import (
    ActionType,
    ExperimentStatus,
    Plan,
    PlanAction,
    State,
)
from .scoring import Scorer, compute_claim_evidence
from .seed_policy import decide_seed
from .utils import now_iso, stable_hash


def compute_state_hash(state: State) -> str:
    payload = {
        "experiments": sorted(
            [(e.id, e.status.value) for e in state.experiments]
        ),
        "results": sorted(
            [(r.run_id, r.experiment_id, tuple(sorted(r.metrics.items()))) for r in state.results]
        ),
    }
    return stable_hash(payload)


class Scheduler:
    """Deterministic, heuristic action scheduler (advisor mode)."""

    def __init__(self, state: State):
        self.state = state
        self.policy = state.policy
        # Bayesian (value-of-information) scores live on a different, smaller scale
        # than the heuristic ones. There, keep the best action queued until the
        # posterior actually decides — EVOI only reaches ~0 when nothing is left to
        # learn — so use a near-zero queue threshold instead of the heuristic 0.15.
        if self.policy.confidence_model == "bayes":
            self.queue_threshold = 1e-4
            self.avoid_threshold = 1e-6
        else:
            self.queue_threshold = self.policy.queue_threshold
            self.avoid_threshold = self.policy.avoid_threshold

    def plan(self, created_at: str | None = None) -> Plan:
        state = self.state
        evidence = compute_claim_evidence(state)
        scorer = Scorer(state, evidence)
        completed = state.completed_experiment_ids()

        scored: list[tuple[PlanAction, str]] = []  # (action, classification hint)

        for exp in state.experiments:
            # Already-finished experiments (by status or by a completed result) are
            # not candidates, even if their status field was not refreshed.
            if exp.id in completed:
                continue
            if exp.status not in (ExperimentStatus.pending, ExperimentStatus.postponed):
                continue

            deps_met = all(d in completed for d in exp.dependencies)

            # Is this cell already observed for any linked claim? -> extra seed.
            observed = any(
                exp.cell_key in evidence[c].observed_conditions
                for c in exp.claim_links
                if c in evidence
            )

            if observed and not exp.is_baseline:
                decision = decide_seed(exp, evidence, self.policy)
                action = scorer.score_add_seed(exp, decision)
            else:
                action = scorer.score_launch(exp)

            if not deps_met:
                blockers = [d for d in exp.dependencies if d not in completed]
                action.rationale = (
                    f"Blocked by unfinished dependencies: {', '.join(blockers)}. " + action.rationale
                )
                scored.append((action, "blocked"))
            else:
                scored.append((action, "open"))

        # In-flight runs (partial monitoring).
        for action in monitor_all(state, evidence, self.policy):
            scored.append((action, "running"))

        # Research actions (user-defined in actions.yaml + auto-generated from the
        # evidence): literature search, reviewer attack, claim refinement, theorem
        # attempt, etc. — scored against experiments so the planner can say "do a
        # literature search before spending compute".
        research = list(state.research_actions) + generate_research_actions(state, evidence)
        seen_action_ids: set[str] = set()
        for ra in research:
            if ra.id in seen_action_ids:
                continue
            seen_action_ids.add(ra.id)
            scored.append((score_research_action(ra, state, evidence), "open"))

        scored.sort(key=lambda pair: pair[0].score, reverse=True)

        queue, postponed, avoided = self._classify(scored)
        claim_conf = [evidence[c.id].confidence for c in state.claims]
        warnings = self._warnings(state, evidence, queue)
        summary = self._summary(queue, postponed)
        assumptions = self._assumptions()
        state_hash = compute_state_hash(state)

        plan = Plan(
            id=f"plan_{state_hash}",
            created_at=created_at or now_iso(),
            actions=queue,
            postponed=postponed,
            avoided=avoided,
            claim_confidence=claim_conf,
            summary=summary,
            warnings=warnings,
            assumptions=assumptions,
            state_hash=state_hash,
        )
        return plan

    # -- classification -----------------------------------------------------
    def _classify(
        self, scored: list[tuple[PlanAction, str]]
    ) -> tuple[list[PlanAction], list[PlanAction], list[PlanAction]]:
        p = self.policy
        queue: list[PlanAction] = []
        postponed: list[PlanAction] = []
        avoided: list[PlanAction] = []
        # Diversify the immediate queue: at most one run per (cell, role) so the
        # queue spreads breadth across conditions instead of stacking seeds of a
        # single new condition. A second same-cell run is, by definition, an
        # extra seed and belongs in 'postponed'.
        queued_cells: set[tuple[str, bool]] = set()

        for action, hint in scored:
            # Running-run actions are surfaced directly in the queue (monitoring).
            if hint == "running":
                if action.action_type in (ActionType.stop, ActionType.pause):
                    queue.append(action)
                elif action.score >= self.avoid_threshold:
                    queue.append(action)
                else:
                    postponed.append(action)
                continue

            if hint == "blocked":
                postponed.append(_relabel(action, ActionType.postpone))
                continue

            exp = self.state.experiment(action.experiment_id)
            cell_role = (exp.cell_key, exp.is_baseline) if exp else (action.experiment_id, False)
            duplicate_cell = cell_role in queued_cells

            if action.score >= self.queue_threshold and len(queue) < p.top_k and not duplicate_cell:
                queue.append(action)
                queued_cells.add(cell_role)
            elif action.score >= self.avoid_threshold:
                relabeled = _relabel(action, ActionType.postpone)
                if duplicate_cell:
                    relabeled.rationale += (
                        " (extra seed of a condition already in the immediate queue; "
                        "do breadth first)."
                    )
                postponed.append(relabeled)
            else:
                avoided.append(_relabel(action, ActionType.avoid))

        return queue, postponed, avoided

    # -- warnings -----------------------------------------------------------
    def _warnings(self, state: State, evidence: dict, queue: list[PlanAction]) -> list[str]:
        warnings: list[str] = []
        for cid, ev in evidence.items():
            claim = ev.claim
            if ev.confidence.status.value in ("weak", "refuted"):
                warnings.append(
                    f"Claim {cid} is currently '{ev.confidence.status.value}' "
                    f"(confidence {ev.confidence.confidence:.2f}): {ev.confidence.note}."
                )
            if claim.reviewer_risk >= 0.6 and ev.baseline_missing_cells:
                warnings.append(
                    f"Reviewer risk: claim {cid} has {len(ev.baseline_missing_cells)} "
                    "observed condition(s) without a baseline - a reviewer could attack this."
                )
            if claim.importance >= 0.7 and ev.evidence_breadth < 1.0 and ev.observed_conditions:
                warnings.append(
                    f"Generality of claim {cid} is unverified: only "
                    f"{ev.evidence_breadth:.0%} of its conditions have been observed."
                )

        # Budget check against the immediate queue.
        budget = state.resources.budget_gpu_hours
        if budget is not None:
            queue_cost = sum(a.expected_cost for a in queue)
            if queue_cost > budget:
                warnings.append(
                    f"Immediate queue costs ~{queue_cost:.1f} units but the budget is {budget:.1f}."
                )

        if not state.experiments:
            warnings.append("No experiments defined. Add experiments to configs/experiments.yaml.")
        elif not any(e.status == ExperimentStatus.pending for e in state.experiments):
            warnings.append("No pending experiments. Nothing left to schedule.")
        return warnings

    # -- summary ------------------------------------------------------------
    def _summary(self, queue: list[PlanAction], postponed: list[PlanAction]) -> str:
        if not queue:
            return "No actions cleared the queue threshold. See postponed/avoided for context."
        top = queue[0]
        lines = [
            "Top recommendation:",
            f"  {top.action_type.value} {top.label}.",
            f"  Reason: {top.rationale}",
        ]
        # Find the most representative postponed extra-seed for contrast.
        seed_postpone = next(
            (a for a in postponed if a.action_type in (ActionType.postpone, ActionType.add_seed)),
            None,
        )
        if seed_postpone is not None:
            lines += [
                "",
                "Postpone:",
                f"  {seed_postpone.label}.",
                f"  Reason: {seed_postpone.rationale}",
            ]
        return "\n".join(lines)

    def _assumptions(self) -> list[str]:
        return [
            "Advisor mode: InsightFlow recommends; it does not launch, pause, or kill runs.",
            "Claim confidence is a transparent heuristic, not a calibrated Bayesian posterior "
            "(see docs/concepts.md). Treat it as a ranking signal.",
            "Scoring is deterministic: the same ledger + policy always yields the same plan.",
            f"Cost term uses lambda={self.policy.lambda_cost} over (time + lambda*cost).",
        ]


def _relabel(action: PlanAction, new_type: ActionType) -> PlanAction:
    """Return a copy of ``action`` whose recommended action_type is changed.

    Used to mark postponed/avoided items while preserving the score breakdown.
    """
    data = action.model_dump()
    original = action.action_type.value
    data["action_type"] = new_type.value
    prefix = {ActionType.postpone: "Postpone", ActionType.avoid: "Avoid"}.get(new_type, "")
    if prefix and not data["rationale"].startswith(prefix):
        data["rationale"] = f"{prefix} ({original}): {data['rationale']}"
    return PlanAction(**data)


def build_plan(state: State, created_at: str | None = None) -> Plan:
    """Convenience wrapper used by the CLI and benchmark."""
    if state is None:
        raise SchedulerError("No state provided to the scheduler.")
    return Scheduler(state).plan(created_at=created_at)

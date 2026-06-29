"""Offline replay evaluation.

Given a project whose results are *already* known (e.g. imported from W&B/CSV/
MLflow), replay them as if they arrived over time and ask: would InsightFlow have
reached the correct research decision with fewer runs than the order they were
actually run in?

This is a counterfactual, leak-free evaluation:

* The **ground truth** decision is what the *complete* history supports.
* The **actual** trajectory reveals results in their real arrival order.
* The **InsightFlow** trajectory repeatedly asks the scheduler what to run next
  and reveals that result *if it exists in the history* (you can only replay runs
  that were actually performed), until the claims are decided.

The gap is how many runs InsightFlow would have saved on this real project.
"""

from __future__ import annotations

from dataclasses import dataclass

from .scheduler import build_plan
from .schemas import (
    ActionType,
    ClaimStatus,
    ExperimentStatus,
    RunResult,
    RunStatus,
    State,
)
from .scoring import compute_claim_confidence

_DECIDED = (ClaimStatus.supported, ClaimStatus.refuted)


@dataclass
class ReplayResult:
    total_runs: int
    ground_truth: dict[str, str]
    actual_decided_at: int | None
    insight_decided_at: int | None
    runs_saved: int | None
    insight_order: list[str]


def _state_with(base: State, results: list[RunResult]) -> State:
    done = {r.experiment_id for r in results if r.status == RunStatus.completed}
    exps = [
        e.model_copy(update={"status": ExperimentStatus.completed})
        if e.id in done
        else e.model_copy(update={"status": ExperimentStatus.pending})
        for e in base.experiments
    ]
    return State(
        claims=list(base.claims),
        experiments=exps,
        results=list(results),
        policy=base.policy,
        resources=base.resources,
    )


def _decided(state: State, gt: dict[str, str]) -> bool:
    conf = {c.claim_id: c.status for c in compute_claim_confidence(state).values()}
    return all(conf.get(cid) == ClaimStatus(status) for cid, status in gt.items())


def _arrival_order(state: State) -> list[RunResult]:
    """Real arrival order: by finished_at when present, else original order."""
    completed = [r for r in state.results if r.status == RunStatus.completed]
    indexed = sorted(enumerate(completed), key=lambda iv: (iv[1].finished_at or "", iv[0]))
    return [r for _, r in indexed]


def replay(state: State) -> ReplayResult:
    """Replay a project's known results and compare actual vs InsightFlow order."""
    history = _arrival_order(state)
    results_by_exp = {r.experiment_id: r for r in history}

    # Ground truth: the decision the full history supports.
    full = compute_claim_confidence(state)
    gt = {c.claim_id: c.status.value for c in full.values() if c.status in _DECIDED}

    # Actual: reveal in real arrival order.
    actual_at: int | None = None
    revealed: list[RunResult] = []
    for i, r in enumerate(history, start=1):
        revealed.append(r)
        if gt and _decided(_state_with(state, revealed), gt):
            actual_at = i
            break

    # InsightFlow: greedily follow the scheduler, constrained to runs we actually have.
    insight_at: int | None = None
    revealed = []
    revealed_ids: set[str] = set()
    order: list[str] = []
    for step in range(1, len(history) + 1):
        st = _state_with(state, revealed)
        plan = build_plan(st)
        nxt = None
        for a in plan.actions:
            if a.action_type in (ActionType.launch, ActionType.add_seed, ActionType.launch_baseline):
                if a.experiment_id in results_by_exp and a.experiment_id not in revealed_ids:
                    nxt = a.experiment_id
                    break
        if nxt is None:  # scheduler had nothing available; reveal any remaining run
            remaining = [r for r in history if r.experiment_id not in revealed_ids]
            if not remaining:
                break
            nxt = remaining[0].experiment_id
        revealed.append(results_by_exp[nxt])
        revealed_ids.add(nxt)
        order.append(nxt)
        if gt and _decided(_state_with(state, revealed), gt):
            insight_at = step
            break

    runs_saved = (
        actual_at - insight_at if (actual_at is not None and insight_at is not None) else None
    )
    return ReplayResult(
        total_runs=len(history),
        ground_truth=gt,
        actual_decided_at=actual_at,
        insight_decided_at=insight_at,
        runs_saved=runs_saved,
        insight_order=order,
    )

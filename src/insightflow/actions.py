"""Research actions beyond training runs.

A claim-centered planner must be able to recommend more than runs: a
literature/novelty check, a reviewer-style attack on a thin claim, a theorem
attempt for a theory claim, a claim refinement for a refuted one, and so on.

This module (1) **auto-generates** the research actions that the current evidence
warrants and (2) **scores** any research action (user-defined in ``actions.yaml``
or auto-generated) into a :class:`PlanAction`, so the scheduler ranks them
against experiments by value per unit (human/compute) cost. Non-run actions carry
an ``instruction`` for a human or agent rather than a ``command``.

Everything is a deterministic function of the claim evidence.
"""

from __future__ import annotations

from .schemas import (
    ActionType,
    ClaimStatus,
    ClaimType,
    PlanAction,
    ResearchAction,
    State,
)
from .scoring import ClaimEvidence

_DECIDED_LOOKING = (ClaimStatus.supported, ClaimStatus.weak, ClaimStatus.needs_more_evidence)


def _claim_need(atype: ActionType, ev: ClaimEvidence) -> float:
    """How much this action type is needed, given one claim's evidence. In [0, ~1]."""
    c = ev.claim
    status = ev.confidence.status
    has_runs = bool(ev.observed_conditions)
    breadth_incomplete = has_runs and ev.evidence_breadth < 1.0
    thin = breadth_incomplete or (has_runs and ev.seed_sufficiency < 1.0)
    no_evidence = not has_runs

    if atype == ActionType.literature_search:
        return c.importance * c.reviewer_risk * (1.0 if no_evidence else 0.3)
    if atype == ActionType.reviewer_attack:
        return c.reviewer_risk * (1.0 if (status in _DECIDED_LOOKING and thin) else 0.2)
    if atype in (ActionType.theorem_attempt, ActionType.counterexample_search,
                 ActionType.proof_verification):
        return c.importance * (1.0 if (c.type == ClaimType.theory and status != ClaimStatus.supported)
                               else 0.1)
    if atype in (ActionType.run_ablation, ActionType.run_stress_test,
                 ActionType.run_negative_control):
        relevant = c.type in (ClaimType.mechanism, ClaimType.robustness)
        return c.importance * (0.8 if (relevant and status != ClaimStatus.supported) else 0.3)
    if atype == ActionType.claim_refinement:
        return c.importance * (1.0 if status in (ClaimStatus.refuted, ClaimStatus.weak) else 0.1)
    if atype in (ActionType.dataset_addition, ActionType.baseline_design):
        gap = 1.0 if (breadth_incomplete or ev.baseline_missing_cells) else 0.2
        return c.reviewer_risk * gap
    if atype in (ActionType.write_related_work, ActionType.write_limitations,
                 ActionType.paper_readiness_review):
        return 0.2 * c.importance
    return 0.2


def score_research_action(
    action: ResearchAction, state: State, evidence: dict[str, ClaimEvidence]
) -> PlanAction:
    """Score a research action into a PlanAction (value per unit time+cost)."""
    policy = state.policy
    needs = [_claim_need(action.type, evidence[c]) for c in action.claim_links if c in evidence]
    need = (max(needs) + 0.3 * (sum(needs) - max(needs))) if needs else 0.2
    denom = max(1e-6, action.expected_time + policy.lambda_cost * action.expected_cost)
    score = round(need / denom, 4)
    claims = ", ".join(action.claim_links) or "no linked claim"
    rationale = (
        f"{action.type.value} affecting {claims} "
        f"(need {need:.2f} per unit cost; {action.description or 'research action'})."
    )
    return PlanAction(
        experiment_id=action.id,
        action_type=action.type,
        score=score,
        affected_claims=list(action.claim_links),
        rationale=rationale,
        expected_decision_value=round(need, 4),
        expected_cost=action.expected_cost,
        expected_time=action.expected_time,
        factors={"need": round(need, 4)},
        label=action.description or action.id,
        instruction=action.instruction,
    )


def generate_research_actions(
    state: State, evidence: dict[str, ClaimEvidence]
) -> list[ResearchAction]:
    """Auto-generate the research actions the current evidence warrants.

    Deterministic; produces at most a handful per claim so the queue stays
    readable. Users can also predefine actions in ``actions.yaml``.
    """
    out: list[ResearchAction] = []
    for claim in state.claims:
        ev = evidence.get(claim.id)
        if ev is None:
            continue
        status = ev.confidence.status
        has_runs = bool(ev.observed_conditions)
        thin = has_runs and (ev.evidence_breadth < 1.0 or ev.seed_sufficiency < 1.0)

        if not has_runs and claim.importance >= 0.6 and claim.reviewer_risk >= 0.5:
            out.append(ResearchAction(
                id=f"auto:literature_search:{claim.id}", type=ActionType.literature_search,
                description=f"Literature/novelty check for {claim.id}",
                instruction=f"Search related work for {claim.id}: is the contribution novel and "
                            "correctly positioned against existing methods before spending compute?",
                claim_links=[claim.id], expected_cost=0.0, expected_time=1.0,
            ))
        if status in _DECIDED_LOOKING and thin and claim.reviewer_risk >= 0.5:
            out.append(ResearchAction(
                id=f"auto:reviewer_attack:{claim.id}", type=ActionType.reviewer_attack,
                description=f"Reviewer attack on {claim.id}",
                instruction=f"Adversarially stress {claim.id}: it looks decided but its evidence is "
                            "thin (breadth/seeds). Try to break it before a reviewer does.",
                claim_links=[claim.id], expected_cost=0.0, expected_time=1.0,
            ))
        if status in (ClaimStatus.refuted, ClaimStatus.weak):
            out.append(ResearchAction(
                id=f"auto:claim_refinement:{claim.id}", type=ActionType.claim_refinement,
                description=f"Refine/weaken/split {claim.id}",
                instruction=f"The evidence does not support {claim.id} as stated. Weaken, split, or "
                            "scope it to the conditions where it actually holds.",
                claim_links=[claim.id], expected_cost=0.0, expected_time=1.0,
            ))
        if claim.type == ClaimType.theory and status != ClaimStatus.supported:
            out.append(ResearchAction(
                id=f"auto:theorem_attempt:{claim.id}", type=ActionType.theorem_attempt,
                description=f"Theorem attempt for {claim.id}",
                instruction=f"Attempt a proof (or counterexample) for {claim.id} — a theory claim "
                            "that cannot be established by runs alone.",
                claim_links=[claim.id], expected_cost=0.0, expected_time=2.0,
            ))
    return out

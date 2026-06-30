"""Research-action generation and scoring tests."""

from __future__ import annotations

from insightflow.actions import generate_research_actions, score_research_action
from insightflow.scheduler import build_plan
from insightflow.schemas import (
    ActionType,
    Claim,
    ClaimType,
    ExperimentStatus,
    Policy,
    ResearchAction,
    State,
)
from insightflow.scoring import compute_claim_evidence
from tests.conftest import make_baseline, make_claim, make_method, make_result


def _types(actions):
    return {a.type for a in actions}


def test_literature_search_for_unproven_high_importance_claim():
    claim = make_claim("C1", importance=0.9, reviewer_risk=0.7)
    state = State(claims=[claim], experiments=[make_method("cifar10")], policy=Policy())
    actions = generate_research_actions(state, compute_claim_evidence(state))
    assert ActionType.literature_search in _types(actions)


def test_claim_refinement_for_refuted_claim():
    claim = make_claim("C1", required_seeds=1)
    exps, results = [], []
    for ds in ("d1", "d2"):  # method worse than baseline -> refuted
        m = make_method(ds, 0, status=ExperimentStatus.completed)
        b = make_baseline(ds, 0, status=ExperimentStatus.completed)
        exps += [m, b]
        results += [make_result(m, 0.60), make_result(b, 0.72)]
    state = State(claims=[claim], experiments=exps, results=results, policy=Policy())
    actions = generate_research_actions(state, compute_claim_evidence(state))
    assert ActionType.claim_refinement in _types(actions)


def test_theorem_attempt_for_unsupported_theory_claim():
    claim = Claim(id="T1", type=ClaimType.theory, importance=0.8, statement="lemma holds")
    state = State(claims=[claim], policy=Policy())
    actions = generate_research_actions(state, compute_claim_evidence(state))
    assert ActionType.theorem_attempt in _types(actions)


def test_score_research_action_produces_instruction_and_score():
    claim = make_claim("C1", importance=0.9, reviewer_risk=0.8)
    ra = ResearchAction(
        id="lit_C1", type=ActionType.literature_search, description="novelty",
        instruction="search related work", claim_links=["C1"],
    )
    state = State(claims=[claim], experiments=[make_method("cifar10")], policy=Policy())
    action = score_research_action(ra, state, compute_claim_evidence(state))
    assert action.action_type == ActionType.literature_search
    assert action.instruction == "search related work"
    assert action.score > 0.0


def test_scheduler_includes_research_actions_in_plan():
    # A high-importance claim with no evidence -> a literature search should appear.
    claim = make_claim("C1", importance=0.9, reviewer_risk=0.8)
    state = State(claims=[claim], experiments=[make_method("cifar10")], policy=Policy())
    plan = build_plan(state)
    all_actions = plan.actions + plan.postponed + plan.avoided
    assert any(a.action_type == ActionType.literature_search for a in all_actions)


def test_user_defined_action_from_actions_yaml_is_scheduled():
    claim = make_claim("C1", importance=0.9)
    ra = ResearchAction(id="thm", type=ActionType.theorem_attempt, claim_links=["C1"],
                        description="prove L1", instruction="prove lemma L1")
    state = State(claims=[claim], experiments=[make_method("cifar10")],
                  research_actions=[ra], policy=Policy())
    plan = build_plan(state)
    all_actions = plan.actions + plan.postponed + plan.avoided
    assert any(a.experiment_id == "thm" for a in all_actions)

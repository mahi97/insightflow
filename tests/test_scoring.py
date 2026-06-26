"""Scoring-engine behavior tests.

These encode the *intellectual* contract: breadth beats premature replication,
generality is gated on effect-measurable breadth, and missing baselines matter.
They are written so that a trivial cost-sorter would fail them.
"""

from __future__ import annotations

from insightflow.schemas import ClaimStatus, State
from insightflow.scoring import Scorer, compute_claim_confidence, compute_claim_evidence
from tests.conftest import make_claim, make_method, make_result


def test_confidence_unknown_without_results():
    state = State(claims=[make_claim("C1")], experiments=[make_method("cifar10")])
    conf = compute_claim_confidence(state)["C1"]
    assert conf.status == ClaimStatus.unknown
    assert conf.observed_effect is None


def test_confidence_needs_baseline_to_measure_effect():
    m = make_method("cifar10")
    state = State(claims=[make_claim("C1")], experiments=[m], results=[make_result(m, 0.8)])
    conf = compute_claim_confidence(state)["C1"]
    # Method ran but no baseline -> effect unmeasurable -> not yet supported.
    assert conf.observed_effect is None
    assert conf.status == ClaimStatus.needs_more_evidence


def test_single_dataset_does_not_prove_generality(cifar10_observed_state):
    """Effect is clear on CIFAR-10, but generality (breadth) is unverified."""
    conf = compute_claim_confidence(cifar10_observed_state)["C1"]
    assert conf.observed_effect is not None and conf.observed_effect > 0.02
    assert conf.status == ClaimStatus.needs_more_evidence  # NOT 'supported'
    assert conf.near_boundary is True


def test_new_condition_outranks_extra_seed(cifar10_observed_state):
    """A new-condition launch must score higher than an extra CIFAR-10 seed."""
    state = cifar10_observed_state
    evidence = compute_claim_evidence(state)
    scorer = Scorer(state, evidence)

    new_condition = scorer.score_launch(state.experiment("method_a_cifar100_s0"))

    # The extra CIFAR-10 seed is an already-observed cell -> evaluated as a seed.
    from insightflow.seed_policy import decide_seed

    extra_seed_exp = state.experiment("method_a_cifar10_s3")
    decision = decide_seed(extra_seed_exp, evidence, state.policy)
    extra_seed = scorer.score_add_seed(extra_seed_exp, decision)

    assert new_condition.score > extra_seed.score
    assert new_condition.factors["premature_replication_penalty"] == 0.0
    assert extra_seed.factors["premature_replication_penalty"] > 0.0


def test_missing_baseline_drives_reviewer_risk(cifar10_observed_state):
    """A baseline for a not-yet-baselined new condition carries reviewer-risk value."""
    state = cifar10_observed_state
    scorer = Scorer(state)
    baseline = scorer.score_launch(state.experiment("baseline_a_cifar100_s0"))
    assert baseline.factors["reviewer_risk_reduction"] > 0.0


def test_not_a_pure_cost_sorter(cifar10_observed_state):
    """Cheapest action is not automatically the top action."""
    state = cifar10_observed_state
    scorer = Scorer(state)
    actions = [scorer.score_launch(e) for e in state.experiments if e.status.value == "pending"]
    top = max(actions, key=lambda a: a.score)
    cheapest = min(actions, key=lambda a: a.expected_cost)
    # If it were a cost sorter, top would equal cheapest. It must not.
    assert not (top.experiment_id == cheapest.experiment_id and top.expected_cost < 0.85)

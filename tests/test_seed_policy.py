"""Seed-allocation policy tests."""

from __future__ import annotations

from insightflow.schemas import Policy, State
from insightflow.scoring import compute_claim_evidence
from insightflow.seed_policy import decide_seed
from tests.conftest import make_baseline, make_claim, make_method, make_result


def _evidence(state: State):
    return compute_claim_evidence(state)


def test_no_extra_seed_when_well_covered_and_stable():
    """Enough seeds, low variance, claim breadth complete -> prefer breadth."""
    claim = make_claim("C1", required_seeds=3, importance=0.4, reviewer_risk=0.2)
    exps, results = [], []
    # Single dataset, fully covered with 3 stable method seeds + baseline.
    for s in range(3):
        e = make_method("cifar10", s)
        exps.append(e)
        results.append(make_result(e, 0.80))
    b = make_baseline("cifar10", 0)
    exps.append(b)
    results.append(make_result(b, 0.70))
    extra = make_method("cifar10", 3)
    exps.append(extra)
    state = State(claims=[claim], experiments=exps, results=results, policy=Policy())

    decision = decide_seed(extra, _evidence(state), state.policy)
    assert decision.add is False
    assert "breadth" in decision.reason.lower()


def test_extra_seed_when_high_variance():
    claim = make_claim("C1", required_seeds=3, minimum_effect_size=0.02)
    exps, results = [], []
    noisy = [0.60, 0.85, 0.95]  # high seed variance
    for s, acc in enumerate(noisy):
        e = make_method("cifar10", s)
        exps.append(e)
        results.append(make_result(e, acc))
    b = make_baseline("cifar10", 0)
    exps.append(b)
    results.append(make_result(b, 0.70))
    extra = make_method("cifar10", 3)
    exps.append(extra)
    state = State(claims=[claim], experiments=exps, results=results, policy=Policy())

    decision = decide_seed(extra, _evidence(state), state.policy)
    assert decision.add is True
    assert decision.high_variance is True


def test_extra_seed_when_claim_critical_and_under_required():
    claim = make_claim("C1", required_seeds=5, importance=0.95)
    exps, results = [], []
    for s in range(2):  # under the 5 required seeds
        e = make_method("cifar10", s)
        exps.append(e)
        results.append(make_result(e, 0.80))
    b = make_baseline("cifar10", 0)
    exps.append(b)
    results.append(make_result(b, 0.70))
    extra = make_method("cifar10", 2)
    exps.append(extra)
    state = State(claims=[claim], experiments=exps, results=results, policy=Policy())

    decision = decide_seed(extra, _evidence(state), state.policy)
    assert decision.add is True
    assert decision.claim_critical is True

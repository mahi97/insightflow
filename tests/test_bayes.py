"""Bayesian claim model + value-of-information tests."""

from __future__ import annotations

import random

from insightflow.bayes import (
    decision_uncertainty,
    evoi,
    normal_cdf,
    population_posterior,
    status_from_posterior,
)
from insightflow.scheduler import build_plan
from insightflow.schemas import ClaimStatus, Policy
from insightflow.simulator import SCENARIOS, run_policy
from tests.conftest import make_claim

POLICY = Policy(confidence_model="bayes")
SE2 = POLICY.within_seed_sd**2


def test_normal_cdf_basic():
    assert abs(normal_cdf(0.0) - 0.5) < 1e-9
    assert normal_cdf(5.0) > 0.999
    assert normal_cdf(-5.0) < 0.001


def test_finite_population_observing_all_conditions_is_decisive():
    """Observing every defined condition removes between-condition uncertainty."""
    claim = make_claim("C1", minimum_effect_size=0.02)
    one_of_three = population_posterior([0.06], [SE2], 3, claim, POLICY)
    all_three = population_posterior([0.06, 0.06, 0.06], [SE2] * 3, 3, claim, POLICY)
    assert all_three.var < one_of_three.var
    assert all_three.p_supported > one_of_three.p_supported
    # A single dataset of three cannot establish generality at 0.9.
    assert one_of_three.p_supported < 0.9


def test_breadth_buys_more_than_replication():
    """A new condition reduces decision uncertainty more than an extra seed."""
    claim = make_claim("C1", minimum_effect_size=0.02)
    # Start: 1 of 3 conditions observed.
    before = population_posterior([0.06], [SE2], 3, claim, POLICY)
    # New condition: now 2 of 3 observed.
    after_new = population_posterior([0.06, 0.06], [SE2, SE2], 3, claim, POLICY)
    # Extra seed on the one cell: halve its within-noise, still 1 of 3.
    after_seed = population_posterior([0.06], [SE2 / 2], 3, claim, POLICY)
    evoi_new = evoi(before.p_supported, after_new.p_supported)
    evoi_seed = evoi(before.p_supported, after_seed.p_supported)
    assert evoi_new > 3 * max(evoi_seed, 1e-6)


def test_evoi_is_normalised_and_nonnegative():
    assert 0.0 <= evoi(0.5, 0.95) <= 1.0
    assert evoi(0.9, 0.9) == 0.0  # no change -> no value
    assert decision_uncertainty(0.5) == 0.25


def test_p_supported_monotonic_in_effect():
    claim = make_claim("C1", minimum_effect_size=0.02)
    se2 = [SE2, SE2]
    low = population_posterior([0.0, 0.0], se2, 2, claim, POLICY).p_supported
    mid = population_posterior([0.03, 0.03], se2, 2, claim, POLICY).p_supported
    high = population_posterior([0.08, 0.08], se2, 2, claim, POLICY).p_supported
    assert low < mid < high


def test_status_thresholds():
    claim = make_claim("C1", minimum_effect_size=0.02)
    strong = population_posterior([0.1, 0.1, 0.1], [SE2] * 3, 3, claim, POLICY)
    assert status_from_posterior(strong, POLICY)[0] == "supported"
    negative = population_posterior([-0.1, -0.1, -0.1], [SE2] * 3, 3, claim, POLICY)
    assert status_from_posterior(negative, POLICY)[0] == "refuted"


def test_posterior_is_calibrated():
    """Generate claims from the model's own finite-population process and check
    that the posterior is calibrated: aggregate predicted ~= aggregate actual, and
    high-confidence predictions are right far more often than low-confidence ones."""
    rng = random.Random(20260626)
    delta = 0.02
    sigma_b = POLICY.between_condition_sd
    se = POLICY.within_seed_sd
    claim = make_claim("C1", minimum_effect_size=delta)

    preds, actuals = [], []
    for _ in range(600):
        big_k = rng.randint(2, 5)
        mu_hyper = rng.uniform(-0.04, 0.10)
        thetas = [mu_hyper + rng.gauss(0, sigma_b) for _ in range(big_k)]
        m_true = sum(thetas) / big_k  # finite-population mean effect
        k = rng.randint(1, big_k)
        obs = rng.sample(range(big_k), k)
        effects = [thetas[i] + rng.gauss(0, se) for i in obs]
        post = population_posterior(effects, [se**2] * k, big_k, claim, POLICY)
        preds.append(post.p_supported)
        actuals.append(1.0 if m_true >= delta else 0.0)

    assert abs(sum(preds) / len(preds) - sum(actuals) / len(actuals)) < 0.1
    hi = [a for p, a in zip(preds, actuals, strict=True) if p >= 0.8]
    lo = [a for p, a in zip(preds, actuals, strict=True) if p <= 0.2]
    assert hi and lo
    assert sum(hi) / len(hi) > 0.75
    assert sum(lo) / len(lo) < 0.25


def test_bayes_scheduler_decides_and_is_deterministic():
    project = SCENARIOS["breadth"](0, "breadth")
    project.policy = Policy(confidence_model="bayes")
    r1 = run_policy(project, "insightflow", 40)
    r2 = run_policy(project, "insightflow", 40)
    assert r1.correct and r1.decided_step is not None
    assert r1.decided_step == r2.decided_step  # deterministic


def test_bayes_one_dataset_does_not_prove_generality(cifar10_observed_state):
    st = cifar10_observed_state.model_copy(update={"policy": Policy(confidence_model="bayes")})
    plan = build_plan(st)
    c1 = next(c for c in plan.claim_confidence if c.claim_id == "C1")
    assert c1.status != ClaimStatus.supported  # only 1 of 3 datasets observed
    assert 0.0 <= c1.confidence <= 1.0

"""Calibration measurement for the Bayesian claim model.

Draws synthetic claims from the model's own finite-population generative process,
computes the posterior P(supported) for each, and returns a 10-bin reliability
diagram plus the Expected Calibration Error (ECE). Deterministic given the seed.

This is the importable, tested backing for the "ECE ~= 0.011 over 200k draws"
figure (see ``scripts/calibration.py`` for the CLI wrapper and
``tests/test_bayes.py`` for the property + ECE-bound tests).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .bayes import population_posterior
from .schemas import Claim, Policy


@dataclass
class CalibrationResult:
    n: int
    base_rate: float
    ece: float
    bins: list[tuple[float, int, float, float]]  # (bin_lo, count, mean_pred, emp_freq)


def measure_calibration(
    n: int = 200_000, seed: int = 20260626, policy: Policy | None = None
) -> CalibrationResult:
    policy = policy or Policy(confidence_model="bayes")
    sigma_b = policy.between_condition_sd
    se = policy.within_seed_sd
    delta = 0.02
    claim = Claim(id="C1", minimum_effect_size=delta, importance=0.5,
                  required_seeds=3, reviewer_risk=0.5)
    rng = random.Random(seed)

    preds: list[float] = []
    actuals: list[float] = []
    for _ in range(n):
        big_k = rng.randint(2, 5)
        mu_hyper = rng.uniform(-0.05, 0.12)
        thetas = [mu_hyper + rng.gauss(0, sigma_b) for _ in range(big_k)]
        m_true = sum(thetas) / big_k
        k = rng.randint(1, big_k)
        obs = rng.sample(range(big_k), k)
        effects = [thetas[i] + rng.gauss(0, se) for i in obs]
        post = population_posterior(effects, [se**2] * k, big_k, claim, policy)
        preds.append(post.p_supported)
        actuals.append(1.0 if m_true >= delta else 0.0)

    buckets: list[list[tuple[float, float]]] = [[] for _ in range(10)]
    for p, a in zip(preds, actuals, strict=True):
        buckets[min(9, int(p * 10))].append((p, a))

    total = len(preds)
    ece = 0.0
    bins: list[tuple[float, int, float, float]] = []
    for i, b in enumerate(buckets):
        if not b:
            continue
        mp = sum(p for p, _ in b) / len(b)
        ef = sum(a for _, a in b) / len(b)
        ece += len(b) / total * abs(mp - ef)
        bins.append((i / 10, len(b), mp, ef))

    return CalibrationResult(
        n=total, base_rate=sum(actuals) / total, ece=round(ece, 4), bins=bins
    )

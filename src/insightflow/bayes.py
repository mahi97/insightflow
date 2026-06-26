"""Bayesian claim model and value-of-information scoring (deterministic).

The v0.2 upgrade from the transparent heuristic to a calibrated model. Closed-form
(no sampling), so it stays deterministic and fast.

Model
-----
A claim is about the effect (method minus baseline) on the project's **defined,
finite set of K conditions** (datasets x settings). We want the population mean
over those K conditions, ``M = (1/K) * sum_i theta_i``. Each observed cell gives a
noisy estimate ``e_i`` of its ``theta_i`` with within-cell error ``se_i``;
conditions vary around a hyper-mean with between-condition variance ``sigma_b^2``.

With ``k`` of ``K`` conditions observed, the variance of the estimate of ``M`` is

    obs_var = sigma_b^2 / k * (K - k) / K        (finite-population correction)
            + sum_i se_i^2 / k^2                  (within-cell noise)

The **finite-population correction** is the key: when ``k = K`` the between term
vanishes (you have measured every condition — no generality risk left); when
``k << K`` it is large (a single dataset cannot establish generality). A Normal
prior on ``M`` then gives a conjugate Normal posterior.

Decisions:  P(supported) = P(M >= delta);  P(refuted) = P(M <= 0).

Value of information is the expected drop in decision uncertainty ``u(p)=p(1-p)``
from an action, computed by recomputing the posterior with the action's
(pre-posterior expected) observation. A new condition adds a cell (big drop); an
extra seed only shrinks an already-small ``se_i`` (tiny drop).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .schemas import Claim, Policy

_SQRT2 = math.sqrt(2.0)
_EPS = 1e-12


def normal_cdf(z: float) -> float:
    """Standard normal CDF via erf (deterministic)."""
    return 0.5 * (1.0 + math.erf(z / _SQRT2))


@dataclass
class Posterior:
    mean: float
    var: float
    p_supported: float
    p_refuted: float
    n_cells: int

    @property
    def sd(self) -> float:
        return math.sqrt(max(self.var, _EPS))


def _p_ge(threshold: float, mean: float, var: float) -> float:
    sd = math.sqrt(max(var, _EPS))
    return 1.0 - normal_cdf((threshold - mean) / sd)


def population_posterior(
    effects: list[float],
    se2s: list[float],
    total_conditions: int,
    claim: Claim,
    policy: Policy,
) -> Posterior:
    """Closed-form posterior on the finite-population mean effect ``M``."""
    m0 = policy.prior_effect_mean
    v0 = max(policy.prior_effect_var, _EPS)
    sigma_b2 = policy.between_condition_sd**2
    delta = claim.minimum_effect_size

    if len(effects) != len(se2s):
        raise ValueError("effects and se2s must be the same length")
    k = len(effects)
    if k == 0:
        mean, var = m0, v0
    else:
        big_k = max(total_conditions, k)
        mean_e = sum(effects) / k
        between = sigma_b2 / k * (max(0, big_k - k) / max(1, big_k))
        within = sum(se2s) / (k * k)
        obs_var = max(between + within, _EPS)
        precision = 1.0 / v0 + 1.0 / obs_var
        var = 1.0 / precision
        mean = var * (m0 / v0 + mean_e / obs_var)

    return Posterior(
        mean=mean,
        var=var,
        p_supported=_p_ge(delta, mean, var),
        p_refuted=normal_cdf((0.0 - mean) / math.sqrt(max(var, _EPS))),
        n_cells=k,
    )


def decision_uncertainty(p: float) -> float:
    """Uncertainty of the Bernoulli 'supported' decision (max 0.25 at p=0.5)."""
    return p * (1.0 - p)


def evoi(p_before: float, p_after: float) -> float:
    """Normalised expected drop in decision uncertainty, in [0, 1]."""
    return max(0.0, decision_uncertainty(p_before) - decision_uncertainty(p_after)) / 0.25


def status_from_posterior(posterior: Posterior, policy: Policy) -> tuple[str, bool]:
    """Map a posterior to a claim status and a near-boundary flag."""
    t = policy.decision_prob_threshold
    if posterior.p_supported >= t:
        return "supported", False
    if posterior.p_refuted >= t:
        return "refuted", False
    if posterior.mean > 0 and posterior.p_supported >= 0.5:
        return "weak", True
    return "needs_more_evidence", True

"""Seed allocation policy.

The job here is to answer one question for a candidate replication (an extra
seed of an *already-observed* condition):

    Is this seed worth running now, or should the worker do breadth instead?

We add a seed only when at least one of these holds (per the spec):

* the result is claim-critical and still under the required seed count,
* the current effect is borderline (claim sits near its decision boundary),
* seed variance is high,
* the result feeds a main paper table and is under the required seeds,
* evidence is under the required seed threshold *and* confidence is near the
  decision boundary.

Otherwise we prefer broad coverage, and the returned :class:`SeedDecision`
carries ``add=False`` with an explanation. The scheduler still scores the seed
action, but a non-added seed gets little seed-value and a premature-replication
penalty, so breadth wins early.
"""

from __future__ import annotations

from .schemas import Experiment, Policy
from .scoring import ClaimEvidence, SeedDecision
from .utils import clamp

CRITICAL_IMPORTANCE = 0.7


def decide_seed(
    exp: Experiment,
    evidence: dict[str, ClaimEvidence],
    policy: Policy,
) -> SeedDecision:
    """Decide whether to add a seed for ``exp`` (which replicates an observed cell)."""
    reasons: list[str] = []
    urgency = 0.0
    add = False
    claim_critical = False
    high_variance = False
    borderline = False

    for cid in exp.claim_links:
        ev = evidence.get(cid)
        if ev is None:
            continue
        cell = exp.cell_key
        seeds = ev.seeds_per_cell.get(cell, 0)
        var = ev.variance_per_cell.get(cell, 0.0)
        importance = ev.claim.importance
        required = ev.claim.required_seeds
        near = ev.confidence.near_boundary
        support = ev.support

        is_critical = importance >= CRITICAL_IMPORTANCE
        under_required = seeds < required
        # "Borderline" = the effect sits right on the decision line, where one more
        # seed could flip the conclusion (within boundary_margin of the boundary).
        is_borderline = (
            near
            and support is not None
            and abs(support - policy.decision_boundary) < policy.boundary_margin
        )
        var_threshold = policy.high_variance_threshold * max(ev.claim.minimum_effect_size, 0.02)
        is_high_var = var > var_threshold

        triggered = False
        if is_critical and under_required:
            reasons.append(f"{cid}: claim-critical and under {required} seeds")
            urgency += 0.4
            triggered = True
            claim_critical = True
        if is_borderline:
            reasons.append(f"{cid}: effect is borderline near the decision boundary")
            urgency += 0.4
            triggered = True
            borderline = True
        if is_high_var:
            reasons.append(f"{cid}: seed variance is high ({var:.3f})")
            urgency += 0.4
            triggered = True
            high_variance = True
        if under_required and near:
            reasons.append(f"{cid}: under required seeds while confidence is near the boundary")
            urgency += 0.3
            triggered = True

        add = add or triggered

    if not add:
        return SeedDecision(
            add=False,
            urgency=0.0,
            reason="Prefer breadth: extra replication has low decision value until "
            "remaining conditions are covered.",
        )

    return SeedDecision(
        add=True,
        urgency=clamp(urgency),
        reason="Add seed - " + "; ".join(reasons) + ".",
        claim_critical=claim_critical,
        high_variance=high_variance,
        borderline=borderline,
    )

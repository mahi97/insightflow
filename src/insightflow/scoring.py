"""Deterministic scoring engine.

This module turns the scheduling objective from the spec into concrete,
reproducible numbers:

    priority(action) =
        ( w_dv * decision_value
        + w_unc * uncertainty_reduction
        + w_dep * dependency_unlock
        + w_rev * reviewer_risk_reduction
        + w_seed * seed_value
        - w_red * redundancy_penalty
        - w_prp * premature_replication_penalty )
      / ( expected_time + lambda * expected_cost )

Everything is a pure function of :class:`State` + :class:`Policy`, so the same
inputs always yield the same plan. Each term is also stored on the resulting
:class:`PlanAction.factors` so ``explain`` can show *why* an action ranked where
it did.

The claim-confidence model here is an explicit, documented heuristic - a
transparent stand-in for the Bayesian value-of-information model on the v0.2
roadmap (see ``docs/concepts.md``). It is intentionally simple enough to test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .bayes import (
    Posterior,
    evoi,
    expected_voi_new_cell,
    population_posterior,
    status_from_posterior,
    two_step_voi_new_cell,
)
from .schemas import (
    ActionType,
    Claim,
    ClaimConfidence,
    ClaimStatus,
    Experiment,
    PlanAction,
    Policy,
    RunStatus,
    State,
)
from .utils import clamp, mean, pstdev


def _logistic(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _combine(values: list[float]) -> float:
    """Aggregate per-claim contributions: the dominant claim plus a discounted
    bonus for additionally affected claims."""
    if not values:
        return 0.0
    m = max(values)
    return m + 0.3 * (sum(values) - m)


def _oriented(effect: float, claim: Claim) -> float:
    """Orient an effect so that 'good for the claim' is always positive."""
    if claim.desired_direction.value == "lower":
        return -effect
    return effect


@dataclass
class ClaimEvidence:
    """Internal, richer view of one claim's evidence used by the scorer."""

    claim: Claim
    confidence: ClaimConfidence
    total_conditions: int
    observed_conditions: set[str]
    baseline_missing_cells: set[str]
    seeds_per_cell: dict[str, int]
    variance_per_cell: dict[str, float]
    evidence_breadth: float
    seed_sufficiency: float
    support: float | None  # P(claim true) in [0,1], or None if unmeasured
    reliability: float
    # Per-effect-cell estimate + squared standard error (for the Bayesian model).
    cell_effects: dict[str, float] = field(default_factory=dict)
    cell_se2: dict[str, float] = field(default_factory=dict)
    posterior: Posterior | None = None  # set when policy.confidence_model == "bayes"


def _cell_results(state: State, experiments: list[Experiment], target: str) -> dict[str, list[float]]:
    """Map cell_key -> list of completed metric values for the given experiments."""
    out: dict[str, list[float]] = {}
    for exp in experiments:
        for r in state.results_for(exp.id):
            if r.status != RunStatus.completed:
                continue
            val = r.metric(target)
            if val is None:
                continue
            out.setdefault(exp.cell_key, []).append(val)
    return out


def compute_claim_evidence(state: State) -> dict[str, ClaimEvidence]:
    """Compute evidence + confidence for every claim. Deterministic."""
    policy = state.policy
    evidence: dict[str, ClaimEvidence] = {}

    for claim in state.claims:
        linked = state.experiments_for_claim(claim.id)
        method_exps = [e for e in linked if not e.is_baseline]
        baseline_exps = [e for e in linked if e.is_baseline]
        target = claim.target_metric

        all_cells = {e.cell_key for e in method_exps}
        method_results = _cell_results(state, method_exps, target)
        baseline_results = _cell_results(state, baseline_exps, target)

        # Cells where the method has run (used for redundancy / new-condition logic).
        method_observed = {cell for cell, vals in method_results.items() if vals}
        seeds_per_cell = {cell: len(vals) for cell, vals in method_results.items()}
        variance_per_cell = {cell: pstdev(vals) for cell, vals in method_results.items()}

        baseline_missing = {cell for cell in method_observed if not baseline_results.get(cell)}

        # Cells where the *effect* is measurable (method AND baseline present).
        # Generality is about the effect holding, so breadth counts these.
        effect_cells = {cell for cell in method_observed if baseline_results.get(cell)}
        within = policy.within_seed_sd
        cell_effects_map: dict[str, float] = {}
        cell_se2_map: dict[str, float] = {}
        # sorted() so insertion order (and thus the Bayesian float sums) is
        # independent of set hash-ordering across processes -> fully deterministic.
        for cell in sorted(effect_cells):
            m_vals = method_results[cell]
            b_vals = baseline_results[cell]
            s_m = max(pstdev(m_vals) if len(m_vals) >= 2 else within, within * 0.25)
            s_b = max(pstdev(b_vals) if len(b_vals) >= 2 else within, within * 0.25)
            cell_effects_map[cell] = _oriented(mean(m_vals) - mean(b_vals), claim)
            cell_se2_map[cell] = s_m**2 / max(1, len(m_vals)) + s_b**2 / max(1, len(b_vals))
        effects = list(cell_effects_map.values())
        observed_effect = mean(effects) if effects else None

        observed = method_observed  # for scoring's launch-vs-seed decision
        total_conditions = max(1, len(all_cells))
        evidence_breadth = clamp(len(effect_cells) / total_conditions)
        if effect_cells:
            seed_sufficiency = clamp(
                mean([seeds_per_cell[c] for c in effect_cells]) / claim.required_seeds
            )
        else:
            seed_sufficiency = 0.0
        seed_variance = mean([variance_per_cell[c] for c in effect_cells]) if effect_cells else 0.0

        support, status, near = _confidence(
            claim, policy, observed, observed_effect, evidence_breadth, seed_sufficiency
        )
        reliability = 0.5 * evidence_breadth + 0.5 * seed_sufficiency

        # Bayesian override: a calibrated posterior on the population effect.
        posterior: Posterior | None = None
        if policy.confidence_model == "bayes":
            posterior = population_posterior(
                effects, list(cell_se2_map.values()), total_conditions, claim, policy
            )
            status_str, near = status_from_posterior(posterior, policy)
            status = ClaimStatus(status_str)
            support = posterior.p_supported

        conf = ClaimConfidence(
            claim_id=claim.id,
            status=status,
            confidence=clamp(support if support is not None else 0.3 * evidence_breadth),
            n_conditions_observed=len(effect_cells),
            n_seeds_observed=sum(seeds_per_cell.get(c, 0) for c in effect_cells),
            observed_effect=observed_effect,
            required_effect=claim.minimum_effect_size,
            seed_variance=seed_variance,
            near_boundary=near,
            note=_confidence_note(status, observed_effect, evidence_breadth, baseline_missing),
        )
        evidence[claim.id] = ClaimEvidence(
            claim=claim,
            confidence=conf,
            total_conditions=len(all_cells) or len(observed),
            observed_conditions=observed,
            baseline_missing_cells=baseline_missing,
            seeds_per_cell=seeds_per_cell,
            variance_per_cell=variance_per_cell,
            evidence_breadth=evidence_breadth,
            seed_sufficiency=seed_sufficiency,
            support=support,
            reliability=reliability,
            cell_effects=cell_effects_map,
            cell_se2=cell_se2_map,
            posterior=posterior,
        )
    return evidence


def _confidence(
    claim: Claim,
    policy: Policy,
    observed: set[str],
    observed_effect: float | None,
    breadth: float,
    seed_sufficiency: float,
) -> tuple[float | None, ClaimStatus, bool]:
    if not observed:
        return None, ClaimStatus.unknown, True
    if observed_effect is None:
        # We have method numbers but no baseline to compare against.
        return None, ClaimStatus.needs_more_evidence, True

    ref = max(claim.minimum_effect_size, 0.02)
    z = (observed_effect - claim.minimum_effect_size) / ref
    support = _logistic(z)
    reliability = 0.5 * breadth + 0.5 * seed_sufficiency
    b = policy.decision_boundary
    margin = policy.support_margin
    # Generality gate: a claim is not 'supported'/'refuted' until most of its
    # conditions are observed. Seed depth must NOT compensate for missing breadth,
    # otherwise a single well-replicated dataset would 'prove' a cross-dataset claim.
    breadth_ok = breadth >= 0.6

    if reliability < 0.5:
        return support, ClaimStatus.needs_more_evidence, True
    if support >= b + margin:
        return (support, ClaimStatus.supported, False) if breadth_ok else (
            support,
            ClaimStatus.needs_more_evidence,
            True,
        )
    if support <= b - margin:
        return (support, ClaimStatus.refuted, False) if breadth_ok else (
            support,
            ClaimStatus.needs_more_evidence,
            True,
        )
    return support, ClaimStatus.weak, True


def _confidence_note(
    status: ClaimStatus,
    effect: float | None,
    breadth: float,
    baseline_missing: set[str],
) -> str:
    bits = []
    if status == ClaimStatus.unknown:
        bits.append("no evidence yet")
    if effect is None and status != ClaimStatus.unknown:
        bits.append("no baseline to compare against")
    if breadth < 1.0:
        bits.append(f"breadth {breadth:.0%} of conditions observed")
    if baseline_missing:
        bits.append(f"{len(baseline_missing)} condition(s) missing a baseline")
    return "; ".join(bits)


def compute_claim_confidence(state: State) -> dict[str, ClaimConfidence]:
    """Public helper: just the confidence table."""
    return {cid: ev.confidence for cid, ev in compute_claim_evidence(state).items()}


# --------------------------------------------------------------------------- #
# Action scoring
# --------------------------------------------------------------------------- #
@dataclass
class SeedDecision:
    add: bool
    urgency: float
    reason: str
    claim_critical: bool = False
    high_variance: bool = False
    borderline: bool = False


@dataclass
class Scorer:
    """Scores candidate actions against the current state."""

    state: State
    evidence: dict[str, ClaimEvidence] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence:
            self.evidence = compute_claim_evidence(self.state)

    @property
    def policy(self) -> Policy:
        return self.state.policy

    # -- public -------------------------------------------------------------
    def score_launch(self, exp: Experiment) -> PlanAction:
        terms = self._launch_terms(exp)
        return self._assemble(exp, ActionType.launch, terms)

    def score_add_seed(self, exp: Experiment, decision: SeedDecision) -> PlanAction:
        terms = self._seed_terms(exp, decision)
        action = self._assemble(exp, ActionType.add_seed, terms)
        action.rationale = decision.reason + " " + action.rationale
        return action

    # -- term computation ---------------------------------------------------
    def _launch_terms(self, exp: Experiment) -> dict[str, float]:
        if self.policy.confidence_model == "bayes":
            return self._bayes_terms(exp, ActionType.launch)
        dv, ur, rr, rp, prp = [], [], [], [], []
        for cid in exp.claim_links:
            ev = self.evidence.get(cid)
            if ev is None:
                continue
            cell = exp.cell_key
            is_new_condition = (not exp.is_baseline) and cell not in ev.observed_conditions
            is_missing_baseline = exp.is_baseline and cell in ev.observed_conditions
            already_covered = (not exp.is_baseline) and cell in ev.observed_conditions

            if is_new_condition:
                novelty = 1.0
            elif is_missing_baseline:
                novelty = 0.9
            elif exp.is_baseline:
                novelty = 0.4
            else:
                novelty = 0.3

            boundary_factor = 1.0 if ev.confidence.near_boundary else 0.3
            coverage_gap = 1.0 - ev.evidence_breadth
            uncertainty = (
                1.0 if ev.support is None else (1.0 - 2.0 * abs(ev.support - 0.5))
            )

            dv.append(ev.claim.importance * boundary_factor * (0.5 * coverage_gap + 0.5 * novelty))
            ur.append(clamp(uncertainty) * novelty)
            rr.append(
                ev.claim.reviewer_risk
                * (1.0 if is_missing_baseline else (0.7 if is_new_condition else 0.2))
            )
            # Redundancy: relaunching a well-covered cell with low variance.
            seeds = ev.seeds_per_cell.get(cell, 0)
            var = ev.variance_per_cell.get(cell, 0.0)
            well_covered = (
                already_covered
                and seeds >= ev.claim.required_seeds
                and var <= self.policy.high_variance_threshold * max(ev.claim.minimum_effect_size, 0.02)
                and not ev.confidence.near_boundary
            )
            rp.append(ev.claim.importance if well_covered else 0.0)
            # Premature replication: adding depth to an already-observed cell
            # while breadth is still incomplete.
            prp.append((1.0 - ev.evidence_breadth) * ev.claim.importance if already_covered else 0.0)

        return {
            "decision_value": _combine(dv),
            "uncertainty_reduction": _combine(ur),
            "dependency_unlock": self._dependency_unlock(exp),
            "reviewer_risk_reduction": _combine(rr),
            "seed_value": 0.0,
            "redundancy_penalty": _combine(rp),
            "premature_replication_penalty": _combine(prp),
        }

    def _seed_terms(self, exp: Experiment, decision: SeedDecision) -> dict[str, float]:
        if self.policy.confidence_model == "bayes":
            return self._bayes_terms(exp, ActionType.add_seed)
        dv, ur, rr, rp, prp, sv = [], [], [], [], [], []
        urgency = decision.urgency if decision.add else 0.0
        for cid in exp.claim_links:
            ev = self.evidence.get(cid)
            if ev is None:
                continue
            cell = exp.cell_key
            boundary_factor = 1.0 if ev.confidence.near_boundary else 0.3
            uncertainty = (
                1.0 if ev.support is None else (1.0 - 2.0 * abs(ev.support - 0.5))
            )
            seeds = ev.seeds_per_cell.get(cell, 0)
            var = ev.variance_per_cell.get(cell, 0.0)
            high_var = var > self.policy.high_variance_threshold * max(ev.claim.minimum_effect_size, 0.02)

            dv.append(ev.claim.importance * boundary_factor * urgency * 0.5)
            ur.append(clamp(uncertainty) * (0.5 if high_var else 0.2) * urgency)
            rr.append(0.1 * ev.claim.reviewer_risk * urgency)
            # Redundancy: already have enough seeds, low variance, not borderline.
            well_covered = (
                seeds >= ev.claim.required_seeds and not high_var and not ev.confidence.near_boundary
            )
            rp.append(ev.claim.importance if (well_covered and not decision.add) else 0.0)
            # Premature replication penalty scales with how much breadth is missing.
            prp.append((1.0 - ev.evidence_breadth) * ev.claim.importance)
            sv.append(urgency * (ev.claim.importance if decision.claim_critical else 0.5))

        return {
            "decision_value": _combine(dv),
            "uncertainty_reduction": _combine(ur),
            "dependency_unlock": 0.0,
            "reviewer_risk_reduction": _combine(rr),
            "seed_value": _combine(sv),
            "redundancy_penalty": _combine(rp),
            "premature_replication_penalty": _combine(prp),
        }

    def _dependency_unlock(self, exp: Experiment) -> float:
        dependents = [
            d
            for d in self.state.experiments
            if exp.id in d.dependencies and d.status.value in ("pending", "postponed")
        ]
        if not dependents:
            return 0.0
        raw = 0.0
        for d in dependents:
            importances = [
                self.evidence[c].claim.importance for c in d.claim_links if c in self.evidence
            ]
            raw += _combine(importances) if importances else 0.3
        return 1.0 - 1.0 / (1.0 + raw)  # saturating in [0, 1)

    # -- Bayesian (value-of-information) terms ------------------------------
    def _bayes_evi(self, exp: Experiment, ev: ClaimEvidence) -> float:
        """Normalised Expected Value of Information of this action for ``ev``.

        * Extra seed on an existing cell: variance reduction only (the observation
          is a re-measurement, not a new cell) -> point estimate, diminishing.
        * Baseline completing a method-observed cell: a realized new effect cell ->
          faithful preposterior EVI integrated over the predictive (full credit).
        * Speculative new condition (pair not yet complete): the same EVI at half
          credit, since the baseline still has to follow.
        """
        assert ev.posterior is not None
        within = self.policy.within_seed_sd
        cell = exp.cell_key
        effects = list(ev.cell_effects.values())
        se2s = list(ev.cell_se2.values())
        cells = list(ev.cell_effects.keys())
        post = ev.posterior

        if cell in ev.cell_effects:
            idx = cells.index(cell)
            n_m = max(1, ev.seeds_per_cell.get(cell, 1))
            ns = list(se2s)
            ns[idx] = se2s[idx] * (n_m / (n_m + 1.0))
            after = population_posterior(effects, ns, ev.total_conditions, ev.claim, self.policy)
            return evoi(post.p_supported, after.p_supported)
        voi = two_step_voi_new_cell if self.policy.lookahead_depth >= 2 else expected_voi_new_cell
        if exp.is_baseline and cell in ev.observed_conditions:
            n_m = max(1, ev.seeds_per_cell.get(cell, 1))
            return voi(
                effects, se2s, ev.total_conditions, within**2 * (1.0 / n_m + 1.0),
                ev.claim, self.policy,
            )
        return 0.5 * voi(
            effects, se2s, ev.total_conditions, within**2 * 2.0, ev.claim, self.policy
        )

    def _bayes_terms(self, exp: Experiment, action_type: ActionType) -> dict[str, float]:
        dv, rr = [], []
        for cid in exp.claim_links:
            ev = self.evidence.get(cid)
            if ev is None or ev.posterior is None:
                continue
            cell = exp.cell_key
            dv.append(ev.claim.importance * self._bayes_evi(exp, ev))
            is_missing_baseline = (
                exp.is_baseline and cell in ev.observed_conditions and cell not in ev.cell_effects
            )
            is_new = (not exp.is_baseline) and cell not in ev.observed_conditions
            rr.append(
                ev.claim.reviewer_risk * (1.0 if is_missing_baseline else (0.5 if is_new else 0.1))
            )
        # EVOI subsumes redundancy/premature-replication penalties (a redundant
        # seed simply has ~0 EVOI), so those terms are 0 in Bayesian mode.
        return {
            "decision_value": _combine(dv),
            "uncertainty_reduction": 0.0,
            "dependency_unlock": self._dependency_unlock(exp),
            "reviewer_risk_reduction": _combine(rr),
            "seed_value": 0.0,
            "redundancy_penalty": 0.0,
            "premature_replication_penalty": 0.0,
        }

    # -- assembly -----------------------------------------------------------
    def _assemble(self, exp: Experiment, action_type: ActionType, terms: dict[str, float]) -> PlanAction:
        p = self.policy
        numerator = (
            p.weight_decision_value * terms["decision_value"]
            + p.weight_uncertainty * terms["uncertainty_reduction"]
            + p.weight_dependency * terms["dependency_unlock"]
            + p.weight_reviewer_risk * terms["reviewer_risk_reduction"]
            + p.weight_seed_value * terms["seed_value"]
            - p.weight_redundancy_penalty * terms["redundancy_penalty"]
            - p.weight_premature_replication_penalty * terms["premature_replication_penalty"]
        )
        denominator = max(1e-6, exp.expected_time + p.lambda_cost * exp.expected_cost)
        score = numerator / denominator

        risk = clamp(max(terms["redundancy_penalty"], terms["premature_replication_penalty"]))
        label = f"{exp.method} / {exp.dataset} / {exp.condition} / seed={exp.seed}"
        rationale = self._rationale(exp, action_type, terms, score)

        factors = dict(terms)
        factors["numerator"] = numerator
        factors["denominator"] = denominator

        return PlanAction(
            experiment_id=exp.id,
            action_type=action_type,
            score=round(score, 4),
            affected_claims=list(exp.claim_links),
            rationale=rationale,
            expected_decision_value=round(terms["decision_value"], 4),
            expected_uncertainty_reduction=round(terms["uncertainty_reduction"], 4),
            expected_cost=exp.expected_cost,
            expected_time=exp.expected_time,
            risk=round(risk, 4),
            checkpoint=None,
            factors={k: round(v, 4) for k, v in factors.items()},
            label=label,
        )

    def _rationale(
        self, exp: Experiment, action_type: ActionType, terms: dict[str, float], score: float
    ) -> str:
        # Identify the dominant driver for a readable explanation.
        drivers = {
            "decision value": terms["decision_value"],
            "uncertainty reduction": terms["uncertainty_reduction"],
            "dependency unlock": terms["dependency_unlock"],
            "reviewer-risk reduction": terms["reviewer_risk_reduction"],
            "seed value": terms["seed_value"],
        }
        top = max(drivers, key=lambda k: drivers[k])
        parts = []
        cell = exp.cell_key
        is_new = not exp.is_baseline and not any(
            cell in self.evidence[c].observed_conditions for c in exp.claim_links if c in self.evidence
        )
        if action_type == ActionType.launch and is_new:
            parts.append("covers a new, unobserved condition (breadth over replication)")
        if exp.is_baseline:
            parts.append("supplies a missing baseline that could decide the claim")
        if action_type == ActionType.add_seed:
            parts.append("adds a seed")
        parts.append(f"dominant factor: {top}")
        if terms["premature_replication_penalty"] > 0.2:
            parts.append("penalized for replicating before breadth is established")
        if terms["redundancy_penalty"] > 0.2:
            parts.append("penalized as redundant with existing evidence")
        claims = ", ".join(exp.claim_links) or "no linked claim"
        return f"Affects {claims}; " + "; ".join(parts) + f"; score={score:.3f}."

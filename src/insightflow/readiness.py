"""Paper-readiness assessment over the claim graph.

This is the layer that makes InsightFlow *claim-centered* rather than experiment-
centered. It takes the per-claim evidence (from :mod:`scoring`) and the claim
graph (``depends_on``) and answers the questions a researcher actually has before
submission:

* which claims are supported / refuted / weak / still need evidence,
* which *main* claims are **blocked** because a supporting subclaim is unmet,
* which reviewer attacks are currently most dangerous,
* which baselines are missing, which generality claims are thin, which seeds are
  insufficient,
* what to do next, and which claims should be weakened, split, or abandoned.

Everything here is a deterministic, auditable function of the ledger state. It
never invents a verdict; statuses come from the same evidence the scheduler uses.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .schemas import Claim, ClaimStatus, State
from .scoring import ClaimEvidence, compute_claim_evidence

_SUPPORTED = ClaimStatus.supported


class ClaimReadiness(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_id: str
    type: str
    importance: float
    own_status: ClaimStatus  # from this claim's own evidence
    effective_status: ClaimStatus  # after accounting for unmet dependencies
    confidence: float
    blockers: list[str] = Field(default_factory=list)  # unmet depends_on subclaims
    missing_baselines: list[str] = Field(default_factory=list)
    thin_generality: bool = False
    insufficient_seeds: bool = False
    reviewer_risk: float = 0.0
    reviewer_attacks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claims: list[ClaimReadiness] = Field(default_factory=list)
    supported: list[str] = Field(default_factory=list)
    refuted: list[str] = Field(default_factory=list)
    weak: list[str] = Field(default_factory=list)
    needs_more_evidence: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)
    dangerous_attacks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    paper_ready: bool = False
    summary: str = ""


def _reviewer_attacks(
    claim: Claim, ev: ClaimEvidence, effective: ClaimStatus, blockers: list[str]
) -> list[str]:
    attacks: list[str] = []
    cid = claim.id
    if ev.observed_conditions and ev.evidence_breadth < 1.0 and claim.importance >= 0.5:
        attacks.append(
            f"Generality: {cid} is argued from {ev.evidence_breadth:.0%} of its conditions — "
            "a reviewer will say it is overclaimed from too few settings."
        )
    if ev.baseline_missing_cells:
        attacks.append(
            f"Attribution: {cid} has {len(ev.baseline_missing_cells)} condition(s) with no "
            "baseline — the effect cannot be attributed to the method."
        )
    if ev.observed_conditions and ev.seed_sufficiency < 1.0 and effective == _SUPPORTED:
        attacks.append(
            f"Seed variance: {cid} rests on fewer than the required seeds — a reviewer will "
            "question whether the effect survives seed noise."
        )
    if blockers:
        if ev.confidence.status == _SUPPORTED:
            attacks.append(
                f"Unsupported premise: {cid}'s own evidence is positive but it depends on "
                f"{', '.join(blockers)}, which are not yet established."
            )
        else:
            attacks.append(
                f"Unestablished premise: {cid} depends on {', '.join(blockers)}, "
                "which are not yet established."
            )
    if effective == ClaimStatus.refuted:
        attacks.append(f"Contradiction: the evidence currently refutes {cid} as stated.")
    return attacks


def _recommended_actions(
    claim: Claim, ev: ClaimEvidence, effective: ClaimStatus, blockers: list[str],
    missing_baselines: list[str],
) -> list[str]:
    actions: list[str] = []
    cid = claim.id
    if effective == ClaimStatus.refuted:
        actions.append(
            f"Weaken or split {cid}: the evidence does not support it as stated "
            "(consider scoping it to the conditions where it holds)."
        )
    if blockers:
        actions.append(f"Establish the supporting subclaim(s) first: {', '.join(blockers)}.")
    if missing_baselines:
        actions.append(
            f"Run the missing baseline for {cid} on: {', '.join(missing_baselines)} "
            "(the claim cannot be decided without it)."
        )
    if ev.observed_conditions and ev.evidence_breadth < 1.0 and effective != ClaimStatus.refuted:
        actions.append(
            f"Add breadth for {cid}: cover an unobserved condition before more seeds "
            "(generality is the binding uncertainty)."
        )
    if ev.observed_conditions and ev.seed_sufficiency < 1.0 and ev.confidence.near_boundary:
        actions.append(f"Add a seed for {cid}: the effect is near the decision boundary.")
    if claim.type == "theory" and effective in (ClaimStatus.needs_more_evidence, ClaimStatus.unknown):
        actions.append(
            f"Attempt a proof or counterexample for {cid} (theory claim, not establishable "
            "by runs alone)."
        )
    if not ev.observed_conditions and claim.importance >= 0.6:
        actions.append(
            f"Consider a literature/novelty check for {cid} before committing compute "
            "(no evidence yet, high importance)."
        )
    return actions


def _effective_status(
    own: ClaimStatus, depends_on: list[str], blockers: list[str], dep_refuted: bool
) -> ClaimStatus:
    """Combine a claim's own evidence with its claim-graph dependencies.

    * own evidence supports, but a subclaim is unmet -> blocked.
    * a *meta-claim* (no own evidence) is derived from its subgraph: supported iff
      all subclaims are supported, weak if any is refuted, else blocked.
    * otherwise the claim keeps its own status (a refuted claim stays refuted).
    """
    if not depends_on:
        return own
    if own == _SUPPORTED:
        return _SUPPORTED if not blockers else ClaimStatus.blocked
    if own == ClaimStatus.unknown:  # meta-claim with no runs of its own
        if not blockers:
            return _SUPPORTED
        if dep_refuted:
            return ClaimStatus.weak
        return ClaimStatus.blocked
    return own


def assess_readiness(state: State) -> ReadinessReport:
    evidence = compute_claim_evidence(state)
    own_status = {cid: ev.confidence.status for cid, ev in evidence.items()}
    rows: list[ClaimReadiness] = []

    for claim in state.claims:
        ev = evidence[claim.id]
        conf = ev.confidence
        blockers = [d for d in claim.depends_on if own_status.get(d) != _SUPPORTED]
        dep_refuted = any(own_status.get(d) == ClaimStatus.refuted for d in claim.depends_on)
        effective = _effective_status(conf.status, claim.depends_on, blockers, dep_refuted)
        missing = sorted(ev.baseline_missing_cells)
        thin = bool(ev.observed_conditions) and ev.evidence_breadth < 1.0 and claim.importance >= 0.5
        insufficient = bool(ev.observed_conditions) and ev.seed_sufficiency < 1.0
        rows.append(
            ClaimReadiness(
                claim_id=claim.id,
                type=claim.type.value,
                importance=claim.importance,
                own_status=conf.status,
                effective_status=effective,
                confidence=conf.confidence,
                blockers=blockers,
                missing_baselines=missing,
                thin_generality=thin,
                insufficient_seeds=insufficient,
                reviewer_risk=claim.reviewer_risk,
                reviewer_attacks=_reviewer_attacks(claim, ev, effective, blockers),
                recommended_actions=_recommended_actions(claim, ev, effective, blockers, missing),
            )
        )

    def ids(status: ClaimStatus) -> list[str]:
        return [r.claim_id for r in rows if r.effective_status == status]

    # Dangerous attacks: weight each claim's attacks by its reviewer_risk * importance.
    scored_attacks = sorted(
        ((r.reviewer_risk * r.importance, a) for r in rows for a in r.reviewer_attacks),
        key=lambda x: -x[0],
    )
    dangerous = [a for _, a in scored_attacks]

    # Next actions: from the highest importance * reviewer_risk claims first.
    rows_by_priority = sorted(rows, key=lambda r: -(r.importance + r.reviewer_risk))
    next_actions = [a for r in rows_by_priority for a in r.recommended_actions]

    # Paper-ready iff every main/high-importance claim is effectively supported.
    key_claims = [r for r in rows if r.type == "main" or r.importance >= 0.7]
    paper_ready = bool(key_claims) and all(
        r.effective_status == _SUPPORTED for r in key_claims
    )

    n_key = len(key_claims)
    n_key_ok = sum(1 for r in key_claims if r.effective_status == _SUPPORTED)
    summary = (
        f"{n_key_ok}/{n_key} key claim(s) effectively supported; "
        f"{len(ids(ClaimStatus.blocked))} blocked, {len(ids(ClaimStatus.refuted))} refuted, "
        f"{len(dangerous)} reviewer attack(s) open."
        if key_claims
        else "No main or high-importance claims defined."
    )

    return ReadinessReport(
        claims=rows,
        supported=ids(ClaimStatus.supported),
        refuted=ids(ClaimStatus.refuted),
        weak=ids(ClaimStatus.weak),
        needs_more_evidence=ids(ClaimStatus.needs_more_evidence),
        blocked=ids(ClaimStatus.blocked),
        dangerous_attacks=dangerous,
        next_actions=next_actions,
        paper_ready=paper_ready,
        summary=summary,
    )

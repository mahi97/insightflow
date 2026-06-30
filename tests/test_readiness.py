"""Paper-readiness / claim-graph tests."""

from __future__ import annotations

from insightflow.readiness import assess_readiness
from insightflow.schemas import Claim, ClaimStatus, ClaimType, ExperimentStatus, Policy, State
from tests.conftest import make_baseline, make_claim, make_method, make_result


def _supported_claim_state(observe_c2: bool = True) -> State:
    """C0 (main) depends_on C1 (empirical) and C2 (efficiency). C1 is fully
    observed (supported); C2 is observed iff observe_c2."""
    c0 = Claim(id="C0", statement="main", type=ClaimType.main, importance=0.95,
               reviewer_risk=0.8, depends_on=["C1", "C2"])
    c1 = make_claim("C1", required_seeds=1)
    c2 = make_claim("C2", required_seeds=1, importance=0.6, reviewer_risk=0.3)
    exps, results = [], []
    # C1: two datasets, method+baseline each, clear effect -> supported.
    for ds in ("d1", "d2"):
        m = make_method(ds, 0, claims=("C1",), status=ExperimentStatus.completed)
        b = make_baseline(ds, 0, claims=("C1",), status=ExperimentStatus.completed)
        exps += [m, b]
        results += [make_result(m, 0.80), make_result(b, 0.72)]
    if observe_c2:
        for ds in ("e1", "e2"):
            m = make_method(ds, 0, claims=("C2",), status=ExperimentStatus.completed)
            m = m.model_copy(update={"method": "method_b", "id": f"method_b_{ds}_s0"})
            b = make_baseline(ds, 0, claims=("C2",), status=ExperimentStatus.completed)
            exps += [m, b]
            results += [make_result(m, 0.80), make_result(b, 0.72)]
    else:
        # C2 has a pending experiment but no results -> needs_more_evidence.
        exps.append(make_method("e1", 0, claims=("C2",)))
    return State(claims=[c0, c1, c2], experiments=exps, results=results, policy=Policy())


def test_main_claim_supported_when_subclaims_supported():
    report = assess_readiness(_supported_claim_state(observe_c2=True))
    by_id = {r.claim_id: r for r in report.claims}
    assert by_id["C1"].effective_status == ClaimStatus.supported
    assert by_id["C2"].effective_status == ClaimStatus.supported
    assert by_id["C0"].effective_status == ClaimStatus.supported  # derived from subgraph
    assert report.paper_ready is True


def test_main_claim_blocked_when_a_subclaim_is_unmet():
    report = assess_readiness(_supported_claim_state(observe_c2=False))
    by_id = {r.claim_id: r for r in report.claims}
    assert by_id["C0"].effective_status == ClaimStatus.blocked
    assert "C2" in by_id["C0"].blockers
    assert "C0" in report.blocked
    assert report.paper_ready is False


def test_report_serializes_and_has_attacks_and_actions():
    report = assess_readiness(_supported_claim_state(observe_c2=False))
    d = report.model_dump()
    assert "claims" in d and "dangerous_attacks" in d and "next_actions" in d
    # An unmet main claim should produce at least one recommended action.
    assert report.next_actions


def test_refuted_subclaim_makes_meta_claim_weak():
    c0 = Claim(id="C0", statement="m", type=ClaimType.main, importance=0.9, depends_on=["C1"])
    c1 = make_claim("C1", required_seeds=1)
    exps, results = [], []
    # C1: method clearly WORSE than baseline on two datasets -> refuted.
    for ds in ("d1", "d2"):
        m = make_method(ds, 0, claims=("C1",), status=ExperimentStatus.completed)
        b = make_baseline(ds, 0, claims=("C1",), status=ExperimentStatus.completed)
        exps += [m, b]
        results += [make_result(m, 0.60), make_result(b, 0.72)]  # method worse
    state = State(claims=[c0, c1], experiments=exps, results=results, policy=Policy())
    report = assess_readiness(state)
    by_id = {r.claim_id: r for r in report.claims}
    assert by_id["C1"].effective_status == ClaimStatus.refuted
    assert by_id["C0"].effective_status == ClaimStatus.weak

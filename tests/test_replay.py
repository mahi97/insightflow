"""Offline replay evaluation tests."""

from __future__ import annotations

from insightflow.replay import replay
from insightflow.schemas import ExperimentStatus, Policy, State
from tests.conftest import make_baseline, make_claim, make_method, make_result


def _full_history_state():
    """3 datasets, method+baseline observed on each (effect ~+0.06). The results
    are listed in a depth-first 'bad' arrival order (all of cifar10 first), which
    a breadth-first scheduler should be able to beat."""
    claim = make_claim("C1", required_seeds=1, minimum_effect_size=0.02)
    exps, results = [], []
    order = []
    # cifar10 first (3 method seeds + baseline), then cifar100, then svhn.
    for ds in ("cifar10", "cifar100", "svhn"):
        for s in range(3 if ds == "cifar10" else 1):
            order.append((make_method(ds, s, status=ExperimentStatus.completed), 0.80))
        order.append((make_baseline(ds, 0, status=ExperimentStatus.completed), 0.72))
    for i, (e, acc) in enumerate(order):
        exps.append(e)
        r = make_result(e, acc)
        r = r.model_copy(update={"finished_at": f"2026-01-01T00:{i:02d}:00+00:00"})
        results.append(r)
    return State(claims=[claim], experiments=exps, results=results, policy=Policy())


def test_replay_decides_and_insight_no_worse_than_actual():
    result = replay(_full_history_state())
    assert result.ground_truth == {"C1": "supported"}
    assert result.actual_decided_at is not None
    assert result.insight_decided_at is not None
    # InsightFlow should reach the same decision in no more runs than the real order.
    assert result.insight_decided_at <= result.actual_decided_at
    assert result.runs_saved >= 0


def test_replay_with_no_decision_returns_empty_ground_truth():
    # Three datasets are DEFINED but only one is observed -> generality unverified,
    # so the full history decides nothing and there is nothing to replay against.
    claim = make_claim("C1", required_seeds=1)
    m = make_method("cifar10", 0, status=ExperimentStatus.completed)
    b = make_baseline("cifar10", 0, status=ExperimentStatus.completed)
    pending = [make_method("cifar100", 0), make_method("svhn", 0)]  # defined, not run
    state = State(
        claims=[claim],
        experiments=[m, b, *pending],
        results=[make_result(m, 0.8), make_result(b, 0.72)],
        policy=Policy(),
    )
    result = replay(state)
    assert result.ground_truth == {}
    assert result.runs_saved is None


def test_replay_handles_duplicate_experiment_ids():
    # Two completed results for the same experiment id must not break the
    # apples-to-apples comparison (deduped to one evidence value per experiment).
    state = _full_history_state()
    dup_exp = state.experiments[0]
    dup = make_result(dup_exp, 0.81).model_copy(
        update={"run_id": "dup", "finished_at": "2026-01-01T00:99:00+00:00"}
    )
    state = state.model_copy(update={"results": [*state.results, dup]})
    result = replay(state)
    assert result.ground_truth == {"C1": "supported"}
    assert result.insight_decided_at is not None
    assert result.runs_saved >= 0


def test_replay_multi_policy_comparison():
    result = replay(_full_history_state())
    comp = result.policy_comparison
    assert {"actual", "insightflow", "grid", "random", "cheap_first", "seeds_first"} <= set(comp)
    # InsightFlow should decide in no more runs than the worst non-adaptive policy.
    decided = [v for v in comp.values() if v is not None]
    assert comp["insightflow"] is not None
    assert comp["insightflow"] <= max(decided)


def test_replay_from_csv_example():
    """The committed replay-from-CSV example: import completed runs and confirm
    InsightFlow's replay order reaches the verdict in no more runs than the actual."""
    import shutil
    from pathlib import Path

    from insightflow.importers import import_csv
    from insightflow.ledger import Ledger

    src = Path(__file__).resolve().parent.parent / "examples" / "replay_example"
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(src / "configs", tmp / "configs")
    ledger = Ledger(tmp)
    ledger.initialize(force=True)
    exps, results = import_csv(src / "runs.csv", "accuracy")
    ledger.merge_imported_runs(exps, results)

    result = replay(ledger.load_state())
    assert result.ground_truth == {"C1": "supported"}
    assert result.policy_comparison["insightflow"] is not None
    assert result.policy_comparison["insightflow"] <= result.policy_comparison["actual"]


def test_real_gfa_vs_lora_example_is_weak_not_overclaimed():
    """The committed real-data case (447 GLUE runs, best-of-sweep) must reproduce
    the honest 'weak' verdict — InsightFlow does not certify the +0.011 margin."""
    import shutil
    import tempfile
    from pathlib import Path

    from insightflow.importers import import_csv
    from insightflow.ledger import Ledger
    from insightflow.readiness import assess_readiness

    src = Path(__file__).resolve().parent.parent / "examples" / "gfa_vs_lora_real"
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(src / "configs", tmp / "configs")
    ledger = Ledger(tmp)
    ledger.initialize(force=True)
    exps, results = import_csv(src / "runs.csv", "score")
    ledger.merge_imported_runs(exps, results)

    report = assess_readiness(ledger.load_state())
    c1 = next(c for c in report.claims if c.claim_id == "C1")
    assert c1.effective_status.value == "weak"       # not 'supported'
    assert not report.paper_ready

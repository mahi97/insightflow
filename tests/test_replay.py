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

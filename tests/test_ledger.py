"""Ledger persistence tests."""

from __future__ import annotations

import pytest

from insightflow.config import write_default_configs
from insightflow.errors import NotInitializedError
from insightflow.ledger import Ledger
from insightflow.schemas import (
    Experiment,
    ExperimentStatus,
    Plan,
    RunResult,
    RunSource,
    RunStatus,
)


def _init(tmp_path) -> Ledger:
    write_default_configs(tmp_path)
    ledger = Ledger(tmp_path)
    ledger.initialize(force=True)
    return ledger


def test_requires_initialization(tmp_path):
    ledger = Ledger(tmp_path)
    assert ledger.is_initialized() is False
    with pytest.raises(NotInitializedError):
        ledger.load_state()


def test_init_creates_ledger(tmp_path):
    ledger = _init(tmp_path)
    assert ledger.is_initialized()
    assert (tmp_path / ".insightflow" / "ledger.db").exists()
    assert (tmp_path / ".insightflow" / "decisions.jsonl").exists()


def test_results_roundtrip_and_status_inference(tmp_path):
    ledger = _init(tmp_path)
    # The default config has one experiment 'method_dataset_seed0'.
    result = RunResult(
        run_id="r1",
        experiment_id="method_dataset_seed0",
        metrics={"accuracy": 0.8},
        status=RunStatus.completed,
        source=RunSource.manual,
    )
    ledger.add_result(result)
    state = ledger.load_state()
    exp = state.experiment("method_dataset_seed0")
    assert exp is not None
    assert exp.status == ExperimentStatus.completed  # inferred from completed result
    assert len(state.results) == 1


def test_plan_save_and_latest(tmp_path):
    ledger = _init(tmp_path)
    p1 = Plan(id="plan_a", created_at="2026-01-01T00:00:00+00:00")
    p2 = Plan(id="plan_b", created_at="2026-02-01T00:00:00+00:00")
    ledger.save_plan(p1)
    ledger.save_plan(p2)
    assert ledger.get_plan("plan_a").id == "plan_a"
    assert ledger.latest_plan().id == "plan_b"


def test_decision_log_appends(tmp_path):
    ledger = _init(tmp_path)
    ledger.log_decision({"event": "test", "n": 1})
    ledger.log_decision({"event": "test", "n": 2})
    decisions = ledger.read_decisions()
    assert len(decisions) == 2
    assert decisions[0]["n"] == 1
    assert "ts" in decisions[0]


def test_state_hash_changes_with_results(tmp_path):
    ledger = _init(tmp_path)
    h0 = ledger.state_hash()
    ledger.add_result(
        RunResult(run_id="r", experiment_id="method_dataset_seed0", status=RunStatus.completed)
    )
    h1 = ledger.state_hash()
    assert h0 != h1
    assert ledger.state_hash() == h1  # deterministic


def test_merge_imported_runs(tmp_path):
    ledger = _init(tmp_path)
    exp = Experiment(id="wb_run", method="m", dataset="d", tags=["wandb"])
    res = RunResult(
        run_id="wb_run", experiment_id="wb_run", metrics={"accuracy": 0.9}, source=RunSource.wandb
    )
    n_exp, n_res = ledger.merge_imported_runs([exp], [res])
    assert (n_exp, n_res) == (1, 1)
    state = ledger.load_state()
    assert state.experiment("wb_run") is not None
    assert any(r.run_id == "wb_run" for r in state.results)

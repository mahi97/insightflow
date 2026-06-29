"""CSV / JSONL / MLflow importer tests (no live services)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from insightflow.errors import InsightFlowError
from insightflow.importers import import_csv, import_jsonl, import_mlflow
from insightflow.schemas import RunStatus


def test_import_csv_maps_columns(tmp_path):
    csv = tmp_path / "runs.csv"
    csv.write_text(
        "id,method,dataset,seed,alpha,accuracy,cost\n"
        "r1,method_a,cifar10,0,0.1,0.81,1.5\n"
        "r2,baseline_a,cifar10,0,0.1,0.74,1.2\n"
    )
    experiments, results = import_csv(csv, "accuracy")
    assert len(experiments) == 2
    exp = next(e for e in experiments if e.id == "r1")
    assert exp.method == "method_a"
    assert exp.dataset == "cifar10"
    assert exp.condition == "alpha=0.1"
    res = next(r for r in results if r.run_id == "r1")
    assert res.metrics["accuracy"] == 0.81
    assert res.cost == 1.5


def test_import_csv_missing_metric_raises(tmp_path):
    csv = tmp_path / "runs.csv"
    csv.write_text("id,method,loss\nr1,m,0.3\n")
    with pytest.raises(InsightFlowError) as exc:
        import_csv(csv, "accuracy")
    assert "accuracy" in str(exc.value)


def test_import_csv_missing_file_raises(tmp_path):
    with pytest.raises(InsightFlowError):
        import_csv(tmp_path / "nope.csv", "accuracy")


def test_import_jsonl(tmp_path):
    p = tmp_path / "runs.jsonl"
    p.write_text(
        json.dumps({"run_id": "a", "method": "method_a", "dataset": "svhn", "seed": 1, "accuracy": 0.9})
        + "\n"
        + json.dumps({"run_id": "b", "method": "baseline_a", "dataset": "svhn", "accuracy": 0.85})
        + "\n"
    )
    experiments, results = import_jsonl(p, "accuracy")
    assert {e.id for e in experiments} == {"a", "b"}
    assert next(r for r in results if r.run_id == "a").metrics["accuracy"] == 0.9


# --- MLflow (mocked) -------------------------------------------------------
class _FakeRun:
    def __init__(self, run_id, params, metrics, status="FINISHED"):
        self.info = SimpleNamespace(run_id=run_id, status=status)
        self.data = SimpleNamespace(params=params, metrics=metrics)


class _FakeClient:
    def __init__(self, runs, experiment=SimpleNamespace(experiment_id="0")):
        self._runs = runs
        self._experiment = experiment

    def get_experiment_by_name(self, name):
        return self._experiment

    def search_runs(self, experiment_ids, max_results=200):
        return list(self._runs)[:max_results]


def _client():
    return _FakeClient(
        [
            _FakeRun("m1", {"method": "method_a", "dataset": "cifar10", "seed": "0"}, {"accuracy": 0.8}),
            _FakeRun("b1", {"method": "baseline_a", "dataset": "cifar10"}, {"accuracy": 0.73}, "RUNNING"),
        ]
    )


def test_import_mlflow_maps_runs():
    experiments, results = import_mlflow("exp", "accuracy", client=_client())
    assert len(experiments) == 2
    assert next(r for r in results if r.run_id == "m1").metrics["accuracy"] == 0.8
    assert next(r for r in results if r.run_id == "b1").status == RunStatus.running


def test_import_mlflow_unknown_experiment_raises():
    client = _FakeClient([], experiment=None)
    with pytest.raises(InsightFlowError) as exc:
        import_mlflow("missing", "accuracy", client=client)
    assert "not found" in str(exc.value)


def test_import_mlflow_missing_metric_raises():
    client = _FakeClient([_FakeRun("m1", {"method": "m"}, {"loss": 0.3})])
    with pytest.raises(InsightFlowError) as exc:
        import_mlflow("exp", "accuracy", client=client)
    assert "accuracy" in str(exc.value)


def test_import_mlflow_not_installed_message(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("mlflow"):
            raise ImportError("no mlflow")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(InsightFlowError) as exc:
        import_mlflow("exp", "accuracy")
    assert "uv add mlflow" in str(exc.value)

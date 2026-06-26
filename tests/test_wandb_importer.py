"""W&B importer tests using a mocked API (no live W&B required)."""

from __future__ import annotations

import pytest

from insightflow.errors import WandbImportError
from insightflow.schemas import RunSource, RunStatus
from insightflow.wandb_importer import import_wandb


class FakeRun:
    def __init__(self, id, config, summary, state="finished", history=None):
        self.id = id
        self.name = id
        self.config = config
        self.summary = summary
        self.state = state
        self.job_type = config.get("method", "method")
        self._history = history or []

    def history(self, keys=None):
        return list(self._history)


class FakeApi:
    def __init__(self, runs):
        self._runs = runs

    def runs(self, path):
        return list(self._runs)


def _api():
    return FakeApi(
        [
            FakeRun(
                "run_a",
                config={"method": "method_a", "dataset": "cifar10", "seed": 0, "alpha": 0.1},
                summary={"accuracy": 0.81, "_runtime": 3600},
                history=[{"_step": 1, "accuracy": 0.5}, {"_step": 2, "accuracy": 0.81}],
            ),
            FakeRun(
                "run_b",
                config={"method": "baseline_a", "dataset": "cifar10", "seed": 0},
                summary={"accuracy": 0.74, "_runtime": 1800},
                state="running",
            ),
        ]
    )


def test_import_maps_config_and_summary():
    experiments, results = import_wandb("ent", "proj", "accuracy", api=_api())
    assert len(experiments) == 2
    assert len(results) == 2

    exp_a = next(e for e in experiments if e.id == "run_a")
    assert exp_a.method == "method_a"
    assert exp_a.dataset == "cifar10"
    assert exp_a.condition == "alpha=0.1"

    res_a = next(r for r in results if r.run_id == "run_a")
    assert res_a.metrics["accuracy"] == 0.81
    assert res_a.source == RunSource.wandb
    assert res_a.partial_history  # history was mapped
    assert res_a.status == RunStatus.completed

    res_b = next(r for r in results if r.run_id == "run_b")
    assert res_b.status == RunStatus.running


def test_missing_metric_raises_clear_error():
    api = FakeApi([FakeRun("r", config={"method": "m"}, summary={"loss": 0.1})])
    with pytest.raises(WandbImportError) as exc:
        import_wandb("ent", "proj", "accuracy", api=api)
    assert "accuracy" in str(exc.value)


def test_empty_project_raises():
    with pytest.raises(WandbImportError):
        import_wandb("ent", "proj", "accuracy", api=FakeApi([]))


def test_missing_args_raise():
    with pytest.raises(WandbImportError):
        import_wandb("", "proj", "accuracy", api=_api())
    with pytest.raises(WandbImportError):
        import_wandb("ent", "proj", "", api=_api())


def test_limit_is_respected():
    runs = [
        FakeRun(f"r{i}", config={"method": "m", "dataset": "d"}, summary={"accuracy": 0.5})
        for i in range(10)
    ]
    experiments, _ = import_wandb("ent", "proj", "accuracy", limit=3, api=FakeApi(runs))
    assert len(experiments) == 3


def test_not_installed_message(monkeypatch):
    """When wandb is absent and no api is injected, the error is actionable."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "wandb":
            raise ImportError("No module named 'wandb'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(WandbImportError) as exc:
        import_wandb("ent", "proj", "accuracy")
    assert "uv add wandb" in str(exc.value)

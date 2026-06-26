"""Weights & Biases importer.

Design goals from the spec:

* ``wandb`` is an *optional* dependency. Importing this module never requires it;
  only calling :func:`import_wandb` without an injected API does.
* Map W&B ``config`` fields onto :class:`Experiment` fields, and
  ``summary``/``history`` metrics onto :class:`RunResult`.
* Give clear, actionable errors for: wandb not installed, not logged in, missing
  project, and a metric that no run reports.
* Be testable without live W&B by accepting an ``api`` object (see
  ``tests/test_wandb_importer.py``), so tests mock the API surface.
"""

from __future__ import annotations

from typing import Any

from .errors import WandbImportError
from .schemas import Experiment, ExperimentStatus, RunResult, RunSource, RunStatus

_STATE_MAP = {
    "finished": RunStatus.completed,
    "running": RunStatus.running,
    "crashed": RunStatus.failed,
    "failed": RunStatus.failed,
    "killed": RunStatus.failed,
}


def _get_api(api: Any | None) -> Any:
    if api is not None:
        return api
    try:
        import wandb  # noqa: PLC0415  (deliberately lazy)
    except ImportError as exc:  # pragma: no cover - exercised via message in tests
        raise WandbImportError(
            "The 'wandb' package is not installed. Install it with "
            "`uv add wandb` (or `uv pip install insightflow[wandb]`), then run "
            "`uv run wandb login` before importing."
        ) from exc
    try:
        return wandb.Api()
    except Exception as exc:  # pragma: no cover - network/auth at runtime
        raise WandbImportError(
            f"Could not create a W&B API client (are you logged in? run `wandb login`): {exc}"
        ) from exc


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    try:
        return dict(obj)
    except (TypeError, ValueError):
        return {}


def _condition_label(config: dict[str, Any]) -> str:
    for key in ("condition", "alpha", "ratio", "split"):
        if key in config:
            return f"{key}={config[key]}" if key != "condition" else str(config[key])
    return "default"


def _history(run: Any, metric: str) -> list[dict[str, float]]:
    """Best-effort extraction of a metric's history into partial_history."""
    fn = getattr(run, "history", None)
    if not callable(fn):
        return []
    try:
        rows = fn(keys=[metric])
    except TypeError:
        try:
            rows = fn()
        except Exception:
            return []
    except Exception:
        return []
    out: list[dict[str, float]] = []
    # Support pandas-like (.iterrows / to_dict) and plain list-of-dicts.
    if hasattr(rows, "to_dict"):
        try:
            records = rows.to_dict("records")
        except Exception:
            records = []
    else:
        records = list(rows) if rows is not None else []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or metric not in rec or rec[metric] is None:
            continue
        step_val = rec.get("_step", rec.get("step", i))
        step = float(step_val) if step_val is not None else float(i)
        out.append({"step": step, metric: float(rec[metric])})
    return out


def _map_run(run: Any, metric: str) -> tuple[Experiment, RunResult, bool]:
    config = _as_dict(getattr(run, "config", {}))
    summary = _as_dict(getattr(run, "summary", {}))
    run_id = str(getattr(run, "id", None) or getattr(run, "name", "unknown"))
    name = str(getattr(run, "name", run_id))

    method = str(config.get("method") or config.get("model") or getattr(run, "job_type", "") or "method")
    dataset = str(config.get("dataset") or config.get("data") or "dataset")
    seed = int(config.get("seed", 0) or 0)
    state = str(getattr(run, "state", "finished")).lower()
    status = _STATE_MAP.get(state, RunStatus.completed)

    raw_metric = summary.get(metric)
    history = _history(run, metric)
    if raw_metric is None and history:
        raw_metric = history[-1][metric]
    metric_value: float | None = float(raw_metric) if raw_metric is not None else None
    metric_found = metric_value is not None

    raw_runtime = summary.get("_runtime", summary.get("runtime", 0.0))
    runtime = float(raw_runtime) if isinstance(raw_runtime, (int, float)) else 0.0
    metrics: dict[str, float] = {metric: metric_value} if metric_value is not None else {}

    experiment = Experiment(
        id=name,
        method=method,
        dataset=dataset,
        model=config.get("model"),
        condition=_condition_label(config),
        seed=seed,
        baseline=config.get("baseline"),
        command=config.get("command"),
        expected_cost=max(0.0, runtime / 3600.0) or 1.0,
        expected_time=max(1e-3, runtime / 3600.0) or 1.0,
        status=ExperimentStatus.completed if status == RunStatus.completed else ExperimentStatus.running,
        tags=["wandb"],
        notes=f"Imported from W&B run '{name}'.",
    )
    result = RunResult(
        run_id=run_id,
        experiment_id=name,
        seed=seed,
        metrics=metrics,
        cost=max(0.0, runtime / 3600.0),
        wall_time=runtime,
        status=status,
        source=RunSource.wandb,
        partial_history=history,
        notes=f"state={state}",
    )
    return experiment, result, metric_found


def import_wandb(
    entity: str,
    project: str,
    metric: str,
    limit: int = 200,
    api: Any | None = None,
) -> tuple[list[Experiment], list[RunResult]]:
    """Import up to ``limit`` runs from ``entity/project`` for ``metric``."""
    if not entity or not project:
        raise WandbImportError("Both --entity and --project are required for W&B import.")
    if not metric:
        raise WandbImportError("A --metric name is required (e.g. --metric accuracy).")

    client = _get_api(api)
    path = f"{entity}/{project}"
    try:
        runs = client.runs(path)
    except Exception as exc:
        raise WandbImportError(
            f"Could not list runs for '{path}'. Check the entity/project names and that you "
            f"have access (run `wandb login`). Underlying error: {exc}"
        ) from exc

    experiments: list[Experiment] = []
    results: list[RunResult] = []
    any_metric = False
    count = 0
    for run in runs:
        if count >= limit:
            break
        exp, res, found = _map_run(run, metric)
        any_metric = any_metric or found
        experiments.append(exp)
        results.append(res)
        count += 1

    if count == 0:
        raise WandbImportError(
            f"No runs found in '{path}'. Is the project name correct and non-empty?"
        )
    if not any_metric:
        raise WandbImportError(
            f"None of the {count} imported runs report metric '{metric}'. "
            "Check the metric name (it must match a key in run.summary or history)."
        )
    return experiments, results

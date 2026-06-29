"""Importers for run results from CSV/JSONL and MLflow.

These complement the W&B importer (``wandb_importer.py``). CSV/JSONL need no
extra dependencies; MLflow is optional and imported lazily, with an injectable
client so tests never need a live server. All of them map flat run records onto
:class:`Experiment` + :class:`RunResult` and degrade with clear errors.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .errors import InsightFlowError
from .schemas import Experiment, ExperimentStatus, RunResult, RunSource, RunStatus


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _condition_label(params: dict[str, Any]) -> str:
    for key in ("condition", "alpha", "ratio", "split"):
        if key in params and params[key] not in (None, ""):
            return str(params[key]) if key == "condition" else f"{key}={params[key]}"
    return "default"


def _build_models(
    run_id: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    metric: str,
    source: RunSource,
    status: RunStatus = RunStatus.completed,
) -> tuple[Experiment, RunResult, bool]:
    method = str(params.get("method") or params.get("model") or "method")
    dataset = str(params.get("dataset") or params.get("data") or "dataset")
    seed = int(_num(params.get("seed", 0)))
    runtime = _num(params.get("wall_time", params.get("time", params.get("runtime", 0.0))))
    cost = _num(params.get("cost", params.get("expected_cost", runtime / 3600.0 if runtime else 0.0)))

    raw_value = metrics.get(metric)
    metric_value = _num(raw_value, default=float("nan")) if raw_value is not None else None
    found = metric_value is not None and not (metric_value != metric_value)  # not None, not NaN
    experiment = Experiment(
        id=run_id,
        method=method,
        dataset=dataset,
        model=params.get("model"),
        baseline=params.get("baseline"),
        condition=_condition_label(params),
        seed=seed,
        expected_cost=max(cost, 0.0) or 1.0,
        expected_time=max(runtime, 1e-3) or 1.0,
        status=ExperimentStatus.completed,
        tags=[source.value],
        notes=f"Imported from {source.value}.",
    )
    result = RunResult(
        run_id=run_id,
        experiment_id=run_id,
        seed=seed,
        metrics={metric: metric_value} if found and metric_value is not None else {},
        cost=max(cost, 0.0),
        wall_time=runtime,
        status=status,
        source=source,
    )
    return experiment, result, found


# --------------------------------------------------------------------------- #
# CSV / JSONL
# --------------------------------------------------------------------------- #
_ID_KEYS = ("id", "run_id", "name", "run")


def _row_id(row: dict[str, Any], index: int) -> str:
    for k in _ID_KEYS:
        if row.get(k):
            return str(row[k])
    return f"row{index}"


def _records_to_models(
    records: list[dict[str, Any]], metric: str, source: RunSource
) -> tuple[list[Experiment], list[RunResult]]:
    if not records:
        raise InsightFlowError("No rows found to import.")
    experiments, results = [], []
    any_metric = False
    seen: set[str] = set()
    for i, row in enumerate(records):
        rid = _row_id(row, i)
        while rid in seen:  # keep ids unique
            rid = f"{rid}_{i}"
        seen.add(rid)
        # In a flat record the metric is just another column.
        metrics = {metric: row[metric]} if metric in row and row[metric] not in (None, "") else {}
        exp, res, found = _build_models(rid, row, metrics, metric, source)
        any_metric = any_metric or found
        experiments.append(exp)
        results.append(res)
    if not any_metric:
        raise InsightFlowError(
            f"None of the {len(records)} rows contain metric '{metric}'. "
            "Check the column/field name."
        )
    return experiments, results


def import_csv(path: str | Path, metric: str) -> tuple[list[Experiment], list[RunResult]]:
    """Import runs from a CSV file (one run per row; the metric is a column)."""
    p = Path(path)
    if not p.exists():
        raise InsightFlowError(f"CSV file not found: {p}")
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    # Coerce numeric-looking metric/seed/cost strings.
    for r in rows:
        for k in (metric, "seed", "cost", "expected_cost", "wall_time", "time", "runtime"):
            if k in r and r[k] not in (None, ""):
                try:
                    r[k] = float(r[k])
                except (TypeError, ValueError):
                    pass
    return _records_to_models(rows, metric, RunSource.import_)


def import_jsonl(path: str | Path, metric: str) -> tuple[list[Experiment], list[RunResult]]:
    """Import runs from a JSONL file (one JSON run object per line)."""
    p = Path(path)
    if not p.exists():
        raise InsightFlowError(f"JSONL file not found: {p}")
    records = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return _records_to_models(records, metric, RunSource.import_)


# --------------------------------------------------------------------------- #
# MLflow (optional dependency, injectable client)
# --------------------------------------------------------------------------- #
def _get_mlflow_client(tracking_uri: str | None, client: Any | None) -> Any:
    if client is not None:
        return client
    try:
        from mlflow.tracking import MlflowClient  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised via message in tests
        raise InsightFlowError(
            "The 'mlflow' package is not installed. Install it with `uv add mlflow`, "
            "then point --tracking-uri at your MLflow server."
        ) from exc
    try:
        return MlflowClient(tracking_uri=tracking_uri)
    except Exception as exc:  # pragma: no cover - runtime connection issues
        raise InsightFlowError(f"Could not create an MLflow client: {exc}") from exc


_MLFLOW_STATE = {
    "FINISHED": RunStatus.completed,
    "RUNNING": RunStatus.running,
    "FAILED": RunStatus.failed,
    "KILLED": RunStatus.failed,
}


def import_mlflow(
    experiment_name: str,
    metric: str,
    tracking_uri: str | None = None,
    limit: int = 200,
    client: Any | None = None,
) -> tuple[list[Experiment], list[RunResult]]:
    """Import runs from an MLflow experiment (degrades gracefully)."""
    if not experiment_name:
        raise InsightFlowError("An --experiment-name is required for MLflow import.")
    if not metric:
        raise InsightFlowError("A --metric name is required (e.g. --metric accuracy).")

    mlflow_client = _get_mlflow_client(tracking_uri, client)
    experiment = mlflow_client.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise InsightFlowError(
            f"MLflow experiment '{experiment_name}' not found at "
            f"'{tracking_uri or 'default tracking URI'}'."
        )
    exp_id = getattr(experiment, "experiment_id", None) or experiment["experiment_id"]
    try:
        runs = mlflow_client.search_runs([exp_id], max_results=limit)
    except Exception as exc:
        raise InsightFlowError(f"Could not search MLflow runs: {exc}") from exc

    experiments, results = [], []
    any_metric = False
    for run in list(runs)[:limit]:
        params = dict(getattr(run.data, "params", {}) or {})
        metrics = dict(getattr(run.data, "metrics", {}) or {})
        run_id = str(getattr(run.info, "run_id", None) or getattr(run.info, "run_uuid", "unknown"))
        status = _MLFLOW_STATE.get(str(getattr(run.info, "status", "FINISHED")), RunStatus.completed)
        exp, res, found = _build_models(run_id, params, metrics, metric, RunSource.import_, status)
        any_metric = any_metric or found
        experiments.append(exp)
        results.append(res)

    if not experiments:
        raise InsightFlowError(f"No runs found in MLflow experiment '{experiment_name}'.")
    if not any_metric:
        raise InsightFlowError(
            f"None of the {len(experiments)} MLflow runs report metric '{metric}'."
        )
    return experiments, results

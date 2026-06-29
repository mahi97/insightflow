"""Local experiment launcher.

v0.1 is advisor-mode, but for *local* runs InsightFlow can also execute an
experiment's ``command`` and record the result — closing the loop without a
cluster. This is intentionally minimal and safe:

* It runs ``experiment.command`` as a subprocess and measures wall-clock time.
* It reads metrics from the command's output: the last line of stdout that
  parses as a JSON object of numbers, or a JSON file named by the
  ``INSIGHTFLOW_METRICS_FILE`` environment variable that the command writes.
* Exit code 0 + metrics found -> ``completed``; otherwise ``failed`` (recorded
  honestly, never silently dropped).

Slurm/Ray launchers and live monitoring are on the roadmap (see docs/roadmap.md);
this is the local, synchronous case.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .errors import InsightFlowError
from .schemas import Experiment, RunResult, RunSource, RunStatus
from .utils import now_iso, stable_hash

METRICS_FILE_ENV = "INSIGHTFLOW_METRICS_FILE"


def _parse_metrics_from_stdout(stdout: str) -> dict[str, float]:
    """Return the last stdout line that is a JSON object of numeric values."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            metrics = {
                k: float(v)
                for k, v in obj.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
            if metrics:
                return metrics
    return {}


def _read_metrics_file(path: str) -> dict[str, float]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(obj, dict):
        return {}
    return {
        k: float(v)
        for k, v in obj.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


class LocalLauncher:
    """Runs experiments locally and turns them into RunResults."""

    def __init__(self, cwd: str | Path | None = None, timeout: float | None = None):
        self.cwd = str(cwd) if cwd else None
        self.timeout = timeout

    def run(self, experiment: Experiment, monotonic: float | None = None) -> RunResult:
        if not experiment.command:
            raise InsightFlowError(
                f"Experiment '{experiment.id}' has no `command` to run. "
                "Add one to configs/experiments.yaml, or record results manually with "
                "`insightflow log-result`."
            )

        env = dict(os.environ)
        metrics_file = env.get(METRICS_FILE_ENV)
        started = now_iso()
        t0 = time.monotonic() if monotonic is None else monotonic
        try:
            proc = subprocess.run(
                experiment.command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.cwd,
                env=env,
                timeout=self.timeout,
            )
            elapsed = max(0.0, time.monotonic() - t0)
            returncode = proc.returncode
            stdout = proc.stdout
        except subprocess.TimeoutExpired as exc:
            elapsed = float(self.timeout or 0.0)
            returncode = -1
            # Recover whatever the process printed before timing out (bytes or str).
            partial = exc.stdout
            stdout = partial.decode(errors="replace") if isinstance(partial, bytes) else (partial or "")

        metrics = _parse_metrics_from_stdout(stdout)
        if not metrics and metrics_file:
            # A relative INSIGHTFLOW_METRICS_FILE is written by the child under the
            # launcher's cwd, so resolve it there (not the launcher's own cwd).
            mf = Path(metrics_file)
            if not mf.is_absolute() and self.cwd:
                mf = Path(self.cwd) / mf
            metrics = _read_metrics_file(str(mf))

        ok = returncode == 0 and bool(metrics)
        status = RunStatus.completed if ok else RunStatus.failed
        note = "" if ok else f"exit={returncode}; metrics_found={bool(metrics)}"

        return RunResult(
            run_id=f"local-{experiment.id}-{stable_hash((experiment.id, started), 8)}",
            experiment_id=experiment.id,
            seed=experiment.seed,
            metrics=metrics,
            cost=experiment.expected_cost,
            wall_time=round(elapsed, 3),
            status=status,
            started_at=started,
            finished_at=now_iso(),
            source=RunSource.manual,
            notes=note,
        )

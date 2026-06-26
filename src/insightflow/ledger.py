"""The ledger: InsightFlow's source of truth.

Definitions (claims, experiments, policy, resources) live in editable YAML
configs. Dynamic state - run results, status changes, plans, and an append-only
decision log - lives here:

    <project>/.insightflow/ledger.db        (SQLite, structured state)
    <project>/.insightflow/decisions.jsonl  (append-only audit log)

``load_state`` reconstructs a :class:`State` by combining configs with stored
results, imported experiments, and status overrides. The agent never edits this
directly; it goes through the CLI, which goes through here.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from . import config as configmod
from .errors import LedgerError, NotInitializedError
from .schemas import (
    Experiment,
    ExperimentStatus,
    Plan,
    RunResult,
    RunStatus,
    State,
)
from .utils import ensure_dir, now_iso, stable_hash

LEDGER_DIRNAME = ".insightflow"
DB_NAME = "ledger.db"
DECISIONS_NAME = "decisions.jsonl"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS results (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiment_status (
    experiment_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    payload TEXT NOT NULL
);
"""


class Ledger:
    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir).resolve()
        self.ledger_dir = self.project_dir / LEDGER_DIRNAME
        self.db_path = self.ledger_dir / DB_NAME
        self.decisions_path = self.ledger_dir / DECISIONS_NAME

    # -- lifecycle ----------------------------------------------------------
    def is_initialized(self) -> bool:
        return self.db_path.exists()

    def initialize(self, force: bool = False) -> None:
        ensure_dir(self.ledger_dir)
        if self.db_path.exists() and force:
            self.db_path.unlink()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('created_at', ?)",
                (now_iso(),),
            )
        if not self.decisions_path.exists():
            self.decisions_path.touch()

    def _require_init(self) -> None:
        if not self.is_initialized():
            raise NotInitializedError(str(self.project_dir))

    def _connect(self) -> sqlite3.Connection:
        ensure_dir(self.ledger_dir)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as exc:  # pragma: no cover - filesystem failure
            raise LedgerError(f"Could not open ledger at {self.db_path}: {exc}") from exc

    # -- results ------------------------------------------------------------
    def add_result(self, result: RunResult) -> None:
        self.add_results([result])

    def add_results(self, results: list[RunResult]) -> None:
        self._require_init()
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO results(run_id, experiment_id, payload) VALUES (?, ?, ?)",
                [(r.run_id, r.experiment_id, r.model_dump_json()) for r in results],
            )

    def get_results(self) -> list[RunResult]:
        self._require_init()
        with self._connect() as conn, closing(conn.execute("SELECT payload FROM results")) as cur:
            return [RunResult(**json.loads(row["payload"])) for row in cur.fetchall()]

    # -- experiments (imported / added) -------------------------------------
    def upsert_experiments(self, experiments: list[Experiment]) -> None:
        self._require_init()
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO experiments(id, payload) VALUES (?, ?)",
                [(e.id, e.model_dump_json()) for e in experiments],
            )

    def get_stored_experiments(self) -> list[Experiment]:
        self._require_init()
        with self._connect() as conn, closing(conn.execute("SELECT payload FROM experiments")) as cur:
            return [Experiment(**json.loads(row["payload"])) for row in cur.fetchall()]

    def update_experiment_status(self, experiment_id: str, status: ExperimentStatus) -> None:
        self._require_init()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO experiment_status(experiment_id, status, updated_at) "
                "VALUES (?, ?, ?)",
                (experiment_id, status.value, now_iso()),
            )

    def _status_overrides(self) -> dict[str, str]:
        with self._connect() as conn, closing(
            conn.execute("SELECT experiment_id, status FROM experiment_status")
        ) as cur:
            return {row["experiment_id"]: row["status"] for row in cur.fetchall()}

    # -- plans --------------------------------------------------------------
    def save_plan(self, plan: Plan) -> None:
        self._require_init()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO plans(id, created_at, payload) VALUES (?, ?, ?)",
                (plan.id, plan.created_at, plan.model_dump_json()),
            )

    def get_plan(self, plan_id: str) -> Plan | None:
        self._require_init()
        with self._connect() as conn, closing(
            conn.execute("SELECT payload FROM plans WHERE id = ?", (plan_id,))
        ) as cur:
            row = cur.fetchone()
            return Plan(**json.loads(row["payload"])) if row else None

    def latest_plan(self) -> Plan | None:
        self._require_init()
        with self._connect() as conn, closing(
            conn.execute("SELECT payload FROM plans ORDER BY created_at DESC LIMIT 1")
        ) as cur:
            row = cur.fetchone()
            return Plan(**json.loads(row["payload"])) if row else None

    # -- decision log -------------------------------------------------------
    def log_decision(self, record: dict[str, Any]) -> None:
        """Append a decision record to the audit log (creates the file if needed)."""
        ensure_dir(self.ledger_dir)
        entry = {"ts": now_iso(), **record}
        with open(self.decisions_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def read_decisions(self) -> list[dict[str, Any]]:
        if not self.decisions_path.exists():
            return []
        out = []
        with open(self.decisions_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    # -- W&B merge ----------------------------------------------------------
    def merge_imported_runs(
        self, experiments: list[Experiment], results: list[RunResult]
    ) -> tuple[int, int]:
        """Persist imported experiment definitions and run results.

        Returns ``(n_experiments, n_results)`` merged.
        """
        self._require_init()
        if experiments:
            self.upsert_experiments(experiments)
        if results:
            self.add_results(results)
        self.log_decision(
            {"event": "import", "experiments": len(experiments), "results": len(results)}
        )
        return len(experiments), len(results)

    # -- state assembly -----------------------------------------------------
    def load_state(self) -> State:
        """Reconstruct the full :class:`State` from configs + ledger."""
        self._require_init()
        claims = configmod.load_claims(self.project_dir)
        config_exps = configmod.load_experiments(self.project_dir)
        policy = configmod.load_policy(self.project_dir)
        resources = configmod.load_resources(self.project_dir)
        results = self.get_results()

        # Merge config experiments with stored (imported/added) ones; config wins on id.
        by_id: dict[str, Experiment] = {e.id: e for e in self.get_stored_experiments()}
        for e in config_exps:
            by_id[e.id] = e

        # Apply status overrides and infer completion from results.
        overrides = self._status_overrides()
        completed_ids = {r.experiment_id for r in results if r.status == RunStatus.completed}
        running_ids = {
            r.experiment_id for r in results if r.status in (RunStatus.running, RunStatus.partial)
        }
        experiments = []
        for e in by_id.values():
            if e.id in overrides:
                e = e.model_copy(update={"status": ExperimentStatus(overrides[e.id])})
            elif e.id in completed_ids:
                e = e.model_copy(update={"status": ExperimentStatus.completed})
            elif e.id in running_ids and e.status == ExperimentStatus.pending:
                e = e.model_copy(update={"status": ExperimentStatus.running})
            experiments.append(e)

        return State(
            claims=claims,
            experiments=experiments,
            results=results,
            policy=policy,
            resources=resources,
        )

    def state_hash(self) -> str:
        state = self.load_state()
        payload = {
            "experiments": sorted((e.id, e.status.value) for e in state.experiments),
            "results": sorted((r.run_id, r.experiment_id) for r in state.results),
        }
        return stable_hash(payload)

    # -- export -------------------------------------------------------------
    def export_json(self) -> dict[str, Any]:
        state = self.load_state()
        return json.loads(state.model_dump_json())

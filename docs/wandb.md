# Importing from Weights & Biases

InsightFlow can pull run history from an existing W&B project into the local
ledger, letting the scheduler reason over real experimental evidence without
requiring you to re-run anything.

`wandb` is an **optional dependency**. The importer module loads cleanly without
it; only calling `import-wandb` with live W&B (i.e., without an injected test
API) requires the package at runtime.

---

## 1. Install the optional dependency

```bash
uv add wandb
```

Or, if the project ships an extras group:

```bash
uv pip install insightflow[wandb]
```

Then authenticate once:

```bash
uv run wandb login
```

---

## 2. Run the import

```bash
uv run insightflow import-wandb \
  --entity  MY_TEAM_OR_USER \
  --project MY_PROJECT \
  --metric  accuracy \
  --limit   200
```

All four flags and their defaults:

| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--entity` | yes | — | W&B entity (team name or username) |
| `--project` | yes | — | W&B project name |
| `--metric` | yes | — | Metric key to import (e.g. `accuracy`, `val_loss`) |
| `--limit` | no | `200` | Maximum number of runs to fetch |

Use `-C / --project-dir` or `$INSIGHTFLOW_HOME` to point at a non-CWD project:

```bash
uv run insightflow import-wandb --entity acme --project nlp-sweep --metric f1 -C /path/to/project
```

On success the CLI prints:

```
Imported N run(s) and M experiment definition(s) from entity/project.
Link them to claims in configs/experiments.yaml, then run `uv run insightflow plan`.
```

---

## 3. What gets mapped

The importer reads each W&B run's `config` dict and `summary` dict (plus
`history` as a fallback) and produces one `Experiment` record and one
`RunResult` record per run.

### W&B → InsightFlow field mapping

| W&B source | InsightFlow field | Notes |
|-----------|-------------------|-------|
| `run.config["method"]` (then `"model"`, then `run.job_type`) | `Experiment.method` | Falls back to the literal string `"method"` if all are absent |
| `run.config["dataset"]` (then `"data"`) | `Experiment.dataset` | Falls back to `"dataset"` |
| `run.config["model"]` | `Experiment.model` | `None` if absent |
| `run.config["condition"]` | `Experiment.condition` | See condition-label logic below |
| `run.config["alpha"]`, `"ratio"`, or `"split"]` | `Experiment.condition` | Used as `key=value` when `"condition"` is absent; first match wins |
| `run.config["seed"]` | `Experiment.seed` and `RunResult.seed` | Defaults to `0` |
| `run.config["baseline"]` | `Experiment.baseline` | `None` if absent |
| `run.config["command"]` | `Experiment.command` | `None` if absent |
| `run.summary["_runtime"]` (then `"runtime"`) | `Experiment.expected_cost`, `Experiment.expected_time`, `RunResult.cost`, `RunResult.wall_time` | Converted from seconds to hours; clamped to `≥ 0`; defaults to `1.0 h` if zero |
| `run.state` | `RunResult.status` | `"finished"` → `completed`, `"running"` → `running`, `"crashed"/"failed"/"killed"` → `failed` |
| `run.summary[metric]` | `RunResult.metrics[metric]` | If absent, falls back to the last row in `history` for that metric |
| `run.history(keys=[metric])` | `RunResult.partial_history` | List of `{"step": N, metric: V}` dicts; best-effort, gracefully empty |
| `run.name` (then `run.id`) | `Experiment.id`, `RunResult.run_id`, `RunResult.experiment_id` | |
| — | `RunResult.source` | Always `RunSource.wandb` |
| — | `Experiment.tags` | Always `["wandb"]` |

**Condition-label logic.** `Experiment.condition` is set by scanning `config` for
keys in the order `condition`, `alpha`, `ratio`, `split`. The first key found
determines the label: if the key is `condition`, its value is used as-is;
otherwise the label is `key=value`. If none of the four keys are present the
condition is `"default"`.

**Limitation: one metric per call.** Each invocation imports a single metric
name. If your runs track both `accuracy` and `val_loss`, run `import-wandb`
twice with `--metric accuracy` and `--metric val_loss`. The second call merges
results rather than duplicating experiment definitions.

**Config-field mapping is best-effort.** The importer does not know your project's
exact config schema. If your runs use non-standard key names (e.g. `arch` instead
of `model`, or `lr` as a condition), the relevant `Experiment` fields will be
empty or default. Edit `configs/experiments.yaml` after importing to fill in any
missing fields.

---

## 4. After importing: link runs to claims

Imported experiments land in the ledger but are **not automatically linked to
claims**. After importing, open `configs/experiments.yaml` and add a
`claim_ids` list to each imported experiment so the scheduler knows which claims
the run provides evidence for:

```yaml
- id: run_a
  method: method_a
  dataset: cifar10
  claim_ids: [C1, C2]   # add this line
```

Then validate and replan:

```bash
uv run insightflow validate
uv run insightflow plan
```

---

## 5. Graceful-degradation and error scenarios

The importer fails with a clear, actionable `WandbImportError` in each of the
following cases. It never silently swallows errors.

| Scenario | Error message (excerpt) |
|----------|------------------------|
| `wandb` not installed | `"The 'wandb' package is not installed. Install it with \`uv add wandb\` (or \`uv pip install insightflow[wandb]\`), then run \`uv run wandb login\` before importing."` |
| Not logged in / API init failure | `"Could not create a W&B API client (are you logged in? run \`wandb login\`): ..."` |
| Entity or project not found / no access | `"Could not list runs for 'entity/project'. Check the entity/project names and that you have access (run \`wandb login\`). Underlying error: ..."` |
| Project exists but has no runs | `"No runs found in 'entity/project'. Is the project name correct and non-empty?"` |
| Runs found but none report the metric | `"None of the N imported runs report metric 'metric'. Check the metric name (it must match a key in run.summary or history)."` |
| Missing `--entity` or `--project` | `"Both --entity and --project are required for W&B import."` |
| Missing `--metric` | `"A --metric name is required (e.g. --metric accuracy)."` |

The hook is fail-open: if the W&B API returns an unexpected response shape, the
importer yields what it can (partial history may be empty, runtime may default to
`0.0`) rather than crashing.

---

## 6. How imports merge into the ledger

`ledger.merge_imported_runs(experiments, results)` is idempotent on experiment
IDs. Re-running `import-wandb` for the same project adds new results and
updates experiment definitions but does not create duplicates for runs already
present.

---

## 7. Testing the importer (for contributors)

No live W&B connection is needed. `import_wandb` accepts an optional `api`
argument that accepts any object with a `.runs(path)` method returning an
iterable of run-like objects. The test suite in
`tests/test_wandb_importer.py` uses two lightweight fake classes:

```python
class FakeRun:
    def __init__(self, id, config, summary, state="finished", history=None): ...
    def history(self, keys=None): ...   # returns list of dicts

class FakeApi:
    def __init__(self, runs): ...
    def runs(self, path): ...           # returns list of FakeRuns
```

To add a test for a new mapping behavior, construct a `FakeRun` with the
relevant `config`/`summary` fields and inject a `FakeApi`:

```python
from insightflow.wandb_importer import import_wandb

api = FakeApi([FakeRun("my_run", config={"method": "bert", "dataset": "glue", "alpha": 0.3},
                        summary={"f1": 0.88, "_runtime": 7200})])
experiments, results = import_wandb("ent", "proj", "f1", api=api)
assert experiments[0].method == "bert"
assert experiments[0].condition == "alpha=0.3"
assert results[0].metrics["f1"] == 0.88
```

The `test_not_installed_message` test patches `builtins.__import__` to simulate
the `wandb` package being absent and verifies the error message mentions
`uv add wandb`. The remaining tests cover field mapping, limit enforcement, and
each error scenario without any network calls.

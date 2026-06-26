# Importing W&B runs into InsightFlow

InsightFlow can ingest existing Weights & Biases runs so you can ask "what should
I run next?" against evidence you already have. `wandb` is an **optional**
dependency — InsightFlow never requires it unless you actually run the import
command.

## 1. Install the optional dependency

```bash
uv sync --extra wandb     # or: uv add wandb
uv run wandb login        # authenticate once
```

## 2. Initialize (or demo) a project

```bash
uv run insightflow init
```

## 3. Import runs

```bash
uv run insightflow import-wandb \
  --entity YOUR_ENTITY \
  --project YOUR_PROJECT \
  --metric accuracy \
  --limit 200
```

What happens:

- Each W&B run becomes an `Experiment` definition plus a `RunResult` in the
  ledger (`source = wandb`).
- `run.config` is mapped onto experiment fields where available:

  | W&B field                         | InsightFlow field         |
  | --------------------------------- | ------------------------- |
  | `config.method` / `config.model`  | `method`                  |
  | `config.dataset` / `config.data`  | `dataset`                 |
  | `config.seed`                     | `seed`                    |
  | `config.model`                    | `model`                   |
  | `config.alpha`/`ratio`/`split`    | `condition` (e.g. `alpha=0.1`) |
  | `summary[<metric>]` / history     | `RunResult.metrics` + `partial_history` |
  | `run.state`                       | run status                |

- Only the metric you pass is imported per call. Run the command again with a
  different `--metric` to add more.

## 4. Link imported runs to claims

Imported experiments start with no `claim_links`. Edit
`configs/experiments.yaml` to connect them to the claims they support or
threaten, then:

```bash
uv run insightflow validate
uv run insightflow plan
```

## Graceful degradation

The importer fails with a clear, actionable message (not a traceback) when:

- `wandb` is not installed (tells you to `uv add wandb`),
- you are not logged in,
- the entity/project is wrong or empty,
- no run reports the requested metric.

## Testing without live W&B

The importer accepts an injected API object, so the test suite
(`tests/test_wandb_importer.py`) mocks the W&B API entirely — tests never need
network access or credentials. See that file for the mock shape if you want to
extend the importer.

# CLAUDE.md — InsightFlow

Guidance for Claude Code working in this repository. See **[AGENTS.md](AGENTS.md)**
for the full agent operating rules; this file is the Claude-specific summary.

## What this project is

InsightFlow is an **adaptive experiment scheduler for ML research** that optimizes
**time-to-insight** — which experiment, seed, baseline, or ablation to run, avoid,
or postpone to decide research claims fastest under cost and uncertainty. It is
**not** AutoML, HPO, or experiment tracking.

The deterministic CLI + ledger are the **source of truth**. Claude is the
**interface**, never the authority.

## Non-negotiables when operating the tool

- **Use `uv` for everything**: `uv run insightflow ...`, `uv run pytest`, etc.
- **Run `uv run insightflow state` before any scheduling recommendation.**
- **Run `uv run insightflow plan` before proposing new runs.** Do not invent a
  queue, a claim status, or a rationale — read it from the plan.
- **Optimize time-to-insight, not grid completion.** Prefer breadth and decisive
  baselines over premature replication.
- **Explain recommendations in terms of claims/decisions**, e.g. "this checks
  external validity for C1", not "next in the grid".
- **Never launch expensive runs without showing the plan and getting approval.**
  v0.1 is advisor mode — recommend, don't execute.

There is an `adaptive-experiment-scheduler` skill in
`skills/` and a `guard_expensive_runs.py` PreToolUse hook in
`.claude/hooks/` that enforce these habits.

## When developing the codebase

- Run the dev checks before claiming done: `bash scripts/dev_check.sh`
  (= `uv sync` + `uv run ruff check .` + `uv run mypy src` + `uv run pytest`).
- Keep scoring **deterministic**: the same ledger + policy must yield the same
  plan. Tests in `tests/test_scheduler.py` and `tests/test_scoring.py` enforce
  this and would fail if the scheduler degraded into a trivial cost sorter.
- Architecture: `schemas.py` (models) → `config.py`/`ledger.py` (state) →
  `scoring.py` (terms) → `seed_policy.py` / `partial.py` → `scheduler.py` (plan)
  → `reports.py` / `explain.py` (output) → `cli.py`. Simulator + benchmark live in
  `simulator.py` / `benchmark.py`; W&B import in `wandb_importer.py`.

## Quick command reference

```bash
uv run insightflow demo --force      # toy project ready to plan
uv run insightflow state             # current evidence + claim table
uv run insightflow plan              # ranked queue + rationale (writes reports/)
uv run insightflow explain --plan ID # scoring breakdown + trade-offs
uv run insightflow benchmark --steps 20
uv run insightflow import-wandb --entity E --project P --metric accuracy
uv run insightflow log-result --experiment-id E --metric accuracy=0.72 --status completed
uv run insightflow validate
```

Add `--format json` to `state`/`plan`/`benchmark`/`validate` for machine output.
Use `-C/--project-dir` (or `$INSIGHTFLOW_HOME`) to point at a project directory.

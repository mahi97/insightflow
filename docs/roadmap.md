# Roadmap

This document describes what is built in the current release (v0.1) and what is
planned for future stages. Items in the roadmap sections are **not yet built**.

---

## v0.1 — What exists today

### Core data layer
- Typed Pydantic models in `schemas.py`: `Experiment`, `RunResult`, `Plan`,
  `Action`, `ClaimConfidence`, and related enums (`RunStatus`, `RunSource`,
  `ActionType`, `ExperimentStatus`).
- `Ledger`: SQLite-backed storage for results, plans, and decision logs, with
  JSONL fallback. Stores plan history and a full decision log for auditability.
- Config loader (`config.py`): reads `claims.yaml`, `experiments.yaml`,
  `resources.yaml`, and `policy.yaml`; validates links, duplicate IDs, and
  impossible costs.

### Scheduler
- Deterministic heuristic scheduler (`scheduler.py`): given current ledger state,
  scores available actions and produces a ranked `Plan`.
- Scoring terms (`scoring.py`): claim-confidence computation, breadth bonus,
  seed-replication penalty, baseline-gap penalty, dependency-unlock bonus, and
  partial-run awareness. The same ledger and policy always yield the same plan.
- Seed policy (`seed_policy.py`): decides when additional seeds are justified
  vs. premature.
- Partial-run heuristic (`partial.py`): uses learning-curve shape from
  `partial_history` to estimate whether a partially-completed run is worth
  completing or should be killed.

### Simulator and benchmark
- Simulator (`simulator.py`): generates synthetic projects and runs any
  registered policy against them, recording steps to decision, cost, runs
  launched, and wrong-decision rate.
- Benchmark harness (`benchmark.py`): runs all policies on N synthetic projects
  and prints a comparison table. Eight policies are registered: `insightflow`,
  `grid`, `all_seeds_first`, `all_tasks_first`, `random`, `cheap_first`,
  `fastest_first`, `oracle`. The current benchmark generates a
  breadth-vs.-replication scenario; there is one scenario type.
- `uv run insightflow benchmark --steps N --projects N` exposes this from the
  CLI.

### W&B importer
- `wandb_importer.py`: imports runs from a W&B project into the ledger. `wandb`
  is an optional dependency; the importer raises a clear, actionable
  `WandbImportError` if it is missing, if the user is not logged in, if the
  project is not found, or if no run reports the requested metric.
- `uv run insightflow import-wandb --entity E --project P --metric M` exposes
  this from the CLI.
- Tests in `tests/test_wandb_importer.py` mock the API so no live W&B is needed.

### CLI
All commands are invoked with `uv run insightflow <command>`.

| Command | What it does |
|---------|-------------|
| `init` | Writes starter configs and initializes the ledger |
| `validate` | Checks configs for missing IDs, bad claim links, impossible costs, duplicates |
| `state` | Shows completed/pending/running experiments and claim-confidence summary; writes `reports/state.md` |
| `plan` | Produces a ranked plan, saves it to the ledger, writes `reports/plan_latest.md` and `reports/claim_confidence.md` |
| `explain [--plan ID]` | Prints per-action scoring breakdown and trade-offs for the latest or a named plan |
| `simulate-step` | Runs the top plan action against the simulator and records the result |
| `benchmark [--steps N] [--projects N]` | Compares all policies on synthetic projects |
| `import-wandb` | Imports W&B runs into the ledger |
| `log-result` | Records a run result manually (metric=value format, repeatable) |
| `demo [--force]` | Creates a complete toy project with seeded runs, ready to plan |

All commands support `-C / --project-dir` and `$INSIGHTFLOW_HOME` for project
location. `state`, `plan`, `benchmark`, and `validate` support `--format json`
for machine-readable output.

### Reports
- Markdown reports (`reports.py`): `state.md`, `plan_latest.md`,
  `claim_confidence.md`, `benchmark.md`. Written to `reports/` on each relevant
  command.

### Agent infrastructure
- `AGENTS.md`: operating rules for any AI agent using InsightFlow.
- `CLAUDE.md`: Claude Code-specific summary of the same rules.
- `.claude/skills/adaptive-experiment-scheduler/SKILL.md`: skill definition that
  primes Claude Code with the workflow and iron rules before any scheduling task.
- `.claude/hooks/guard_expensive_runs.py`: PreToolUse hook that warns or blocks
  expensive training launches (patterns: `python train.py`, `torchrun`,
  `accelerate launch`, `deepspeed`, `sbatch`, `srun`, `ray submit`) when no
  recent plan exists. Three modes: `warn` (default), `block`, `off` via
  `INSIGHTFLOW_GUARD`.
- `prompts/`: agent prompt templates — `claude_research_agent_prompt.md`,
  `replanning_prompt.md`, and `review_plan_prompt.md`.
- `specs/REAL_PROJECT_ADAPTATION_PROMPT.md`: prompt for adapting InsightFlow to
  a real research repository.

---

## v0.2 — Planned (not built)

### Improved scoring

**Bayesian / value-of-information scoring.** Replace the current heuristic
claim-confidence computation with a principled Bayesian approach. Instead of
a deterministic formula over run counts and metric values, model each claim
as a belief distribution and score actions by their expected information gain
(value of information). This changes the scoring module but not the plan format.

**Real learning-curve extrapolation for partial runs.** Replace the current
partial-run heuristic with a proper learning-curve model (e.g., freeze-thaw or
a simple parametric fit) that extrapolates final performance from
`partial_history`. This lets the scheduler decide more reliably whether to
continue or kill a partial run based on projected final value, not just curve
shape.

### Additional importers

- **MLflow importer**: import runs from an MLflow tracking server. Same
  interface as the W&B importer; `mlflow` would be an optional dependency.
- **CSV importer**: import run results from a CSV file, for projects that log to
  flat files or export from other trackers.

### Launchers (human-approved execution mode)

- **Slurm launcher**: after human approval in the conversation, issue a `sbatch`
  job for the recommended experiment and record the submitted job ID.
- **Ray launcher**: same for Ray clusters.
- **Local launcher**: run a command locally (e.g., `python train.py`) and stream
  output.

All launchers require explicit human sign-off before running. The guard hook
would integrate with launcher state to verify plan freshness automatically.

### Offline replay evaluation

Run the InsightFlow scheduler on real W&B run logs in replay mode (all results
pre-computed) to evaluate how many runs would have been saved on a real
experiment history. This provides a concrete benchmark beyond the current
synthetic simulator.

### More benchmark scenarios

The current benchmark has one scenario type (breadth vs. replication). Planned
additions:
- **Expensive-branch trap**: a high-cost experiment that looks attractive early
  but provides little unique information once one other task is done.
- **Dependency-unlock scenario**: an experiment that is cheap and unlocks several
  high-value follow-ons.
- **Reviewer-risk baseline**: a scenario where the missing-baseline penalty
  should dominate, to verify the scheduler does not skip it.
- **Noisy-seeds scenario**: high metric variance across seeds, to stress-test the
  seed policy.

---

## v0.3 — Planned (not built)

### FastAPI server

A REST API wrapping the ledger and scheduler, so multiple users or external
tools can query state, submit results, and retrieve plans without a shared
filesystem. This is a prerequisite for the web dashboard and MCP tool.

### MCP tool

An MCP (Model Context Protocol) server that exposes InsightFlow's core
operations — `state`, `plan`, `log-result` — as MCP tools. This would allow
Claude Desktop, Cursor, and other MCP-compatible agents to interact with
InsightFlow natively without using the shell.

There is no MCP server or MCP tool in v0.1. The `AGENTS.md` file acknowledges
this explicitly.

### Web dashboard

A browser-based dashboard with views for:
- **Claim-confidence timeline**: how confidence in each claim evolved over runs.
- **Next-best-run**: interactive view of the current plan queue with rationale.
- **Cost-saved estimate**: projected compute saved vs. running the full grid.

### Multi-user lab mode

Support for multiple researchers sharing a single InsightFlow project: user
authentication, per-user decision logs, and conflict detection when two users
submit results for the same experiment.

### Live W&B monitoring

Poll a W&B project in the background and automatically import new runs as they
finish, triggering a replan when significant new evidence arrives. This removes
the manual `import-wandb` step for teams that already use W&B as their primary
logger.

### Notification hooks

Configurable webhooks or CLI hooks that fire when a plan changes significantly
(e.g., a claim flips to `supported`, a new highest-priority action appears, or
a missing-baseline warning is raised). Intended for Slack, email, or custom
notification channels.

### Plugin system for custom scorers

A plugin interface allowing projects to register custom scoring terms that
contribute to action scores alongside the built-in terms. This lets domain-
specific knowledge (e.g., "always prefer experiments on held-out test sets") be
encoded once and applied automatically by the scheduler.

---

## What InsightFlow is not

InsightFlow is **not** AutoML, a hyperparameter optimizer, or an experiment
tracker. It does not tune hyperparameters, run experiments automatically without
human approval (in v0.1), or replace W&B, MLflow, or similar tools. It
complements those trackers by importing their data and reasoning over which
experiment to run next to decide research claims fastest.

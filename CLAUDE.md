# CLAUDE.md — InsightFlow

Guidance for Claude Code working in this repository. See **[AGENTS.md](AGENTS.md)**
for the full agent operating rules; this file is the Claude-specific summary.

## What this project is

**InsightFlow is a claim-centered research decision layer for AI-assisted ML
research.** It helps researchers and coding agents decide which evidence to acquire
next, when to stop, what to postpone, what to avoid, and which claims are currently
supported, refuted, weak, or still uncertain. Position it as an auditable research
control plane, a claim-evidence ledger, and a value-of-information-inspired
scheduler over a **claim graph** — **not** as AutoML, an HPO scheduler, an
experiment tracker, an AI Scientist, a fully autonomous researcher, or a
guaranteed-optimal planner.

The deterministic CLI + ledger are the **source of truth**. **Claude is the
interface, never the authority** — operate the decision layer faithfully and tie
everything you recommend to a claim.

## Non-negotiables when operating the tool

- **Use `uv` for everything**: `uv run insightflow ...`, `uv run pytest`, etc.
- **Run `uv run insightflow state` before any scheduling recommendation.**
- **Run `uv run insightflow plan` before proposing new runs.** It ranks
  experiments *and research actions* (literature checks, reviewer attacks, theorem
  attempts, claim refinements, etc.). Do not invent a queue, a claim status, or a
  rationale — read it from the plan.
- **Run `uv run insightflow readiness` before judging paper-readiness.** Never
  eyeball whether a claim or the paper is ready: read own-vs-effective status,
  blocked main claims, ranked reviewer attacks, and missing baselines from the
  claim graph.
- **Tie every recommendation to a claim.** Each run/seed/baseline/ablation/research
  action must name the claim it advances and the decision it informs (e.g. "this
  checks external validity for C1", "C1 is *blocked* until C2 is established"), not
  "next in the grid". Optimize evidence acquisition for claim verdicts, not grid
  completion — prefer breadth and decisive baselines over premature replication.
- **Never launch expensive runs without showing the plan and getting approval.**
  Default is advisor mode — recommend, don't execute.

There is an `adaptive-experiment-scheduler` skill (plus `define-claims`,
`interpret-results`, `writeup-from-ledger`) in `skills/` and a
`guard_expensive_runs.py` PreToolUse hook in `.claude/hooks/` that enforce these
habits. The same actions — including `readiness` — are exposed as **MCP tools** via
`insightflow-mcp` (`uv sync --extra mcp`).

## The claim graph (the core abstraction)

Claims have a **type** (`main`, `empirical`, `mechanism`, `efficiency`,
`robustness`, `theory`, `limitation`, `negative`, `auxiliary`), an importance, a
`reviewer_risk`, optional `depends_on` subclaims, and free-text
`evidence_requirements`. Status is one of `unknown`, `needs_more_evidence`, `weak`,
`supported`, `refuted`, or **`blocked`** (own evidence is fine but a `depends_on`
subclaim is unmet). The scheduler and `readiness` reason over this graph, not a flat
list of runs.

## When developing the codebase

- Run the dev checks before claiming done: `bash scripts/dev_check.sh`
  (= `uv sync` + `uv run ruff check .` + `uv run mypy src` + `uv run pytest`).
  The suite is 26 source modules,  passing tests, ruff + mypy clean — keep it so.
- Keep scoring **deterministic**: the same ledger + policy must yield the same
  plan. Tests in `tests/test_scheduler.py` and `tests/test_scoring.py` enforce
  this and would fail if the scheduler degraded into a trivial cost sorter.
- **Be honest in code and docs.** The novelty is the integration + the objective,
  not new math, and not global optimality. The default scorer is a myopic one-step
  approximate EVI per unit cost; the heuristic confidence is a ranking signal, not
  a probability; only the opt-in `bayes` mode is a calibrated probability (measured
  ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`)). Do not inflate these claims.
- Architecture: `schemas.py` (models incl. the claim graph) → `config.py`/`ledger.py`
  (state) → `scoring.py`/`bayes.py` (terms) → `seed_policy.py` / `partial.py` →
  `scheduler.py` (plan) → `readiness.py` / `actions.py` (claim-graph readiness +
  research actions) → `reports.py` / `explain.py` (output) → `cli.py`. Simulator +
  benchmark live in `simulator.py` / `benchmark.py`; replay in `replay.py`;
  importers in `wandb_importer.py` / `importers.py`; agent surface in
  `mcp_server.py`.

## Quick command reference

```bash
uv run insightflow demo --force      # toy project ready to plan
uv run insightflow state             # current evidence + claim table
uv run insightflow plan              # ranked queue (experiments + research actions); writes reports/
uv run insightflow readiness         # paper-readiness over the claim graph (own vs effective status)
uv run insightflow explain --plan ID # scoring breakdown + trade-offs
uv run insightflow benchmark --steps 20
uv run insightflow benchmark --all-scenarios   # 7 scenarios + ablations vs oracle
uv run insightflow import-wandb --entity E --project P --metric accuracy
uv run insightflow log-result --experiment-id E --metric accuracy=0.72 --status completed
uv run insightflow validate
```

Add `--format json` to `state`/`plan`/`readiness`/`benchmark`/`validate` for machine
output. Use `-C/--project-dir` (or `$INSIGHTFLOW_HOME`) to point at a project
directory.

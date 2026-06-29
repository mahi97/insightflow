# InsightFlow

**Adaptive experiment scheduler for ML research that optimizes time-to-insight.**

InsightFlow answers one question: *which experiment, seed, baseline, or ablation should you run next — and which should you skip — to decide your research claims as fast as possible under cost and uncertainty?*

It is CLI-first and agent-native. The CLI and ledger (SQLite + JSONL) are the source of truth. v0.1 is **advisor mode**: InsightFlow recommends; humans launch.

---

## What InsightFlow is

- An **adaptive evidence-acquisition scheduler** over explicitly declared research claims.
- A **decision-making tool** that tells you when you have enough evidence to commit to a claim (supported, refuted, or still uncertain), and which experiment next advances that decision the most.
- **CLI-first and agent-native**: every command reads or writes the ledger; `--format json` makes every output machine-readable for agents and scripts.
- A **complement** to W&B, MLflow, and similar trackers — it uses results they record and tells you what to run next.

## What InsightFlow is NOT

- **Not AutoML or hyperparameter optimization.** It does not tune configurations; it schedules across configurations you define.
- **Not an experiment tracker.** It does not replace W&B or MLflow. Use those to log metrics; use InsightFlow to decide what to run.
- **Not a cluster job launcher.** It can run experiments *locally* (`insightflow run --execute`), but Slurm/Ray submission is on the roadmap — InsightFlow recommends; you (or a launcher) run on the cluster.
- **Not a Bayesian inference engine.** Claim confidence is a transparent deterministic heuristic, not a calibrated Bayesian posterior. Treat it as a ranking signal (see [docs/concepts.md](docs/concepts.md) when published).

---

## Installation

Requires Python 3.10+. InsightFlow uses [uv](https://docs.astral.sh/uv/) for all commands.

```bash
# Install uv if you don't have it
curl -Lsf https://astral.sh/uv/install.sh | sh

# Clone and install (editable, with dev deps)
git clone https://github.com/mahi97/insightflow
cd insightflow
uv sync

# Optional: W&B import support
uv sync --extra wandb

# Verify
uv run insightflow --version
```

The `insightflow` command and its alias `insight` are both available after `uv sync`.

---

## Quick demo

```bash
# Create a toy project (configs + seeded results), ready to plan
uv run insightflow demo --force -C /tmp/my_demo

# See what evidence exists and what claims look like
uv run insightflow state -C /tmp/my_demo

# Get a ranked plan: what to run, postpone, and avoid
uv run insightflow plan -C /tmp/my_demo

# Explain the scoring trade-offs for the latest plan
uv run insightflow explain -C /tmp/my_demo

# Run one step through the simulator and replan
uv run insightflow simulate-step -C /tmp/my_demo
uv run insightflow plan -C /tmp/my_demo
```

### What a plan looks like

After running `demo` and `plan` on the toy project, the top recommendation is:

```
Top recommendation:
  launch method_a / svhn / default / seed=0.
  Reason: Affects C1, C2; covers a new, unobserved condition (breadth over replication);
  dominant factor: uncertainty reduction; score=1.581.

Postpone:
  method_a / svhn / default / seed=1.
  Reason: extra seed of a condition already in the immediate queue; do breadth first.
```

InsightFlow picks a new dataset (svhn) over an extra seed of a dataset already seen (cifar10), because generality evidence is the binding constraint for claim C1. Seeds of svhn are postponed — only one slot per condition enters the immediate queue to enforce breadth-first exploration.

---

## How it works

### Scoring objective

InsightFlow ranks every candidate action with a deterministic heuristic:

```
priority(action) =
    ( w_dv * decision_value
    + w_unc * uncertainty_reduction
    + w_dep * dependency_unlock
    + w_rev * reviewer_risk_reduction
    + w_seed * seed_value
    - w_red * redundancy_penalty
    - w_prp * premature_replication_penalty )
  / ( expected_time + lambda * expected_cost )
```

All weights and `lambda` are set in `configs/policy.yaml` and can be tuned. Every term is stored on the plan action so `explain` can show exactly why an action ranked where it did.

### Action types

Each pending experiment is classified as one of:

- **launch** — new condition (dataset x method pair) not yet observed; breadth-expanding.
- **add_seed** — condition already observed; replication run.
- **launch_baseline** — a missing baseline that prevents computing an effect for an observed condition.
- **postpone** — above avoidance threshold but below queue threshold, or blocked by dependencies.
- **avoid** — dominated or redundant under current evidence.

### Claim confidence

Claim confidence is computed from evidence breadth (fraction of conditions observed) and seed sufficiency (average seeds per condition vs. required seeds). It is a **transparent heuristic**, not a calibrated Bayesian posterior. A claim is marked `supported` or `refuted` only when breadth >= 60% of its conditions are observed and the effect clears the decision boundary with margin. Otherwise it is `weak` or `needs_more_evidence`.

### Benchmark

On the synthetic breadth-vs-replication project (3 synthetic projects, 18 grid cells each):

| policy | decided@ | cost@decision |
|---|---|---|
| oracle | 4.0 | 3.8 |
| **insightflow** | **5.0** | **4.4** |
| all_tasks_first | 5.0 | 4.8 |
| random | 6.0 | 5.8 |
| grid | 11.0 | 11.2 |
| all_seeds_first | 11.0 | 11.2 |

InsightFlow reaches the correct research decision in ~5 runs vs. ~11 for grid / all-seeds-first, with an oracle lower bound of ~4. Run it yourself:

```bash
uv run insightflow benchmark --steps 20 --projects 3
```

---

## Project configuration

An InsightFlow project lives in a directory with:

```
configs/
  claims.yaml       # what you want to prove
  experiments.yaml  # all runs and their claim links
  policy.yaml       # scoring weights (optional, defaults provided)
  resources.yaml    # budget constraints (optional)
.insightflow/       # SQLite ledger + JSONL decision log (managed by InsightFlow)
reports/            # auto-written: state.md, plan_latest.md, claim_confidence.md, benchmark.md
```

### claims.yaml

```yaml
claims:
- id: C1
  statement: method_a improves accuracy over baseline_a, and this generalizes across
    datasets (external validity).
  importance: high          # high | medium | low
  target_metric: accuracy
  desired_direction: higher # higher | lower
  minimum_effect_size: 0.02
  required_seeds: 3
  reviewer_risk: 0.7        # 0–1; high means a reviewer will attack this if unsubstantiated
  notes: Main paper claim. Generality across datasets is the key uncertainty.
- id: C2
  statement: method_a is also more compute-efficient than baseline_a.
  importance: medium
  target_metric: accuracy
  minimum_effect_size: 0.01
  required_seeds: 2
  reviewer_risk: 0.3
```

### experiments.yaml (excerpt)

```yaml
experiments:
- id: method_a_cifar10_s0
  method: method_a
  baseline: baseline_a
  dataset: cifar10
  condition: default
  seed: 0
  claim_links: [C1, C2]       # which claims this run provides evidence for
  expected_cost: 1.0           # arbitrary units (GPU-hours, dollars, etc.)
  expected_time: 1.0
  resource_type: gpu
  tags: [method]
  command: python train.py --method method_a --dataset cifar10 --seed 0

- id: baseline_a_cifar10_s0
  method: baseline_a
  dataset: cifar10
  condition: default
  seed: 0
  claim_links: [C1]
  expected_cost: 0.8
  expected_time: 0.8
  resource_type: gpu
  tags: [baseline]
  command: python train.py --method baseline_a --dataset cifar10 --seed 0
```

---

## CLI reference

All commands use `uv run insightflow` (alias: `uv run insight`).

### Global options

| option | description |
|---|---|
| `-C, --project-dir PATH` | Project directory (default: `$INSIGHTFLOW_HOME` or cwd) |
| `--format md\|json` | Output format; `json` is machine-readable for agents |
| `--version` | Show version and exit |

### Commands

#### `init`

Initialize a project: write starter configs and create the ledger.

```bash
uv run insightflow init [-C DIR] [--force]
```

`--force` reinitializes if a project already exists.

#### `validate`

Validate configs for missing IDs, bad claim links, impossible costs, and duplicates.

```bash
uv run insightflow validate [-C DIR] [--format md|json]
```

Exits with code 1 if issues are found (useful in CI).

#### `state`

Show current state: completed, pending, running experiments, and the claim confidence table. Writes `reports/state.md`.

```bash
uv run insightflow state [-C DIR] [--format md|json]
```

#### `plan`

Produce a ranked plan with an immediate queue, postponed actions, avoided actions, warnings, and a claim-confidence table. Saves the plan to the ledger and writes `reports/plan_latest.md` and `reports/claim_confidence.md`.

```bash
uv run insightflow plan [-C DIR] [--format md|json]
```

#### `explain`

Explain a plan's scoring breakdown and the trade-offs it weighed. Shows per-action term tables (decision value, uncertainty reduction, dependency unlock, etc.).

```bash
uv run insightflow explain [--plan PLAN_ID] [-C DIR]
```

`--plan` defaults to the latest plan.

#### `demo`

Create a complete toy project (configs + seeded runs) ready to plan, with no real experiments needed.

```bash
uv run insightflow demo [--force] [-C DIR]
```

#### `simulate-step`

Run the top recommended launch action through the built-in synthetic simulator and record the result in the ledger. Useful for testing without a real ML pipeline.

```bash
uv run insightflow simulate-step [-C DIR]
```

#### `benchmark`

Benchmark InsightFlow against baseline scheduling policies (grid, all-seeds-first, random, oracle, etc.) on synthetic projects.

```bash
uv run insightflow benchmark [--steps N] [--projects N] [-C DIR] [--format md|json]
```

Writes `reports/benchmark.md`.

#### `import-wandb`

Import runs from a Weights & Biases project into the ledger. Requires `wandb` optional dependency (`uv sync --extra wandb`). Degrades gracefully (mocked in tests) if W&B is not installed.

```bash
uv run insightflow import-wandb \
  --entity MY_TEAM \
  --project my-project \
  --metric accuracy \
  [--limit 200] \
  [-C DIR]
```

After importing, link experiments to claims in `configs/experiments.yaml`, then run `plan`.

#### `log-result`

Record a run result manually (e.g., from a script that does not use W&B).

```bash
uv run insightflow log-result \
  --experiment-id method_a_cifar10_s0 \
  --metric accuracy=0.873 \
  --metric loss=0.41 \
  --status completed \
  [--seed 0] \
  [--cost 1.2] \
  [--wall-time 3600] \
  [-C DIR]
```

`--metric` is repeatable. `--status` accepts: `completed`, `failed`, `running`.

#### `run` (local launcher)

Run an experiment's `command` locally and record the result. Dry-run by default;
pass `--execute` to actually launch. The command must print a JSON metrics line
(e.g. `{"accuracy": 0.81}`) or write one to `$INSIGHTFLOW_METRICS_FILE`.

```bash
uv run insightflow run [--experiment-id ID] [--execute] [-C DIR]
```

#### `import-csv` / `import-mlflow`

Import runs from a local CSV/JSONL file, or from an MLflow experiment (MLflow is
an optional dependency; degrades gracefully).

```bash
uv run insightflow import-csv --path runs.csv --metric accuracy [-C DIR]
uv run insightflow import-mlflow --experiment-name my-exp --metric accuracy \
  [--tracking-uri http://localhost:5000] [--limit 200] [-C DIR]
```

#### `replay` (offline evaluation)

Counterfactually replay a project's already-known results and report whether
InsightFlow would have reached the full-history decision in fewer runs.

```bash
uv run insightflow replay [-C DIR] [--format json]
```

#### `benchmark --all-scenarios`

Run all six task scenarios (breadth, expensive-branch, dependency-unlock,
reviewer-baseline, noisy-seeds, refuted) and report runs/compute saved plus a
robustness summary vs the oracle.

```bash
uv run insightflow benchmark --all-scenarios [--projects N]
```

> **Bayesian mode (opt-in).** Set `confidence_model: bayes` in `configs/policy.yaml`
> for a calibrated value-of-information scorer (ECE 0.0119); see
> [docs/concepts.md](docs/concepts.md).

---

## W&B import

```bash
# Install the optional dependency
uv sync --extra wandb

# Import up to 200 runs, pulling the 'val_accuracy' metric
uv run insightflow import-wandb \
  --entity my-team \
  --project cifar-experiments \
  --metric val_accuracy \
  --limit 200

# Then link the imported experiments to claims in configs/experiments.yaml
# and replan:
uv run insightflow plan
```

See [docs/wandb.md](docs/wandb.md) when available for the full import/linking workflow.

---

## Claude Code and agent workflow

InsightFlow is designed to be driven by a Claude Code agent following the rules in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).

The `skills/adaptive-experiment-scheduler` skill teaches Claude Code the correct workflow:

1. Always call `uv run insightflow state` before making any scheduling recommendation — never invent state.
2. Always call `uv run insightflow plan` before proposing new runs.
3. Use `uv run insightflow explain --plan <id>` to justify recommendations in terms of claims and decisions.
4. Never launch expensive runs without showing the plan and getting human approval.
5. Record results with `log-result` or `import-wandb`; do not hand-edit `.insightflow/`.

A `guard_expensive_runs.py` PreToolUse hook in `.claude/hooks/` enforces that expensive runs are not launched without plan review.

Typical agent loop:

```bash
uv run insightflow state             # what do we know?
uv run insightflow plan              # what to run next, and why?
uv run insightflow explain           # trade-off breakdown
# (human approves) → run experiments → record results:
uv run insightflow log-result --experiment-id E --metric accuracy=0.73 --status completed
uv run insightflow plan              # replan with new evidence
```

For full agent operating rules, see [AGENTS.md](AGENTS.md). For Claude Code-specific guidance, see [CLAUDE.md](CLAUDE.md).

---

## Current limitations (v0.2)

Built in v0.2: a calibrated Bayesian/value-of-information scorer (opt-in),
freeze-thaw learning-curve extrapolation for partial runs, a local launcher,
CSV/JSONL/MLflow importers, and offline replay. The following are still **not
built**:

- **Server / FastAPI / dashboard**: no web UI; CLI only.
- **MCP tool**: agents use the CLI and the Claude Code plugin; a standalone MCP
  server is planned.
- **Cluster launchers (Slurm / Ray) + live monitoring**: runs locally
  (`insightflow run`) or you launch on the cluster; cluster submission/polling is
  planned.
- **Multi-user lab mode**: single-project, single-user.
Documentation (`docs/`): [install_and_use.md](docs/install_and_use.md),
[architecture.md](docs/architecture.md), [concepts.md](docs/concepts.md),
[scheduling_policy.md](docs/scheduling_policy.md), [wandb.md](docs/wandb.md),
[agent_workflow.md](docs/agent_workflow.md),
[agent_driven_project.md](docs/agent_driven_project.md), and
[roadmap.md](docs/roadmap.md).

Install as a Claude Code plugin (skills + guard hook + `/insightflow-*` commands):
`claude plugin marketplace add mahi97/insightflow` then
`claude plugin install insightflow@insightflow`. See
[docs/install_and_use.md](docs/install_and_use.md).

Known honesty constraints:

- Claim confidence is a **transparent heuristic**, not a calibrated Bayesian posterior. Do not treat confidence values as probabilities.
- InsightFlow does not verify that your `command:` fields actually run correctly — it only schedules and records.

---

## Development

```bash
uv sync                            # install all deps including dev
bash scripts/dev_check.sh          # ruff + mypy + pytest (all must pass before PR)
uv run pytest                      # tests only
uv run ruff check .                # linting
uv run mypy src                    # type checking
```

Architecture layers: `schemas.py` (models) -> `config.py` / `ledger.py` (state) -> `scoring.py` (terms) -> `seed_policy.py` / `partial.py` -> `scheduler.py` (plan) -> `reports.py` / `explain.py` (output) -> `cli.py`.

---

## License

Apache 2.0. See [LICENSE](LICENSE).

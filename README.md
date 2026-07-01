# InsightFlow

**InsightFlow is a claim-centered research decision layer for AI-assisted ML research.** It helps
researchers and coding agents decide which evidence to acquire next, when to stop, what to postpone,
what to avoid, and which claims are currently supported, refuted, weak, or still uncertain.

Concretely, it is:

- an **auditable research control plane** — a deterministic CLI + ledger (SQLite + JSONL) that is the
  single source of truth for what you know and what to do next;
- a **claim-evidence ledger** — every result is tied to falsifiable paper claims, and every claim
  carries an explicit, inspectable status;
- a **value-of-information-inspired scheduler** — it ranks the next experiment, seed, baseline,
  ablation, or *research action* by how much it advances a claim verdict per unit cost;
- a **practical decision layer for human and AI research agents** — CLI-first and agent-native, with
  `--format json` on every command and an MCP server so agents can drive it.

It is **advisor mode** by default: InsightFlow recommends and reports; humans (or a launcher) run.

> **Honesty is the project's core principle.** The novelty is the *integration* and the *objective*
> (claim-level state, evidence requirements, reviewer-risk-aware scheduling, a claim graph, a
> ledger-backed agent interface, replay evaluation, and paper-readiness reporting) — **not new math**.
> The scheduler is a myopic one-step approximate expected-value-of-information per unit cost, not a
> multi-step optimal planner. See [docs/limitations.md](docs/limitations.md) and
> [docs/paper_positioning.md](docs/paper_positioning.md).

---

## What InsightFlow is

- A **claim-centered research decision layer**: it manages a *claim graph* (main, empirical,
  mechanism, efficiency, robustness, theory, limitation, negative, auxiliary claims) and decides which
  evidence to acquire to move each claim toward a verdict.
- A **decision-making tool** that tells you when you have enough evidence to commit to a claim
  (supported, refuted, weak, or still uncertain), which experiment or research action next advances
  that decision the most, and **when a paper is ready** (`insightflow readiness`).
- An **auditable control plane and claim-evidence ledger**: every command reads or writes the ledger;
  `--format json` makes every output machine-readable for agents and scripts; configs are
  `extra='forbid'`, so a YAML typo is caught, not silently ignored.
- A **complement** to W&B, MLflow, and similar trackers — it uses results they record and tells you
  what to run next.

## What InsightFlow is NOT

- **Not an AutoML system or HPO scheduler.** It does not tune configurations or allocate compute to
  arms/configs; it schedules across the conditions you define to decide *claims*.
- **Not an experiment tracker.** It does not replace W&B or MLflow. Use those to log metrics; use
  InsightFlow to decide what to run and whether your claims hold.
- **Not an AI Scientist or a fully autonomous researcher.** It does not write your paper or run your
  lab unattended. The agent is the *interface*; the CLI/ledger is the *authority*.
- **Not a guaranteed-optimal planner.** The value-of-information scorer is a *myopic one-step
  approximate EVI per unit cost* (deterministic Gauss–Hermite quadrature), not a multi-step optimal
  plan. Optimality is not claimed.
- **Not a cluster job launcher.** It can run experiments *locally* (`insightflow run --execute`), but
  Slurm/Ray submission is on the roadmap — InsightFlow recommends; you (or a launcher) run on the
  cluster.
- **Not (necessarily) a Bayesian inference engine.** The default heuristic scorer is a transparent
  *ranking* signal, **not** a probability. The opt-in `bayes` mode *is* a calibrated probability
  (measured ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) over 200k draws) under stated assumptions. See
  [docs/concepts.md](docs/concepts.md).

## Why not just Claude Code skills?

A capable coding agent can already read your results and suggest the next run. The problem is that an
agent's judgment is *unauditable, non-reproducible, and easy to anchor on the grid*: it will happily
"prove" a cross-dataset claim from one well-replicated dataset, forget a missing baseline, or rerun
seeds nobody needs. InsightFlow gives the agent a deterministic decision layer to stand on — a claim
graph, an evidence ledger, explicit reviewer-risk and breadth-vs-replication handling, paper-readiness
reporting, and replay-based evaluation — so its recommendations are tied to claims and reproducible
rather than vibes. The Claude Code plugin (skills + commands) and the MCP server are how the agent
*talks to* that layer; they are not a replacement for it. See
[docs/paper_positioning.md](docs/paper_positioning.md) and
[docs/related_work.md](docs/related_work.md).

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

# Get a ranked plan: what to run, postpone, and avoid (experiments AND research actions)
uv run insightflow plan -C /tmp/my_demo

# Explain the scoring trade-offs for the latest plan
uv run insightflow explain -C /tmp/my_demo

# Assess paper-readiness over the claim graph: which claims are
# supported/refuted/weak/blocked, the most dangerous reviewer attacks,
# and the next research actions to take
uv run insightflow readiness -C /tmp/my_demo

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

### The claim graph

Claims are the unit of work. Each claim has a **type** (`main`, `empirical`, `mechanism`, `efficiency`,
`robustness`, `theory`, `limitation`, `negative`, `auxiliary`), an importance and reviewer-risk, and
optional structure: `depends_on` (subclaims a claim needs before it is defensible), `blocks`, and
free-text `evidence_requirements`. A claim's `status` is one of `unknown`, `needs_more_evidence`,
`weak`, `supported`, `refuted`, or **`blocked`** (its own evidence is fine but a `depends_on` subclaim
is unmet). The scheduler and the readiness report reason over this graph, not just a flat list of runs.

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

Claim confidence is computed from evidence breadth (fraction of conditions observed) and seed
sufficiency (average seeds per condition vs. required seeds). The default `heuristic` mode is a
**transparent ranking signal**, *not* a probability: a claim is marked `supported` or `refuted` only
when breadth >= 60% of its conditions are observed and the effect clears the decision boundary with
margin; otherwise it is `weak` or `needs_more_evidence`. The opt-in `bayes` mode replaces this with a
**calibrated probability** (measured ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) over 200k draws) under stated assumptions — see
[docs/concepts.md](docs/concepts.md). Neither mode claims new math or global optimality.

### Research actions (beyond runs)

A claim-centered planner recommends more than training runs. InsightFlow auto-generates — and lets you
predefine in `actions.yaml` — **research actions** such as `literature_search`, `reviewer_attack`,
`theorem_attempt`, `claim_refinement`, `baseline_design`, `dataset_addition`, `run_ablation`, and
`write_limitations`. Each carries a human/agent `instruction` (not always a command) and is scored
against experiments on the *same* value-per-unit-cost basis, so the plan can tell you that the highest
value next step is "adversarially attack C1, its evidence is thin" rather than another GPU run.

### Paper readiness

`insightflow readiness` assesses the whole claim graph for submission. For every claim it reports its
**own status** (from its own evidence) versus its **effective status** (after accounting for unmet
`depends_on` subclaims — this is how a `main` claim becomes `blocked`), the ranked **reviewer attacks**
currently open (weighted by reviewer-risk x importance), **missing baselines**, **thin generality**,
insufficient seeds, and the recommended **next research actions**. A project is only `paper_ready` when
every main / high-importance claim is *effectively* supported.

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

Across the full suite of **7 synthetic scenarios** (`breadth`, `expensive_branch`, `dependency_unlock`,
`reviewer_baseline`, `noisy_seeds`, `refuted`, `mixed_multi_claim`), InsightFlow reaches the decision in
a mean of **~5.4 runs**, with a worst case of **1.25x the oracle** and **7/7 scenarios solved** — the
best among non-oracle policies, saving **~54% of runs vs grid** on average. **Ablations** (each disables
one component: `ablate_reviewer_risk`, `ablate_breadth_penalty`, `ablate_cost`, `uncertainty_only`) show
the components matter — `uncertainty_only` fails the multi-claim scenario. A separate
agent-in-sandbox eval (real Claude/Sonnet agents driving the CLI vs an unaided agent) saw **50–69%
compute saved with no loss in correctness** on the tasks tested (small n; illustrative). The benchmark
is built from 26 source modules with  passing tests, ruff + mypy clean. Full methodology and the
honest caveats are in [docs/evaluation.md](docs/evaluation.md). Run it yourself:

```bash
uv run insightflow benchmark --steps 20 --projects 3   # single-project table above
uv run insightflow benchmark --all-scenarios           # the 7-scenario suite + ablations
```

---

## Project configuration

An InsightFlow project lives in a directory with:

```
configs/
  claims.yaml       # the claim graph: what you want to prove, and how claims depend on each other
  experiments.yaml  # all runs and their claim links
  actions.yaml      # optional user-defined research actions (auto-generated ones need no file)
  policy.yaml       # scoring weights + confidence_model (optional, defaults provided)
  resources.yaml    # budget constraints (optional)
.insightflow/       # SQLite ledger + JSONL decision log (managed by InsightFlow)
reports/            # auto-written: state.md, plan_latest.md, claim_confidence.md,
                    #   readiness.md, benchmark.md
```

### claims.yaml

```yaml
claims:
- id: C1
  statement: method_a improves accuracy over baseline_a, and this generalizes across
    datasets (external validity).
  type: main                # main|empirical|mechanism|efficiency|robustness|theory|...
  importance: high          # high | medium | low (or a float in [0,1])
  target_metric: accuracy
  desired_direction: higher # higher | lower
  minimum_effect_size: 0.02
  required_seeds: 3
  reviewer_risk: 0.7        # 0–1; high means a reviewer will attack this if unsubstantiated
  depends_on: [C2]          # claim graph: C1 is only defensible once C2 is supported
  evidence_requirements:    # free-text requirements the readiness report can surface
    - effect holds on >= 3 datasets with matched baselines
  notes: Main paper claim. Generality across datasets is the key uncertainty.
- id: C2
  statement: method_a is also more compute-efficient than baseline_a.
  type: efficiency
  importance: medium
  target_metric: accuracy
  minimum_effect_size: 0.01
  required_seeds: 2
  reviewer_risk: 0.3
```

Unknown keys are rejected (`extra='forbid'`), so a misspelled field is a hard error, not a silent
no-op. `depends_on` is what lets a `main` claim become **`blocked`** in `readiness` when a supporting
subclaim is not yet established.

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

Produce a ranked plan over **experiments and research actions** with an immediate queue, postponed
actions, avoided actions, warnings, and a claim-confidence table. Research actions (auto-generated from
the claim graph plus any in `actions.yaml`) are scored against experiments on the same value-per-cost
basis. Saves the plan to the ledger and writes `reports/plan_latest.md` and
`reports/claim_confidence.md`.

```bash
uv run insightflow plan [-C DIR] [--format md|json]
```

#### `readiness`

Assess paper/project readiness over the **claim graph**: each claim's own vs. effective status, blocked
main claims, ranked reviewer attacks (by reviewer-risk x importance), missing baselines, thin
generality, and the next research actions. Writes `reports/readiness.md`.

```bash
uv run insightflow readiness [-C DIR] [--format md|json]
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

Validated on **real W&B logs**: on 144 runs from a real BBOB study InsightFlow
reaches the "Muon_ES beats Open_ES" verdict in **58 runs vs the actual 115 (−49.6%)**;
on 447 real GLUE runs it correctly returns a borderline GFA-vs-LoRA claim as *weak*
rather than overclaiming. See [docs/real_data_evaluation.md](docs/real_data_evaluation.md)
and [`examples/muon_bbob_real`](examples/muon_bbob_real) /
[`examples/gfa_vs_lora_real`](examples/gfa_vs_lora_real).

#### `benchmark --all-scenarios`

Run all seven task scenarios (`breadth`, `expensive_branch`, `dependency_unlock`,
`reviewer_baseline`, `noisy_seeds`, `refuted`, `mixed_multi_claim`) against ~12 policies including the
ablations and the oracle, and report runs/compute saved plus a robustness summary vs the oracle. See
[docs/evaluation.md](docs/evaluation.md).

```bash
uv run insightflow benchmark --all-scenarios [--projects N]
```

> **Bayesian mode (opt-in).** Set `confidence_model: bayes` in `configs/policy.yaml`
> for a calibrated value-of-information scorer (ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`)); see
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

InsightFlow is designed to be driven by a Claude Code agent following the rules in [AGENTS.md](AGENTS.md)
and [CLAUDE.md](CLAUDE.md). **The agent is the interface, not the authority**: the deterministic CLI and
ledger decide; the agent reads them, ties every recommendation to a claim, and never invents state.

The `skills/adaptive-experiment-scheduler` skill (plus `define-claims`, `interpret-results`, and
`writeup-from-ledger`) teaches Claude Code the correct workflow:

1. Always call `uv run insightflow state` before making any scheduling recommendation — never invent state.
2. Always call `uv run insightflow plan` before proposing new runs (it ranks experiments *and* research actions).
3. Always call `uv run insightflow readiness` before judging whether the paper/claims are ready — do not eyeball it.
4. Use `uv run insightflow explain --plan <id>` to justify recommendations, and **tie every recommendation to a claim** (which claim it affects and the decision it informs).
5. Never launch expensive runs without showing the plan and getting human approval.
6. Record results with `log-result` or `import-wandb`; do not hand-edit `.insightflow/`.

A `guard_expensive_runs.py` PreToolUse hook in `.claude/hooks/` enforces that expensive runs are not
launched without plan review. The same actions are available to any MCP agent via the **MCP server**
(`uv sync --extra mcp` then `insightflow-mcp`), which exposes `state`, `plan`, `explain`, `validate`,
`log-result`, `replay`, and **`readiness`** as tools.

Typical agent loop:

```bash
uv run insightflow state             # what do we know?
uv run insightflow plan              # what to run/research next, and why?
uv run insightflow explain           # trade-off breakdown (tie it to a claim)
uv run insightflow readiness         # are the claims paper-ready? what's blocked/attacked?
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
- **MCP server**: available (opt-in) — `uv sync --extra mcp` then `insightflow-mcp`
  exposes the tools to any MCP agent. A hosted/remote server is still future.
- **Cluster launchers (Slurm / Ray) + live monitoring**: runs locally
  (`insightflow run`) or you launch on the cluster; cluster submission/polling is
  planned.
- **Multi-user lab mode**: single-project, single-user.

For the full, honest treatment of what is and is not built, see
[docs/limitations.md](docs/limitations.md).

## Documentation

**Positioning and honesty:** [docs/paper_positioning.md](docs/paper_positioning.md),
[docs/related_work.md](docs/related_work.md), [docs/limitations.md](docs/limitations.md),
[docs/evaluation.md](docs/evaluation.md), [docs/examples.md](docs/examples.md), and the
[`paper/`](paper/) directory (the write-up of the integration and objective).

**Concepts and operation:** [install_and_use.md](docs/install_and_use.md),
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

- The novelty is the **integration and the objective**, not new math, and **not** global optimality —
  the scheduler is a myopic one-step approximate EVI per unit cost.
- In the default `heuristic` mode, claim confidence is a **ranking signal, not a probability**. Only the
  opt-in `bayes` mode produces calibrated probabilities (measured ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) over 200k draws) under its
  stated assumptions.
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

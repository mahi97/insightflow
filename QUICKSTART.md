# InsightFlow Quickstart

A 2-minute walkthrough using the built-in demo. No real experiments required.

---

## Prerequisites

```bash
# Install uv if you don't have it
curl -Lsf https://astral.sh/uv/install.sh | sh

# From the repo root:
uv sync
```

---

## 1. Create a demo project

```bash
uv run insightflow demo --force -C /tmp/demo
```

This writes starter configs and seeds the ledger with 5 completed runs (method_a on cifar10, 3 seeds of the method + 2 baseline seeds). You should see:

```
Demo project created at /tmp/demo
Try: `uv run insightflow state` then `uv run insightflow plan`.
```

---

## 2. Inspect the current state

```bash
uv run insightflow state -C /tmp/demo
```

Look for: the claim confidence table shows C1 at `needs_more_evidence` with only 1 of 3 conditions observed, and C2 with 0 conditions. The pending experiments table lists the datasets not yet run (cifar100, svhn).

---

## 3. Get a ranked plan

```bash
uv run insightflow plan -C /tmp/demo
```

The immediate queue (top 5 actions) and the postponed list both appear. Look for:

- **Top action**: `launch method_a / svhn / default / seed=0` — a new dataset, not an extra seed of cifar10.
- **Postponed**: `method_a / svhn / default / seed=1` — postponed because one slot per condition enters the queue first (breadth before replication).
- **Warnings**: "Generality of claim C1 is unverified: only 33% of its conditions have been observed."

The plan is also written to `reports/plan_latest.md` and `reports/claim_confidence.md`.

---

## 4. Explain the scoring

```bash
uv run insightflow explain -C /tmp/demo
```

This shows the full scoring term breakdown for every action in the latest plan — decision value, uncertainty reduction, dependency unlock, reviewer-risk reduction, redundancy penalty, and premature-replication penalty. Look for: why svhn beats an extra cifar10 seed (higher uncertainty reduction, zero premature-replication penalty).

To explain a specific plan by ID:

```bash
uv run insightflow explain --plan plan_200dc073881d -C /tmp/demo
```

---

## 5. Step the simulator forward and replan

```bash
uv run insightflow simulate-step -C /tmp/demo
uv run insightflow plan -C /tmp/demo
```

`simulate-step` runs the top recommended action through the built-in simulator and records the result in the ledger. After a few steps the claim confidence will shift. Keep repeating until a claim reaches `supported` or `refuted`.

---

## 6. Run the benchmark

```bash
uv run insightflow benchmark --steps 20 --projects 3
```

This runs InsightFlow and several baseline scheduling policies (grid, all-seeds-first, random, oracle) on 3 synthetic projects and prints a comparison table. Look for: InsightFlow decides in ~5 runs vs. ~11 for grid/all-seeds-first; oracle lower bound is ~4. The report is also written to `reports/benchmark.md`.

---

## Use it on your own project

### 1. Initialize

```bash
cd my-research-project
uv run insightflow init
```

This writes starter `configs/claims.yaml`, `configs/experiments.yaml`, `configs/policy.yaml`, and `configs/resources.yaml` and creates the `.insightflow/` ledger.

### 2. Edit configs

Edit `configs/claims.yaml` to describe your research claims:

```yaml
claims:
- id: C1
  statement: My method beats the baseline on ImageNet and generalizes to CIFAR-100.
  importance: high
  target_metric: top1_accuracy
  desired_direction: higher
  minimum_effect_size: 0.01
  required_seeds: 3
  reviewer_risk: 0.8
```

Edit `configs/experiments.yaml` to list every run you might run, with `claim_links` pointing to the claims each run provides evidence for.

### 3. Validate

```bash
uv run insightflow validate
```

Exits with code 0 if configs are valid, code 1 with a list of issues otherwise.

### 4. (Optional) Import from W&B

If you already have runs in Weights & Biases:

```bash
uv sync --extra wandb
uv run insightflow import-wandb \
  --entity my-team \
  --project my-project \
  --metric val_accuracy \
  --limit 200
```

Then link the imported experiments to claims in `configs/experiments.yaml`.

### 5. Plan and record results

```bash
uv run insightflow plan                # what to run next
# ... run the suggested experiment ...
uv run insightflow log-result \
  --experiment-id my_exp_id \
  --metric top1_accuracy=0.843 \
  --status completed
uv run insightflow plan                # replan with the new evidence
```

Repeat until your claims reach `supported` or `refuted` with sufficient evidence breadth.

---

## Key output files

| file | contents |
|---|---|
| `reports/state.md` | Current evidence summary and claim confidence table |
| `reports/plan_latest.md` | Latest ranked plan with rationale |
| `reports/claim_confidence.md` | Claim confidence table only |
| `reports/benchmark.md` | Benchmark comparison (written by `benchmark` command) |

---

## Further reading

- [README.md](README.md) — full CLI reference, config schema, agent workflow, and limitations
- [AGENTS.md](AGENTS.md) — rules for operating InsightFlow as an AI agent
- [CLAUDE.md](CLAUDE.md) — Claude Code-specific guidance
- `.claude/skills/adaptive-experiment-scheduler/` — Claude Code skill for the adaptive scheduling workflow

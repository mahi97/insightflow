---
description: Set up InsightFlow for this repository (draft claims + experiments, no code changes)
argument-hint: "[optional: notes about the paper's claims]"
---

Use the `define-claims` skill. Inspect this repository's training scripts,
config files, sweeps, and any Weights & Biases usage. Then, **without changing
any of my training code**, draft InsightFlow configs:

- `configs/claims.yaml` — the claims this project will assert (target metric,
  minimum effect size, required seeds, importance, reviewer risk).
- `configs/experiments.yaml` — the runnable experiment grid mapped from my
  scripts/sweeps, with baselines, dependencies, and cost/time estimates.

Then run `uv run insightflow validate` and show me a dry `uv run insightflow plan`.
If I already have runs in W&B, propose the `uv run insightflow import-wandb`
command to pull them in. Extra context: $ARGUMENTS

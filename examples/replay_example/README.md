# Offline replay from a CSV of completed runs

This is a turnkey, reproducible example of **replay evaluation on historical
results** — the counterfactual "would InsightFlow have reached the same claim
verdict with fewer runs than the order they were actually run in?" It uses a CSV
of completed runs (no W&B needed), so it mirrors what you'd do on a real finished
project by exporting its runs to CSV (or `import-wandb`).

## Files
- `configs/claims.yaml` — one claim `C1` (method_a improves accuracy over
  baseline_a, generalizing across datasets).
- `configs/experiments.yaml` — the grid (method_a + baseline_a on cifar10 /
  cifar100 / svhn), each linked to `C1`.
- `runs.csv` — 15 completed runs (the `id` column matches the experiment ids),
  ordered depth-first (all cifar10 first) — a realistic but *inefficient* human
  order that reaches generality late.

## Run it

```bash
cp -r examples/replay_example /tmp/replay && cd /tmp/replay   # ledger writes .insightflow/
uv run insightflow init -C .                                 # keeps the provided claims/experiments
uv run insightflow import-csv --path runs.csv --metric accuracy -C .
uv run insightflow replay -C .
```

## Expected result

```
Runs-to-decision by replay policy (lower is better):
  actual         8      # the real depth-first order
  insightflow    5      # InsightFlow's order reaches the SAME verdict 3 runs sooner
  grid           8
  random         7
  cheap_first   10
  seeds_first    7
```

The ground-truth verdict is what the **full** history supports (here, `C1:
supported`). During replay each policy only "sees" the runs it selects, revealing
them until it reaches that verdict. InsightFlow gets there in **5 vs the actual
8** because it covers breadth (method+baseline across datasets) before piling on
same-dataset seeds — establishing generality earlier.

## On your own project

Export your completed runs to a CSV with an `id` column matching your
`experiments.yaml` ids (plus your metric column), or use `uv run insightflow
import-wandb ...`. Then `uv run insightflow replay --format json` gives the
per-policy `runs-to-decision` for a figure. See [docs/evaluation.md](../../docs/evaluation.md).

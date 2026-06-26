# Toy project

A small, self-contained InsightFlow project you can read and copy. It is the same
project `uv run insightflow demo --force` generates (minus the pre-seeded runs).

## Files

- `claims.yaml` — two claims. `C1` is the main claim: *method_a beats baseline_a,
  and this generalizes across datasets (external validity)* — high importance,
  high reviewer risk. `C2` is a secondary efficiency claim.
- `experiments.yaml` — `method_a` and `baseline_a` across `cifar10`, `cifar100`,
  and `svhn`, with several seeds each.
- `resources.yaml` — a 4-GPU pool with a compute budget.

## Try it

From a copy of this directory (so the ledger is written here):

```bash
uv run insightflow init -C examples/toy_project        # or copy these files into your own project
uv run insightflow validate -C examples/toy_project
uv run insightflow plan -C examples/toy_project
```

With no runs yet, the plan recommends breadth across datasets and the missing
baselines. If you record a few CIFAR-10 results:

```bash
uv run insightflow log-result -C examples/toy_project \
  --experiment-id method_a_cifar10_s0 --metric accuracy=0.78 --status completed
uv run insightflow log-result -C examples/toy_project \
  --experiment-id baseline_a_cifar10_s0 --metric accuracy=0.72 --status completed
uv run insightflow plan -C examples/toy_project
```

…the recommendation shifts to checking **external validity** (a new dataset like
`cifar100`/`svhn`) rather than piling on more CIFAR-10 seeds — because generality,
not seed variance, is now the live uncertainty.

> Tip: `uv run insightflow demo --force` does exactly this setup for you, with
> CIFAR-10 already run, so you can see the interesting recommendation immediately.

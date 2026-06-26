"""Example training stub for InsightFlow.

This is the kind of script an experiment's ``command`` field points at. It does
no real training - it just shows the shape InsightFlow expects:

* it takes ``--method``, ``--dataset``, ``--seed`` (and any condition flags),
* it produces a final metric,
* optionally it logs to Weights & Biases so the run can later be imported with
  ``uv run insightflow import-wandb``.

Replace the body with your real training loop. InsightFlow never runs this for
you in v0.1 (advisor mode) - you launch it, then record the result with
``uv run insightflow log-result`` or by importing from W&B.

Run standalone:

    uv run python examples/train_stub.py --method method_a --dataset cifar10 --seed 0
"""

from __future__ import annotations

import argparse
import random


def fake_train(method: str, dataset: str, seed: int, alpha: float) -> dict[str, float]:
    """Deterministic fake metric so the stub is reproducible."""
    rng = random.Random(hash((method, dataset, seed, alpha)) & 0xFFFFFFFF)
    base = {"cifar10": 0.72, "cifar100": 0.55, "svhn": 0.88}.get(dataset, 0.70)
    bonus = 0.05 if method != "baseline" and not method.startswith("baseline") else 0.0
    accuracy = base + bonus + rng.uniform(-0.01, 0.01)
    return {"accuracy": round(accuracy, 4)}


def main() -> None:
    parser = argparse.ArgumentParser(description="InsightFlow training stub")
    parser.add_argument("--method", default="method_a")
    parser.add_argument("--dataset", default="cifar10")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--alpha", type=float, default=0.1, help="example condition flag")
    parser.add_argument("--wandb", action="store_true", help="log to W&B if installed")
    args = parser.parse_args()

    metrics = fake_train(args.method, args.dataset, args.seed, args.alpha)
    print(f"[train_stub] method={args.method} dataset={args.dataset} "
          f"seed={args.seed} alpha={args.alpha} -> {metrics}")
    # Final line is a JSON object of metrics, which `insightflow run` parses.
    import json
    print(json.dumps(metrics))

    if args.wandb:
        try:
            import wandb  # noqa: PLC0415

            run = wandb.init(
                project="insightflow-demo",
                config={
                    "method": args.method,
                    "dataset": args.dataset,
                    "seed": args.seed,
                    "alpha": args.alpha,
                },
            )
            wandb.log(metrics)
            run.finish()
            print("[train_stub] logged to W&B. Import later with `insightflow import-wandb`.")
        except ImportError:
            print("[train_stub] wandb not installed; skipping (uv add wandb to enable).")

    # In a real script you would record the result for InsightFlow, e.g.:
    #   uv run insightflow log-result --experiment-id method_a_cifar10_s0 \
    #       --metric accuracy=<value> --status completed


if __name__ == "__main__":
    main()

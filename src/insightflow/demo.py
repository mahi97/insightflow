"""Toy-project builder used by ``insightflow demo --force``.

It writes a small, self-contained project into ``<project>/configs`` and seeds
the ledger with a few completed CIFAR-10 runs. The result is a state where the
*interesting* decision is external validity (does the method generalize to
CIFAR-100 / SVHN?) rather than seed variance - which is exactly the situation
the scheduler is meant to handle. ``plan`` should then recommend a new condition
over more CIFAR-10 seeds.

This module is a small, justified addition to the spec's module list: it keeps
demo setup (which both writes configs *and* seeds the ledger) out of the CLI.
"""

from __future__ import annotations

from pathlib import Path

from .config import config_dir, write_yaml
from .ledger import Ledger
from .schemas import Experiment, Policy
from .simulator import simulate_result_for

DATASETS = ["cifar10", "cifar100", "svhn"]

# CIFAR-10 runs that already exist (method seeds 0-2, baseline seeds 0-1).
PRERUN_IDS = [
    "method_a_cifar10_s0",
    "method_a_cifar10_s1",
    "method_a_cifar10_s2",
    "baseline_a_cifar10_s0",
    "baseline_a_cifar10_s1",
]

CLAIMS = {
    "claims": [
        {
            "id": "C0",
            "statement": "method_a is a better method than baseline_a for this task family.",
            "type": "main",
            "importance": "critical",
            "reviewer_risk": 0.8,
            "depends_on": ["C1", "C2"],
            "evidence_requirements": [
                "C1 (accuracy generalizes) supported",
                "C2 (efficiency) supported",
            ],
            "notes": "Main paper claim. Decided by its supporting subclaims, not by runs of its own.",
        },
        {
            "id": "C1",
            "statement": "method_a improves accuracy over baseline_a, and this generalizes "
            "across datasets (external validity).",
            "type": "empirical",
            "importance": "high",
            "target_metric": "accuracy",
            "desired_direction": "higher",
            "minimum_effect_size": 0.02,
            "required_seeds": 3,
            "reviewer_risk": 0.7,
            "notes": "Generality across datasets is the key uncertainty.",
        },
        {
            "id": "C2",
            "statement": "method_a is also more compute-efficient than baseline_a.",
            "type": "efficiency",
            "importance": "medium",
            "target_metric": "accuracy",
            "minimum_effect_size": 0.01,
            "required_seeds": 2,
            "reviewer_risk": 0.3,
            "notes": "Secondary claim.",
        },
    ]
}

RESOURCES = {
    "pools": [{"type": "gpu", "count": 4, "cost_per_hour": 2.0}],
    "budget_gpu_hours": 60,
}


def _build_experiments() -> list[dict]:
    exps: list[dict] = []
    base_cost = {"cifar10": 1.0, "cifar100": 1.2, "svhn": 1.1}
    for ds in DATASETS:
        # method_a seeds 0..4
        for s in range(5):
            exps.append(
                {
                    "id": f"method_a_{ds}_s{s}",
                    "method": "method_a",
                    "baseline": "baseline_a",
                    "dataset": ds,
                    "condition": "default",
                    "seed": s,
                    "claim_links": ["C1", "C2"],
                    "expected_cost": base_cost[ds],
                    "expected_time": 1.0,
                    "resource_type": "gpu",
                    "tags": ["method"],
                    "command": f"python train.py --method method_a --dataset {ds} --seed {s}",
                }
            )
        # baseline_a seeds 0..1
        for s in range(2):
            exps.append(
                {
                    "id": f"baseline_a_{ds}_s{s}",
                    "method": "baseline_a",
                    "dataset": ds,
                    "condition": "default",
                    "seed": s,
                    "claim_links": ["C1", "C2"],
                    "expected_cost": base_cost[ds] * 0.8,
                    "expected_time": 0.8,
                    "resource_type": "gpu",
                    "tags": ["baseline"],
                    "command": f"python train.py --method baseline_a --dataset {ds} --seed {s}",
                }
            )
    return exps


def write_demo_configs(project_dir: str | Path) -> None:
    cdir = config_dir(project_dir)
    write_yaml(cdir / "claims.yaml", CLAIMS)
    write_yaml(cdir / "experiments.yaml", {"experiments": _build_experiments()})
    write_yaml(cdir / "resources.yaml", RESOURCES)
    write_yaml(cdir / "policy.yaml", Policy().model_dump())


def setup_demo(project_dir: str | Path, force: bool = False) -> Ledger:
    """Write the toy configs and seed the ledger with completed CIFAR-10 runs."""
    write_demo_configs(project_dir)
    ledger = Ledger(project_dir)
    ledger.initialize(force=force)

    # Seed completed CIFAR-10 runs so the interesting decision is generality.
    prerun = [e for e in _build_experiments() if e["id"] in PRERUN_IDS]
    results = [simulate_result_for(Experiment(**e), project_seed=7) for e in prerun]
    ledger.add_results(results)
    ledger.log_decision({"event": "demo_setup", "seeded_runs": len(results)})
    return ledger

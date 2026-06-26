"""Benchmark harness.

Replays synthetic projects under every policy and reports:

* time to correct decision (runs until all claims are correctly decided),
* cost to correct decision,
* number of runs launched,
* unnecessary runs avoided (vs. running the full grid),
* wrong-decision rate,
* claim-confidence evolution (for InsightFlow).

For v0.1 this is a simplified but *real* approximation: the "correct decision"
oracle is the shared claim-confidence readout, so policies differ only in which
experiments they choose to run. Methodology is documented in the report notes.
"""

from __future__ import annotations

from .simulator import POLICIES, PolicyRun, generate_project, run_policy
from .utils import fmt, mean


def run_benchmark(
    steps: int = 20,
    n_projects: int = 3,
    base_seed: int = 0,
    policies: list[str] | None = None,
) -> dict:
    policy_names = policies or list(POLICIES.keys())

    # Run every policy on the same set of projects.
    per_policy: dict[str, list[PolicyRun]] = {p: [] for p in policy_names}
    grid_size = 0
    for i in range(max(1, n_projects)):
        project = generate_project(seed=base_seed + i, name=f"proj{i}")
        grid_size = len(project.experiments)
        for p in policy_names:
            per_policy[p].append(run_policy(project, p, steps))

    rows = []
    raw: dict[str, dict] = {}
    for p in policy_names:
        runs = per_policy[p]
        solved = [r for r in runs if r.correct]
        decided_steps = [r.decided_step for r in solved if r.decided_step is not None]
        costs = [r.cost_at_decision for r in solved if r.cost_at_decision is not None]
        avoided = [grid_size - r.runs_launched for r in solved]
        wrong_rate = mean([1.0 if r.wrong_decisions else 0.0 for r in runs])

        decided_disp = fmt(mean(decided_steps), 1) if decided_steps else "-"
        cost_disp = fmt(mean(costs), 1) if costs else "-"
        avoided_disp = fmt(mean(avoided), 1) if avoided else "-"
        rows.append(
            [
                p,
                decided_disp,
                cost_disp,
                fmt(mean([r.runs_launched for r in runs]), 1),
                avoided_disp,
                fmt(wrong_rate, 2),
                f"{len(solved)}/{len(runs)}",
            ]
        )
        raw[p] = {
            "decided_steps": decided_steps,
            "costs": costs,
            "runs_launched": [r.runs_launched for r in runs],
            "solved": len(solved),
            "total": len(runs),
        }

    # Sort so the fastest-to-decision policies float to the top (unsolved last).
    def sort_key(row: list) -> tuple:
        return (0, float(row[1])) if row[1] != "-" else (1, 0.0)

    rows.sort(key=sort_key)

    insight_runs = per_policy.get("insightflow", [])
    evolution = insight_runs[0].confidence_evolution if insight_runs else []

    notes = [
        f"Projects: {max(1, n_projects)} synthetic 'breadth-beats-replication' projects "
        f"(grid size = {grid_size} runs each), max {steps} steps per policy.",
        "Lower 'decided@' and 'cost@decision' are better. 'avoided' = grid_size - runs_launched.",
        "The correct decision is reached when InsightFlow's shared confidence readout matches "
        "the hidden ground-truth status of every claim.",
        f"InsightFlow confidence evolution (project 0): {evolution}",
        "InsightFlow should reach the correct decision in fewer runs than grid / all-seeds-first "
        "because it prefers breadth and missing baselines over premature replication.",
    ]

    return {
        "description": "Policy comparison on synthetic research projects.",
        "headers": ["policy", "decided@", "cost@decision", "runs", "avoided", "wrong", "solved"],
        "rows": rows,
        "notes": notes,
        "raw": raw,
    }

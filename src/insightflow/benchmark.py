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

from .simulator import POLICIES, SCENARIOS, PolicyRun, generate_project, run_policy
from .utils import fmt, mean


def _aggregate(runs: list[PolicyRun]) -> dict:
    solved = [r for r in runs if r.correct]
    steps = [r.decided_step for r in solved if r.decided_step is not None]
    costs = [r.cost_at_decision for r in solved if r.cost_at_decision is not None]
    return {
        "decided": mean(steps) if steps else None,
        "cost": mean(costs) if costs else None,
        "solved": len(solved),
        "total": len(runs),
    }


def _pct_saved(insight: float | None, baseline: float | None) -> float | None:
    if insight is None or baseline is None or baseline <= 0:
        return None
    return round(100.0 * (baseline - insight) / baseline, 1)


NAIVE = ["grid", "all_seeds_first", "all_tasks_first", "random", "cheap_first",
         "fastest_first", "baseline_first"]
ABLATIONS = ["ablate_reviewer_risk", "ablate_breadth_penalty", "ablate_cost",
             "ablate_seed_policy", "uncertainty_only"]


def run_scenarios(
    steps: int = 40,
    n_projects: int = 5,
    base_seed: int = 0,
    scenarios: list[str] | None = None,
) -> dict:
    """Run every policy on every scenario and quantify InsightFlow's gains.

    For each scenario we report runs-to-correct-decision and cost-to-correct-decision
    for InsightFlow vs the baselines, and the % of runs/compute saved vs the grid
    baseline and vs the best naive baseline, with the oracle as a lower bound.
    """
    names = scenarios or list(SCENARIOS.keys())
    per_scenario: dict[str, dict[str, dict]] = {}
    rows: list[list] = []

    for sname in names:
        gen = SCENARIOS[sname]
        runs_by_policy: dict[str, list[PolicyRun]] = {p: [] for p in POLICIES}
        for i in range(max(1, n_projects)):
            project = gen(base_seed + i, f"{sname}{i}")
            for p in POLICIES:
                runs_by_policy[p].append(run_policy(project, p, steps))
        agg = {p: _aggregate(runs_by_policy[p]) for p in POLICIES}
        per_scenario[sname] = agg

        insight = agg["insightflow"]
        grid = agg["grid"]
        oracle = agg["oracle"]
        naive_decided = [agg[p]["decided"] for p in NAIVE if agg[p]["decided"] is not None]
        best_naive = min(naive_decided) if naive_decided else None
        naive_cost = [agg[p]["cost"] for p in NAIVE if agg[p]["cost"] is not None]
        best_naive_cost = min(naive_cost) if naive_cost else None

        rows.append(
            [
                sname,
                fmt(insight["decided"], 1) if insight["decided"] is not None else "-",
                fmt(grid["decided"], 1) if grid["decided"] is not None else "-",
                _disp_pct(_pct_saved(insight["decided"], grid["decided"])),
                _disp_pct(_pct_saved(insight["decided"], best_naive)),
                _disp_pct(_pct_saved(insight["cost"], best_naive_cost)),
                fmt(oracle["decided"], 1) if oracle["decided"] is not None else "-",
            ]
        )

    # Overall headline: mean % runs saved vs grid across scenarios (where defined).
    vs_grid_raw = [
        _pct_saved(per_scenario[s]["insightflow"]["decided"], per_scenario[s]["grid"]["decided"])
        for s in names
    ]
    vs_grid = [v for v in vs_grid_raw if v is not None]
    overall_runs_saved_vs_grid = round(mean(vs_grid), 1) if vs_grid else None

    # Robustness: each policy's mean runs-to-decision across scenarios and its
    # WORST-case ratio vs the oracle. A naive policy can tie InsightFlow on the one
    # task it suits, but its worst-case ratio exposes the task where it fails.
    robustness_rows = []
    for p in ["oracle", "insightflow", *ABLATIONS, *NAIVE]:
        decided = [per_scenario[s][p]["decided"] for s in names]
        ratios = [
            per_scenario[s][p]["decided"] / per_scenario[s]["oracle"]["decided"]
            for s in names
            if per_scenario[s][p]["decided"] is not None
            and per_scenario[s]["oracle"]["decided"]
        ]
        solved = sum(1 for s in names if per_scenario[s][p]["solved"] == per_scenario[s][p]["total"])
        valid = [d for d in decided if d is not None]
        robustness_rows.append(
            [
                p,
                fmt(mean(valid), 2) if valid else "-",
                fmt(max(ratios), 2) + "x" if ratios else "-",
                f"{solved}/{len(names)}",
            ]
        )

    return {
        "headers": [
            "scenario", "if_runs", "grid_runs", "%saved_vs_grid",
            "%saved_vs_best_naive", "%cost_saved_vs_best", "oracle",
        ],
        "rows": rows,
        "robustness_headers": ["policy", "mean_runs", "worst_vs_oracle", "scenarios_solved"],
        "robustness_rows": robustness_rows,
        "per_scenario": per_scenario,
        "overall_runs_saved_vs_grid": overall_runs_saved_vs_grid,
        "steps": steps,
        "n_projects": max(1, n_projects),
    }


def _disp_pct(v: float | None) -> str:
    return "-" if v is None else f"{v:+.1f}%"


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

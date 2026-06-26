"""Benchmark harness tests."""

from __future__ import annotations

from insightflow.benchmark import run_benchmark, run_scenarios
from insightflow.simulator import SCENARIOS


def _row(result, policy):
    return next(r for r in result["rows"] if r[0] == policy)


def test_benchmark_runs_and_reports_all_policies():
    result = run_benchmark(steps=12, n_projects=2)
    policies = {r[0] for r in result["rows"]}
    for expected in ("insightflow", "grid", "all_seeds_first", "oracle", "random"):
        assert expected in policies
    assert result["headers"][0] == "policy"
    assert result["notes"]


def test_insightflow_beats_depth_first_in_benchmark():
    result = run_benchmark(steps=15, n_projects=2)
    insight = _row(result, "insightflow")
    grid = _row(result, "grid")
    all_seeds = _row(result, "all_seeds_first")
    # decided@ column (index 1); InsightFlow should decide no later than depth-first.
    assert insight[1] != "-"
    assert float(insight[1]) < float(grid[1])
    assert float(insight[1]) < float(all_seeds[1])


def test_scenarios_insightflow_is_robust():
    """Across all task scenarios, InsightFlow solves every one and stays close to
    the oracle, while beating the grid baseline on runs everywhere."""
    result = run_scenarios(steps=40, n_projects=3)
    per = result["per_scenario"]
    assert set(per.keys()) == set(SCENARIOS.keys())
    for sname, agg in per.items():
        inf = agg["insightflow"]
        grid = agg["grid"]
        oracle = agg["oracle"]
        assert inf["solved"] == inf["total"], f"InsightFlow failed to solve {sname}"
        # No worse than grid on runs-to-decision.
        assert inf["decided"] <= grid["decided"], f"InsightFlow lost to grid on {sname}"
        # Within 1.5x of the oracle on every scenario (robustness).
        assert inf["decided"] <= 1.5 * oracle["decided"], f"InsightFlow far from oracle on {sname}"
    # Headline: meaningful average saving vs grid.
    assert result["overall_runs_saved_vs_grid"] is not None
    assert result["overall_runs_saved_vs_grid"] > 25.0

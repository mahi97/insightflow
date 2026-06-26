"""Benchmark harness tests."""

from __future__ import annotations

from insightflow.benchmark import run_benchmark


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

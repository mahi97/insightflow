"""Simulator tests."""

from __future__ import annotations

from insightflow.schemas import ClaimStatus, RunStatus
from insightflow.simulator import (
    generate_project,
    run_policy,
    simulate_result_for,
)


def test_generate_project_is_deterministic():
    p1 = generate_project(0)
    p2 = generate_project(0)
    assert [e.id for e in p1.experiments] == [e.id for e in p2.experiments]
    assert p1.truth.keys() == p2.truth.keys()


def test_execute_is_deterministic_and_has_history():
    project = generate_project(1)
    exp = project.experiments[0]
    r1 = project.execute(exp)
    r2 = project.execute(exp)
    assert r1.metrics == r2.metrics
    assert r1.status == RunStatus.completed
    assert len(r1.partial_history) == 5


def test_ground_truth_is_supported_for_real_effect():
    project = generate_project(0)
    truth = project.ground_truth_statuses()
    assert truth["C1"] == ClaimStatus.supported


def test_insightflow_reaches_decision_faster_than_depth_first():
    project = generate_project(0)
    insight = run_policy(project, "insightflow", max_steps=20)
    all_seeds = run_policy(project, "all_seeds_first", max_steps=20)
    grid = run_policy(project, "grid", max_steps=20)

    assert insight.correct
    assert insight.decided_step is not None
    # Breadth-aware scheduling beats depth-first replication.
    assert insight.decided_step < all_seeds.decided_step
    assert insight.decided_step < grid.decided_step


def test_oracle_is_an_upper_bound():
    project = generate_project(0)
    oracle = run_policy(project, "oracle", max_steps=20)
    insight = run_policy(project, "insightflow", max_steps=20)
    assert oracle.correct
    assert oracle.decided_step <= insight.decided_step


def test_simulate_result_for_is_deterministic_per_seed():
    project = generate_project(0)
    exp = project.experiments[0]
    r1 = simulate_result_for(exp, project_seed=3)
    r2 = simulate_result_for(exp, project_seed=3)
    assert r1.metrics == r2.metrics


def test_mixed_multi_claim_scenario_decides_both_claims():
    project = generate_project  # noqa: F841  (keep import usage stable)
    from insightflow.simulator import SCENARIOS
    p = SCENARIOS["mixed_multi_claim"](0, "m")
    gt = {k: v.value for k, v in p.ground_truth_statuses().items()}
    assert gt == {"C1": "supported", "C2": "refuted"}
    r = run_policy(SCENARIOS["mixed_multi_claim"](0, "m"), "insightflow", 40)
    assert r.correct


def test_ablation_policies_run():
    from insightflow.simulator import POLICIES, SCENARIOS
    for pol in ("baseline_first", "ablate_reviewer_risk", "uncertainty_only"):
        assert pol in POLICIES
        run_policy(SCENARIOS["breadth"](0, "b"), pol, 30)  # must not crash


def test_ablate_seed_policy_runs():
    from insightflow.simulator import POLICIES, SCENARIOS
    assert "ablate_seed_policy" in POLICIES
    r = run_policy(SCENARIOS["noisy_seeds"](0, "n"), "ablate_seed_policy", 40)
    assert r.runs_launched > 0  # must not crash

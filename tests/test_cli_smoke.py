"""CLI smoke tests via Typer's CliRunner (no subprocess needed)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from insightflow.cli import app

runner = CliRunner()


def _run(*args):
    return runner.invoke(app, list(args))


def test_version():
    result = _run("--version")
    assert result.exit_code == 0
    assert "insightflow" in result.output


def test_state_without_project_fails_gracefully(tmp_path):
    result = _run("state", "-C", str(tmp_path))
    assert result.exit_code == 1
    assert "No InsightFlow project" in result.output


def test_demo_state_plan_flow(tmp_path):
    p = str(tmp_path)
    assert _run("demo", "--force", "-C", p).exit_code == 0
    assert _run("validate", "-C", p).exit_code == 0

    state = _run("state", "-C", p)
    assert state.exit_code == 0
    assert "Claims" in state.stdout

    plan = _run("plan", "-C", p)
    assert plan.exit_code == 0
    assert "Top recommendation" in plan.stdout
    # The headline recommendation should be a new dataset, not more CIFAR-10 seeds.
    assert "svhn" in plan.stdout or "cifar100" in plan.stdout
    # Reports were written.
    assert (tmp_path / "reports" / "plan_latest.md").exists()
    assert (tmp_path / "reports" / "claim_confidence.md").exists()


def test_plan_json_output(tmp_path):
    p = str(tmp_path)
    _run("demo", "--force", "-C", p)
    result = _run("plan", "-C", p, "--format", "json")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"].startswith("plan_")
    assert "actions" in data and "claim_confidence" in data


def test_explain_after_plan(tmp_path):
    p = str(tmp_path)
    _run("demo", "--force", "-C", p)
    _run("plan", "-C", p)
    result = _run("explain", "-C", p)
    assert result.exit_code == 0
    assert "Explanation of plan" in result.stdout


def test_simulate_step_advances_state(tmp_path):
    p = str(tmp_path)
    _run("demo", "--force", "-C", p)
    before = _run("state", "-C", p, "--format", "json")
    n_before = json.loads(before.stdout)["results"]
    assert _run("simulate-step", "-C", p).exit_code == 0
    after = _run("state", "-C", p, "--format", "json")
    n_after = json.loads(after.stdout)["results"]
    assert n_after == n_before + 1


def test_log_result(tmp_path):
    p = str(tmp_path)
    _run("demo", "--force", "-C", p)
    result = _run(
        "log-result", "-C", p, "--experiment-id", "method_a_cifar100_s0", "--metric", "accuracy=0.71"
    )
    assert result.exit_code == 0
    assert "Recorded result" in result.stdout


def test_benchmark_cli(tmp_path):
    result = _run("benchmark", "--steps", "8", "--projects", "1", "-C", str(tmp_path))
    assert result.exit_code == 0
    assert "policy" in result.stdout
    assert (tmp_path / "reports" / "benchmark.md").exists()


def test_init_then_validate(tmp_path):
    p = str(tmp_path)
    assert _run("init", "-C", p).exit_code == 0
    assert _run("validate", "-C", p).exit_code == 0


def test_readiness_command(tmp_path):
    p = str(tmp_path)
    _run("demo", "--force", "-C", p)
    result = _run("readiness", "-C", p)
    assert result.exit_code == 0
    assert "readiness" in result.stdout.lower()
    # JSON form is machine-readable.
    j = _run("readiness", "-C", p, "--format", "json")
    assert j.exit_code == 0
    data = json.loads(j.stdout)
    assert "claims" in data and "paper_ready" in data

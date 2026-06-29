"""Tests for the MCP tool logic (pure functions; no MCP runtime needed)."""

from __future__ import annotations

import pytest

from insightflow.demo import setup_demo
from insightflow.errors import InsightFlowError
from insightflow.mcp_server import (
    TOOLS,
    log_result_tool,
    plan_tool,
    replay_tool,
    state_tool,
    validate_tool,
)


@pytest.fixture
def demo_dir(tmp_path):
    setup_demo(tmp_path, force=True)
    return str(tmp_path)


def test_tool_registry_complete():
    for name in ("insightflow_state", "insightflow_plan", "insightflow_validate",
                 "insightflow_log_result", "insightflow_replay", "insightflow_explain"):
        assert name in TOOLS


def test_state_tool(demo_dir):
    out = state_tool(demo_dir)
    assert out["results"] >= 1
    assert out["experiments"]
    assert out["claim_confidence"]


def test_plan_tool_returns_plan(demo_dir):
    out = plan_tool(demo_dir)
    assert out["id"].startswith("plan_")
    assert "actions" in out and "claim_confidence" in out


def test_validate_tool(demo_dir):
    out = validate_tool(demo_dir)
    assert out["valid"] is True
    assert out["claims"] >= 1


def test_log_result_tool_then_state(demo_dir):
    before = state_tool(demo_dir)["results"]
    out = log_result_tool("method_a_svhn_s0", {"accuracy": 0.9}, project_dir=demo_dir)
    assert out["recorded"] is True
    assert state_tool(demo_dir)["results"] == before + 1


def test_replay_tool(demo_dir):
    out = replay_tool(demo_dir)
    assert "ground_truth" in out and "total_runs" in out


def test_tool_on_uninitialized_dir_raises(tmp_path):
    with pytest.raises(InsightFlowError):
        state_tool(str(tmp_path))

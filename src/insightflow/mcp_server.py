"""Model Context Protocol (MCP) server for InsightFlow.

Exposes the InsightFlow ledger/scheduler as MCP tools so *any* MCP-capable agent
(Claude Code, Codex, …) gets the same grounded interface the CLI provides — the
ledger stays the source of truth; the agent never invents the schedule.

The tool *logic* lives in plain functions (``*_tool``) that return JSON-able
dicts and are unit-tested without any MCP runtime. ``build_server`` is a thin
wrapper that lazily imports the optional ``mcp`` package and registers them, so
importing this module never requires ``mcp`` to be installed.

Run it with ``insightflow-mcp`` (after ``uv sync --extra mcp``).
"""

from __future__ import annotations

import os
from typing import Any

from .errors import InsightFlowError
from .ledger import Ledger
from .scheduler import build_plan
from .scoring import compute_claim_confidence


def _resolve_dir(project_dir: str | None) -> str:
    return project_dir or os.environ.get("INSIGHTFLOW_HOME") or os.getcwd()


def _ledger(project_dir: str | None) -> Ledger:
    ledger = Ledger(_resolve_dir(project_dir))
    if not ledger.is_initialized():
        raise InsightFlowError(
            f"No InsightFlow project in '{ledger.project_dir}'. Run `insightflow init` "
            "or `insightflow demo --force` first."
        )
    return ledger


# --------------------------------------------------------------------------- #
# Pure tool logic (testable without an MCP runtime)
# --------------------------------------------------------------------------- #
def state_tool(project_dir: str | None = None) -> dict[str, Any]:
    """Current evidence: experiments by status, result count, claim confidence."""
    ledger = _ledger(project_dir)
    st = ledger.load_state()
    conf = compute_claim_confidence(st)
    return {
        "experiments": [
            {"id": e.id, "status": e.status.value, "method": e.method, "dataset": e.dataset}
            for e in st.experiments
        ],
        "results": len(st.results),
        "claim_confidence": [c.model_dump() for c in conf.values()],
    }


def plan_tool(project_dir: str | None = None) -> dict[str, Any]:
    """The ranked plan: immediate queue, postponed, avoided, claim table, warnings."""
    ledger = _ledger(project_dir)
    plan = build_plan(ledger.load_state())
    ledger.save_plan(plan)
    ledger.log_decision({"event": "plan", "plan_id": plan.id, "via": "mcp"})
    return plan.model_dump()


def explain_tool(project_dir: str | None = None, plan_id: str | None = None) -> dict[str, Any]:
    """Per-action scoring breakdown and the trade-offs the scheduler weighed."""
    from .explain import explain_plan

    ledger = _ledger(project_dir)
    plan = ledger.get_plan(plan_id) if plan_id else ledger.latest_plan()
    if plan is None:
        raise InsightFlowError("No plan found. Call the plan tool first.")
    return {"plan_id": plan.id, "explanation_markdown": explain_plan(plan)}


def validate_tool(project_dir: str | None = None) -> dict[str, Any]:
    """Validate the project's configs (claim links, duplicates, cycles, costs)."""
    from .config import load_claims, load_experiments, validate_configs

    pdir = _resolve_dir(project_dir)
    claims = load_claims(pdir)
    experiments = load_experiments(pdir)
    issues = validate_configs(claims, experiments)
    return {"valid": not issues, "issues": issues,
            "claims": len(claims), "experiments": len(experiments)}


def log_result_tool(
    experiment_id: str,
    metrics: dict[str, float],
    status: str = "completed",
    seed: int = 0,
    project_dir: str | None = None,
) -> dict[str, Any]:
    """Record a run result in the ledger."""
    from .schemas import RunResult, RunSource, RunStatus
    from .utils import now_iso, stable_hash

    ledger = _ledger(project_dir)
    try:
        run_status = RunStatus(status)
    except ValueError as exc:
        raise InsightFlowError(
            f"Invalid status '{status}'. Use: {[s.value for s in RunStatus]}."
        ) from exc
    result = RunResult(
        run_id=f"mcp-{experiment_id}-{stable_hash((experiment_id, now_iso()), 8)}",
        experiment_id=experiment_id,
        seed=seed,
        metrics={k: float(v) for k, v in metrics.items()},
        status=run_status,
        source=RunSource.manual,
        finished_at=now_iso(),
    )
    ledger.add_result(result)
    ledger.log_decision({"event": "log_result", "experiment_id": experiment_id, "via": "mcp"})
    return {"recorded": True, "run_id": result.run_id}


def replay_tool(project_dir: str | None = None) -> dict[str, Any]:
    """Offline replay: would InsightFlow have decided with fewer runs?"""
    from .replay import replay

    result = replay(_ledger(project_dir).load_state())
    return {
        "total_runs": result.total_runs,
        "ground_truth": result.ground_truth,
        "actual_decided_at": result.actual_decided_at,
        "insight_decided_at": result.insight_decided_at,
        "runs_saved": result.runs_saved,
    }


def readiness_tool(project_dir: str | None = None) -> dict[str, Any]:
    """Paper readiness over the claim graph: verdicts, blocked claims, the most
    dangerous reviewer attacks, and recommended next research actions."""
    from .readiness import assess_readiness

    return assess_readiness(_ledger(project_dir).load_state()).model_dump()


TOOLS = {
    "insightflow_state": state_tool,
    "insightflow_plan": plan_tool,
    "insightflow_explain": explain_tool,
    "insightflow_validate": validate_tool,
    "insightflow_log_result": log_result_tool,
    "insightflow_replay": replay_tool,
    "insightflow_readiness": readiness_tool,
}


# --------------------------------------------------------------------------- #
# MCP runtime wrapper (optional dependency)
# --------------------------------------------------------------------------- #
def build_server() -> Any:  # pragma: no cover - requires the optional mcp package
    """Build a FastMCP server exposing the tools. Requires ``mcp``."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise InsightFlowError(
            "The 'mcp' package is not installed. Install it with `uv sync --extra mcp` "
            "(or `uv add mcp`) to run the InsightFlow MCP server."
        ) from exc

    server = FastMCP("insightflow")

    def _wrap(fn):
        def tool(**kwargs: Any) -> Any:
            try:
                return fn(**kwargs)
            except InsightFlowError as exc:
                return {"error": str(exc)}

        tool.__name__ = fn.__name__
        tool.__doc__ = fn.__doc__
        return tool

    for name, fn in TOOLS.items():
        server.add_tool(_wrap(fn), name=name, description=(fn.__doc__ or "").strip())
    return server


def main() -> None:  # pragma: no cover - process entrypoint
    import sys

    try:
        build_server().run()
    except InsightFlowError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()

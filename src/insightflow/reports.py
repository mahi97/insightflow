"""Markdown report rendering.

All reports are regenerated from ledger state, never hand-edited. The ``plan``
command writes ``reports/plan_latest.md`` and ``reports/claim_confidence.md``;
``state`` writes ``reports/state.md``; ``benchmark`` writes ``reports/benchmark.md``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .schemas import (
    ClaimConfidence,
    ExperimentStatus,
    Plan,
    PlanAction,
    State,
)
from .utils import ensure_dir, fmt, markdown_table, write_text


def reports_dir(project_dir: str | Path) -> Path:
    return Path(project_dir) / "reports"


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def render_state_md(state: State, claim_conf: list[ClaimConfidence]) -> str:
    lines = ["# InsightFlow State", ""]

    status_counts = Counter(e.status.value for e in state.experiments)
    lines.append("## Experiments")
    lines.append("")
    if state.experiments:
        rows = [[k, v] for k, v in sorted(status_counts.items())]
        lines.append(markdown_table(["status", "count"], rows))
    else:
        lines.append("_No experiments defined._")
    lines.append("")

    completed = [e for e in state.experiments if e.status == ExperimentStatus.completed]
    pending = [e for e in state.experiments if e.status == ExperimentStatus.pending]
    running = [e for e in state.experiments if e.status == ExperimentStatus.running]

    lines.append(f"- Completed: {len(completed)}")
    lines.append(f"- Running: {len(running)}")
    lines.append(f"- Pending: {len(pending)}")
    lines.append(f"- Results recorded: {len(state.results)}")
    lines.append("")

    lines.append("## Claims")
    lines.append("")
    lines.append(render_claim_confidence_table(claim_conf))
    lines.append("")

    if pending:
        lines.append("## Pending experiments")
        lines.append("")
        rows = [
            [e.id, e.method, e.dataset, e.condition, e.seed, fmt(e.expected_cost, 1), ",".join(e.claim_links)]
            for e in pending[:50]
        ]
        lines.append(
            markdown_table(
                ["id", "method", "dataset", "condition", "seed", "cost", "claims"], rows
            )
        )
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Claim confidence
# --------------------------------------------------------------------------- #
def render_claim_confidence_table(claim_conf: list[ClaimConfidence]) -> str:
    if not claim_conf:
        return "_No claims defined._"
    rows = []
    for c in claim_conf:
        effect = fmt(c.observed_effect, 3) if c.observed_effect is not None else "-"
        rows.append(
            [
                c.claim_id,
                c.status.value,
                fmt(c.confidence, 2),
                c.n_conditions_observed,
                c.n_seeds_observed,
                effect,
                fmt(c.required_effect, 3),
                "yes" if c.near_boundary else "no",
            ]
        )
    return markdown_table(
        ["claim", "status", "conf", "#cond", "#seed", "effect", "min_eff", "near_bdry"], rows
    )


def render_claim_confidence_md(claim_conf: list[ClaimConfidence]) -> str:
    lines = ["# Claim Confidence", "", render_claim_confidence_table(claim_conf), ""]
    notes = [f"- **{c.claim_id}**: {c.note}" for c in claim_conf if c.note]
    if notes:
        lines.append("## Notes")
        lines.append("")
        lines.extend(notes)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #
def _action_rows(actions: list[PlanAction]) -> str:
    rows = [
        [
            i + 1,
            a.action_type.value,
            a.label or a.experiment_id,
            fmt(a.score, 3),
            fmt(a.expected_decision_value, 2),
            fmt(a.expected_cost, 1),
            ",".join(a.affected_claims),
        ]
        for i, a in enumerate(actions)
    ]
    return markdown_table(["#", "action", "target", "score", "dec_val", "cost", "claims"], rows)


def render_plan_md(plan: Plan) -> str:
    lines = [f"# Plan {plan.id}", "", f"_Created: {plan.created_at} | state hash: {plan.state_hash}_", ""]

    lines.append("## Summary")
    lines.append("")
    lines.append("```text")
    lines.append(plan.summary)
    lines.append("```")
    lines.append("")

    lines.append("## Immediate queue")
    lines.append("")
    lines.append(_action_rows(plan.actions) if plan.actions else "_Empty._")
    lines.append("")

    if plan.actions:
        lines.append("### Rationale")
        lines.append("")
        for i, a in enumerate(plan.actions):
            lines.append(f"{i + 1}. **{a.label or a.experiment_id}** ({a.action_type.value}) - {a.rationale}")
        lines.append("")

    if plan.postponed:
        lines.append("## Postponed")
        lines.append("")
        lines.append(_action_rows(plan.postponed))
        lines.append("")

    if plan.avoided:
        lines.append("## Avoided")
        lines.append("")
        lines.append(_action_rows(plan.avoided))
        lines.append("")

    lines.append("## Claim confidence")
    lines.append("")
    lines.append(render_claim_confidence_table(plan.claim_confidence))
    lines.append("")

    if plan.warnings:
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {w}" for w in plan.warnings)
        lines.append("")

    if plan.assumptions:
        lines.append("## Assumptions")
        lines.append("")
        lines.extend(f"- {a}" for a in plan.assumptions)
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Benchmark
# --------------------------------------------------------------------------- #
def render_benchmark_md(result: dict) -> str:
    lines = ["# Benchmark", "", result.get("description", ""), ""]
    headers = result["headers"]
    rows = result["rows"]
    lines.append(markdown_table(headers, rows))
    lines.append("")
    if result.get("notes"):
        lines.append("## Notes")
        lines.append("")
        lines.extend(f"- {n}" for n in result["notes"])
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_report(project_dir: str | Path, name: str, content: str) -> Path:
    rdir = ensure_dir(reports_dir(project_dir))
    path = rdir / name
    write_text(path, content)
    return path

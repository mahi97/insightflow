"""Human-facing explanations of a plan and its scoring.

``explain`` turns the opaque ``factors`` dict on each :class:`PlanAction` into a
readable breakdown so a researcher (or the agent) can see *why* the scheduler
ranked things the way it did - including the explicit trade-offs the spec asks
for (new condition vs extra seed, cheap proxy vs expensive run, baseline vs
method continuation, broad scan vs replication).
"""

from __future__ import annotations

from .schemas import ActionType, Plan, PlanAction
from .utils import fmt, markdown_table

_TERM_LABELS = [
    ("decision_value", "decision value", "+"),
    ("uncertainty_reduction", "uncertainty reduction", "+"),
    ("dependency_unlock", "dependency unlock", "+"),
    ("reviewer_risk_reduction", "reviewer-risk reduction", "+"),
    ("seed_value", "seed value", "+"),
    ("redundancy_penalty", "redundancy penalty", "-"),
    ("premature_replication_penalty", "premature-replication penalty", "-"),
]


def explain_action(action: PlanAction) -> str:
    lines = [f"### {action.label or action.experiment_id} ({action.action_type.value})", ""]
    lines.append(f"- Score: **{fmt(action.score, 4)}**  (risk {fmt(action.risk, 2)})")
    lines.append(f"- Affects: {', '.join(action.affected_claims) or 'no linked claim'}")
    lines.append(f"- Expected cost/time: {fmt(action.expected_cost, 1)} / {fmt(action.expected_time, 1)}")
    lines.append("")
    rows = []
    for key, label, sign in _TERM_LABELS:
        if key in action.factors:
            rows.append([f"{sign} {label}", fmt(action.factors[key], 4)])
    if "numerator" in action.factors and "denominator" in action.factors:
        rows.append(["= numerator", fmt(action.factors["numerator"], 4)])
        rows.append(["/ denominator (time + lambda*cost)", fmt(action.factors["denominator"], 4)])
    if rows:
        lines.append(markdown_table(["term", "value"], rows))
        lines.append("")
    lines.append(f"_Rationale:_ {action.rationale}")
    lines.append("")
    return "\n".join(lines)


def explain_plan(plan: Plan) -> str:
    lines = [f"# Explanation of plan {plan.id}", "", "```text", plan.summary, "```", ""]

    lines.append("## Immediate queue")
    lines.append("")
    if plan.actions:
        for a in plan.actions:
            lines.append(explain_action(a))
    else:
        lines.append("_No queued actions._\n")

    # Explicit trade-off comparisons, which the spec calls out by name.
    comparison = _comparisons(plan)
    if comparison:
        lines.append("## Trade-offs the scheduler weighed")
        lines.append("")
        lines.extend(comparison)
        lines.append("")

    if plan.postponed:
        lines.append("## Why these were postponed")
        lines.append("")
        for a in plan.postponed[:10]:
            lines.append(f"- **{a.label or a.experiment_id}**: {a.rationale}")
        lines.append("")

    return "\n".join(lines)


def _comparisons(plan: Plan) -> list[str]:
    """Surface the canonical comparisons when both sides are present in the plan."""
    out: list[str] = []
    queued = plan.actions
    postponed = plan.postponed

    new_conditions = [a for a in queued if "new" in a.rationale and "condition" in a.rationale]
    extra_seeds = [a for a in postponed if a.action_type in (ActionType.add_seed, ActionType.postpone)]
    if new_conditions and extra_seeds:
        nc = new_conditions[0]
        es = extra_seeds[0]
        out.append(
            f"- **New condition vs extra seed**: queued `{nc.label}` "
            f"(score {fmt(nc.score, 3)}) ahead of `{es.label}` (score {fmt(es.score, 3)}) "
            "because breadth reduces more decision uncertainty than replication right now."
        )

    baselines = [
        a
        for a in queued
        if a.action_type == ActionType.launch_baseline or "baseline" in a.rationale
    ]
    if baselines:
        out.append(
            f"- **Strong baseline vs method continuation**: `{baselines[0].label}` is prioritized "
            "because a missing baseline could decide (or kill) the claim."
        )

    if queued:
        cheapest = min(queued, key=lambda a: a.expected_cost)
        priciest = max(queued, key=lambda a: a.expected_cost)
        if cheapest.experiment_id != priciest.experiment_id:
            out.append(
                f"- **Cheap proxy vs expensive run**: cost-normalized scoring favors "
                f"`{cheapest.label}` (cost {fmt(cheapest.expected_cost, 1)}) when it yields "
                "comparable decision value to pricier runs."
            )
    return out

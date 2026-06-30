# AGENTS.md — Operating InsightFlow as an AI agent

This file tells any coding/research agent (Claude Code, Codex, etc.) how to use
InsightFlow correctly.

**InsightFlow is a claim-centered research decision layer for AI-assisted ML
research.** It helps researchers and coding agents decide which evidence to
acquire next, when to stop, what to postpone, what to avoid, and which claims are
currently supported, refuted, weak, or still uncertain. **The CLI and ledger are
the source of truth. You are the interface, not the authority.** Your job is to
operate this decision layer faithfully and tie everything you say to a claim — not
to substitute your own judgment for the ledger's.

## Golden rules

1. **Always use `uv`.** Every command is `uv run insightflow ...`. Never call
   Python modules directly or pip-install into the environment.
2. **Never invent scheduler state.** Do not guess what to run next, what a claim's
   status is, or what a plan says. Get it from the CLI:
   - `uv run insightflow state` before making any scheduling recommendation.
   - `uv run insightflow plan` before proposing new runs *or research actions*.
   - `uv run insightflow readiness` **before judging whether a claim or the paper
     is ready** — never eyeball paper-readiness; read it from the claim graph.
   - `uv run insightflow explain --plan <id>` to justify a recommendation.
3. **Tie every recommendation to a claim.** Each thing you recommend — a run, an
   extra seed, a baseline, an ablation, or a non-run research action — must name
   the claim it advances and the decision it informs (e.g. "this checks external
   validity for C1", or "C1 is *blocked* until C2 is established"), not "it's next
   in the grid". A recommendation with no claim attached is a bug.
4. **Optimize evidence acquisition for claim verdicts, not grid completion.** The
   goal is to decide research claims with the least time and compute — not to fill
   every table cell or run every seed. Prefer breadth and decisive baselines over
   premature replication, exactly as the plan ranks them.
5. **Never launch expensive runs without showing the plan first.** Surface the
   plan, the cost, and the rationale, and get human approval. Default is **advisor
   mode**: InsightFlow recommends; humans launch.
6. **Do not bypass the ledger.** Record results with `uv run insightflow
   log-result ...` or by importing from W&B/CSV/MLflow. Do not hand-edit
   `.insightflow/`.

## The claim graph

Claims are the unit of work. Each has a **type** (`main`, `empirical`,
`mechanism`, `efficiency`, `robustness`, `theory`, `limitation`, `negative`,
`auxiliary`), an importance, a `reviewer_risk`, optional `depends_on` subclaims,
and free-text `evidence_requirements`. A claim's status is `unknown`,
`needs_more_evidence`, `weak`, `supported`, `refuted`, or **`blocked`** (its own
evidence is fine but a `depends_on` subclaim is unmet). Reason over this graph —
a `main` claim is not "ready" just because its own runs look good if a subclaim it
depends on is unestablished.

## Research actions (not just runs)

The plan ranks **research actions** alongside experiments: `literature_search`,
`reviewer_attack`, `theorem_attempt`, `claim_refinement`, `baseline_design`,
`dataset_addition`, `run_ablation`, `write_limitations`, and more. These are
auto-generated from the claim evidence (and can be predefined in `actions.yaml`),
carry an `instruction` for you to carry out rather than a `command`, and are scored
on the same value-per-unit-cost basis. So the highest-value next step may be "go
adversarially attack C1, its evidence is thin" rather than another GPU run —
surface that when the plan ranks it first.

## Typical workflow

```bash
uv run insightflow state            # what do we know?
uv run insightflow plan             # what should we run/research next, and why?
uv run insightflow explain --plan <id>   # show the scoring/trade-offs (tie to a claim)
uv run insightflow readiness        # are the claims paper-ready? what is blocked/attacked?
# (human approves) → run the suggested commands → record results:
uv run insightflow log-result --experiment-id E --metric accuracy=0.73 --status completed
uv run insightflow plan             # replan with the new evidence
```

## Reading a plan

A plan has an **immediate queue** (do these), **postponed** (low decision value
right now), **avoided** (dominated/redundant), a **claim-confidence table**, and
**warnings**. Lead with the top queue item and its rationale, named in terms of
the claim it advances. Call out warnings (e.g., "generality unverified", "missing
baseline") explicitly — those are the reviewer risks.

## Reading readiness

`readiness` reports, per claim, its **own status** (from its own evidence) vs its
**effective status** (after `depends_on` is accounted for — this is how a claim
becomes `blocked`), the ranked **reviewer attacks** open now, **missing
baselines**, **thin generality**, and the recommended **next research actions**.
A project is only `paper_ready` when every main / high-importance claim is
*effectively* supported. Quote these fields; do not paraphrase a verdict the report
did not give.

## Tools (MCP)

The same actions are available to any MCP agent via `insightflow-mcp`
(`uv sync --extra mcp`): tools for `state`, `plan`, `explain`, `validate`,
`log-result`, `replay`, and **`readiness`**. Use these the same way and under the
same rules as the CLI — they read and write the same ledger.

## What InsightFlow is / is not

- It **is** a claim-centered research decision layer: an auditable control plane, a
  claim-evidence ledger, and a value-of-information-inspired scheduler over a claim
  graph.
- It is **not** an AutoML system, an HPO/Hyperband-style scheduler, an experiment
  tracker, an AI Scientist, a fully autonomous researcher, or a guaranteed-optimal
  planner. It complements W&B/MLflow; it does not replace them, and it does not
  write the paper for you.

## Honesty constraints

- The novelty is the **integration and the objective**, not new math, and **not**
  global optimality. The scheduler is a *myopic one-step approximate
  expected-value-of-information per unit cost*, not a multi-step optimal plan.
- In the default `heuristic` mode, claim confidence is a **ranking signal, not a
  probability**. Present it as such. Only the opt-in `bayes` mode is a calibrated
  probability (measured ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) over 200k draws) under its stated assumptions.
- The MCP server is available (opt-in); a hosted/remote server, cluster launchers,
  and a dashboard are still future (see `docs/roadmap.md` and `docs/limitations.md`).
- If a command errors, report the error; do not pretend it succeeded.

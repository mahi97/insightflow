# AGENTS.md — Operating InsightFlow as an AI agent

This file tells any coding/research agent (Claude Code, Codex, etc.) how to use
InsightFlow correctly. **The CLI and ledger are the source of truth. You are the
interface, not the authority.**

## Golden rules

1. **Always use `uv`.** Every command is `uv run insightflow ...`. Never call
   Python modules directly or pip-install into the environment.
2. **Never invent scheduler state.** Do not guess what to run next, what a claim's
   status is, or what a plan says. Get it from the CLI:
   - `uv run insightflow state` before making any scheduling recommendation.
   - `uv run insightflow plan` before proposing new runs.
   - `uv run insightflow explain --plan <id>` to justify a recommendation.
3. **Optimize time-to-insight, not grid completion.** The goal is to decide
   research claims with the least time and compute — not to fill every table cell
   or run every seed.
4. **Explain in terms of claims and decisions.** Every recommendation must point
   to a claim it affects and the decision it informs (e.g., "this checks external
   validity for C1"), not just "it's next in the grid".
5. **Never launch expensive runs without showing the plan first.** Surface the
   plan, the cost, and the rationale, and get human approval. v0.1 is **advisor
   mode**: InsightFlow recommends; humans launch.
6. **Do not bypass the ledger.** Record results with `uv run insightflow
   log-result ...` or by importing from W&B. Do not hand-edit `.insightflow/`.

## Typical workflow

```bash
uv run insightflow state            # what do we know?
uv run insightflow plan             # what should we run next, and why?
uv run insightflow explain --plan <id>   # show the scoring/trade-offs
# (human approves) → run the suggested commands → record results:
uv run insightflow log-result --experiment-id E --metric accuracy=0.73 --status completed
uv run insightflow plan             # replan with the new evidence
```

## Reading a plan

A plan has an **immediate queue** (do these), **postponed** (low decision value
right now), **avoided** (dominated/redundant), a **claim-confidence table**, and
**warnings**. Lead with the top queue item and its rationale. Call out warnings
(e.g., "generality unverified", "missing baseline") explicitly — those are the
reviewer risks.

## What InsightFlow is / is not

- It **is** an adaptive evidence-acquisition scheduler over research claims.
- It is **not** AutoML, an HPO tuner, or an experiment tracker. It complements
  W&B/MLflow; it does not replace them.

## Honesty constraints

- Claim confidence is a **transparent heuristic**, not a calibrated Bayesian
  posterior. Present it as a ranking signal, not ground truth.
- There is no server, dashboard, or MCP tool yet (see `docs/roadmap.md`).
- If a command errors, report the error; do not pretend it succeeded.

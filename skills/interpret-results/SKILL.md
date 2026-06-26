---
name: interpret-results
description: Use AFTER experiment results land — interpret surprising, borderline, negative, or high-variance results and decide research strategy, while grounding every claim status and next-run decision in the InsightFlow CLI. The agent supplies judgment the scripts can't (is this weird? reviewer-dangerous? should we weaken or pivot the claim?); the CLI supplies the numbers and the schedule. Trigger when new runs complete, a result is unexpected, or someone asks "what does this mean and what now?".
---

# Interpret results and decide what's next

The scripts compute *what the evidence says*; you reason about *what it means for
the research*. This is the division of labor: never overrule the ledger's numbers
with intuition, but do add the strategic judgment the numbers can't express.

**Boundary**: claim statuses, the queue, and scores come from
`uv run insightflow plan` / `state` — read them, don't invent them. Your value is
the interpretation layer on top.

## Steps

1. **Record the evidence first.** Make sure results are in the ledger:
   `uv run insightflow log-result --experiment-id ID --metric name=value
   --status completed` (or `import-wandb`). The ledger is the source of truth.
2. **Recompute.** Run `uv run insightflow state` and `uv run insightflow plan`,
   and `uv run insightflow explain` for the top items. Note what *changed*: did a
   claim move (e.g. `needs_more_evidence` → `supported`, or toward `weak`/`refuted`)?
3. **Now reason — the part that's yours:**
   - **Surprising?** A result far from expectation, or high seed variance, is a
     signal to add a seed there (confirm with the seed policy in `plan`) rather
     than trusting a single noisy number.
   - **Reviewer-dangerous?** A strong baseline that nearly closes the gap, or a
     generality claim still at low breadth — flag it even if the heuristic looks
     fine. These are the things that sink papers.
   - **Negative result on a cheap proxy?** That may mean an expensive branch
     should be postponed or dropped — check the dependency/postpone reasoning in
     the plan, then recommend accordingly.
   - **Claim no longer holds?** Recommend weakening the claim's `statement` /
     `minimum_effect_size` in `configs/claims.yaml`, or pivoting — and say so
     explicitly. A negative result is often a better story.
4. **Hand back to the loop.** Translate your judgment into concrete next actions
   from the immediate queue (via `adaptive-experiment-scheduler`), each tied to a
   claim and a decision, with cost. Re-validate if you changed any config.

## Don'ts

- Don't assert a claim is supported/refuted against what `state`/`plan` say.
- Don't treat the heuristic confidence as a calibrated probability — back strong
  conclusions with the measured effects and seed counts in the ledger.
- Don't silently drop a result; record it, then interpret it.

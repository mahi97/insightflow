---
name: define-claims
description: Use at the START of an InsightFlow research project — turn a research idea, paper outline, or existing codebase into claims.yaml and experiments.yaml. The agent reasons about WHAT to prove and WHAT to run (judgment); the InsightFlow CLI validates the structure and later computes confidence. Trigger when setting up a new project, encoding a hypothesis, or asking "what claims and experiments should this project have?".
---

# Define claims and experiments

This is the one step that is genuinely the agent's job: deciding *what the paper
will assert* and *what runs could provide evidence*. The scripts cannot invent
your hypotheses. But once you write them down, the deterministic CLI takes over.

**Boundary**: you (the agent) reason about the science; `insightflow validate`
checks the structure; `insightflow plan`/`state` later score the evidence. Do not
hand-author confidence numbers or a schedule — only the claims and the grid.

## Steps

1. **Extract the claims.** From the research idea / outline / codebase, write
   `configs/claims.yaml`. One claim per assertion the paper will make. For each:
   - `statement` — the precise scientific claim.
   - `target_metric`, `desired_direction`, `minimum_effect_size` — the decision
     rule (what effect counts as real).
   - `required_seeds` — how much replication a reviewer would demand.
   - `importance` (high/medium/low) and `reviewer_risk` (0–1) — what's central and
     what a reviewer will attack if unsubstantiated.
   Prefer a few sharp, falsifiable claims over many vague ones. Mark generality /
   external-validity claims explicitly — those are usually the binding constraint.

2. **Enumerate the experiment grid.** Write `configs/experiments.yaml`: every
   `(method, dataset, condition, seed)` cell that *could* provide evidence, with
   `claim_links`, `dependencies`, `expected_cost`, `expected_time`, and a real
   `command`. **Always include baselines** (tag them `baseline`) — a missing
   baseline is the #1 reviewer risk and the scheduler rewards filling it. If you
   read it from a codebase, map training scripts/configs/sweeps to cells.

3. **Set resources.** `configs/resources.yaml`: workers and a real
   `budget_gpu_hours`.

4. **Validate deterministically.** Run `uv run insightflow validate`. Fix every
   issue it reports (unknown claim links, duplicate ids, dependency cycles,
   impossible costs) before spending any compute. Re-run until clean.

5. **Sanity-check with a dry plan.** Run `uv run insightflow plan` on the empty
   ledger. The first recommendations and warnings tell you whether your claims and
   grid are coherent (e.g., "no baseline for C1" means you forgot a baseline).

## Don'ts

- Don't write claim statuses or confidence — those are computed from results.
- Don't omit baselines or dependencies; the scheduler reasons over them.
- Don't enumerate runs with no `claim_links` — if a run can't affect a claim,
  question why it's in the grid.

When the configs validate and a dry `plan` looks sane, hand off to the
`adaptive-experiment-scheduler` skill to run the loop.

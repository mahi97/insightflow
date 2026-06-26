---
name: writeup-from-ledger
description: Use when writing the paper, blog post, report, or figures for an InsightFlow-driven project — generate prose and figures STRICTLY from the ledger, reports, and decision log, never from memory or invented numbers. The agent writes and explains (its strength); the scripts supply every fact. Trigger when asked to draft results, methods, an experiments appendix, a blog narrative, or to make figures/tables of what was run.
---

# Write up from the ledger (never from memory)

Writing is the agent's strength — but in a research write-up, every number must
be traceable. The rule: **prose and structure are yours; facts come from the
ledger.** If a number isn't in the ledger/reports, don't write it.

**Boundary**: pull facts via the CLI with `--format json`; you compose. Cite the
plan `state_hash` so every figure/table is reproducible from a known state.

## Sources of truth

| You are writing… | Pull it from |
| --- | --- |
| Methods / experimental setup | `configs/claims.yaml`, `configs/experiments.yaml` |
| "What we ran and why" appendix | `.insightflow/decisions.jsonl` (timestamped decision log) |
| Main results table | `uv run insightflow state --format json` → claim_confidence; `reports/claim_confidence.md` |
| Per-run numbers | the ledger results (`log-result`/W&B) — measured effects and seed counts |
| "Compute saved by adaptive scheduling" figure | `uv run insightflow benchmark --format json` (runs & cost to the correct decision vs baselines) |
| Claim-confidence-over-time figure | `confidence_evolution` in the benchmark JSON, or successive `plan --format json` snapshots |

## Steps

1. **Gather facts.** Run the relevant commands with `--format json` and read the
   reports in `reports/`. Build a small table of the exact numbers you'll cite.
2. **Draft prose around them.** Write the methods, results, and narrative. For the
   blog, tell the story the decision log tells: what was prioritized, what was
   postponed, what was avoided, and the moment each claim flipped.
3. **Make figures from structured output**, not screenshots — plot from the JSON
   so figures are regenerable. Label each with the `state_hash` it came from.
4. **Report the negatives.** What was *not* run, and why, is part of the
   contribution (compute saved). Include the avoided/postponed reasoning.

## Honesty rules (non-negotiable)

- Describe claim confidence as a **heuristic decision signal**, not a calibrated
  posterior. Support final claims with measured effects + seed counts.
- Never invent or round-trip a number you didn't read from the ledger.
- If the evidence is weak, say so — write `weak`/`needs_more_evidence` claims as
  exactly that.

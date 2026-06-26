---
description: Draft paper/blog results and figures strictly from the InsightFlow ledger
argument-hint: "[what to write: results section | methods | blog | figure]"
---

Use the `writeup-from-ledger` skill. Pull facts only from the ledger and reports:
`uv run insightflow state --format json`, `uv run insightflow benchmark --format json`,
the files in `reports/`, and `.insightflow/decisions.jsonl`. Then draft what I
asked for using only those numbers — never invent or round-trip a figure you did
not read from the ledger. Report what was NOT run and why (compute saved) as part
of the methodology. Describe claim confidence as a heuristic decision signal, and
back final claims with the measured effects and seed counts.

What to write: $ARGUMENTS

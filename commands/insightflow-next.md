---
description: Ask InsightFlow what experiment to run next (grounded in the CLI, not guessed)
---

Use the `adaptive-experiment-scheduler` skill. In the current project run
`uv run insightflow state` then `uv run insightflow plan`. Read the immediate
queue, postponed, avoided, the claim-confidence table, and the warnings, then
tell me:

- the top runs to do now, each tied to the claim and decision it advances,
- what to postpone and why (low decision value right now),
- what to avoid (redundant/dominated),
- any dangerous gaps (missing baseline, generality unverified, budget).

Optimize time-to-insight, not grid completion. Never invent the schedule or a
claim status — read them from the CLI. $ARGUMENTS

---
name: adaptive-experiment-scheduler
description: Use when deciding which ML research experiments, seeds, baselines, or ablations to run next, postpone, or avoid — to reach a research decision fastest under cost and uncertainty. Operates the InsightFlow CLI as the source of truth; never invents the schedule.
---

# Adaptive Experiment Scheduler (InsightFlow)

Use this skill whenever a researcher asks "what should I run next?", "do I need
more seeds?", "which baseline is missing?", "what's safe to skip?", or wants to
plan remaining experiments for a paper. The goal is **time-to-insight**, not grid
completion or best accuracy.

## Iron rule: the CLI is the source of truth

**Never guess the schedule, a claim's status, or a rationale.** Always read them
from InsightFlow:

```bash
uv run insightflow state             # current evidence + claim-confidence table
uv run insightflow plan              # ranked queue + postponed + avoided + warnings
uv run insightflow explain --plan <id>   # per-action scoring breakdown & trade-offs
```

If the project is not set up yet, create configs (`claims.yaml`,
`experiments.yaml`, `resources.yaml`) and run `uv run insightflow validate`, or
start from `uv run insightflow demo --force`.

## Workflow

1. **Get state.** Run `uv run insightflow state`. Note completed vs pending and
   each claim's status (`supported` / `weak` / `needs_more_evidence` / ...).
2. **Get the plan.** Run `uv run insightflow plan`. The immediate queue is what to
   run; postponed/avoided are what to hold or skip.
3. **Explain the top picks.** Run `uv run insightflow explain --plan <id>` and
   translate the scoring into research language: which claim, which decision, why
   now (breadth vs seed, missing baseline, dependency unlock, reviewer risk).
4. **Present, don't execute.** Show the human the top runs, their cost, and the
   rationale. Call out warnings (generality unverified, missing baseline). Get
   approval before any expensive launch. v0.1 is **advisor mode**.
5. **Record results, then replan.** After runs finish:
   `uv run insightflow log-result --experiment-id E --metric accuracy=0.73 --status completed`
   (or `import-wandb`), then run `uv run insightflow plan` again.

## How to phrase a recommendation

Lead with the top action and tie it to a decision:

> **Run `method_a` on cifar100 (seed 0).** It checks external validity for claim
> C1 — currently the main uncertainty is generality, not seed variance. High
> decision value, and it should come before more cifar10 seeds.
>
> **Postpone** `method_a cifar10 seed=4`: extra replication has low decision value
> until generality is established.

## Don'ts

- Don't recommend completing the grid or running all seeds blindly.
- Don't invent claim confidence numbers — read them from `plan`/`state`.
- Don't launch expensive runs without showing the plan and getting approval.
- Don't treat the heuristic claim confidence as a calibrated probability.

# Agent Workflow: Operating InsightFlow as an AI Agent

This document describes how an AI agent — Claude Code, Codex, or any coding
agent — should operate InsightFlow. The same principles apply to humans using the
CLI directly; the agent is simply the interface, not the authority.

---

## The core principle

**The CLI and ledger are the source of truth. You are the interface, never the
authority.**

InsightFlow is not a model the agent reasons over privately. Every scheduling
decision, claim confidence, and run recommendation is produced by the
deterministic CLI. The agent's job is to invoke the CLI, translate its output
into research language, and present recommendations to the human for approval.

---

## Golden rules

1. **Always use `uv`.** Every InsightFlow command is
   `uv run insightflow ...`. Never call Python modules directly, never pip-install
   into the environment without using uv.

2. **Never invent scheduler state.** Do not guess what to run next, what a
   claim's status is, or what a plan says. Read it from the CLI:
   - `uv run insightflow state` before any scheduling recommendation.
   - `uv run insightflow plan` before proposing new runs.
   - `uv run insightflow explain` to justify a recommendation.

3. **Optimize time-to-insight, not grid completion.** The goal is to decide
   research claims with the least time and compute — not to fill every table cell
   or run every seed. Breadth and decisive baselines almost always beat premature
   replication.

4. **Explain in terms of claims and decisions.** Every recommendation must name
   a claim it affects and the decision it informs (e.g., "this checks external
   validity for C1"), not just "it's next in the grid".

5. **Never launch expensive runs without showing the plan.** Surface the plan,
   the cost, and the rationale first, then get explicit human approval. In v0.1,
   InsightFlow is **advisor mode**: InsightFlow recommends; humans launch.

6. **Do not bypass the ledger.** Record results with
   `uv run insightflow log-result ...` or by importing from W&B. Do not
   hand-edit `.insightflow/`.

7. **Report errors faithfully.** If a command errors, report the exact error
   message. Do not pretend it succeeded.

---

## Full session walkthrough

### Step 1 — Get the current state

Always start here. Never assume you know what experiments have completed.

```bash
uv run insightflow state
```

This prints a Markdown report (also written to `reports/state.md`) showing:
- completed, running, and pending experiments
- claim-confidence summary for each claim

Add `--format json` for machine-readable output:

```bash
uv run insightflow state --format json
```

**Read the output.** Note which claims are `needs_more_evidence` and which
experiments are already completed. You will use this to frame the plan.

---

### Step 2 — Generate a plan

```bash
uv run insightflow plan
```

The plan is saved to the ledger and written to `reports/plan_latest.md` and
`reports/claim_confidence.md`. It contains:

- **Immediate queue**: experiments to run now, in ranked order.
- **Postponed**: experiments with low decision value given the current evidence.
- **Avoided**: experiments that are dominated or redundant.
- **Claim-confidence table**: per-claim status and confidence.
- **Warnings**: missing baselines, generality unverified, reviewer risks.

Add `--format json` for programmatic access.

---

### Step 3 — Explain the top picks

```bash
uv run insightflow explain
# or for a specific plan:
uv run insightflow explain --plan PLAN_ID
```

This prints per-action scoring breakdowns: which scoring terms drove the
recommendation, what trade-offs were weighed (breadth vs. seed, missing
baseline, dependency unlock, reviewer risk). Translate this into plain research
language for the human.

---

### Step 4 — Present to the human

Do not launch anything yet. Write a message that grounds every recommendation in
actual CLI output. Example:

> `uv run insightflow state` shows C1 ("method_a beats baseline") is currently
> `needs_more_evidence`: we have 1 completed run on cifar10, no result on cifar100.
>
> `uv run insightflow plan` puts `method_a / cifar100 / seed=0` first in the
> immediate queue. The explain output says the primary driver is "generality" —
> we need at least one other dataset before the claim has any validity beyond
> one setting. Cost: ~1.0 GPU-hour.
>
> **Recommended next run:** `method_a` on `cifar100`, seed 0. This checks
> external validity for C1 and is the highest decision-value action right now.
>
> The plan **postpones** `method_a / cifar10 / seed=1` through `seed=4`: extra
> replication on the same dataset has low value until generality is established.
>
> **Please confirm before I help you launch.**

---

### Step 5 — Record results (after human runs the experiment)

After the human runs the experiment and has the metric value:

```bash
uv run insightflow log-result \
  --experiment-id method_a_cifar100 \
  --metric accuracy=0.79 \
  --status completed \
  --seed 0 \
  --cost 1.1 \
  --wall-time 3960
```

`--metric` is repeatable for multiple metrics:

```bash
uv run insightflow log-result \
  --experiment-id method_a_cifar100 \
  --metric accuracy=0.79 \
  --metric val_loss=0.41 \
  --status completed
```

Or, if results are already in W&B:

```bash
uv run insightflow import-wandb \
  --entity MY_TEAM \
  --project MY_PROJECT \
  --metric accuracy
```

---

### Step 6 — Replan

```bash
uv run insightflow plan
```

The new plan incorporates the recorded evidence. Repeat from Step 3.

---

## The adaptive-experiment-scheduler skill

The `.claude/skills/adaptive-experiment-scheduler/` skill primes the agent with
the workflow above. It is triggered automatically when a researcher asks
questions like "what should I run next?", "do I need more seeds?", "which
baseline is missing?", or "what's safe to skip?".

The skill enforces the same iron rule: always run `state` then `plan` before
making any recommendation, never invent the schedule, and always ground
recommendations in CLI output.

Ready-to-use prompt templates live in `prompts/`:

- `prompts/claude_research_agent_prompt.md` — start a scheduling session.
- `prompts/replanning_prompt.md` — replan after new results land.
- `prompts/review_plan_prompt.md` — critically review a generated plan before
  spending compute.

---

## The guard_expensive_runs.py hook

`.claude/hooks/guard_expensive_runs.py` is a Claude Code `PreToolUse` hook that
watches Bash commands about to be run. If a command matches a pattern for an
expensive training launch — `python train.py`, `torchrun`, `accelerate launch`,
`deepspeed`, `sbatch`, `srun`, `ray submit`, `ray job submit` — and
`reports/plan_latest.md` is either missing or older than 30 minutes, the hook
fires.

The hook has three modes, controlled by the `INSIGHTFLOW_GUARD` environment variable:

| `INSIGHTFLOW_GUARD` | Behavior |
|---------------------|----------|
| `warn` (default) | Allows the command but prints a warning to stderr reminding the agent to run `uv run insightflow plan` first |
| `block` | Denies the command via the PreToolUse JSON protocol (exit 2 + deny decision); the agent must run `plan` first |
| `off` | Hook is disabled entirely; all commands pass through |

The hook is **fail-open**: if the JSON payload from Claude Code is malformed, it
exits 0 and allows the command rather than blocking on a parsing error.

To install the hook, add this to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/guard_expensive_runs.py"
          }
        ]
      }
    ]
  }
}
```

---

## Three operating modes

### Advisor mode (v0.1 — what is built)

The agent recommends; the human decides and launches. The agent runs `state`,
`plan`, and `explain`, translates the output, surfaces warnings, and presents a
prioritized list of next runs with rationale. The human copies the suggested
launch commands and runs them. Results are recorded back with `log-result` or
`import-wandb`.

This is the only mode that exists in v0.1. There are no launchers, no server,
and no autonomous execution.

### Human-approved execution (planned for v0.2)

The agent presents the plan and, after explicit human approval in the
conversation, runs the approved launch command directly. A Slurm or Ray launcher
integration is planned to issue jobs programmatically after human sign-off.
This mode is **not yet built**.

### Guardrailed-autonomous mode (planned for v0.3)

For trusted, low-cost experiments the agent may run the full loop
autonomously — plan, launch, record, replan — subject to per-session cost caps and
the guard hook. This mode is **not yet built**.

---

## Reading a plan output

A plan's Markdown output has clear sections. When presenting to a human:

- Lead with the **top item in the immediate queue** and one sentence on which
  claim it advances and why now.
- Name any **warnings** explicitly — a missing baseline or "generality
  unverified" is a reviewer risk the human needs to know about.
- State the **postponed** items briefly so the human understands what is
  being deferred and why (low decision value right now, not forgotten).
- Do **not** present avoided items as recommendations to revisit.

Never present claim confidence numbers as calibrated probabilities. They are
transparent heuristic ranking signals. Say "the scheduler rates this as the
highest decision-value action" rather than "we are 87% confident in C1".

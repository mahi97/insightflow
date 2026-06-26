# Running an entire research project with an autonomous agent

This guide is for the case where there is **no human researcher in the loop**: an
AI agent (Claude Code, Codex, …) drives a research project from zero to one —
writing the code, defining the claims, running and monitoring experiments,
deciding what to run next, and producing the paper, blog, and figures.

In that setting InsightFlow plays three roles for the agent:

1. **The experiment brain.** The agent does not decide what to run from vibes. It
   runs `insightflow plan` and follows it. This is what stops an autonomous agent
   from blindly running the full grid or burning compute on runs that cannot
   change any claim.
2. **Durable memory across context resets.** An agent's context window is
   ephemeral; the InsightFlow **ledger** (`.insightflow/ledger.db` +
   `decisions.jsonl`) is not. When the agent's context is summarized or a new
   session starts, the ledger still holds every completed run, every pending
   experiment, every plan, and every decision. The agent rehydrates its world
   with `insightflow state`, not from memory.
3. **The audit trail that becomes the paper.** Every plan and decision is logged.
   That log is the methodology section, the "compute saved" figure, and the blog
   narrative — generated from facts, not reconstructed from a fuzzy memory.

> **Mode note.** v0.1 is *advisor mode*: InsightFlow recommends; it does not
> launch or kill runs. In the autonomous setting **the agent is the executor** —
> it runs the training commands itself (via its shell) and records the results.
> InsightFlow tells it *what* to run and *when to stop*; the agent does the
> running — or, for local runs, `uv run insightflow run --execute` launches the
> top experiment and records the result. Slurm/Ray launchers are on the roadmap.

---

## The autonomous research loop

```text
        ┌──────────────────────────────────────────────────────────┐
        │ 1. (re)hydrate:   uv run insightflow state                │
        │ 2. plan:          uv run insightflow plan                 │
        │ 3. read top queue + warnings; pick the next run(s)        │
        │ 4. GUARD: is this run in the immediate queue (not         │
        │    postponed/avoided)? within budget? -> if not, replan   │
        │ 5. launch it yourself (shell / W&B / cluster)             │
        │ 6. record the result:                                     │
        │      uv run insightflow log-result ...    (or import-wandb)│
        │ 7. replan with the new evidence  ── back to step 2        │
        └──────────────────────────────────────────────────────────┘
   Stop when every paper-critical claim is `supported` or `refuted`
   (read the claim-confidence table), or the budget is exhausted.
```

The loop is **claim-terminated, not grid-terminated.** The agent keeps going
until the claims are decided — not until every cell is filled. That is the whole
point: time-to-insight, not grid completion.

---

## Bootstrapping a new project (what the agent does once)

1. **Turn the research idea into claims.** Write `configs/claims.yaml`: one claim
   per thing the paper will assert, with `target_metric`, `minimum_effect_size`,
   `required_seeds`, `importance`, and `reviewer_risk`. These are the agent's
   success criteria.
2. **Enumerate the experiment grid.** Write `configs/experiments.yaml`: every
   `(method, dataset, condition, seed)` cell the agent *could* run, with
   `claim_links`, `dependencies`, `expected_cost`, `expected_time`, and a
   `command` it can actually execute. Include baselines (tag them `baseline`) —
   missing baselines are the #1 reviewer risk and the scheduler rewards filling
   them.
3. **Declare resources/budget.** `configs/resources.yaml`: workers and a
   `budget_gpu_hours`. The planner warns when the queue exceeds it.
4. **Validate, then init.** `uv run insightflow validate` catches bad claim
   links, duplicate ids, and dependency cycles before any compute is spent.
5. **(Optional) seed from existing logs.** If runs already exist in W&B,
   `uv run insightflow import-wandb --entity E --project P --metric M`.

From here the agent enters the loop above.

---

## Guardrails when there is no human to approve

An autonomous agent needs the discipline a human approver would otherwise
provide. Use all three:

- **Hard-block expensive launches without a fresh plan.** Set
  `INSIGHTFLOW_GUARD=block` and wire `.claude/hooks/guard_expensive_runs.py` as a
  `PreToolUse` hook. Now a `python train.py` / `sbatch` / `torchrun` command is
  *blocked* unless a recent `reports/plan_latest.md` exists and the agent has
  consulted it. This forces "plan before you spend."
- **Budget as a stop condition.** Put a real `budget_gpu_hours` in
  `resources.yaml`. Treat the plan's budget warning as a hard stop, and stop the
  loop when cumulative cost (sum of recorded `RunResult.cost`) approaches it.
- **Claim-gated stopping.** After each replan, read the claim-confidence table.
  When a paper-critical claim is decisively `supported`/`refuted`, stop running
  experiments for it — further runs have low decision value by construction.

Never let the loop run open-ended. It must terminate on *claims decided* or
*budget exhausted*, whichever comes first.

---

## Monitoring partial runs (v0.1 reality)

There is no live monitor yet. The agent supplies the monitoring by recording
intermediate metrics as a *running* result with `partial_history`, then asking
the scheduler what to do:

- Log a partial curve (e.g. by polling W&B or reading the trainer's logs) into a
  `RunResult` with `status=running` and `partial_history=[{step, metric}, …]`.
- Run `insightflow plan`. The partial-run policy (`partial.py`) will surface a
  `continue` / `pause` / `stop` / `promote` / `add_seed` / `launch_baseline`
  recommendation for that run, judged by **decision impact** — e.g. "stop: the
  linked claim is already decided" or "launch_baseline: this looks strong but has
  nothing to compare against."
- The agent then acts (kills/continues the job) and records the final result.

---

## From ledger to paper, blog, and figures

Because the ledger is the source of truth, the writing is grounded, not invented:

| Artifact the agent produces | Where it comes from |
| --- | --- |
| **Methods / experimental setup** | `configs/claims.yaml` + `configs/experiments.yaml` (the declared claims and grid) |
| **"What we ran and why" appendix** | `.insightflow/decisions.jsonl` — the full, timestamped decision log |
| **Main results table** | `reports/claim_confidence.md` — each claim's status, effect, and evidence |
| **"Compute saved by adaptive scheduling" figure** | `uv run insightflow benchmark --format json` — InsightFlow vs grid/all-seeds-first (runs and cost to the correct decision) |
| **Claim-confidence-over-time figure** | the `confidence_evolution` series in the benchmark JSON, or successive `plan --format json` snapshots |
| **Blog narrative** | the decision log read in order: what was prioritized, what was postponed, what was avoided, and the moment each claim flipped |

For figures, prefer `--format json` on `state`, `plan`, and `benchmark` and plot
from the structured output. Cite the `state_hash` on each plan so every figure is
reproducible from a known ledger state.

### Honesty the agent must preserve

- Claim confidence is a **heuristic**, not a calibrated posterior — the paper
  should describe it as a decision *heuristic*, and back the final claims with the
  actual measured effects and seed counts (which are in the ledger), not with the
  confidence number alone.
- Report what was **not** run and why (the avoided/postponed lists) — that is a
  feature (compute saved), and hiding it would misrepresent the methodology.

---

## Minimal end-to-end example

```bash
# once
uv run insightflow validate
export INSIGHTFLOW_GUARD=block      # don't launch expensive runs without a plan

# the loop (repeat until claims decided or budget hit)
uv run insightflow state
uv run insightflow plan             # writes reports/plan_latest.md
# -> read the top queue item, confirm it's not postponed/avoided
python train.py --method method_a --dataset cifar100 --seed 0   # agent launches
uv run insightflow log-result --experiment-id method_a_cifar100_s0 \
    --metric accuracy=0.71 --status completed --cost 1.2 --wall-time 3.5
uv run insightflow plan             # replan; did C1's status change?
# ... continue until the claim-confidence table says the paper's claims are decided
```

See also: [agent_workflow.md](agent_workflow.md) (the human-in-the-loop version),
[scheduling_policy.md](scheduling_policy.md), and the
`adaptive-experiment-scheduler` skill in `skills/`.

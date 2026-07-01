# Agent-vs-ledger study

**Question.** Does the InsightFlow interface help a *real* LLM agent reach correct
claim verdicts with fewer experiments than the same agent reasoning unaided? The
synthetic policy benchmark ([`benchmark.py`](../src/insightflow/benchmark.py))
shows the deterministic *scheduler* is efficient; this study asks whether that
efficiency transfers when a capable LLM is the one deciding.

## Design

A within-task A/B over identical worlds:

- **Environment** ([`agent_env.py`](agent_env.py)): the InsightFlow ledger plus a
  hidden simulator ground truth. The agent inspects state, reveals one
  experiment result per `run` (the unit we minimise), then commits verdicts,
  which `score` grades against the hidden truth. The agent never sees the truth;
  the ledger is the single source of observed results.
- **Conditions.** *Guided* agents may consult `insightflow plan` (ranked next
  action + what to postpone/avoid) and `insightflow readiness` (per-claim
  supported/refuted/weak + reviewer attacks). *Naive* agents get the same menu,
  results, and claim definitions but **no** planner and must reason for
  themselves. Both are told to minimise runs while staying correct.
- **Scenarios** (distinct failure modes): `breadth` (truth = supported; needs
  method+baseline across datasets, *not* many seeds on one), `noisy_seeds`
  (supported, but the signal needs enough seeds to separate from noise),
  `refuted` (the method does **not** beat the baseline — the agent must not
  overclaim and should stop early on a decisive counterexample).
- **Agent model.** Claude Opus (via the Claude Code Agent tool), one agent per
  world, identical prompts except the guidance paragraph.

## Reproduce

```bash
# 1. create the worlds
for scen in breadth noisy_seeds refuted; do
  for cond in guided naive; do
    uv run python eval/agent_env.py setup --scenario $scen --seed 0 \
      --dir /tmp/if_agents/${scen}_${cond}
  done
done
# 2. run one LLM agent per world with the prompts in this file
#    (guided prompt includes the `insightflow plan/readiness` paragraph; naive omits it)
# 3. aggregate
uv run python eval/agent_study.py --dir /tmp/if_agents
```

## Metrics

- **runs-to-decision** (primary): experiments revealed before the agent commits
  its final, correct verdict — lower is better.
- **correct rate**: fraction of worlds whose committed verdicts all match ground
  truth.
- **wrong decisions**: verdicts committed against the ground truth (overclaims /
  misclaims) — the failure the readiness gate is meant to prevent.

## Honesty notes

- These are capable Opus agents; a strong agent often reasons well *without* the
  tool, so the interesting signal is where the naive agent **over-collects**
  (runs redundant seeds it can't tell are redundant) or **overclaims** (declares
  generality from one dataset). Expect the guided advantage to concentrate there,
  not everywhere.
- Small n (one agent per world per seed in the committed pilot). Treat the
  numbers as a **pilot**, not a powered result; scale seeds for a real study.
- The naive condition is asked not to call the planner; this is prompt-enforced,
  not sandboxed. A fully isolated harness (planner binary absent) is future work.

## Results (pilot, n=1 agent per world, Opus, 2026-07-01)

| world | condition | runs | verdict | correct? |
|-------|-----------|------|---------|----------|
| refuted | guided | 4 | refuted | ✓ |
| refuted | naive | 4 | refuted | ✓ |
| breadth | guided | 13 | supported | ✓ |
| breadth | naive | 15 | supported | ✓ |
| noisy_seeds | guided | 12 | refuted | ✗ (truth: supported) |
| noisy_seeds | naive | 14 | refuted | ✗ (truth: supported) |

By condition: both **2/3 correct**; mean runs among correctly-decided worlds
**guided 8.5 vs naive 9.5**.

**Honest reading — this is a modest, mixed result, not a win for the tool:**

1. **A strong agent often needs no help.** On the unambiguous `refuted` scenario
   both conditions used 4 runs and were correct. On `breadth` both were correct;
   guided used 13 vs 15 (a small saving), and `readiness` actually surfaced
   "supported" after **5** runs — but both agents (rightly) kept going to satisfy
   the claim's explicit "3 seeds across all datasets" bar and to close the open
   reviewer attacks before committing. So the run-count advantage is real but
   small with a capable base agent.

2. **`noisy_seeds` is confounded by the environment, not a signal about the
   tool.** The true per-cell effects are both >= 0.02 (so ground truth =
   supported), but the noisy condition's menu is under-powered (2 baseline seeds,
   sigma ~0.035), so the *observed* effect looked like ~+0.007 and **both** agents
   refuted. The tool's `readiness` correctly reported **weak** (it did *not*
   overclaim), and the planner recommended `claim_refinement` — the honest state.
   But the original env only offered a binary supported/refuted verdict, forcing
   both agents to over-commit to refuted. That is an **environment flaw**. It is
   fixed here (an `inconclusive` verdict now exists); a fair re-run with the
   abstain option and a properly-powered noisy menu is future work.

**Takeaway.** With a strong Opus agent on these small tasks the InsightFlow
interface did not change *correctness* and gave only a modest run-count saving;
its clearest observed contributions were (a) surfacing the reachable verdict
earlier and (b) staying at "weak" rather than overclaiming where the evidence was
genuinely insufficient. We are **not** claiming a large agent-vs-ledger effect
from this pilot. The synthetic *policy* benchmark (where the decision uses the
shared readout) remains the stronger, higher-n evidence for the scheduler itself.

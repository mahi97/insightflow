# Agent-vs-ledger evaluation harness (illustrative pilot)

This harness measures whether a real coding agent (Claude Code, Codex, …) driving
InsightFlow decides research claims with **less compute** than the same agent
*without* the decision layer. It is the reproducible scaffolding behind the
"≈50–69% compute saved" figure quoted in the docs.

> **Honesty note.** That figure is an **illustrative pilot**, not a powered
> result: a small number of trials with strong models, comparing a guided agent
> (InsightFlow CLI in the loop) to an unaided agent on a few synthetic scenarios.
> It requires *running real LLM agents*, so it is **not** part of the automated
> test suite or CI. Treat it as a qualitative demonstration; a powered study
> (more trials, weaker models, refuted scenarios, significance testing) is future
> work. See `docs/limitations.md` and `paper/claims.md` (claim C6).

## Protocol

1. **Build a sandbox** with a hidden ground truth, a fresh ledger, and an oracle
   that reveals a result only when an experiment is "run":

   ```bash
   uv run python eval/agent_harness/make_sandbox.py <scenario> <seed> <sandbox_dir>
   # scenario in: breadth | expensive_branch | dependency_unlock | reviewer_baseline
   #              | noisy_seeds | refuted | mixed_multi_claim
   ```

   This writes `configs/` + an initialized ledger, plus `run_exp.py` (runs a chosen
   experiment against the hidden truth and records it) and `show_results.py`.

2. **Drop a real agent into each sandbox**, two arms on the *same* sandbox/oracle:
   - **guided**: the agent may call `uv run insightflow state|plan|readiness` and
     follows the plan; it runs experiments via `run_exp.py`.
   - **naive**: the agent gets only the configs + `run_exp.py`/`show_results.py`
     and no scheduler — it decides on its own.
   Both are told to decide the claim(s) with the fewest runs, then stop.

3. **Measure objectively from the ledger** (not self-report): number of runs and
   total `cost` in each sandbox, plus whether the final verdict matches the
   ground truth.

## Why it's leak-free

The agent only learns a result by *running* an experiment through the oracle; the
hidden truth lives in the package (`insightflow.simulator`), not in the sandbox.
Ground truth = the verdict the full history supports. The guided and naive arms
share the same sandbox and oracle, so the only difference is the decision layer.

# Evaluation methodology

InsightFlow is a claim-centered research decision layer for AI-assisted ML
research. It helps researchers and coding agents decide which evidence to acquire
next, when to stop, what to postpone, what to avoid, and which claims are
currently supported, refuted, weak, or still uncertain.

This document describes how we evaluate that decision layer. The thing under test
is **a scheduling/decision policy over a claim-evidence ledger**, not a model, an
optimizer, or a paper generator. We therefore do **not** measure final task
accuracy; we measure how *efficiently and reliably* a policy reaches the *correct
research decision* about a set of falsifiable claims, where "correct" is defined
by a ground truth the policy cannot see.

A note on novelty, stated up front because honesty is the project's core
principle: the contribution evaluated here is the **integration and the
objective** — claim-level state, evidence requirements, reviewer-risk-aware
scheduling, breadth-vs-replication handling, a claim graph, a ledger-backed agent
interface, replay evaluation for research trajectories, and paper-readiness
reporting. The math is not new. The value-of-information scorer is a **myopic
one-step approximate EVI per unit cost** (deterministic Gauss-Hermite
quadrature), not a multi-step optimal plan, and nothing here is claimed to be
globally optimal.

All evaluations are **deterministic**: every synthetic project is sampled from a
`random.Random` keyed by `(project_seed, experiment_id)`, so re-running the
benchmark reproduces the numbers below exactly.

---

## 1. The three evaluation protocols

| protocol | code | what it answers |
| --- | --- | --- |
| Synthetic-scenario benchmark | `simulator.py`, `benchmark.py` | On controlled tasks with hidden ground truth, how many runs/how much compute does each policy need to reach the correct decision, and how robust is it across *different* failure modes? |
| Offline multi-policy replay | `replay.py` | On a project whose runs are *already known* (imported from W&B / CSV / MLflow), would InsightFlow have reached the full-history decision in fewer runs than the order the runs were actually performed in? |
| Agent-vs-ledger | `simulator.py` policies (deterministic proxy) + manual real-LLM runs | Does giving an agent the ledger + scheduler reduce the compute it spends to reach a correct decision, vs. an unaided agent? |

The first two are fully automated and reproducible from the CLI. The third uses a
**deterministic proxy** in CI (the scheduler policy stands in for an agent that
follows the ledger) and **real LLM comparisons are run manually** (small n,
illustrative).

---

## 2. The seven synthetic scenarios

The benchmark does **not** average over one task. A single naive heuristic can tie
InsightFlow on the one task it happens to suit; the point of a suite is to expose
the task where each heuristic *fails*. Each scenario in
`simulator.py::SCENARIOS` is constructed to stress one specific failure mode of
experiment scheduling. Every scenario has **hidden ground truth** (true per-cell
means, seed noise, costs, dependencies) that the policy cannot read; the policy
only observes the simulated run results it chooses to launch.

| scenario | generator | failure mode it stresses | correct decision |
| --- | --- | --- | --- |
| `breadth` | `generate_project` | **Premature replication.** The method truly beats the baseline on every dataset, so generality needs *breadth* (one method+baseline pair per dataset), not many seeds on one dataset. Punishes policies that pile seeds. | C1 supported |
| `expensive_branch` | `generate_expensive_branch` | **Cost-blindness.** One dataset (`tinyimagenet`) is 5x more expensive and listed first, so grid-order hits it early; the cheap datasets decide the claim just as well. Punishes policies with no cost term. | C1 supported |
| `dependency_unlock` | `generate_dependency_unlock` | **Dependency myopia.** A single cheap ablation unlocks the runs that actually decide the claim; four distractor runs carry no decision value. Punishes order-/random-based policies that waste steps on distractors. | C1 supported |
| `reviewer_baseline` | `generate_reviewer_baseline` | **Missing baseline / over-running.** Many method seeds are available but the claim cannot be decided without a baseline. Punishes all-seeds-first/grid that pile method seeds before pairing a baseline. | C1 supported |
| `noisy_seeds` | `generate_noisy_seeds` | **Mis-allocated replication.** One dataset is clean, one is high-variance with a smaller effect; only the noisy one needs replication. Punishes both under-seeding the noisy cell and over-seeding the clean one. | C1 supported |
| `refuted` | `generate_refuted` | **Chasing a non-effect.** The method genuinely does *not* beat the baseline (true effect ~ -0.05); the correct decision is *refuted*. Punishes policies that keep spending in search of an improvement that does not exist. | C1 refuted |
| `mixed_multi_claim` | `generate_mixed_multi_claim` | **Single-objective tunnel vision.** Two claims with different evidence needs: C1 (accuracy, truly supported) and C2 (a second method's robustness, truly refuted). The correct verdict requires deciding *both* — supporting C1 while not overclaiming C2. Punishes a scheduler that chases one claim or treats all claims alike. | C1 supported, C2 refuted |

Ground truth per claim is computed in `SimProject.ground_truth_statuses()`: for
each claim it averages the true method-minus-baseline effect across the claim's
cells and labels it `supported` (effect >= `minimum_effect_size`), `refuted`
(effect <= 0), or `weak` (in between), oriented by the claim's
`desired_direction`.

---

## 3. Policies

All policies are pure functions `(State, SimProject, RunnerContext) -> exp_id`
registered in `simulator.py::POLICIES`. They differ *only* in which experiment
they pick next; they all read claim status through the same shared confidence
readout (`scoring.compute_claim_confidence`), so the comparison is about
*scheduling*, not about each policy having a different notion of "decided".

### 3.1 The policy under test and the upper bound

- **`insightflow`** — picks the top runnable action from
  `scheduler.build_plan(state)` (`launch` / `add_seed` / `launch_baseline`).
- **`oracle`** — an upper bound that *knows the ground truth* and decides claims
  with the fewest runs by completing method+baseline cells to maximize breadth
  fastest. Not achievable in practice; it sets the denominator for the
  worst-case ratios below.

### 3.2 Baseline policies (`benchmark.py::NAIVE`)

Each baseline is a defensible heuristic a researcher might actually use:

| policy | rule |
| --- | --- |
| `grid` | Run experiments in config order (run the whole grid). |
| `all_seeds_first` | Finish every seed of a cell before moving on (depth-first). |
| `all_tasks_first` | One seed of every cell before deepening any (breadth-first by seed). |
| `random` | Uniformly random pending experiment (seeded, deterministic). |
| `cheap_first` | Lowest `expected_cost` first. |
| `fastest_first` | Lowest `expected_time` first. |
| `baseline_first` | Baselines before methods. |

### 3.3 Ablation policies (`benchmark.py::ABLATIONS`)

An ablation is **InsightFlow with exactly one scoring component disabled**,
constructed by `_insightflow_with(mods)`, which copies the policy with one weight
set to zero and otherwise runs the unchanged scheduler. This isolates the
contribution of each component of the objective.

| ablation | component disabled (`Policy` field) | what it tests |
| --- | --- | --- |
| `ablate_reviewer_risk` | `weight_reviewer_risk = 0` | Does reviewer-risk-aware scheduling (prioritizing missing baselines / generality the way a reviewer would attack) matter? |
| `ablate_breadth_penalty` | `weight_premature_replication_penalty = 0` | Does the explicit penalty for replicating before breadth is established matter? |
| `ablate_cost` | `lambda_cost = 0` | Does putting cost in the denominator (value *per unit cost*) matter? |
| `uncertainty_only` | every term except `weight_uncertainty` set to 0 | What happens if you schedule on raw uncertainty reduction alone — the "just reduce variance" baseline that ignores decision value, dependencies, reviewer risk, redundancy, replication, and seed value? |

The headline finding from the ablations is that **`uncertainty_only` fails the
multi-claim scenario** (it solves only 3/7), confirming that the integrated
objective — not any single term — is what makes the policy robust. The other
three ablations still solve 7/7 on this suite, i.e. on these tasks no single one
of those components is individually load-bearing for *correctness*, though they
affect cost and the order of acquisition (see the single-project cost column in
§7).

---

## 4. Metrics

For each `(scenario, policy, project)` run, `simulator.run_policy` replays the
project up to `max_steps`, recording (`PolicyRun`):

- **runs-to-correct-decision** (`decided_step`) — the step at which the shared
  confidence readout's verdict matches the hidden ground truth for *every*
  decidable claim. Lower is better. This is the primary metric.
- **cost-to-correct-decision** (`cost_at_decision`) — cumulative `expected_cost`
  at that step.
- **runs launched** and **runs avoided** (`grid_size - runs_launched`).
- **wrong-decision rate** — the fraction of runs in which the policy ever
  asserted a `supported`/`refuted` verdict that contradicts ground truth. This is
  the safety metric: a fast policy that confidently decides *wrong* is worse than
  a slow one. In the suite below every policy has a wrong rate of **0.00** — the
  shared confidence model is conservative (it requires breadth before it will
  call a cross-condition claim decided), so policies differ in *speed*, not in
  *correctness of the verdict they report*.
- **claim-confidence evolution** — the per-step confidence trace, reported for
  InsightFlow so the curve toward the decision is auditable.

Across scenarios (`benchmark.py::run_scenarios`) we additionally report, per
policy:

- **mean runs-to-decision** across the seven scenarios;
- **worst-case ratio to the oracle** (`max` over scenarios of
  `policy_runs / oracle_runs`) — the single most informative robustness number,
  because it surfaces the task on which a policy is worst, not the task on which
  it looks good;
- **scenarios solved** (`solved == total`, i.e. reached the correct decision on
  every project of the scenario within `max_steps`).

---

## 5. Robustness results (real, measured)

Captured from `uv run insightflow benchmark --all-scenarios --projects 3`
(3 synthetic projects per scenario, up to 40 steps per policy). These are the
real numbers from this repository, not illustrative ones.

### 5.1 Per-scenario, InsightFlow vs grid and best naive baseline

| scenario | if_runs | grid_runs | %saved_vs_grid | %saved_vs_best_naive | %cost_saved_vs_best | oracle |
| --- | --- | --- | --- | --- | --- | --- |
| breadth | 5.0 | 11.0 | +54.5% | +0.0% | +8.3% | 4.0 |
| expensive_branch | 4.0 | 8.0 | +50.0% | +20.0% | +35.7% | 4.0 |
| dependency_unlock | 5.0 | 9.0 | +44.4% | +0.0% | +0.0% | 5.0 |
| reviewer_baseline | 4.0 | 12.0 | +66.7% | +0.0% | +0.0% | 4.0 |
| noisy_seeds | 7.7 | 15.3 | +50.0% | -4.5% | -2.9% | 7.7 |
| refuted | 4.0 | 10.0 | +60.0% | +20.0% | +21.7% | 4.0 |
| mixed_multi_claim | 8.0 | 20.0 | +60.0% | +0.0% | +0.0% | 8.0 |

**Overall: InsightFlow saves 55.1% of runs vs grid, averaged across scenarios.**

Read the `%saved_vs_best_naive` column honestly: on several scenarios the *best*
naive policy for *that scenario* ties InsightFlow (+0.0%). That is expected and
intended — for any single task there is usually a heuristic tuned to it. On
`noisy_seeds` InsightFlow is slightly *behind* the per-scenario best naive
(-4.5%). The robustness table below is where the integration earns its keep.

### 5.2 Robustness summary (the real story)

`worst_vs_oracle` is each policy's worst-case runs relative to the oracle across
*all* scenarios; `mean_runs` is its mean runs-to-decision over the suite.

| policy | mean_runs | worst_vs_oracle | scenarios_solved |
| --- | --- | --- | --- |
| oracle | 5.24 | 1.00x | 7/7 |
| **insightflow** | **5.38** | **1.25x** | **7/7** |
| ablate_reviewer_risk | 5.38 | 1.25x | 7/7 |
| ablate_breadth_penalty | 5.38 | 1.25x | 7/7 |
| ablate_cost | 5.38 | 1.25x | 7/7 |
| uncertainty_only | 4.50 | 1.25x | **3/7** |
| grid | 12.19 | 3.00x | 7/7 |
| all_seeds_first | 11.62 | 3.00x | 7/7 |
| all_tasks_first | 6.19 | 1.80x | 7/7 |
| random | 9.29 | 2.50x | 7/7 |
| cheap_first | 10.19 | 2.75x | 7/7 |
| fastest_first | 10.19 | 2.75x | 7/7 |
| baseline_first | 9.76 | 2.75x | 7/7 |

How to read this:

- **InsightFlow is the best non-oracle policy that solves every scenario**: mean
  ~5.4 runs-to-decision, worst case **1.25x** the oracle, **7/7 solved**. The
  closest robust naive policy (`all_tasks_first`) is 1.80x worst-case; grid is
  3.00x.
- **`uncertainty_only` has a *lower* mean (4.50) but solves only 3/7.** This is
  the trap the suite is designed to catch: a policy can look cheap on average
  precisely because it gives up / mis-decides on the hard scenarios (it fails
  `mixed_multi_claim` and others). Mean alone is misleading; "solved" and
  "worst-case" are what matter. This is direct evidence that the *integrated*
  objective — decision value + dependency + reviewer risk + redundancy/replication
  penalties + seed value, not uncertainty alone — is what buys robustness.
- The three single-component ablations match InsightFlow on this suite's
  *coarse* runs-to-decision metric (5.38 / 1.25x / 7/7), so the suite does not
  separate them on *correctness*; their effect shows up in *cost* and acquisition
  order on the single-project breakdown in §7.

---

## 6. Offline multi-policy replay protocol

`replay.py` is the leak-free, counterfactual evaluation used on **real** projects
(runs imported from W&B / CSV / MLflow, where the results are already known). It
answers: *given the runs that were actually performed, would InsightFlow have
reached the same decision sooner?*

The protocol (in `replay.replay`):

1. **Dedup** the history to one result per experiment (last occurrence wins), so
   every trajectory evaluates the same evidence per experiment.
2. **Ground truth = the full-history verdict.** Compute claim confidence over the
   *complete* deduped history; the decided claims (`supported`/`refuted`) are the
   ground truth. If the full history decides nothing, there is nothing to replay
   against and the command says so.
3. **Reveal only what each policy selects.** Each policy is a function over
   results that have been *revealed so far*; a result is revealed only when a
   policy chooses to "run" it (and only if it exists in the recorded history —
   you can only replay runs that were actually performed). No policy can peek at
   an unrevealed result. This is what makes it counterfactual and leak-free.
   - **`actual`** reveals in real arrival order (by `finished_at`, else file
     order).
   - **`insightflow`** repeatedly asks `scheduler.build_plan` what to run next and
     reveals that result if it exists, until the claims are decided.
   - Non-adaptive comparators **`grid`, `random`, `cheap_first`, `seeds_first`**
     each impose a fixed ordering on the same history.
4. Report, per policy, the **run index at which the ground-truth decision is
   reached** (`None` if never), plus `runs_saved = actual_decided_at -
   insight_decided_at`.

### Worked replay result (real, captured)

Built by importing a 9-run CSV history (`import-csv`) for a three-dataset
generality claim, where the *actual* arrival order is the suboptimal "all method
seeds first, baselines last" ordering. From `uv run insightflow replay`:

```
# Offline replay (9 recorded runs)

Ground-truth decision (from full history): {'C1': 'supported'}
Actual order decided at run:     8
InsightFlow order decided at run: 4
InsightFlow would have saved 4 run(s) to reach the same decision.

Runs-to-decision by replay policy (lower is better):
  actual         8
  insightflow    4
  grid           8
  random         7
  cheap_first    6
  seeds_first    5
```

InsightFlow reaches the full-history decision at run **4** vs the actual order's
run **8** (4 runs saved), and beats every non-adaptive ordering. Its acquisition
order shows *why* — it pairs a method with its baseline on a new dataset before
replicating (`method_a_cifar10_s0`, `baseline_a_cifar10_s0`, `method_a_svhn_s0`,
`baseline_a_svhn_s0`), i.e. breadth + missing-baseline first. The end-state
`readiness` then reports C1 as effectively `supported` and the project as
paper-ready. The full CSV-import + replay walkthrough is in
[docs/examples.md](examples.md).

---

## 7. Single-project benchmark (cost breakdown)

`uv run insightflow benchmark --steps 20 --projects 3` runs the default
`breadth` project (grid size = 18 runs each) and adds a **cost@decision** column
that the all-scenarios robustness table does not. Real captured numbers:

| policy | decided@ | cost@decision | runs | avoided | wrong | solved |
| --- | --- | --- | --- | --- | --- | --- |
| oracle | 4.0 | 3.8 | 4.0 | 14.0 | 0.00 | 3/3 |
| insightflow | 5.0 | 4.4 | 5.0 | 13.0 | 0.00 | 3/3 |
| all_tasks_first | 5.0 | 4.8 | 5.0 | 13.0 | 0.00 | 3/3 |
| ablate_reviewer_risk | 5.0 | 4.4 | 5.0 | 13.0 | 0.00 | 3/3 |
| ablate_breadth_penalty | 5.0 | 4.4 | 5.0 | 13.0 | 0.00 | 3/3 |
| ablate_cost | 5.0 | 4.6 | 5.0 | 13.0 | 0.00 | 3/3 |
| uncertainty_only | 5.0 | 4.4 | 5.0 | 13.0 | 0.00 | 3/3 |
| random | 6.0 | 5.8 | 6.0 | 12.0 | 0.00 | 3/3 |
| grid | 11.0 | 11.2 | 11.0 | 7.0 | 0.00 | 3/3 |
| all_seeds_first | 11.0 | 11.2 | 11.0 | 7.0 | 0.00 | 3/3 |
| cheap_first | 11.0 | 9.8 | 11.0 | 7.0 | 0.00 | 3/3 |
| fastest_first | 11.0 | 10.6 | 11.0 | 7.0 | 0.00 | 3/3 |
| baseline_first | 11.0 | 10.6 | 11.0 | 7.0 | 0.00 | 3/3 |

Note `ablate_cost` reaches the decision in the same 5 runs but at a *higher*
cost@decision (4.6 vs 4.4): with `lambda_cost = 0` the scheduler stops preferring
the cheaper of two equally-informative runs. That is the cost term doing its job,
visible here even though the coarse runs-to-decision metric does not separate it.
The wrong-decision rate is **0.00** for every policy.

---

## 8. Agent-vs-ledger evaluation protocol

The question here is different from §5–7: not "which scheduling rule is best" but
"does exposing the ledger + scheduler to an **agent** change its compute spend?"
InsightFlow exposes the same logic to agents through `mcp_server.py` (MCP tools:
`insightflow_state`, `insightflow_plan`, `insightflow_explain`,
`insightflow_validate`, `insightflow_log_result`, `insightflow_replay`,
`insightflow_readiness`) and a Claude Code plugin (skills + commands).

Two tiers, by design:

- **Deterministic proxy (in CI, reproducible).** An agent that *follows the
  ledger* is modeled by the `insightflow` scheduler policy; an *unaided* agent is
  modeled by a naive ordering (`grid` / `random`). The §5–7 benchmark *is* this
  proxy comparison: it is exactly the gap between following the scheduler and not.
  The proxy is deterministic, so it can gate CI and ship as a number anyone can
  reproduce. It deliberately abstracts away LLM stochasticity, prompt sensitivity,
  and tool-use errors — it measures the *decision logic*, not the model.
- **Real LLM comparisons (run manually, small n, illustrative).** Real
  Claude/Sonnet agents drive the same CLI on the same tasks, once with the
  InsightFlow tools available and once without. In the runs we performed, the
  ledger-aided agent **saved 50–69% of compute with no loss in correctness** on
  the tasks tested. This is an honest, small-n, illustrative result — not a
  controlled study with significance claims, and not a guarantee. We report it as
  evidence of direction, and keep it manual because it depends on a live model.

The reason for the two tiers is honesty about what is reproducible: the
deterministic proxy is what we stand behind as a measured, repeatable number; the
real-LLM figure is a manually-collected illustration of the same effect with a
live agent.

---

## 9. Threats to validity (honest caveats)

- **Synthetic ground truth.** Scenarios are generated from a known model, so they
  reward policies whose inductive bias matches that model (breadth-beats-
  replication, cost-sensitivity, dependency structure). They are *constructions
  that isolate failure modes*, not samples from real research projects. The replay
  protocol (§6) is the complement: it runs on real, already-performed histories.
- **Shared confidence readout.** All policies decide via the same
  `compute_claim_confidence`, so the benchmark isolates *scheduling* and cannot
  credit or blame a policy for a different verdict model. The verdict model itself
  is evaluated separately by calibration (below).
- **Myopic scorer, not optimal.** The value-of-information scorer is a one-step
  approximate EVI per unit cost (deterministic 5-point Gauss-Hermite quadrature
  in `bayes.py`), not a multi-step lookahead and not a guaranteed-optimal plan.
  The oracle column shows the remaining gap (~1.25x worst case).
- **Calibration is mode-specific.** The default `heuristic` confidence is a
  **ranking score, not a probability** — it should not be read as a calibrated
  P(claim true). The opt-in `bayes` mode is a **calibrated probability** under the
  finite-population Normal–Normal model's stated assumptions: an independent
  reliability experiment (N = 200,000 draws from the model) measured an Expected
  Calibration Error of **0.011** (well under 0.05). The repository's
  `tests/test_bayes.py::test_posterior_is_calibrated` is a fast in-suite version
  of the same check.
- **Small n for the agent eval.** The 50–69% real-LLM figure is illustrative
  (§8).

---

## 10. Reproducing every number here

```bash
# 7-scenario robustness suite (§5) — produces the robustness table verbatim
uv run insightflow benchmark --all-scenarios --projects 3

# single-project cost breakdown (§7)
uv run insightflow benchmark --steps 20 --projects 3

# offline replay on a real/imported history (§6) — see docs/examples.md for the
# CSV used to produce the worked result
uv run insightflow replay -C /path/to/project

# calibration check for bayes mode (§9)
uv run pytest tests/test_bayes.py -k calibrated
```

Project health backing these claims (measured in this repository): **25 source
modules,  passing tests, ruff and mypy clean** (`uv run pytest`,
`uv run ruff check src/`, `uv run mypy src/insightflow`).

---

## What this evaluation does and does not claim

- It **does** show that an integrated, claim-centered, reviewer-risk- and
  cost-aware scheduler reaches correct research decisions in fewer runs than naive
  baselines, robustly across distinct failure modes, and that the integration
  (not any single term) is what makes it robust.
- It **does** show, via leak-free replay, that the same logic would have saved
  runs on a real, already-performed history.
- It does **not** claim new math, global optimality, or that InsightFlow is an
  AutoML system, an HPO scheduler, an experiment tracker, or an autonomous
  researcher. InsightFlow optimizes the *acquisition of evidence required for
  falsifiable paper claims*, with auditable state and explicit claim-evidence
  linkage — that objective, and the integration that serves it, is what is being
  evaluated.

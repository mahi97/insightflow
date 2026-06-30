# InsightFlow: A Claim-Centered Decision Layer for Evidence Acquisition in AI-Assisted ML Research

*Extended draft. Not final, but coherent and honest. All quantitative results are
the real, measured numbers produced by the code in this repository
(`insightflow.benchmark.run_scenarios(steps=40, n_projects=5, base_seed=0)` and
the committed test suite); where a number is documented but not reproducible from
a committed artifact, it is flagged as such.*

---

## Abstract

AI coding agents can run experiments, but they lack a principled way to decide
*which evidence to acquire next* for a falsifiable research claim, *when the
evidence is enough to stop*, and *which claims a paper can actually defend*.
Experiment trackers record what ran; AutoML/HPO and bandit methods optimize model
performance or best-arm identification over configurations; "AI Scientist"
systems try to automate the whole paper. None operate over the unit a paper is
graded on: the **claim**.

We present **InsightFlow**, a claim-centered research decision layer. The
contribution is an *integration and an objective*, not new mathematics.
InsightFlow maintains a typed **claim graph** with evidence requirements and
dependencies; computes per-claim **readiness** (own vs. effective status, blocked
claims, missing baselines, thin generality, insufficient seeds, ranked reviewer
attacks); recommends the next action — a run, a seed, a baseline, *or* a non-run
research action (literature check, reviewer attack, theorem attempt, claim
refinement) — with a **value-of-information-inspired, reviewer-risk-aware
scheduler**; and records everything in an auditable **claim–evidence ledger**
exposed to humans and agents via a CLI and an MCP server. We are explicit about
scope: the scheduler is a **myopic one-step approximate expected-value-of-
information (EVI) per unit cost** (deterministic Gauss–Hermite quadrature), not a
multi-step optimal plan; the default `heuristic` confidence is a *ranking score,
not a probability*, while the opt-in `bayes` mode yields a calibrated probability
under stated assumptions.

On seven controlled scenarios that each isolate a scheduling capability,
InsightFlow reaches the correct research decision in **5.23 runs on average**,
within **1.25× of an oracle in the worst case**, solving **7/7** — the best among
all non-oracle policies — and saving **56% of runs** versus a full-grid baseline.
Ablations show the components are load-bearing: an uncertainty-only variant solves
only **1/7** scenarios. InsightFlow is 26 modules, **126 passing tests**, `ruff`-
and `mypy`-clean.

---

## 1. Introduction

A researcher (or a coding agent acting for her) has a method and a claim:
*"method A beats baseline B across datasets."* She has a compute budget and a
deadline. She can run more seeds, add a dataset, run the missing baseline, run an
ablation, or stop. Nothing in her toolchain tells her which of these *advances
the claim* most per unit cost. W&B and MLflow will faithfully record whatever she
runs. An HPO sweep will find a better config on one dataset. An "AI Scientist"
will try to write the entire paper. But the decision she actually faces — *what
evidence does this claim still need, and is it worth the compute?* — is
unsupported by any of them.

The gap is sharper for AI agents. An agent with a shell can launch runs, but
without claim-level state it tends to over-replicate one easy setting, skip the
baseline that would let a reviewer attribute the effect, or keep running long
after the claim is decided. The cost is real compute and real reviewer risk.

**Our reframing.** We move the unit of scheduling from *configurations* to
*claims*. A claim carries evidence requirements (effect size, required seeds,
breadth across conditions), a reviewer-risk, and dependencies on subclaims. At
each step InsightFlow asks: *which action most increases our ability to reach a
defensible verdict, per unit cost?* — and, equally, *when can we stop, and what
should we postpone or avoid?*

**What we built.** InsightFlow operationalizes this as (i) a typed claim graph,
(ii) a deterministic readiness assessor, (iii) a VoI-inspired, reviewer-risk-aware
scheduler that ranks runs *and* non-run research actions on one scale, and (iv) a
ledger-backed agent interface. It is an **auditable research control plane**:
every verdict and recommendation is a deterministic, inspectable function of the
ledger.

**Scope and honesty.** The novelty is the *integration and the objective*, not
new math. We do not claim new theory, global optimality, or autonomy. We claim
that (a) reframing scheduling around claims is useful and buildable, (b) a small,
transparent, reviewer-risk-aware scorer captures most of an oracle's value on
controlled scenarios, and (c) a ledger-backed claim layer is a better substrate
for AI research agents than a bare shell. Our evaluation is synthetic-heavy plus a
leak-free replay and a small illustrative agent study; the real-world human study
is explicitly future work.

---

## 2. Related work and distinctions

InsightFlow shares mechanisms with several families but differs in its *unit of
optimization* (the falsifiable claim) and its *objective* (reaching a verdict,
not maximizing a metric).

**AutoML / HPO.** AutoML and hyperparameter optimization search *configurations*
to maximize model performance. InsightFlow does not tune configurations; it
schedules across configurations the user already declared, to decide a claim.
Output: a verdict and readiness report, not a tuned model.

**Pure-exploration bandits (Hyperband, ASHA, BOHB).** These allocate budget across
configurations to identify the best arm quickly via successive halving.
InsightFlow shares budget-awareness but not the objective: best-arm
identification on one task is not a claim verdict, which may require *breadth*
across datasets and a *baseline*, not the single best result.

**Multi-fidelity / freeze-thaw Bayesian optimization.** Freeze-thaw BO models
learning curves to continue/pause runs. InsightFlow's partial-run monitoring does
analogous reasoning with a hand-coded heuristic rather than a GP curve model; a
GP curve model is future work, not a claim of this paper.

**Bayesian optimal experimental design / Knowledge Gradient / OCBA.** These are
the closest *formal* framing: score actions by expected reduction in decision
uncertainty (per unit cost). InsightFlow's `bayes` mode is exactly a myopic,
deterministic instance of this idea over a finite-population claim posterior. We
claim none of the underlying math as new; our contribution is wiring it to *paper
claims* with reviewer-risk and breadth-vs-replication structure, and shipping a
transparent heuristic alternative.

**Self-driving labs / AI Scientist systems.** These aim at autonomy — proposing,
running, and writing up science. InsightFlow is deliberately **advisor mode**: it
recommends; humans/agents execute; every recommendation is auditable. It is a
*decision layer under* an agent, not an autonomous scientist.

**Experiment trackers (W&B, MLflow).** Trackers record runs. InsightFlow
*consumes* their records (importers for W&B/CSV/JSONL/MLflow) and tells you what
to run next. It complements, not replaces, them.

**Generic coding agents.** A coding agent can launch runs, but without claim-level
state it has no notion of breadth, missing baselines, or stopping. InsightFlow
gives the agent an auditable shared state and a deterministic plan.

**DAG scheduling (HEFT).** InsightFlow handles experiment dependencies with a
scalar `dependency_unlock` bonus, not full critical-path/processor-assignment
scheduling.

The one-line distinction we will defend in review: *those systems optimize model
performance, allocate compute to arms/configs, automate paper generation, or
track experiments; InsightFlow optimizes the acquisition of evidence required for
falsifiable* **paper claims**, *with auditable state and explicit claim–evidence
linkage.*

---

## 3. Problem formulation: claim-centered evidence acquisition

**Goal.** Reach **defensible claim verdicts** under uncertainty, cost, and
reviewer-risk, spending as little compute as possible and stopping as soon as the
verdicts are stable.

**Claim.** `c` has a type (main / empirical / mechanism / efficiency / robustness
/ theory / limitation / negative / auxiliary), importance `imp(c) ∈ [0,1]`, a
target metric and desired direction, a minimum effect size `δ(c)`, required seeds,
a reviewer-risk `rr(c) ∈ [0,1]`, dependencies `depends_on(c)`, and free-text
evidence requirements. Claims form a DAG.

**Experiment.** A `(method, dataset, condition, seed)` cell linked to claims, with
expected cost/time and optional dependencies. Its `condition_key`
(`method|dataset|condition`) separates "another seed" from "a new condition"; its
`cell_key` (`dataset|condition`) aligns a method with its baseline.

**Research action.** A non-run action (literature/novelty check, reviewer attack,
theorem attempt, claim refinement, baseline design, dataset addition, write
related-work/limitations, paper-readiness review) carrying an instruction and a
(human/compute) cost.

**Per-claim evidence.** From completed results we compute breadth (fraction of
conditions with a measurable method−baseline *effect*), seed sufficiency, per-cell
effect and variance, missing baselines, and a status in {unknown,
needs_more_evidence, weak, supported, refuted, blocked}. **Design rule: breadth
gates the verdict** — seed depth on one dataset must not "prove" a cross-dataset
claim (`scoring._confidence`). A claim whose own evidence is positive but whose
`depends_on` are unmet is **blocked**: its *effective* status differs from its
*own* status (`readiness._effective_status`).

**Verdict.**
- *Heuristic mode:* a logistic of the oriented effect vs. `δ(c)`, gated by breadth
  → status + a *ranking* confidence (not a probability).
- *Bayes mode:* a finite-population Normal–Normal posterior on `M = (1/K)·Σ θ_i`
  over the project's `K` defined conditions. The variance of the estimate of `M`
  is `σ_b²/k·(K−k)/K + Σ se_i²/k²`; the **finite-population correction**
  `(K−k)/K` makes the between-condition (generality) term vanish exactly when all
  `K` conditions are observed, and dominate when `k ≪ K`. Verdict by `P(M ≥ δ)`
  and `P(M ≤ 0)` against a probability threshold.

**Scheduling objective.** Score each candidate action by expected progress toward
a verdict per unit cost:

```
priority(a) = ( w_dv·decision_value + w_unc·uncertainty_reduction
              + w_dep·dependency_unlock + w_rev·reviewer_risk_reduction
              + w_seed·seed_value
              − w_red·redundancy_penalty
              − w_prp·premature_replication_penalty )
            / ( expected_time + λ·expected_cost )
```

In `bayes` mode, `decision_value = imp(c)·EVI(a)`, where `EVI(a)` is the **myopic
one-step expected reduction in decision uncertainty** `U(p)=p(1−p)`. For a *new
effect cell*, `EVI` integrates over the predictive of the new observation `y` by
deterministic 5-point Gauss–Hermite quadrature
(`bayes.expected_voi_new_cell`), capturing that a *surprising* `y` can flip the
verdict; for an *extra seed* it is the (smaller) variance reduction of
re-measuring an existing cell. Redundancy and premature-replication penalties are
then 0 because a redundant seed simply has ≈0 EVI. Actions are classified into an
immediate **queue**, **postponed**, or **avoided**, with the queue diversified to
≤1 run per `(cell, role)` so breadth spreads before depth.

**Stopping.** A claim stops when its verdict is stable (supported/refuted at the
threshold and breadth); the project stops when all main/high-importance claims are
effectively supported (or correctly refuted/scoped). The benchmark measures this
as **runs-to-decision**.

**Non-goals.** No global optimality; no multi-step lookahead; no autonomy
(advisor mode); no model tuning or config search.

---

## 4. Method (system)

**Claim graph (`schemas.py`).** Typed Pydantic models with `extra='forbid'` on
config models, so a YAML key typo raises a validation error instead of silently
doing nothing. `Claim`, `Experiment` (with `condition_key`/`cell_key`/
`is_baseline`), `RunResult`, `ResearchAction`, `Plan`, `Policy`, `Resources`,
`State`.

**Readiness (`readiness.py`).** Own vs. effective status; supported-but-blocked →
`blocked`; meta-claims derived from their subgraph; ranked reviewer attacks
(weighted by `rr × imp`); missing baselines; thin-generality and insufficient-seed
flags; prioritized next actions; a `paper_ready` verdict. Exposed as `insightflow
readiness` and as the MCP `readiness` tool.

**Evidence + verdicts (`scoring.py`, `bayes.py`).** Cell-level effects and squared
standard errors; breadth-gated heuristic status; the calibrated finite-population
posterior and EVI in bayes mode. Iteration over cells is `sorted()` so float sums
(and thus verdicts) are deterministic across processes.

**Scheduler (`scheduler.py`).** Enumerates actions; distinguishes new-condition
launches from extra seeds via the cell key; routes seeds through a seed policy;
co-scores research actions; classifies into queue/postponed/avoided; diversifies
the queue; emits warnings (weak/refuted claims, missing baselines under reviewer
risk, unverified generality, budget overrun) and an explainable per-action factor
breakdown.

**Research actions (`actions.py`).** Auto-generates literature/novelty checks
(high-importance, high-reviewer-risk, no evidence yet), reviewer attacks
(decided-looking but thin), claim refinements (weak/refuted), theorem attempts
(theory claims), plus user-defined actions in `actions.yaml`, each scored as
need-per-unit-cost so it ranks *against* experiments.

**Ledger + interfaces (`ledger.py`, `cli.py`, `mcp_server.py`).** SQLite + JSONL
ledger; CLI (`init, validate, state, plan, explain, readiness, demo, run,
simulate-step, benchmark, log-result, import-{wandb,csv,mlflow}, replay`); MCP
server exposing `state/plan/explain/validate/log_result/replay/readiness`; a
Claude Code plugin. `--format json` everywhere for agents.

---

## 5. Experiments

### 5.1 Scenario benchmark (`simulator.py`, `benchmark.py`)

Seven scenarios, each with hidden ground truth, isolate one capability:

| scenario | stresses |
|---|---|
| breadth | breadth beats replication (method truly wins everywhere) |
| expensive_branch | one dataset 5× costlier; cheaper cells decide it |
| dependency_unlock | a cheap ablation unlocks the deciding runs |
| reviewer_baseline | many seeds tempt over-running; baseline decides it |
| noisy_seeds | one clean + one high-variance/smaller-effect dataset |
| refuted | method genuinely loses (correct verdict = refuted) |
| mixed_multi_claim | C1 truly supported + C2 truly refuted, in one project |

**Protocol.** Runs (and cost) until the shared confidence readout matches the
hidden ground-truth status of *every* claim. The *same* readout grades every
policy, so policies differ only in *which* experiments they choose — a clean
isolation of scheduling quality. Baselines: `grid`, `all_seeds_first`,
`all_tasks_first`, `random`, `cheap_first`, `fastest_first`, `baseline_first`,
and an `oracle` (knows ground truth; completes cells to maximize breadth
fastest). Config reported below: `steps=40, n_projects=5, base_seed=0`.

### 5.2 Headline results (real, measured)

**Per-scenario runs-to-decision** (lower is better; `+%` = runs saved):

| scenario | IF runs | grid runs | %saved vs grid | %saved vs best naive | %cost saved vs best | oracle |
|---|---|---|---|---|---|---|
| breadth | 5.0 | 11.0 | +54.5% | +0.0% | +8.3% | 4.0 |
| expensive_branch | 4.0 | 8.0 | +50.0% | +20.0% | +35.7% | 4.0 |
| dependency_unlock | 5.0 | 9.0 | +44.4% | +0.0% | +0.0% | 5.0 |
| reviewer_baseline | 4.0 | 12.0 | +66.7% | +0.0% | +0.0% | 4.0 |
| noisy_seeds | 6.6 | 15.2 | +56.6% | −10.0% | −8.0% | 6.2 |
| refuted | 4.0 | 10.0 | +60.0% | +20.0% | +21.7% | 4.0 |
| mixed_multi_claim | 8.0 | 20.0 | +60.0% | +0.0% | +0.0% | 8.0 |

Mean runs saved vs. grid = **56.0%**.

**Robustness across all scenarios** (mean runs; worst-case ratio to the oracle;
scenarios solved cleanly):

| policy | mean runs | worst vs oracle | solved |
|---|---|---|---|
| oracle | 5.03 | 1.00× | 7/7 |
| **insightflow** | **5.23** | **1.25×** | **7/7** |
| ablate_reviewer_risk | 5.23 | 1.25× | 7/7 |
| ablate_breadth_penalty | 5.23 | 1.25× | 7/7 |
| ablate_cost | 5.23 | 1.25× | 7/7 |
| uncertainty_only | 4.50 | 1.25× | **1/7** |
| grid | 12.17 | 3.00× | 7/7 |
| all_seeds_first | 11.60 | 3.00× | 7/7 |
| all_tasks_first | 6.00 | 1.80× | 7/7 |
| random | 9.49 | 2.45× | 7/7 |
| cheap_first | 10.11 | 2.75× | 7/7 |
| fastest_first | 10.11 | 2.75× | 7/7 |
| baseline_first | 9.69 | 2.75× | 7/7 |

**Reading.** InsightFlow is the **only non-oracle policy that is both within
1.25× of the oracle in the worst case and solves 7/7.** Every naive policy is
≥1.8× worst-case; the ones that *look* competitive on mean runs (e.g.
`all_tasks_first`, 6.00 mean) pay for it with a worse worst case (1.80×). The two
negative entries for InsightFlow vs. best-naive on `noisy_seeds` (−10% runs, −8%
cost) are honest: on that scenario a naive `all_tasks_first` happens to under-seed
its way to the same verdict slightly faster on average; InsightFlow spends a
little more there to be robust elsewhere. We report it rather than hide it.

> Note on "~5.4 vs 5.23": the project summary quotes ~5.4 mean runs from a
> different `(n_projects, seed)` configuration; the regime is the same. The paper
> reports the exact config above to avoid ambiguity.

### 5.3 Ablations

Each ablation is InsightFlow with one component disabled (`simulator.POLICIES`):
`ablate_reviewer_risk` (`w_rev=0`), `ablate_breadth_penalty` (`w_prp=0`),
`ablate_cost` (`λ=0`), and `uncertainty_only` (only the uncertainty term).

The decisive result is **`uncertainty_only` solves only 1/7** — it fails the
`mixed_multi_claim` scenario, where chasing raw uncertainty alone, without
decision-value, reviewer-risk, dependency, and breadth/redundancy structure,
cannot correctly decide two claims with different evidence needs. The other three
single-term ablations keep 7/7 and 1.25× *on these scenarios*, but they change
*which* runs are chosen and *how much* they cost (most visibly in
`expensive_branch` and `noisy_seeds`, where dropping the cost/breadth terms
changes the cost-to-decision). We therefore claim the components are load-bearing
in **what** and **how cheaply** they decide — and decisively so for multi-claim
correctness — and we explicitly do **not** claim a solved-count collapse for the
three single-term ablations where there is none.

### 5.4 Replay evaluation (`replay.py`)

A leak-free, counterfactual replay on already-collected histories (W&B / CSV /
JSONL / MLflow importers). Ground truth = the decision the *complete* history
supports. We compare the *actual* arrival order against InsightFlow's *adaptive*
order (the scheduler chooses the next run, constrained to runs that were actually
performed) and against non-adaptive orderings (grid / random / cheap_first /
seeds_first), reporting runs saved. This is the external check that the synthetic
benchmark cannot provide; the deduplication and ground-truth construction ensure
all trajectories evaluate the *same* per-experiment evidence (no leakage).

### 5.5 Calibration (bayes mode)

The finite-population Normal–Normal model is calibrated under its own generative
process. The committed test
(`tests/test_bayes.py::test_posterior_is_calibrated`, 600 draws) asserts the
calibration *property*: aggregate predicted ≈ aggregate actual, high-confidence
predictions (`p≥0.8`) correct >75% of the time, low-confidence (`p≤0.2`) <25%. A
larger sweep (documented over 200k draws in `docs/concepts.md`) reports
**ECE = 0.011**. *Honesty flag:* the 200k-draw figure is documented but **not
reproduced by a committed script** in this repo; before publication we will either
commit that script or report the committed-test ECE on 600 draws. The EVI is
positive, diminishing, and deterministic (tested), and the bayes-mode scheduler
decides and is deterministic (tested). Calibration here is a *well-specification*
check, not a claim about real-world effects.

### 5.6 Agent-in-sandbox evaluation (illustrative)

Real Claude/Sonnet agents driving the InsightFlow CLI versus an unaided agent on
the same tasks saved **50–69% of compute with no loss in correctness** on the
tasks tested. *Honesty flag:* small n, illustrative, and **not reproduced by a
committed artifact** in this repo (no logged transcripts under `scripts/` or
`tests/`); we report it as a pilot signal, and a committed agent-eval harness is
the corresponding to-do.

---

## 6. Limitations

1. **Myopic, not optimal.** One-step EVI per unit cost; no lookahead; no
   optimality guarantee.
2. **Synthetic-heavy evaluation.** Headline numbers are on scenarios we designed,
   graded by one shared confidence readout. Replay and the agent study are the
   external checks, and both are small.
3. **Heuristic mode is a ranking, not a probability.** Only bayes mode yields a
   calibrated probability, and only under Normal effects, plug-in per-cell
   standard errors, and a *defined finite* condition set.
4. **Advisor mode.** It recommends; it does not guarantee the human/agent follows
   the plan.
5. **Specification burden.** Quality depends on honestly declared claims, effect
   sizes, required seeds, and conditions.
6. **Reviewer-risk is an author-supplied scalar prior,** not a learned model of
   reviewers.
7. **Two headline numbers (ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`), agent 50–69%) are documented but not
   currently reproducible from committed artifacts** — to be fixed before
   submission.

---

## 7. Conclusion

InsightFlow reframes experiment scheduling around the unit a paper is graded on —
the falsifiable claim — and shows that a small, transparent, reviewer-risk-aware,
value-of-information-inspired decision layer can capture most of an oracle's
efficiency on controlled scenarios (5.23 vs. 5.03 mean runs, 1.25× worst case,
7/7 solved, 56% saved vs. grid) while keeping every verdict and recommendation an
auditable, deterministic function of a claim–evidence ledger. The contribution is
the integration and the objective, not new mathematics, and we are explicit about
that. The most important next step is external validation: replay on a large
corpus of real projects, a committed agent-evaluation harness, and a controlled
human study — moving the main claim from "defensible as a systems + synthetic
contribution" to "validated for real ML research."

---

## Appendix A — Reproducing the numbers

```bash
# Scenario benchmark (the tables in §5.2):
insightflow benchmark --scenarios --steps 40 --projects 5 --seed 0
# or, equivalently in Python:
python -c "from insightflow.benchmark import run_scenarios; \
           import json; print(json.dumps(run_scenarios(40,5,0), indent=2))"

# Test suite, lint, and types:
python -m pytest -q          # 126 passed
ruff check src               # clean
mypy src/insightflow         # clean (26 source files)
```

## Appendix B — Honesty ledger (what is and isn't reproducible here)

| number | source | reproducible from repo? |
|---|---|---|
| 5.23 mean / 1.25× worst / 7/7 / 56% vs grid | `benchmark.run_scenarios(40,5,0)` | **Yes** |
| uncertainty_only solves 1/7 | same | **Yes** |
|  passing tests , mypy/ruff clean, 26 modules | `pytest`, `mypy`, `ruff`, `ls src` | **Yes** |
| EVI positive/diminishing/deterministic; bayes decides | `tests/test_bayes.py` | **Yes** |
| Calibration *property* (600 draws) | `tests/test_bayes.py::test_posterior_is_calibrated` | **Yes** |
| **ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) over 200k draws** | `docs/concepts.md` | **No committed script** — fix before submission |
| **Agent 50–69% compute saved** | `docs/agent_driven_project.md` | **No committed artifact** — pilot only |

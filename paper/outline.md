# InsightFlow — Paper Outline

> Working framing (use everywhere): **InsightFlow is a claim-centered research
> decision layer for AI-assisted ML research. It helps researchers and coding
> agents decide which evidence to acquire next, when to stop, what to postpone,
> what to avoid, and which claims are currently supported, refuted, weak, or
> still uncertain.**
>
> Position it as: an auditable research control plane; a claim–evidence ledger;
> a value-of-information-inspired scheduler; a practical decision layer for human
> and AI research agents. Do **not** position it as AutoML/HPO, an experiment
> tracker, an AI Scientist, an autonomous researcher, or a guaranteed-optimal
> planner.

---

## 1. Title candidates (claim-centered family)

Primary:

1. **InsightFlow: A Claim-Centered Decision Layer for Evidence Acquisition in
   AI-Assisted ML Research**
2. **Deciding What to Run Next: Claim-Centered, Value-of-Information Scheduling
   for ML Research**
3. **From Experiments to Claims: An Auditable Research Control Plane for Human
   and Agent Researchers**

Alternates:

4. **The Claim–Evidence Ledger: Reaching Defensible Paper Claims Under Cost,
   Uncertainty, and Reviewer Risk**
5. **Evidence, Not Accuracy: Reframing Experiment Scheduling Around Falsifiable
   Claims**
6. **InsightFlow: A Research Control Plane That Knows When to Stop**

Recommended: **#1** as the formal title, with **#3** as a subtitle-style framing
for an applied/systems venue (e.g., a tools/automation track or workshop on
AI-for-science tooling).

---

## 2. Abstract (draft)

AI coding agents can now run experiments, but they have no principled way to
decide *which evidence is worth acquiring next* for a falsifiable research
claim, *when the evidence is enough to stop*, and *which claims a paper can
actually defend*. Experiment trackers record what ran; AutoML and HPO optimize
model performance; bandit and Bayesian-optimal-experimental-design methods
allocate compute to arms or configurations. None of them operate over the unit
that a paper is graded on: the **claim**.

We present **InsightFlow**, a claim-centered research decision layer. The
contribution is an *integration and an objective*, not new mathematics:
InsightFlow maintains a typed **claim graph** with explicit evidence
requirements and dependencies; computes per-claim **readiness** (own vs.
effective status, blocked claims, missing baselines, thin generality,
insufficient seeds); recommends the next action — a run, an extra seed, a
baseline, *or* a non-run research action (literature check, reviewer attack,
theorem attempt, claim refinement) — using a **value-of-information-inspired,
reviewer-risk-aware scheduler**; and records every decision in an auditable
**claim–evidence ledger** exposed to humans and agents over a CLI and an MCP
interface. We are explicit about scope: the scheduler is a **myopic one-step
approximate EVI per unit cost** (deterministic Gauss–Hermite quadrature), not a
multi-step optimal plan; in the calibrated `bayes` mode the claim confidence is
a probability (measured ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) on draws from the model's own generative
process) under stated assumptions, while the default `heuristic` mode produces a
ranking score, not a probability.

On seven synthetic scenarios that each stress a different scheduling capability
(breadth, expensive branch, dependency unlock, reviewer baseline, noisy seeds,
refuted, mixed multi-claim), InsightFlow reaches the correct research decision in
~5.2 runs on average, within **1.25× of an oracle in the worst case**, solves
**7/7** scenarios — the best among all non-oracle policies tested — and saves
**~56%** of runs versus a full-grid baseline. Ablations confirm each scheduler
component matters: removing the reviewer-risk, breadth-penalty, or cost terms
degrades behavior, and an uncertainty-only variant solves only the single-claim
scenarios (1/7). In an illustrative agent-in-the-loop study, real coding agents
driving the InsightFlow CLI saved 50–69% of compute versus an unaided agent with
no loss in correctness on the tasks tested (small n). The system is 26 modules,
126 passing tests, `ruff`- and `mypy`-clean.

---

## 3. Introduction story

**Opening tension.** A graduate student (or a coding agent acting on her behalf)
has a method and a claim: "method A beats baseline B across datasets." She has a
fixed compute budget and a deadline. She can run more seeds, add datasets, run
the missing baseline, run an ablation, or stop. Today, nothing tells her which
of these *advances the claim* most per unit cost. Experiment trackers (W&B,
MLflow) will faithfully record whatever she runs; an HPO sweep will find a better
config for one dataset; an "AI Scientist" will try to write the whole paper. But
the decision she actually faces — *what evidence does this claim still need, and
is it worth the compute?* — is unsupported.

**The agent angle.** This gap is sharper for AI agents. An agent with a shell can
launch runs, but with no claim-level state it tends to (a) over-replicate one
easy setting, (b) skip the baseline that would let a reviewer attribute the
effect, or (c) keep going long after the claim is decided. The cost is real
compute and real reviewer risk.

**Our reframing.** We move the unit of scheduling from *configurations* to
*claims*. A claim has evidence requirements (effect size, required seeds,
breadth across conditions), a reviewer-risk, and dependencies on subclaims. The
decision layer asks, at each step: *which action most increases our ability to
reach a defensible verdict on the claims, per unit cost?* — and equally
importantly, *when can we stop, and what should we postpone or avoid?*

**What we built.** InsightFlow operationalizes this as a claim graph, a
deterministic readiness assessor, a value-of-information-inspired scheduler that
ranks runs *and* non-run research actions together, and a ledger-backed agent
interface. It is an **auditable research control plane**: every verdict and every
recommendation is a deterministic, inspectable function of the ledger.

**What we claim — and what we don't.** The novelty is the integration and the
objective. We do not claim new math, global optimality, or autonomy. We claim
that (i) reframing scheduling around claims is useful and buildable, (ii) a
small, transparent, reviewer-risk-aware scorer captures most of the value of an
oracle on controlled scenarios, and (iii) a ledger-backed claim layer is a
better substrate for AI research agents than a bare shell.

---

## 4. Problem formulation — claim-centered evidence acquisition

**Goal.** Reach **defensible claim verdicts** under uncertainty, cost, and
reviewer-risk, while spending as little compute as possible and stopping as soon
as the verdicts are stable.

**Objects.**

- A **claim** `c` has: type (main / empirical / mechanism / efficiency /
  robustness / theory / limitation / negative / auxiliary), importance
  `imp(c) ∈ [0,1]`, a target metric and desired direction, a minimum effect size
  `δ(c)`, required seeds, a reviewer-risk `rr(c) ∈ [0,1]`, dependencies
  `depends_on(c)` on supporting subclaims, and free-text evidence requirements.
  Claims form a **graph** (DAG of `depends_on`).
- An **experiment** is a `(method, dataset, condition, seed)` cell, linked to one
  or more claims, with an expected cost and time, optional dependencies on other
  experiments, and a baseline relationship. Its *condition key*
  (`method|dataset|condition`) distinguishes "same condition, another seed" from
  "a new condition"; its *cell key* (`dataset|condition`) lines a method up
  against its baseline.
- A **research action** is a non-run action (literature/novelty check, reviewer
  attack, theorem attempt, claim refinement, baseline design, dataset addition,
  write related work / limitations, paper-readiness review). It carries an
  instruction for a human or agent and a (human/compute) cost.
- A **ledger** holds claims, experiments, results, and policy; every verdict and
  plan is a deterministic function of it.

**Per-claim evidence.** For each claim we compute from completed results:
breadth (fraction of conditions with a measurable method−baseline *effect*),
seed sufficiency (observed vs. required seeds), per-cell effect and variance,
missing baselines, and a status in {unknown, needs_more_evidence, weak,
supported, refuted, blocked}. A key design rule: **breadth gates the verdict** —
seed depth on one dataset must not "prove" a cross-dataset claim. A claim whose
own evidence is positive but whose `depends_on` subclaims are unmet is
**blocked**, not supported (its *effective* status differs from its *own*
status).

**Decision (verdict).**

- Heuristic mode: a logistic of the oriented effect vs. `δ(c)`, gated by breadth,
  yielding a status and a *ranking* confidence (not a probability).
- Bayes mode: a finite-population Normal–Normal posterior on the population mean
  effect `M = (1/K)·Σ θ_i` over the project's `K` defined conditions, with a
  **finite-population correction** so that observing all `K` conditions removes
  the generality term. Verdict by `P(M ≥ δ)` and `P(M ≤ 0)` against a probability
  threshold.

**Scheduling objective (what to do next).** Score each candidate action by
expected progress toward a verdict per unit cost:

```
priority(a) = ( w_dv·decision_value + w_unc·uncertainty_reduction
              + w_dep·dependency_unlock + w_rev·reviewer_risk_reduction
              + w_seed·seed_value
              − w_red·redundancy_penalty
              − w_prp·premature_replication_penalty )
            / ( expected_time + λ·expected_cost )
```

In bayes mode, `decision_value = imp(c)·EVI(a)` where `EVI` is the **myopic
one-step expected reduction in decision uncertainty** `U(p)=p(1−p)`, computed by
deterministic 5-point Gauss–Hermite quadrature over the predictive of the action's
observation; redundancy and premature-replication penalties become 0 because a
redundant seed simply has ≈0 EVI. Actions are then classified into an immediate
**queue**, **postponed** (e.g., an extra seed before breadth is established), or
**avoided** (e.g., a redundant well-covered cell).

**Stopping.** Stop a claim when its verdict is stable (supported/refuted at the
required threshold and breadth); stop the project when all main/high-importance
claims are effectively supported (or correctly refuted/scoped). This is what the
benchmark measures as "runs-to-decision."

**Non-goals (explicit).** No global optimality; no multi-step lookahead; no
autonomy (advisor mode by default — InsightFlow recommends, humans/agents
execute); no model tuning, no config search.

---

## 5. Contributions

1. **A claim-centered reframing of experiment scheduling.** The unit is the
   falsifiable paper claim, not the configuration or the arm. We give a typed
   claim graph with evidence requirements, dependencies, reviewer-risk, and a
   verdict taxonomy (supported/refuted/weak/needs-more/blocked).
2. **A paper-readiness assessor.** A deterministic function over the claim graph
   that reports own vs. effective status, blocked main claims, ranked reviewer
   attacks, missing baselines, thin generality, and prioritized next actions.
3. **A value-of-information-inspired, reviewer-risk-aware scheduler.** A single
   objective that handles breadth-vs-replication, missing baselines, dependency
   unlocking, cost, and reviewer-risk; with a transparent heuristic mode and an
   opt-in calibrated bayes/EVI mode (myopic, deterministic).
4. **Research actions as first-class, co-scheduled items.** Literature checks,
   reviewer attacks, theorem attempts, and claim refinements are auto-generated
   from evidence and scored *against* experiments, so the planner can say "do a
   literature check before spending compute."
5. **A ledger-backed agent interface and an auditable control plane.** SQLite +
   JSONL ledger, deterministic plans, a CLI, and an MCP server (incl. a
   `readiness` tool) so human and AI agents share one inspectable state.
6. **Replay evaluation for research trajectories.** A leak-free, counterfactual
   offline replay that asks whether InsightFlow would have reached the same
   decision with fewer runs on *already-collected* histories (W&B/CSV/MLflow
   importers), plus a multi-policy comparison on the same history.
7. **A scenario benchmark with ablations and an agent study.** Seven controlled
   scenarios, ~12 policies including an oracle and four ablations, with measured
   runs/cost-to-decision and a worst-case-vs-oracle robustness summary.

---

## 6. Method

### 6.1 Claim graph (`schemas.py`)
Typed `Claim` (type, importance, `δ`, required seeds, reviewer_risk,
`depends_on`, `blocks`, `evidence_requirements`, status incl. `blocked`),
`Experiment` (with `condition_key` / `cell_key` / `is_baseline`), `RunResult`,
`ResearchAction`, `Plan`, `Policy`, `Resources`, `State`. Config models are
`extra='forbid'` so a YAML typo surfaces as a validation error rather than
silently doing nothing.

### 6.2 Readiness (`readiness.py`)
Own status (from this claim's own evidence) vs. effective status (after unmet
dependencies). A supported-but-blocked claim is surfaced as `blocked`; a
meta-claim with no runs of its own is derived from its subgraph. Produces ranked
reviewer attacks (weighted by reviewer_risk × importance), missing baselines,
thin-generality and insufficient-seed flags, prioritized next actions, and a
`paper_ready` verdict (all main/high-importance claims effectively supported).

### 6.3 Per-claim evidence + verdicts (`scoring.py`, `bayes.py`)
Cell-level effects and squared standard errors; breadth = fraction of conditions
with a measurable effect; seed sufficiency; breadth-gated heuristic status; or
the calibrated finite-population Normal–Normal posterior with finite-population
correction (bayes mode). EVI via deterministic Gauss–Hermite quadrature.

### 6.4 Scheduler (`scheduler.py`, `scoring.py`)
Enumerates actions, distinguishing new-condition launches from extra seeds via
the cell key; routes extra seeds through a seed policy; scores runs and research
actions on one scale; classifies into queue / postponed / avoided; diversifies
the queue (≤1 run per (cell, role)) so breadth spreads before depth; emits
warnings (weak/refuted claims, missing baselines under reviewer risk, unverified
generality, budget overrun) and an explainable factor breakdown per action.

### 6.5 Research actions (`actions.py`)
Auto-generates literature/novelty checks (high-importance, high-reviewer-risk,
no evidence yet), reviewer attacks (decided-looking but thin), claim refinements
(weak/refuted), and theorem attempts (theory claims) — plus user-defined actions
in `actions.yaml` — and scores them as value (need) per unit human/compute cost.

### 6.6 Ledger + interfaces (`ledger.py`, `cli.py`, `mcp_server.py`)
SQLite + JSONL ledger; CLI (`init, validate, state, plan, explain, readiness,
demo, run, simulate-step, benchmark, log-result, import-{wandb,csv,mlflow},
replay`); MCP server exposing `state/plan/explain/validate/log_result/replay/
readiness`; a Claude Code plugin (skills + commands). `--format json` everywhere
for agents.

---

## 7. Experiments

### 7.1 Seven synthetic scenarios (`simulator.py`)
Each scenario has *hidden ground truth* and isolates one capability:

| scenario | what it stresses |
|---|---|
| breadth | breadth beats replication (method truly wins everywhere) |
| expensive_branch | one dataset 5× costlier; cheaper cells decide it |
| dependency_unlock | a cheap ablation unlocks the deciding runs |
| reviewer_baseline | many seeds tempt over-running; baseline decides it |
| noisy_seeds | one clean + one high-variance/smaller-effect dataset |
| refuted | method genuinely loses (correct verdict = refuted) |
| mixed_multi_claim | C1 truly supported + C2 truly refuted in one project |

**Metric.** Runs (and cost) until the shared confidence readout matches the
hidden ground-truth status of *every* claim ("runs-to-decision"). The same
confidence readout is used for all policies, so policies differ only in *which*
experiments they choose — a clean isolation of scheduling quality.

### 7.2 Baselines / policies
`grid`, `all_seeds_first`, `all_tasks_first`, `random`, `cheap_first`,
`fastest_first`, `baseline_first`, and an `oracle` lower bound (knows ground
truth; completes cells to maximize breadth fastest).

### 7.3 Headline results (real, measured; `benchmark.run_scenarios`, n=5, seed=0)
- Mean runs-to-decision ≈ **5.2** (reported as ~5.4 in the project summary; both
  are within rounding of the same regime), **worst-case 1.25× the oracle**, **7/7
  solved** — best among non-oracle policies.
- **~56%** mean runs saved vs. the full grid (range +44% to +67% per scenario).
- Per-scenario runs-saved-vs-grid and worst-case-vs-oracle in the draft's tables.

### 7.4 Ablations (`ablate_reviewer_risk`, `ablate_breadth_penalty`,
`ablate_cost`, `uncertainty_only`)
Each is InsightFlow with one component disabled. The first three keep 7/7 and
1.25× worst-case on these scenarios but change *which* runs are chosen (and cost
in the expensive/noisy scenarios); the decisive result is that
**`uncertainty_only` solves only 1/7** — it fails the multi-claim scenario,
showing the non-uncertainty terms are load-bearing.

> Honesty note: on these particular scenarios the three single-term ablations
> still solve 7/7 at the same worst-case ratio; their effect shows up in
> *choices and cost*, not always in solved count. We report this rather than
> overclaim a solved-count collapse. The draft will additionally report
> cost-to-decision deltas for these ablations.

### 7.5 Replay evaluation (`replay.py`)
Leak-free counterfactual replay on already-collected histories: ground truth =
what the complete history supports; compare actual arrival order vs. InsightFlow's
adaptive order vs. non-adaptive orderings (grid/random/cheap_first/seeds_first);
report runs saved. Importers: W&B / CSV / JSONL / MLflow.

### 7.6 Calibration (bayes mode)
Finite-population Normal–Normal model; **ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`)** (documented over 200k draws
from the model's own generative process; the committed unit test reproduces the
calibration property on 600 draws — aggregate predicted ≈ actual, high-confidence
predictions right >75%, low-confidence <25%). Bayes-mode scheduler decides and is
deterministic (tested).

### 7.7 Agent-in-sandbox evaluation (illustrative)
Real Claude/Sonnet agents driving the InsightFlow CLI vs. an unaided agent on the
same tasks: **50–69% compute saved with no loss in correctness** on the tasks
tested. Small n; illustrative, not a controlled user study.

---

## 8. Limitations

1. **Myopic, not optimal.** One-step EVI per unit cost; no multi-step lookahead;
   no optimality guarantee.
2. **Synthetic-heavy evaluation.** The headline numbers are on synthetic
   scenarios *we designed*; the oracle and the policies share one confidence
   readout. Replay on real histories and the agent study are the external checks,
   and both are small.
3. **Heuristic mode is a ranking, not a probability.** Only bayes mode yields a
   calibrated probability, and only under its stated assumptions (Normal effects,
   plug-in per-cell standard errors, a *defined finite* condition set).
4. **Advisor mode.** It recommends; it does not guarantee humans/agents follow
   the plan; no closed-loop execution guarantees.
5. **Claim/condition specification burden.** Quality depends on honestly declared
   claims, effect sizes, required seeds, and conditions; garbage-in/garbage-out.
6. **Reviewer-risk is a scalar prior, not a model of reviewers.** It encodes the
   author's own estimate, not a learned model.
7. **Agent-eval n is small** and the ECE-over-200k figure is documented but not
   reproduced by a committed script (the committed test checks the property on
   600 draws). We will either commit the 200k script or report the 600-draw ECE.

---

## 9. Expected reviewer attacks and responses

**A. "This is just AutoML / HPO / a bandit with extra words."**
Response: those optimize *model performance* or *best-arm identification* over
configurations. InsightFlow optimizes *evidence for a falsifiable claim*, with
breadth-vs-replication, missing-baseline, dependency, and reviewer-risk terms
that have no analog in HPO. The objective is verdict-reaching, not accuracy; the
output is a verdict + readiness report, not a tuned model. We make the distinction
concrete in Related Work and show uncertainty-only (the closest "pure
information" reduction) fails the multi-claim scenario.

**B. "The novelty is just engineering; there's no new math."**
Response: we agree and say so. The contribution is the *integration and the
objective* — claim-level state, evidence requirements, reviewer-risk-aware
scheduling, a ledger-backed agent interface, replay evaluation, and
paper-readiness reporting. We deliberately use known tools (Normal–Normal
posterior, myopic EVI, Gauss–Hermite quadrature) and claim none of them as new.

**C. "Synthetic benchmarks are rigged in your favor."**
Response: the oracle and all baselines run on the *same* confidence readout, so
the comparison isolates scheduling; we report a *worst-case* ratio to the oracle
(1.25×) rather than only an average; and we add a leak-free replay on real,
externally-collected histories. We also publish the generators.

**D. "Your ablations still solve 7/7, so the components don't matter."**
Response: three single-term ablations keep 7/7 on these scenarios but change
*which* runs and *how much* they cost; the load-bearing result is that
`uncertainty_only` solves only 1/7 (fails multi-claim). We report cost deltas and
do not claim a solved-count collapse where there is none.

**E. "Calibration is on data sampled from your own model."**
Response: correct, and stated. The ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) is a *self-consistency /
well-specification* check, not a real-world calibration claim; the heuristic mode
makes no probability claim at all. Real-world calibration is future work.

**F. "Agents could do this with a good prompt; you don't need a system."**
Response: the agent study compares exactly that (unaided agent) against the
ledger-backed CLI and finds 50–69% compute saved at equal correctness (small n).
The value is the *auditable shared state and deterministic plan*, not a smarter
LLM.

**G. "Why advisor mode? Real value would be autonomy."**
Response: advisor mode is a deliberate safety/auditability choice; every verdict
and plan is a deterministic, inspectable function of the ledger. Autonomy without
auditability is the failure mode we are reacting to.

**H. "Reviewer-risk is hand-wavy."**
Response: it is an explicit scalar prior the author sets, used transparently
(reviewer_risk × importance ranks attacks and weights baseline urgency). We
present it as an author-supplied prior, not a learned reviewer model.

**I. "Where is the human study?"**
Response: out of scope for this version; we report a small agent study and
replay on real histories, and flag a user study as the most important next step.

# InsightFlow Concepts

## Core Domain Model

### Claim

A `Claim` is a falsifiable research assertion that InsightFlow is trying to
support, weaken, or refute. Claims are the **unit of work**: InsightFlow is a
*claim-centered* decision layer, so the scheduler, the readiness report, and the
research actions all reason about claims, not just runs. Every claim has:

- `id` and `statement`: a unique key and a human-readable description.
- `type`: a `ClaimType` (`main`, `empirical`, `mechanism`, `efficiency`,
  `robustness`, `theory`, `limitation`, `negative`, `auxiliary`). The type changes
  how the claim is treated: e.g. a `theory` claim cannot be established by runs
  alone (it warrants a `theorem_attempt`), and `main`/high-importance claims gate
  paper readiness.
- `importance` (alias: priority): a float in [0, 1], or a word like `high`
  (maps to 0.85) or `critical` (maps to 1.0). Controls how much scheduling
  weight a claim gets.
- `target_metric` and `desired_direction`: the metric (e.g. `accuracy`) and
  whether higher or lower is better.
- `minimum_effect_size`: the smallest improvement that would be considered
  meaningful. Used in the confidence heuristic's logistic function.
- `required_seeds`: how many independent seeds are considered sufficient
  evidence for each condition. The scheduler uses this to decide when extra
  seeds are justified.
- `reviewer_risk`: a float in [0, 1] signalling how likely a reviewer is to
  attack this claim. High-risk claims receive extra pressure to have baselines
  present.
- `depends_on`: a list of subclaim IDs this claim needs before it is fully
  defensible (e.g. a `main` claim depending on an `empirical` and a `robustness`
  subclaim). This is the edge set of the **claim graph** (see below). An unmet
  `depends_on` is what makes a claim `blocked`.
- `blocks`: an optional, often-derivable list of claims this one blocks. Provided
  for convenience/readability; the readiness logic computes blocking from
  `depends_on`.
- `evidence_requirements`: free-text requirements (e.g. "effect holds on >= 3
  datasets with matched baselines") that the readiness report surfaces but does
  not parse.
- `status`: a `ClaimStatus` reflecting the current evidence (see below).

Config-loaded claims are `extra='forbid'`: an unknown/misspelled YAML key is a hard
validation error, not a silent no-op.

### The claim graph

The set of claims plus their `depends_on` edges forms a directed **claim graph**.
A `main` claim typically depends on supporting `empirical`, `mechanism`, or
`robustness` subclaims; those may in turn depend on others. The graph matters
because a claim is only fully defensible once **both** its own evidence **and** all
of its dependencies are met — a `main` claim whose runs look good but whose
supporting subclaim is unestablished is **`blocked`**, not `supported`. Two layers
consume the graph:

- the **readiness** report (`readiness.py`), which computes each claim's *effective*
  status by combining own evidence with the status of its dependencies, and
- the **research actions** generator (`actions.py`), which proposes establishing a
  blocking subclaim before piling more evidence onto the claim that depends on it.

(`ClaimStatus` values, including `blocked`, are defined under *Status values* in the
Claim Confidence section below.)

### Experiment

An `Experiment` is one runnable unit of evidence: a specific combination of
method, dataset, condition, and seed. Each experiment has:

- `method`, `dataset`, `condition`, `seed`: the four dimensions of the
  experiment grid.
- `baseline`: the name of the baseline that this method run is compared
  against (this field names the comparator; it does NOT make this experiment
  a baseline itself).
- `is_baseline`: a read-only property that is `True` when the experiment's
  `tags` list contains `"baseline"` or when `method` starts with `"baseline"`.
  Note the asymmetry: only this property — not the `baseline` field — is used
  to decide whether an experiment is a baseline.
- `claim_links`: a list of claim IDs this experiment provides evidence for.
- `dependencies`: a list of experiment IDs that must complete before this one
  can run.
- `expected_cost` and `expected_time`: used in the scoring denominator.
- `command`: the shell command to run (populated by the researcher or importer;
  InsightFlow never auto-generates commands).

#### `condition_key` vs `cell_key`

Two distinct identity keys appear on `Experiment`:

**`condition_key`** (`method|dataset|condition`): identifies the experimental
condition for a specific method. Two experiments that differ only by seed share
the same `condition_key`. This is the "same condition" test — it is what lets
the scheduler distinguish a *new condition* (the method has never run on this
dataset+condition combination) from an *extra seed* (the method has already
produced at least one result for this condition).

**`cell_key`** (`dataset|condition`): identifies the results-table cell,
ignoring method and seed. A method run and its baseline run occupy the same
cell. This is used to line up a method's results against its baseline's results
when computing effects, and to enforce diversification in the immediate queue
(at most one run per `cell_key` + role).

The key practical consequence: deciding "is this a new condition or a
replication?" is done using `condition_key` (via `observed_conditions`, which
is keyed on `cell_key` from the method experiments' perspective). Effect
measurement requires both method and baseline to occupy the same `cell_key`.

### RunResult

A `RunResult` is the outcome (complete or partial) of executing one experiment.
It records:

- `metrics`: final metric values.
- `partial_history`: a list of per-step metric snapshots for in-flight or
  partial runs.
- `status`: `running`, `completed`, `failed`, or `partial`.
- `source`: `manual`, `wandb`, `simulator`, or `import`.
- `cost` and `wall_time`: actuals (not estimates).

`RunResult.metric(name)` falls back to the last entry in `partial_history` if
the final metrics dict does not contain the key.

### Plan and PlanAction

A `Plan` is the output of one scheduler run. It contains:

- `actions`: the immediate queue — up to `top_k` actions to run now, sorted by
  score.
- `postponed`: actions worth running eventually but not now (blocked,
  duplicate-cell, or below the queue threshold but above the avoid threshold).
- `avoided`: actions with scores so low they should be skipped entirely.
- `claim_confidence`: the current `ClaimConfidence` record for every claim.
- `warnings`: human-readable alerts (claim status, missing baselines, budget
  overrun).
- `assumptions`: the assumptions the scheduler is making (e.g. advisor mode,
  heuristic confidence).
- `state_hash`: a stable hash of experiment statuses and result identities.
  The same hash means the same plan will be produced again.

A `PlanAction` captures a single recommendation. Its `factors` dict stores
every intermediate term of the scoring objective so the `explain` command can
render a full breakdown without recomputing anything.

### Policy

`Policy` holds all tunable weights and thresholds for the scheduler. The
defaults are chosen to behave sensibly with an empty `policy.yaml`. Every
weight maps directly onto a term of the scheduling objective. Key fields:

- `weight_decision_value`, `weight_uncertainty`, `weight_dependency`,
  `weight_reviewer_risk`, `weight_seed_value`: positive weights for the
  five benefit terms.
- `weight_redundancy_penalty`, `weight_premature_replication_penalty`: weights
  for the two penalty terms (subtracted from the numerator).
- `lambda_cost`: multiplier on cost in the denominator (default 0.3).
- `queue_threshold` (default 0.15): minimum score to enter the immediate queue.
- `avoid_threshold` (default 0.03): minimum score to appear in postponed rather
  than avoided.
- `top_k` (default 5): maximum size of the immediate queue.
- `prefer_breadth` (default True): global flag signalling the breadth-first
  orientation.
- `decision_boundary` (default 0.5): the logistic threshold separating
  support from refutation.
- `support_margin` (default 0.25): how far past `decision_boundary` the
  logistic score must be before a claim is labeled `supported` or `refuted`.
- `high_variance_threshold` (default 0.4): variance threshold (relative to
  `minimum_effect_size`) above which a cell is considered high-variance.

---

## Claim Confidence

Claim confidence is computed by `compute_claim_evidence` in `scoring.py`. There
are **two confidence models**, selected by `policy.confidence_model`:

- **`heuristic`** (default) — the transparent, explainable model described below.
  Simple enough to unit-test and explain to a researcher.
- **`bayes`** — a calibrated, closed-form **Bayesian** model (`bayes.py`). See
  [the Bayesian model](#the-bayesian-model-v02) below.

The two share the same evidence-gathering and the same `ClaimConfidence`
interface, so reports, the CLI, and the scheduler are identical either way; only
how `status`/`confidence` and the action scores are computed differs.

### The Bayesian model (v0.2)

Set `confidence_model: bayes` in `policy.yaml` to use a **finite-population
Normal–Normal hierarchical** model of the population effect `M` over the
project's `K` defined conditions. With `k` of `K` observed:

    obs_var = sigma_b^2 / k * (K - k) / K      (finite-population correction)
            + sum_i se_i^2 / k^2               (within-cell noise)

and a conjugate Normal prior gives `P(supported) = P(M >= minimum_effect_size)`.
The finite-population correction is the crux: observing **all** conditions
(`k = K`) removes between-condition uncertainty entirely, while a single dataset
(`k << K`) cannot establish generality — breadth-over-replication falls out of
the math, not a tuned penalty. Action scores use **value of information**: the
expected drop in decision uncertainty `p(1-p)` an action buys, so a new condition
scores far above an extra seed automatically.

This model is **calibrated**: an independent reliability experiment
(N = 200,000 draws from the model) measured an Expected Calibration Error of
**0.011** (well under 0.05) — when it says 80%, it is right about 80% of the
time. It is the honest upgrade from the heuristic; the heuristic remains the
default because it is faster to reach a decision and trivially explainable, while
`bayes` gives calibrated probabilities and a principled stopping rule. The
heuristic below is what runs unless you opt in.

### Evidence breadth

`evidence_breadth = len(effect_cells) / total_conditions`

where `effect_cells` is the set of `cell_key` values where both a method result
**and** a baseline result are present. A cell where the method has run but the
baseline has not contributes to `method_observed` but not to `effect_cells`.
This is the breadth gate: **generality is about the effect holding across
conditions, so only cells where the effect is actually measurable count toward
breadth**.

### Seed sufficiency

`seed_sufficiency = mean(seeds_per_cell[c] for c in effect_cells) / required_seeds`

clamped to [0, 1]. Like breadth, this is computed only over `effect_cells`.

### Reliability

`reliability = 0.5 * evidence_breadth + 0.5 * seed_sufficiency`

### The logistic support score

When at least one effect is measurable:

```
ref = max(minimum_effect_size, 0.02)
z   = (observed_effect - minimum_effect_size) / ref
support = logistic(z) = 1 / (1 + exp(-z))
```

`observed_effect` is the mean of per-cell effects, where each cell's effect is
`mean(method_results[cell]) - mean(baseline_results[cell])`, oriented so that
"good for the claim" is positive.

### Status assignment (the breadth gate)

```
if no results at all:          status = unknown
if method but no baseline:     status = needs_more_evidence
if reliability < 0.5:          status = needs_more_evidence
if support >= boundary + margin:
    if breadth >= 0.6:         status = supported
    else:                      status = needs_more_evidence   <- breadth gate
if support <= boundary - margin:
    if breadth >= 0.6:         status = refuted
    else:                      status = needs_more_evidence   <- breadth gate
else:                          status = weak
```

The breadth gate at 0.6 is the critical invariant: **a claim cannot reach
`supported` or `refuted` status unless at least 60% of its conditions have a
measurable effect (both method and baseline present)**. Adding more seeds on a
single dataset cannot compensate for missing conditions. This prevents a
single well-replicated dataset from "proving" a cross-dataset generality claim.

### Status values

| Status | Meaning |
|---|---|
| `unknown` | No experiment results linked to this claim yet |
| `needs_more_evidence` | Results exist but breadth < 60%, reliability < 0.5, or no baseline yet |
| `weak` | Support score near the decision boundary (`boundary ± margin`) |
| `supported` | Support score clearly above boundary and breadth >= 60% |
| `refuted` | Support score clearly below boundary and breadth >= 60% |
| `blocked` | The claim's *own* evidence is fine, but a `depends_on` subclaim is unmet |

The first five statuses come from the per-claim evidence above (`compute_claim_evidence`).
`blocked` is an **effective** status: it is assigned by the readiness layer when a
claim's own status would be `supported` but one of its `depends_on` subclaims is not
yet established (see *Paper Readiness* below). A claim's *own* status is never
`blocked`; only its effective status can be.

The `confidence` scalar on `ClaimConfidence` is `support` if measurable, else
`0.3 * evidence_breadth`. In the default `heuristic` mode it is a **ranking signal,
not a calibrated probability**; only the opt-in `bayes` mode (above) produces a
calibrated probability.

---

## Breadth vs Replication

"Breadth" refers to the fraction of a claim's experimental conditions where
the effect is measurable. "Replication" refers to running additional seeds of
an already-observed condition.

InsightFlow's central scheduling bias is: **breadth beats premature
replication**. The scheduler implements this in three places:

1. **Scoring**: an experiment whose cell is not yet observed (new condition)
   receives full `novelty = 1.0` in the decision-value and uncertainty-reduction
   terms. An experiment that duplicates an already-covered cell receives
   `novelty = 0.3` and a `premature_replication_penalty` proportional to
   `(1 - evidence_breadth) * importance`.

2. **Seed policy**: `decide_seed` returns `add=False` unless at least one
   specific criterion is met (see `docs/scheduling_policy.md`). When
   `add=False`, the seed-value term is zeroed and the premature-replication
   penalty is applied, making breadth alternatives dominate.

3. **Queue diversification**: `_classify` in the scheduler keeps at most one
   action per `(cell_key, is_baseline)` pair in the immediate queue. A second
   action on the same cell is relabelled as postponed with an explicit "do
   breadth first" annotation.

---

## Reviewer Risk

`reviewer_risk` on a `Claim` models the probability that a reviewer will
scrutinise this claim. It contributes to the `reviewer_risk_reduction` term in
the scoring objective:

- For a **missing-baseline launch**: full `reviewer_risk` weight (1.0
  multiplier). A result with no baseline to compare against is the most
  vulnerable to reviewer attack.
- For a **new-condition launch**: 0.7 multiplier.
- For an **extra seed or baseline rerun on an already-covered cell**: 0.2
  multiplier.

When `reviewer_risk >= 0.6` and a condition has method results but no baseline,
the scheduler emits a warning.

---

## Dependency Unlock

The `dependency_unlock` term rewards launching an experiment that unblocks
downstream experiments. The score for a pending experiment `e` is:

```
raw   = sum(_combine(importances of dependents' claims))
unlock = 1 - 1 / (1 + raw)          (saturating function in [0, 1))
```

where `_combine` gives the maximum contribution plus a 30% bonus for each
additional affected claim. The saturating form means a single high-importance
chain contributes most of the value; additional dependents add diminishing
returns.

---

## Paper Readiness

`readiness.py` is the layer that makes InsightFlow *claim-centered* rather than
experiment-centered. Given the per-claim evidence (from `scoring.py`) and the claim
graph (`depends_on`), it answers the question a researcher actually has before
submission: **is this paper ready, and if not, what is in the way?** It is a
deterministic, auditable function of the ledger — it never invents a verdict;
statuses come from the same evidence the scheduler uses. The CLI surface is
`insightflow readiness` (also an MCP tool).

### Own status vs. effective status

Each claim carries two statuses in the readiness report:

- **own status** — the `ClaimStatus` computed from *this claim's own evidence*
  (exactly the breadth-gated logistic status described under Claim Confidence).
- **effective status** — the own status combined with the claim graph. This is
  where `blocked` appears. `_effective_status` works as follows:
  - No `depends_on` -> effective status equals own status.
  - Own status is `supported` but a subclaim is unmet -> **`blocked`**.
  - A *meta-claim* with no runs of its own (own status `unknown`) is derived from
    its subgraph: `supported` if all subclaims are supported, `weak` if a subclaim
    is refuted, otherwise `blocked`.
  - Otherwise the claim keeps its own status (a `refuted` claim stays `refuted`).

A subclaim counts as a *blocker* whenever its own status is anything other than
`supported`.

### What the report contains

For every claim, `ClaimReadiness` records its type, importance, own and effective
status, confidence, the unmet `blockers`, `missing_baselines`, a `thin_generality`
flag (observed but breadth < 100% on an important claim), an `insufficient_seeds`
flag, its `reviewer_risk`, the ranked `reviewer_attacks`, and the recommended
`recommended_actions`.

At the project level, `ReadinessReport` buckets claims by effective status
(`supported` / `refuted` / `weak` / `needs_more_evidence` / `blocked`), lists the
**most dangerous reviewer attacks** (every claim's attacks sorted by
`reviewer_risk x importance`), the **next actions** (recommended actions ordered by
`importance + reviewer_risk`), and a single `paper_ready` boolean.

### Reviewer attacks and the paper-ready gate

The reviewer attacks are the auditable list of how a reviewer could break the paper
*right now*: generality argued from too few conditions, an effect with no baseline
to attribute it to, a "supported" claim resting on fewer than the required seeds, an
unestablished premise (a `depends_on` subclaim that is not yet supported), or a
direct contradiction (the evidence refutes the claim as stated).

`paper_ready` is intentionally strict: it is `True` only when **every** main or
high-importance (`importance >= 0.7`) claim is *effectively* supported. One blocked
main claim, one refuted key claim, or one key claim still gathering evidence is
enough to make the project not paper-ready. This is the signal an agent must read
(`insightflow readiness`) instead of eyeballing whether the paper is done.

---

## Research Actions

A claim-centered planner must recommend more than training runs. `actions.py`
provides **research actions** — units of work that advance a claim but are often not
GPU runs:

- `literature_search` — a novelty/positioning check before committing compute,
- `reviewer_attack` — adversarially stress a claim that *looks* decided but is thin,
- `theorem_attempt` / `counterexample_search` / `proof_verification` — for `theory`
  claims that runs alone cannot establish,
- `claim_refinement` — weaken, split, or scope a refuted/weak claim,
- `baseline_design`, `dataset_addition`, `run_ablation`, `run_stress_test`,
  `run_negative_control`, `write_related_work`, `write_limitations`,
  `paper_readiness_review`, and more (see `ActionType` in `schemas.py`).

A `ResearchAction` carries an `instruction` (what a human or agent should *do*)
rather than always a `command`, plus `expected_cost` (often ~0 for non-run actions)
and `expected_time` (a human/agent-time proxy).

### Where they come from

1. **Auto-generated** by `generate_research_actions` from the current claim
   evidence — deterministically, a handful per claim. For example: a
   `literature_search` for an important, high-reviewer-risk claim with no evidence
   yet; a `reviewer_attack` for a decided-looking but thin claim; a
   `claim_refinement` for a refuted or weak claim; a `theorem_attempt` for an
   unestablished `theory` claim.
2. **User-defined** in `actions.yaml` (config-loaded, `extra='forbid'`).

### How they are scored

`score_research_action` scores a research action into the same `PlanAction` shape as
an experiment, on the **same value-per-unit-cost basis**:

```
need  = max(claim_needs) + 0.3 * (sum(claim_needs) - max(claim_needs))
score = need / (expected_time + lambda_cost * expected_cost)
```

where `_claim_need` measures how strongly a given action type is warranted by a
claim's evidence (e.g. a `reviewer_attack` is needed in proportion to
`reviewer_risk` when the claim looks decided but thin; a `theorem_attempt` is needed
for an unestablished theory claim). Because actions and experiments share the
denominator, the scheduler can rank "adversarially attack C1" *above* another GPU run
when that is genuinely the higher-value next step — that is the point of having them.

---

## Theoretical Lineage

InsightFlow v0.1 is best understood against its related work.

### Pure-exploration bandits (Hyperband, ASHA, BOHB)

These methods allocate budget across hyperparameter configurations to find the
best one quickly. InsightFlow does not search hyperparameters and does not use
successive halving. The shared idea is budget-aware scheduling, but the
objectives are different: bandit methods maximise the probability of identifying
the best arm; InsightFlow maximises the probability of reaching a *claim
verdict* — which may require breadth across datasets, not just the best result
on one.

### Multi-fidelity / freeze-thaw Bayesian optimisation

Methods like freeze-thaw BO (Swersky et al. 2014) model learning curves to
decide whether to continue or pause a run. InsightFlow's `partial.py` does
analogous reasoning — stop a run that trails the baseline with no upward
trend, continue one that is beating the baseline on a critical condition — but
uses a hand-coded heuristic rather than a GP model of the learning curve. The
v0.2 roadmap lists "real partial-run monitoring" as a future upgrade.

### Value of Information / Knowledge Gradient / OCBA

The closest formal framing for InsightFlow's objective is **value of
information** (VoI): each action is scored by the expected reduction in
decision uncertainty per unit cost. The Knowledge Gradient (Frazier 2009) and
OCBA (Chen et al. 2010) formalise this for ranking/selection problems.

InsightFlow ships **two** scorers against this framing:

- The default `heuristic` scorer is a **transparent approximation** of VoI per
  unit cost: `decision_value` approximates information gain (importance ×
  boundary_factor × coverage_gap × novelty) and the denominator
  `expected_time + lambda * expected_cost` is the cost. It does not maintain a
  posterior and is not asymptotically optimal — it prioritises transparency and
  testability.
- The opt-in `bayes` scorer (`confidence_model: bayes`) **does** maintain a
  calibrated posterior (the finite-population Normal–Normal model above, ECE
  0.011) and scores actions by the literal expected reduction in decision
  uncertainty — a concrete, deterministic value-of-information rule. This is the
  Knowledge-Gradient-style scorer the earlier roadmap promised, now implemented.

Still future (v0.2+): learning-curve / freeze-thaw posteriors for partial runs,
and replacing the plug-in per-cell standard errors with a fully hierarchical
treatment of within-cell variance.

### DAG scheduling (HEFT)

The Heterogeneous Earliest Finish Time (HEFT) algorithm schedules a DAG of
tasks onto heterogeneous processors by ranking tasks on their upward cumulative
weight. InsightFlow handles experiment dependencies in a similar spirit: the
`dependency_unlock` term increases the score of an experiment that unblocks a
high-importance downstream experiment. InsightFlow does not do full HEFT
scheduling (no processor assignment, no critical-path analysis); it adds a
scalar unlock bonus to the existing multi-term objective.

### The novel framing

Existing tools (Hyperband, BO, AutoML) optimise **model performance** under a
compute budget. InsightFlow optimises **claim validation** under a research
budget. The distinction is:

- The optimisation target is a human-readable, falsifiable claim, not a
  metric value on a single dataset.
- The information unit is a claim verdict (supported/refuted), not a
  performance rank.
- Generality (effect measurable across conditions) is a first-class
  constraint, not an afterthought.
- Cost is the researcher's time-to-insight, not GPU-hours alone.

This makes InsightFlow complementary to AutoML and HPO tools: a researcher can
use Hyperband to find good hyperparameters, then use InsightFlow to decide which
datasets and baselines to run next to turn that finding into a defensible paper
claim.

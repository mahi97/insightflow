# InsightFlow Scheduling Policy

## Scheduling Objective

Every candidate action is assigned a priority score using the following
objective (from `scoring.py`):

```
priority(action) =
    ( w_dv  * decision_value
    + w_unc * uncertainty_reduction
    + w_dep * dependency_unlock
    + w_rev * reviewer_risk_reduction
    + w_seed * seed_value
    - w_red  * redundancy_penalty
    - w_prp  * premature_replication_penalty )
  / ( expected_time + lambda * expected_cost )
```

Default weights (from `Policy` defaults in `schemas.py`):

| Symbol | Field | Default |
|---|---|---|
| w_dv | `weight_decision_value` | 1.0 |
| w_unc | `weight_uncertainty` | 0.8 |
| w_dep | `weight_dependency` | 0.6 |
| w_rev | `weight_reviewer_risk` | 0.7 |
| w_seed | `weight_seed_value` | 0.5 |
| w_red | `weight_redundancy_penalty` | 0.9 |
| w_prp | `weight_premature_replication_penalty` | 1.0 |
| lambda | `lambda_cost` | 0.3 |

All weights are configurable in `configs/policy.yaml`.

---

## Term Definitions

Each term is computed per linked claim and then combined with `_combine(values)
= max(values) + 0.3 * (sum - max)`, which gives the dominant claim full weight
and adds a 30% bonus for each additional affected claim.

### Decision Value

```python
novelty = 1.0  if is_new_condition  (cell not yet observed for any linked claim)
        = 0.9  if is_missing_baseline  (baseline cell, method already there)
        = 0.4  if is_baseline and cell already has a baseline
        = 0.3  if cell already observed (extra seed or rerun)

boundary_factor = 1.0 if claim is near_boundary else 0.3
coverage_gap    = 1.0 - evidence_breadth

decision_value[claim] = importance * boundary_factor * (0.5 * coverage_gap + 0.5 * novelty)
```

In words: a new-condition launch on a high-importance claim whose evidence
is uncertain and whose conditions are not yet well covered scores highest.
A redundant rerun of an already-covered cell on a claim far from its decision
boundary scores close to zero.

### Uncertainty Reduction

```python
uncertainty = 1.0                               if support is None (unmeasured)
            = 1.0 - 2 * |support - 0.5|        otherwise   (0 at certainty, 1 at 50/50)

uncertainty_reduction[claim] = clamp(uncertainty) * novelty
```

In words: the expected reduction in decision uncertainty is highest when the
claim is currently at 50/50 and the action covers new territory (novelty = 1.0).
A run that adds more data to an already-decided claim reduces little uncertainty.

### Dependency Unlock

```python
dependents = [d for d in experiments if exp.id in d.dependencies and d is pending/postponed]

raw    = sum(_combine(importances of each dependent's linked claims))
unlock = 1 - 1 / (1 + raw)        # saturating in [0, 1)
```

In words: finishing an experiment that gates several high-importance downstream
experiments scores a large unlock bonus. The saturating form prevents the term
from dominating the objective when many dependents exist.

This term is always 0 for add-seed actions (seeds do not unlock dependencies).

### Reviewer Risk Reduction

```python
reviewer_risk_reduction[claim] = reviewer_risk * multiplier

multiplier = 1.0  if is_missing_baseline  (most vulnerable to reviewer attack)
           = 0.7  if is_new_condition
           = 0.2  otherwise
```

In words: the most valuable reviewer-risk reduction comes from supplying a
missing baseline for a condition that already has method results. Reviewers
cannot credibly challenge a comparison that has a proper baseline; they can
easily dismiss one that does not.

For add-seed actions the multiplier is `0.1 * reviewer_risk * urgency`.

### Seed Value (add-seed actions only)

```python
seed_value[claim] = urgency * (importance if claim_critical else 0.5)
```

`urgency` comes from `decide_seed` (see below). For launch actions, seed_value
is always 0.0.

### Redundancy Penalty

For launch actions:

```python
well_covered = (
    already_covered
    and seeds >= required_seeds
    and variance <= high_variance_threshold * max(minimum_effect_size, 0.02)
    and not near_boundary
)
redundancy_penalty[claim] = importance  if well_covered  else 0.0
```

For add-seed actions:

```python
well_covered = seeds >= required_seeds and not high_var and not near_boundary
redundancy_penalty[claim] = importance  if well_covered and not decision.add  else 0.0
```

In words: the penalty fires when the cell is already well-covered (enough seeds,
low variance, claim not near its decision boundary). Launching another run into
a well-covered cell wastes budget that could go to uncovered conditions.

### Premature Replication Penalty

For launch actions:

```python
premature_replication_penalty[claim] = (1 - evidence_breadth) * importance
                                       if already_covered  else 0.0
```

For add-seed actions:

```python
premature_replication_penalty[claim] = (1 - evidence_breadth) * importance
```

In words: adding depth to a cell while breadth is still incomplete is
penalised proportionally to how much breadth is missing and how important
the claim is. If only one of three datasets has been observed, the penalty
is large. If all datasets are covered, the penalty is zero.

Note that premature-replication penalty is always applied for add-seed actions
(there is always some breadth cost to deepening a single cell), while for launch
actions it fires only when the cell is already covered.

### Denominator

```python
denominator = max(1e-6, expected_time + lambda * expected_cost)
```

Cost is discounted relative to time by `lambda` (default 0.3). An experiment
that takes 2 GPU-hours and costs 4 units has denominator `2 + 0.3 * 4 = 3.2`.
This normalises the benefit terms to a "per unit resource" basis.

---

## Seed Allocation Policy

`seed_policy.decide_seed(exp, evidence, policy)` is called whenever the
candidate experiment's cell has already been observed (i.e. it would be an
extra seed). It returns a `SeedDecision` with `add: bool` and `urgency: float`.

**A seed is added (`add=True`) if at least one of these criteria fires:**

1. **Claim-critical and under-seeded**: the claim's `importance >= 0.7` (the
   `CRITICAL_IMPORTANCE` threshold) and the current seed count for this cell
   is below `required_seeds`. Urgency += 0.4.

2. **Borderline**: the claim is `near_boundary` (see `docs/concepts.md` — this
   is `True` for any status other than `supported` or `refuted`) and
   `|support - decision_boundary| < 0.25`. Urgency += 0.4.

3. **High variance**: the observed variance for this cell exceeds
   `high_variance_threshold * max(minimum_effect_size, 0.02)`. Urgency += 0.4.

4. **Under-seeded near boundary**: seeds < required_seeds AND the claim is
   `near_boundary`. Urgency += 0.3. (This can fire alongside criterion 1 for
   critical claims and alongside criterion 2 for borderline claims.)

Note: criterion 4 is distinct from criterion 1 — it covers non-critical claims
(importance < 0.7) that happen to be near the decision boundary.

**If none of the above fires (`add=False`)**:

The returned reason is: "Prefer breadth: extra replication has low decision
value until remaining conditions are covered." The scheduler still scores this
as an add-seed action, but because the seed-value term is zeroed (urgency = 0.0)
and the premature-replication penalty applies, breadth alternatives will
dominate in the ranked list.

**Urgency** is the sum of all triggered urgency increments, clamped to [0, 1].
Multiple criteria can trigger simultaneously (e.g. a critical, borderline,
high-variance cell accumulates urgency 0.4 + 0.4 + 0.4 = clamped to 1.0).

---

## Partial-Run Policy

`partial.monitor_partial(result, exp, state, evidence, policy)` examines an
in-flight run's `partial_history` and recommends one of six actions, based on
decision impact rather than raw performance.

### Decision tree

```
if no partial_history:
    -> continue (urgency 0.2, "no partial metric yet")

if linked claims are all decided (none near_boundary):
    -> stop (urgency 0.7, "cannot change the decision")

else (claim still at stake):

    if baseline is available:
        gap = oriented(current - baseline)

        if gap < 0 and not improving:
            -> stop (urgency 0.6, "trailing baseline, no upward trend")

        if gap > 0 and not declining:
            if claim_critical (importance >= 0.7) and under-seeded:
                -> continue (urgency 0.5, "beating baseline, lock in result")
            else:
                -> promote (urgency 0.5, "clearly beats baseline, shift workers to uncovered conditions")

        else (gap near 0 or trajectory uncertain):
            -> continue (urgency 0.4, "near decision boundary, still informative")

    if no baseline available:
        if improving:
            -> launch_baseline (urgency 0.6, "strong trend but no comparator")
        if declining:
            -> pause (urgency 0.5, "flat/declining, low decision value")
        else:
            -> continue (urgency 0.3, "early, inconclusive")
```

**Action definitions**:
- `continue`: keep the run running.
- `stop`: kill the run; free the worker.
- `pause`: suspend the run pending a decision.
- `promote`: accept the partial result as sufficient; redirect workers to
  uncovered conditions instead of finishing this run.
- `launch_baseline`: the method looks strong but there is no baseline; start
  one so the claim can be decided.
- `add_seed`: not currently emitted by `monitor_partial` directly; handled by
  the launch-time seed policy instead.

The `slope` used for "improving" / "declining" is computed as the average
step-to-step change over the most recent half of the partial history curve.

Partial-run actions are scored as `urgency / denominator` and inserted into
the scheduler's scored list alongside launch and add-seed actions.

---

## Queue Classification

After scoring all candidates, `Scheduler._classify` assigns each action to one
of three output lists.

### Diversification rule

At most one action per `(cell_key, is_baseline)` pair enters the immediate
queue. If a second action on the same cell would otherwise qualify, it is
relabelled as postponed with the annotation "extra seed of a condition already
in the immediate queue; do breadth first."

### Classification thresholds

```
if score >= queue_threshold (default 0.15)
   AND len(queue) < top_k (default 5)
   AND cell not already in queue:
       -> immediate queue

elif score >= avoid_threshold (default 0.03):
       -> postponed  (relabelled with ActionType.postpone)

else:
       -> avoided    (relabelled with ActionType.avoid)
```

For running-run actions (from `monitor_all`):
- `stop` or `pause` actions always enter the queue regardless of score.
- Other running-run actions enter the queue if `score >= avoid_threshold`,
  otherwise postponed.

For blocked actions (unmet dependencies): always postponed, regardless of score.

---

## Warnings

The scheduler generates warnings in three situations:

1. **Weak or refuted claim**: any claim currently at status `weak` or `refuted`
   gets a warning with its confidence score and the heuristic note.

2. **Missing baseline, high reviewer risk**: a claim with `reviewer_risk >= 0.6`
   that has at least one condition observed without a corresponding baseline.

3. **Incomplete generality on important claim**: a claim with
   `importance >= 0.7` where `evidence_breadth < 1.0` and at least one
   condition has been observed.

4. **Budget exceeded**: if the summed `expected_cost` of the immediate queue
   exceeds `resources.budget_gpu_hours`.

5. **No experiments defined** or **no pending experiments**: operational
   warnings to prevent silent no-ops.

---

## Assumptions Emitted by the Scheduler

Every plan includes these standing assumptions:

- InsightFlow is in **advisor mode**: it recommends; it does not launch, pause,
  or kill runs automatically.
- Claim confidence is a transparent heuristic, not a calibrated Bayesian
  posterior (see `docs/concepts.md`).
- Scoring is deterministic: the same ledger + policy always yields the same
  plan.
- The cost term uses `lambda=<value>` over `(time + lambda * cost)`.

---

## Worked Example: Demo Project

The `insightflow demo --force` command creates a project with:

- Three datasets: `cifar10`, `cifar100`, `svhn`.
- `method_a` (5 seeds per dataset) and `baseline_a` (2 seeds per dataset).
- Two claims: `C1` (high importance, reviewer_risk=0.7, required_seeds=3,
  minimum_effect_size=0.02) and `C2` (medium importance).
- Pre-seeded results: `method_a` seeds 0-2 on cifar10, and `baseline_a` seeds
  0-1 on cifar10.

**State after demo setup**:

- `effect_cells` for C1: `{cifar10|default}` (method and baseline both present).
- `evidence_breadth` for C1: 1 / 3 ≈ 0.33 (only cifar10 out of three datasets
  has a measurable effect).
- `seed_sufficiency`: 3 method seeds / 3 required = 1.0, but only over
  cifar10|default.
- `reliability` = 0.5 * 0.33 + 0.5 * 1.0 = 0.67.

**How the scheduler handles `method_a_cifar10_s3` (an extra seed)**:

- `cell_key = cifar10|default`, which is already in `observed_conditions`.
- `decide_seed` is called. For claim C1: importance=0.85 (>= CRITICAL_IMPORTANCE
  0.7) and seeds=3 which equals required_seeds=3, so criterion 1 does not fire
  (seeds are NOT under required). Assuming variance is within threshold and
  confidence is not borderline, no criterion fires -> `add=False`.
- The action is scored as add-seed with `urgency=0.0`, zeroing seed_value and
  applying the premature-replication penalty:
  `(1 - 0.33) * 0.85 ≈ 0.57` (large, because breadth is only 33%).
- Score is pulled down substantially relative to new-condition actions.

**How the scheduler handles `method_a_cifar100_s0` (new condition)**:

- `cell_key = cifar100|default`, not in `observed_conditions`.
- Scored as a launch with `novelty = 1.0`, `coverage_gap = 1 - 0.33 = 0.67`,
  `boundary_factor = 1.0` (claim is near boundary because breadth < 0.6 and
  reliability >= 0.5 but support is uncertain), no premature-replication
  penalty.
- `decision_value` for C1 ≈ `0.85 * 1.0 * (0.5 * 0.67 + 0.5 * 1.0) = 0.71`.

**Resulting plan**:

- `method_a_cifar100_s0` and `method_a_svhn_s0` enter the immediate queue
  (new conditions, high scores).
- The baseline `baseline_a_cifar100_s0` also enters (missing baseline for a
  new cell, reviewer risk is high).
- Extra cifar10 seeds (`method_a_cifar10_s3`, `method_a_cifar10_s4`) are
  postponed with rationale: "Postpone (add_seed): Prefer breadth: extra
  replication has low decision value until remaining conditions are covered.
  (extra seed of a condition already in the immediate queue; do breadth first)."

This matches the design goal stated in `demo.py`: "the interesting decision is
external validity (does the method generalize to CIFAR-100 / SVHN?) rather
than seed variance."

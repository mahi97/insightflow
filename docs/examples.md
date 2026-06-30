# Worked examples

InsightFlow is a claim-centered research decision layer for AI-assisted ML
research. It helps researchers and coding agents decide which evidence to acquire
next, when to stop, what to postpone, what to avoid, and which claims are
currently supported, refuted, weak, or still uncertain.

Every example below is **copy-pasteable** and the output is **real, captured**
from this repository — not hand-written. Everything is deterministic, so running
the commands yourself reproduces the same numbers.

> All commands use `uv run insightflow ...`. The `-C DIR` flag points at the
> project directory; without it, InsightFlow uses `$INSIGHTFLOW_HOME` or the
> current directory.

---

## 1. The demo claim graph

`demo` writes a small, self-contained project and seeds it with five completed
CIFAR-10 runs (three `method_a` seeds + two `baseline_a` seeds), so the
*interesting* decision is external validity — does the method generalize to
CIFAR-100 and SVHN? — rather than seed variance.

```bash
uv run insightflow demo --force -C /tmp/eval_demo
```

```
Demo project created at /tmp/eval_demo
Try: `uv run insightflow state` then `uv run insightflow plan`.
```

The project's `configs/claims.yaml` is a small **claim graph**: a main claim that
**depends on** two subclaims and is decided by *them*, not by runs of its own.

```yaml
claims:
- id: C0
  statement: method_a is a better method than baseline_a for this task family.
  type: main
  importance: critical
  reviewer_risk: 0.8
  depends_on: [C1, C2]            # <-- the claim graph edge
  evidence_requirements:
  - C1 (accuracy generalizes) supported
  - C2 (efficiency) supported
- id: C1
  statement: method_a improves accuracy over baseline_a, and this generalizes
    across datasets (external validity).
  type: empirical
  importance: high
  minimum_effect_size: 0.02
  required_seeds: 3
  reviewer_risk: 0.7
- id: C2
  statement: method_a is also more compute-efficient than baseline_a.
  type: efficiency
  importance: medium
  minimum_effect_size: 0.01
  required_seeds: 2
  reviewer_risk: 0.3
```

The graph is `C0 -> {C1, C2}`: `C0` is the headline paper claim, and it cannot be
defensible until both subclaims are. `state` shows the current evidence
(captured):

```
## Claims

| claim | status | conf | #cond | #seed | effect | min_eff | near_bdry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | unknown | 0.00 | 0 | 0 | - | 0.000 | yes |
| C1 | needs_more_evidence | 0.88 | 1 | 3 | 0.060 | 0.020 | yes |
| C2 | needs_more_evidence | 0.92 | 1 | 3 | 0.060 | 0.010 | yes |
```

`C1`/`C2` have a clear effect (0.060, well past the minimum) but only **1 of 3**
datasets observed, so they are `needs_more_evidence` (the breadth gate, not seed
count, is what is binding). `C0` has no runs of its own — it is `unknown` until
its subclaims are established. This is the whole point: **status is a function of
the claim graph and the evidence, computed deterministically, never invented.**

---

## 2. Readiness walkthrough: blocked main claim, reviewer attacks, next actions

`readiness` is the claim-centered report a researcher actually wants before
submission. On the demo project (captured):

```bash
uv run insightflow readiness -C /tmp/eval_demo
```

```
# Paper / project readiness

**0/2 key claim(s) effectively supported; 1 blocked, 0 refuted, 3 reviewer attack(s) open.**

Paper-ready (all key claims effectively supported): **False**

## Claim verdicts

| claim | type | own | effective | conf | rev_risk | blocked_by |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | main | unknown | blocked | 0.00 | 0.80 | C1, C2 |
| C1 | empirical | needs_more_evidence | needs_more_evidence | 0.88 | 0.70 | - |
| C2 | efficiency | needs_more_evidence | needs_more_evidence | 0.92 | 0.30 | - |

## Blocked claims: C0

## Most dangerous reviewer attacks (ranked)

1. Unestablished premise: C0 depends on C1, C2, which are not yet established.
2. Generality: C1 is argued from 33% of its conditions — a reviewer will say it is overclaimed from too few settings.
3. Generality: C2 is argued from 33% of its conditions — a reviewer will say it is overclaimed from too few settings.

## Recommended next research actions

- Establish the supporting subclaim(s) first: C1, C2.
- Consider a literature/novelty check for C0 before committing compute (no evidence yet, high importance).
- Add breadth for C1: cover an unobserved condition before more seeds (generality is the binding uncertainty).
- Add breadth for C2: cover an unobserved condition before more seeds (generality is the binding uncertainty).
```

Three things to read here:

- **`own` vs `effective` status.** `C0`'s own evidence is `unknown` (no runs), but
  its *effective* status is **`blocked`** — own evidence might be fine, but a
  `depends_on` subclaim is unmet. The distinction is the claim-graph logic in
  `readiness.py`.
- **Reviewer attacks are ranked by danger** (`reviewer_risk * importance`). The
  most dangerous attack is the structural one — `C0` rests on premises that are
  not yet established — followed by the generality attacks on the thin subclaims.
  These are the sentences a reviewer would actually write.
- **Next actions are concrete and ordered**: establish the subclaims first, do a
  literature/novelty check before spending compute on a high-importance claim with
  no evidence, and add *breadth* (a new dataset) before more seeds — because
  generality, not seed noise, is the binding uncertainty.

---

## 3. Research actions surfacing in a plan

`plan` ranks **research actions** (literature checks, reviewer attacks, claim
refinements, theorem attempts) *against* training runs by value per unit cost, so
the queue is not just "which experiment" but "what to do next, run or not."
Auto-generated actions come from `actions.py`; users can add their own in
`actions.yaml`. On the demo project (captured immediate queue):

```bash
uv run insightflow plan -C /tmp/eval_demo
```

```
## Immediate queue

| # | action | target | score | dec_val | cost | claims |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | launch | method_a / svhn / default / seed=0 | 1.091 | 0.83 | 1.1 | C1,C2 |
| 2 | launch | method_a / cifar100 / default / seed=0 | 1.067 | 0.83 | 1.2 | C1,C2 |
| 3 | literature_search | Literature/novelty check for C0 | 0.800 | 0.80 | 0.0 | C0 |
| 4 | reviewer_attack | Reviewer attack on C1 | 0.700 | 0.70 | 0.0 | C1 |
| 5 | launch | baseline_a / svhn / default / seed=0 | 0.692 | 0.53 | 0.9 | C1,C2 |
```

The two top recommendations are **new-condition launches** (SVHN, then
CIFAR-100) — breadth over replication. But ranked above the baseline run are two
**non-run research actions**: a literature/novelty check for the high-importance
main claim `C0` (which has no evidence yet), and a reviewer attack on `C1` (whose
evidence looks decided but is thin). Each carries an instruction for a human or
agent, e.g.:

```
3. **Literature/novelty check for C0** (literature_search) - literature_search affecting C0 ...
   - _Instruction:_ Search related work for C0: is the contribution novel and correctly positioned against existing methods before spending compute?
4. **Reviewer attack on C1** (reviewer_attack) - reviewer_attack affecting C1 ...
   - _Instruction:_ Adversarially stress C1: it looks decided but its evidence is thin (breadth/seeds). Try to break it before a reviewer does.
```

The **postponed** section shows the breadth-vs-replication logic explicitly:
extra SVHN/CIFAR-100 *seeds* are postponed with the reason *"extra seed of a
condition already in the immediate queue; do breadth first"*, and `explain` shows
the full scoring breakdown for the top action (captured):

```bash
uv run insightflow explain -C /tmp/eval_demo
```

```
### method_a / svhn / default / seed=0 (launch)

- Score: **1.0906**  (risk 0.00)

| term | value |
| --- | --- |
| + decision value | 0.8333 |
| + uncertainty reduction | 0.2875 |
| + dependency unlock | 0.0000 |
| + reviewer-risk reduction | 0.5530 |
| + seed value | 0.0000 |
| - redundancy penalty | 0.0000 |
| - premature-replication penalty | 0.0000 |
| = numerator | 1.4504 |
| / denominator (time + lambda*cost) | 1.3300 |
```

Every term is auditable, and the denominator is `time + lambda*cost`
(`lambda = 0.3`) — value **per unit cost**, not raw value.

---

## 4. CSV import + offline replay

This is the leak-free, counterfactual evaluation on a project whose runs are
already known. We build a three-dataset generality claim, import a 9-run history
in a deliberately suboptimal order (all method seeds first, baselines last), and
ask whether InsightFlow would have decided the claim sooner.

**Project configs** (`configs/claims.yaml` — one generality claim across three
datasets; `configs/experiments.yaml` — for each dataset, two `method_a` seeds and
one `baseline_a`, all linked to `C1`). **The CSV row ids match the experiment ids**,
so the configs supply the claim links and the CSV supplies the results:

```csv
id,method,dataset,seed,accuracy,finished_at,cost
method_a_cifar10_s0,method_a,cifar10,0,0.78,2026-01-01T00:00:00,1.0
method_a_cifar10_s1,method_a,cifar10,1,0.78,2026-01-01T01:00:00,1.0
method_a_cifar100_s0,method_a,cifar100,0,0.61,2026-01-01T02:00:00,1.0
method_a_cifar100_s1,method_a,cifar100,1,0.61,2026-01-01T03:00:00,1.0
method_a_svhn_s0,method_a,svhn,0,0.94,2026-01-01T04:00:00,1.0
method_a_svhn_s1,method_a,svhn,1,0.94,2026-01-01T05:00:00,1.0
baseline_a_cifar10_s0,baseline_a,cifar10,0,0.72,2026-01-01T06:00:00,1.0
baseline_a_cifar100_s0,baseline_a,cifar100,0,0.55,2026-01-01T07:00:00,1.0
baseline_a_svhn_s0,baseline_a,svhn,0,0.88,2026-01-01T08:00:00,1.0
```

Import and replay:

```bash
uv run insightflow import-csv -C /tmp/eval_csv --path /tmp/eval_csv/runs.csv --metric accuracy
uv run insightflow replay -C /tmp/eval_csv
```

```
Imported 9 run(s) from /tmp/eval_csv/runs.csv.
```

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

The **ground truth is the full-history verdict** (`C1: supported`). The *actual*
seeds-first order does not decide until run 8 — it only pairs baselines at the
very end. InsightFlow reveals results in scheduler order and decides at run **4**,
saving 4 runs and beating every non-adaptive ordering. The `--format json`
output shows *why* — its acquisition order pairs each method with its baseline on
a new dataset before replicating:

```bash
uv run insightflow replay -C /tmp/eval_csv --format json
```

```json
{
  "total_runs": 9,
  "ground_truth": {"C1": "supported"},
  "actual_decided_at": 8,
  "insight_decided_at": 4,
  "runs_saved": 4,
  "insight_order": [
    "method_a_cifar10_s0",
    "baseline_a_cifar10_s0",
    "method_a_svhn_s0",
    "baseline_a_svhn_s0"
  ],
  "policy_comparison": {"actual": 8, "insightflow": 4, "grid": 8, "random": 7, "cheap_first": 6, "seeds_first": 5}
}
```

After replay, `readiness` confirms the end state (captured):

```bash
uv run insightflow readiness -C /tmp/eval_csv
```

```
**1/1 key claim(s) effectively supported; 0 blocked, 0 refuted, 0 reviewer attack(s) open.**

Paper-ready (all key claims effectively supported): **True**

| claim | type | own | effective | conf | rev_risk | blocked_by |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | empirical | supported | supported | 0.88 | 0.70 | - |
```

> Note: `init --force` writes *default* starter configs. If you are scripting
> this, write your `configs/claims.yaml` and `configs/experiments.yaml` **after**
> `init` (or use `init` without `--force` on a fresh directory), then import — the
> import only adds run results, it does not define your claim links.

The same protocol works with `import-jsonl`, `import-mlflow`, and `import-wandb`;
CSV/JSONL need no extra dependencies, MLflow and W&B degrade gracefully if the
package or server is absent.

---

## 5. Bayesian mode (`confidence_model: bayes`)

By default, claim confidence is a transparent **ranking score** — a heuristic,
*not* a probability. Opt into the calibrated model by setting one field in
`configs/policy.yaml`:

```yaml
confidence_model: bayes
```

This switches the claim model to a finite-population Normal–Normal posterior on
the population effect and the scorer to a **myopic one-step approximate
value-of-information per unit cost** (deterministic 5-point Gauss–Hermite
quadrature). It is a *calibrated probability* under the model's stated
assumptions — an independent reliability experiment (N = 200,000 draws) measured
an Expected Calibration Error of **0.011** — not new math and not a guarantee of
optimality.

The same demo project, now in bayes mode (captured):

```bash
uv run insightflow state -C /tmp/eval_bayes
```

```
## Claims

| claim | status | conf | #cond | #seed | effect | min_eff | near_bdry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0 | needs_more_evidence | 0.50 | 0 | 0 | - | 0.000 | yes |
| C1 | weak | 0.83 | 1 | 3 | 0.060 | 0.020 | yes |
| C2 | weak | 0.88 | 1 | 3 | 0.060 | 0.010 | yes |
```

The numbers are now **calibrated posteriors**, and they read differently from the
heuristic:

- `C0` with no evidence sits at the **prior**, `0.50` (`needs_more_evidence`)
  rather than the heuristic's `0.00 / unknown` — an honest "we don't know yet."
- `C1`/`C2` are `weak`: their posterior mean effect is positive, but with only
  1 of 3 datasets observed, `P(supported)` is below the decision threshold (0.9).
  A single well-replicated dataset *cannot* push a cross-dataset claim to
  `supported` — that falls out of the finite-population correction, not a tuned
  penalty.

This changes the plan. Because `C1`/`C2` now read as `weak`, the top
recommendations become **claim-refinement / reviewer actions** — weaken or scope
the overclaimed generality before spending more compute (captured immediate
queue):

```bash
uv run insightflow plan -C /tmp/eval_bayes
```

```
| # | action | target | score | dec_val | cost | claims |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | claim_refinement | Refine/weaken/split C1 | 0.850 | 0.85 | 0.0 | C1 |
| 2 | literature_search | Literature/novelty check for C0 | 0.800 | 0.80 | 0.0 | C0 |
| 3 | reviewer_attack | Reviewer attack on C1 | 0.700 | 0.70 | 0.0 | C1 |
| 4 | claim_refinement | Refine/weaken/split C2 | 0.500 | 0.50 | 0.0 | C2 |
| 5 | launch | method_a / svhn / default / seed=0 | 0.293 | 0.11 | 1.1 | C1,C2 |
```

And `explain` shows the launch action now scored by **EVI**: in bayes mode the
`decision value` term *is* the value-of-information (an extra seed has ~0 EVI, so
the redundancy/replication penalties are subsumed and read 0), and the new-dataset
launch is driven mostly by reviewer-risk reduction (captured):

```bash
uv run insightflow explain -C /tmp/eval_bayes
```

```
### method_a / svhn / default / seed=0 (launch)

- Score: **0.2928**

| term | value |
| --- | --- |
| + decision value | 0.1129 |   # one-step EVI per the posterior
| + reviewer-risk reduction | 0.3950 |
| - redundancy penalty | 0.0000 |   # EVI subsumes these in bayes mode
| - premature-replication penalty | 0.0000 |
```

When to use which: the **heuristic** (default) is faster to a decision and
trivially explainable as a ranking; **bayes** gives calibrated probabilities and a
principled stopping rule (`P >= 0.9`) at the cost of being more conservative about
declaring generality. Both are fully deterministic.

---

## Reproducing these examples

```bash
uv run insightflow demo --force -C /tmp/eval_demo
uv run insightflow state     -C /tmp/eval_demo
uv run insightflow plan      -C /tmp/eval_demo
uv run insightflow readiness -C /tmp/eval_demo
uv run insightflow explain   -C /tmp/eval_demo

# bayes mode: copy the demo, set confidence_model: bayes in configs/policy.yaml
uv run insightflow state -C /tmp/eval_bayes
uv run insightflow plan  -C /tmp/eval_bayes

# CSV import + replay: see section 4 for the configs and runs.csv
uv run insightflow import-csv -C /tmp/eval_csv --path /tmp/eval_csv/runs.csv --metric accuracy
uv run insightflow replay     -C /tmp/eval_csv
```

For the evaluation methodology behind the replay and benchmark numbers, see
[docs/evaluation.md](evaluation.md). For the scoring math, see
[docs/concepts.md](concepts.md) and [docs/scheduling_policy.md](scheduling_policy.md).

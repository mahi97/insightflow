# Limitations

Honesty is the project's core principle: overstating what InsightFlow does is the
worst failure it can make. This document lists the real boundaries of the current
implementation, grounded in the code. None of these are hidden; they are part of
how the system should be understood and cited. For the positioning these
limitations qualify, see [`docs/paper_positioning.md`](paper_positioning.md); for
the field boundaries, see [`docs/related_work.md`](related_work.md).

The novelty of InsightFlow is the **integration and the objective** (claim-level
state, evidence requirements, reviewer-risk-aware scheduling, breadth-vs-
replication handling, a claim graph, a ledger-backed agent interface, replay
evaluation, and paper-readiness reporting) — **not new mathematics**, and **not**
any optimality guarantee.

---

## 1. The scheduler is myopic, not multi-step optimal

The value-of-information scorer is a **one-step (myopic) approximate EVI per unit
cost**. In Bayesian mode it computes, for a single candidate action, the expected
reduction in the decision uncertainty `u(p) = p(1-p)` over the next observation,
using deterministic 5-point Gauss-Hermite quadrature over the predictive
distribution ([`bayes.py:expected_voi_new_cell`](../src/insightflow/bayes.py)),
and divides by `expected_time + lambda * expected_cost`. It does **not** plan a
multi-step sequence and does **not** solve the underlying optimal-stopping /
sequential-design problem. Consequently there is **no global-optimality
guarantee**. What we can say is empirical: on the synthetic benchmark its
worst-case runs-to-decision is 1.25x the oracle (see §3), which is good one-step
behavior, not optimality.

## 2. Confidence is calibrated *under assumptions*; the default mode is a ranking score

There are two scorers, and their epistemic status differs:

- **Bayesian mode** (`confidence_model: bayes`) maintains a finite-population
  Normal-Normal posterior on the mean effect over the project's defined K
  conditions ([`bayes.py:population_posterior`](../src/insightflow/bayes.py)). Its
  `P(supported)` is a **calibrated probability** — measured Expected Calibration
  Error of **0.011 over 200k draws** — but that calibration holds **under the
  model's stated assumptions** (effects Normal around a hyper-mean, a Normal prior
  on the mean, a finite-population correction, and per-cell standard errors). When
  reality departs from those assumptions, the calibration claim weakens
  accordingly. The calibration is verified against the model's *own* generative
  process in [`tests/test_bayes.py:test_posterior_is_calibrated`](../tests/test_bayes.py),
  which is a self-consistency / correct-implementation check, not evidence of
  calibration on real-world ML projects.
- **Heuristic mode** (the default) is an explicit, transparent **ranking score**,
  **not a probability** ([`scoring.py`](../src/insightflow/scoring.py)). Its
  "confidence" numbers are monotone signals for ordering actions and flagging
  claims; they should not be read as `P(claim is true)`. The scheduler itself
  states this in its assumptions output
  ([`scheduler.py:_assumptions`](../src/insightflow/scheduler.py)).

## 3. The benchmark is synthetic, and the agent evaluation has small n

The quantitative evidence is honest but limited in scope:

- **Synthetic benchmark.** Results come from **7 synthetic scenarios** —
  `breadth`, `expensive_branch`, `dependency_unlock`, `reviewer_baseline`,
  `noisy_seeds`, `refuted`, `mixed_multi_claim`
  ([`simulator.py:SCENARIOS`](../src/insightflow/simulator.py)) — with *hidden
  ground truth*, not real research projects. On these, InsightFlow reaches the
  correct decision in **~5.4 runs on average**, with **worst-case 1.25x the
  oracle** and **7/7 scenarios solved** — the best record among the non-oracle
  policies — and saves roughly **54% of runs vs the full grid** on average. These
  scenarios were authored to exercise specific capabilities; they are designed to
  be favorable to the kind of reasoning InsightFlow does, and should be read as
  *illustrative of where the gains come from*, not as a claim about arbitrary
  real projects.
- **Ablations confirm the components matter, on the same synthetic data.** Each
  ablation is InsightFlow with one component disabled —
  `ablate_reviewer_risk`, `ablate_breadth_penalty`, `ablate_cost`,
  `uncertainty_only` ([`simulator.py:POLICIES`](../src/insightflow/simulator.py)).
  The `uncertainty_only` ablation **fails the multi-claim scenario** (it solves
  only one of the seven), which shows the non-uncertainty terms are load-bearing —
  but, again, on synthetic projects.
- **Agent-in-sandbox evaluation has small n and is illustrative.** In a sandbox,
  real Claude/Sonnet agents driving the InsightFlow CLI saved roughly **50-69% of
  compute with no loss in correctness** versus an unaided agent, on the tasks
  tested. The sample is **small** and the tasks are hand-selected; treat this as
  an encouraging illustration, not a statistically powered result.

## 4. Per-cell standard errors are plugged in, not jointly modeled

The Bayesian model treats each observed cell's within-cell variance as a **plug-in
standard error** rather than inferring it jointly with the population effect. When
a cell has fewer than two seeds, the per-seed noise falls back to a configured
default (`within_seed_sd`) floored to avoid degeneracy
([`scoring.py:compute_claim_evidence`](../src/insightflow/scoring.py),
[`bayes.py`](../src/insightflow/bayes.py)). This is a deliberate simplification
that keeps the posterior closed-form and deterministic, at the cost of not
propagating uncertainty in the variance estimates. A fully hierarchical treatment
of within-cell variance is named as future work, not a current capability.

## 5. No cluster launchers, live monitoring, server, or dashboard

InsightFlow is advisor-first. There is a **local** launcher that can run an
experiment on the spot and record the result
([`launcher.py`](../src/insightflow/launcher.py)), and a partial-history
monitor that reasons over already-recorded curve points
([`partial.py`](../src/insightflow/partial.py)). There is **no** Slurm/Ray cluster
submission, **no** live run-monitoring service, **no** long-running server, and
**no** web dashboard. The interfaces are a CLI, a Python library, an MCP server,
and a Claude Code plugin — all reading and writing the same ledger.

## 6. Most research actions are represented and scored, but not executed

Beyond training runs, InsightFlow can represent and rank research actions such as
literature search, reviewer attack, theorem attempt, claim refinement, and
baseline design ([`actions.py`](../src/insightflow/actions.py),
[`schemas.py:ActionType`](../src/insightflow/schemas.py)). These are auto-generated
from the evidence and/or user-defined in `actions.yaml`, and scored against
experiments by value per unit cost — but for the most part they produce an
**instruction for a human or agent to carry out**, not an executed result. The
exceptions are run-level actions and the local launcher. In other words,
InsightFlow decides *what should be done*; with few exceptions it does not *do* the
non-run actions itself.

## 7. It is not a guarantee of truth, and not a replacement for human judgment

A `supported` verdict means *the available evidence supports the claim under the
stated assumptions and thresholds* — it is **not proof that the claim is true**,
and a `refuted` or `weak` verdict is not proof of the opposite. The verdicts and
the value-of-information scores are decision aids. They are deterministic and
auditable so a human can inspect and overrule them, which is the intended use:
**InsightFlow informs research judgment; it does not replace it.**

---

## Tested, lint-clean, and type-checked — with one honest caveat

The codebase is **26 source modules** with ** passing tests** and is **mypy
clean** (26 source files, no issues). It is *intended* to be `ruff` clean; at the
time of writing `ruff check src/` reports a single auto-fixable import-ordering
warning in `src/insightflow/__init__.py` (`I001`), unrelated to the behavior of
the system. This is noted here rather than rounded up to "clean," in keeping with
the project's honesty principle.

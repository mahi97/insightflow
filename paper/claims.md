# InsightFlow — The Paper's Own Claims (as a claim graph)

This file applies InsightFlow to itself: it states the paper's claims as a claim
graph (one main claim, supporting empirical / method / evaluation subclaims),
and for each records (a) the statement, (b) type / importance / reviewer-risk,
(c) `depends_on`, (d) **evidence that currently supports it**, (e) **what is
still missing**, and (f) a self-critical **verdict NOW**:

- **SUPPORTED (now)** — evidence in the repo backs it as stated.
- **WEAK (now)** — partially supported; the framing overreaches the evidence.
- **NOT YET** — would need work/data we do not have.
- **BLOCKED** — own evidence ok but depends on an unmet subclaim.

> Honesty is the project's core principle. Where the evidence is thin or sampled
> from our own model, the verdict says so. We do **not** claim new math or global
> optimality anywhere below.

---

## C0 — MAIN CLAIM

**Statement.** *A claim-centered decision layer — a claim graph + readiness
assessor + value-of-information-inspired, reviewer-risk-aware scheduler + a
ledger-backed agent interface — lets human and AI researchers reach defensible
paper-claim verdicts with substantially less compute than naive scheduling, while
keeping every verdict and recommendation auditable.*

- type: main · importance: 1.0 · reviewer_risk: 0.8
- depends_on: **C1, C2, C3, C4, C5, C6**

**Supports now.** The system exists end-to-end (26 modules,  passing tests —
the test suite has
`mypy`-clean): claim graph (`schemas.py`), readiness (`readiness.py`), scheduler
(`scheduler.py` + `scoring.py` + `bayes.py`), research actions (`actions.py`),
ledger + CLI + MCP. The benchmark shows ~56% runs saved vs. grid and 7/7 solved
at 1.25× worst-case oracle (C1). Determinism/auditability is structural (C5).

**Missing.** The "substantially less compute" half is shown on synthetic
scenarios + a small agent study + replay; it is **not** shown on a controlled
real-world human study. "Defensible verdict" is graded by our own confidence
readout, not by real reviewers.

**Verdict NOW: WEAK (defensible as a *systems + synthetic-evaluation*
contribution; the strong "for real researchers, at scale" reading is NOT YET).**
The main claim is **BLOCKED** in the strict sense only if any required subclaim
fails; none do, but C7 (real-world generalization) is intentionally *not* a
dependency because we do not yet support it — and that is the honest scope limit.

---

## C1 — Empirical: efficiency on the scenario benchmark

**Statement.** *On 7 controlled scenarios, InsightFlow reaches the correct
research decision in ~5.2 runs on average, within 1.25× of an oracle in the
worst case, solving 7/7 — the best among non-oracle policies — and saving ~56% of
runs vs. a full grid.*

- type: empirical · importance: 0.95 · reviewer_risk: 0.7 · depends_on: —

**Supports now (measured, this repo, `run_scenarios(steps=40, n=5, seed=0)`):**
- mean runs-to-decision (insightflow) = **5.23**; oracle = 5.03.
- worst-case ratio vs oracle = **1.25×**; scenarios solved = **7/7**.
- best non-oracle: every naive policy is ≥1.8× worst-case (all_tasks_first 1.80×,
  grid 3.00×, all_seeds_first 3.00×) and several solve fewer cleanly.
- mean runs saved vs grid = **56.0%** (per-scenario +44.4% … +66.7%).

**Missing / caveats.** Synthetic scenarios we designed; the oracle and all
policies share one confidence readout (isolates scheduling but is not external
ground truth). "~5.4" in the project summary vs "5.23" here is a
seed/`n_projects` difference, not a discrepancy — both describe the same regime;
the draft must state the exact config it reports.

**Verdict NOW: SUPPORTED** (as a claim about *these scenarios under this
protocol*). The generalization beyond them is C7, separately scoped.

---

## C2 — Method: the claim-centered formulation is well-posed and implemented

**Statement.** *Claims (typed, with effect sizes, required seeds, reviewer-risk,
dependencies) and the verdict taxonomy (supported/refuted/weak/needs-more/
blocked, own vs. effective) form a coherent, implemented model in which breadth
gates generality and unmet dependencies block a claim.*

- type: method · importance: 0.9 · reviewer_risk: 0.5 · depends_on: —

**Supports now.** `schemas.py` (typed claim graph, `extra='forbid'`),
`scoring.py` (breadth-gated status: seed depth cannot prove a cross-condition
claim), `readiness.py` (`_effective_status`: supported-but-unmet-dependency →
`blocked`; meta-claim derived from subgraph). Tests in `test_schemas.py`,
`test_scoring.py`, `test_readiness.py`.

**Missing.** It is *a* coherent formalization, not *the* canonical one; no
axiomatic justification. The claim taxonomy is pragmatic, not derived.

**Verdict NOW: SUPPORTED** (as "a coherent, implemented, tested formulation").

---

## C3 — Method: VoI-inspired scheduler with a calibrated opt-in mode

**Statement.** *Actions are scored by expected progress toward a verdict per unit
cost; the opt-in `bayes` mode uses a finite-population Normal–Normal posterior
and a deterministic myopic one-step EVI (Gauss–Hermite quadrature) that is
calibrated under its assumptions (ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`)).*

- type: method · importance: 0.9 · reviewer_risk: 0.7 · depends_on: —

**Supports now.** `scoring.py` objective; `bayes.py` posterior with
finite-population correction + `expected_voi_new_cell` (5-point Gauss–Hermite).
Tests: `test_bayes.py` (`test_posterior_is_calibrated` — 600 draws: aggregate
predicted ≈ actual, hi-confidence >75% right, lo-confidence <25%;
`test_expected_voi_quadrature_is_positive_diminishing_and_deterministic`;
bayes-mode scheduler decides & is deterministic). EVI determinism is structural
(fixed grid).

**Missing / honest caveats.**
- **Myopic, not optimal** — one step, no lookahead. (Stated, not a flaw to hide.)
- **ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) "over 200k draws"** is documented in `docs/concepts.md` /
  `docs/roadmap.md` but **no committed script reproduces the 200k figure**; the
  committed test uses 600 draws and asserts the *property*, not the 0.011 value.
  → Either commit the 200k script or report the 600-draw ECE in the paper.
- Calibration is on data from the model's **own** generative process
  (well-specification check), not real effects.
- Heuristic mode is a **ranking**, not a probability — must never be reported as
  one.

**Verdict NOW: WEAK.** The *mechanism* and the *property* are SUPPORTED and
tested; the specific number **0.011** is **NOT independently reproducible from
the repo as committed** and must be downgraded/-qualified or backed by a
committed script before it appears as a headline figure.

---

## C4 — Method: research actions are co-scheduled with experiments

**Statement.** *Non-run research actions (literature check, reviewer attack,
theorem attempt, claim refinement, …) are auto-generated from evidence and scored
on the same value-per-cost scale as experiments, so the planner can recommend
"check the literature before spending compute."*

- type: method · importance: 0.8 · reviewer_risk: 0.5 · depends_on: —

**Supports now.** `actions.py` (`generate_research_actions`,
`score_research_action`); scheduler merges them into the ranked queue
(`scheduler.py`). Tests in `test_actions.py`.

**Missing.** The *value* of recommending a literature check or reviewer attack is
not measured against an outcome — it is plausible and implemented, but there is
no experiment showing it changes research outcomes. The need-scores are
hand-designed.

**Verdict NOW: SUPPORTED as "implemented and co-scheduled"; NOT YET as "shown to
improve outcomes."** The paper must phrase this as a *capability*, not a measured
*benefit*.

---

## C5 — Method/Systems: auditable, deterministic control plane

**Statement.** *Every verdict and plan is a deterministic, inspectable function
of the ledger; the same ledger + policy always yields the same plan, with a
per-action factor breakdown.*

- type: method · importance: 0.8 · reviewer_risk: 0.4 · depends_on: —

**Supports now.** `compute_state_hash`, deterministic scoring (pure functions of
`State`+`Policy`), `explain` factor breakdown, sorted iteration for
float-determinism in `scoring.py`, determinism tests (`test_bayes.py`,
`test_scheduler.py`, `test_replay.py`). SQLite+JSONL ledger (`ledger.py`).

**Missing.** "Auditable" is a property of the *plan*, not a guarantee that a
human/agent acts on it; no audit-trail UI study.

**Verdict NOW: SUPPORTED.**

---

## C6 — Eval/Systems: ledger-backed agent interface + replay evaluation

**Statement.** *A ledger-backed CLI + MCP interface lets AI agents share one
auditable state, and a leak-free replay lets us evaluate research trajectories on
already-collected histories; an illustrative agent study shows 50–69% compute
saved at equal correctness.*

- type: eval · importance: 0.85 · reviewer_risk: 0.7 · depends_on: C5

**Supports now.** `mcp_server.py` (tools incl. `readiness`), CLI (`replay`,
`import-{wandb,csv,mlflow}`), `replay.py` (leak-free counterfactual + multi-policy
comparison), tests `test_mcp_server.py`, `test_replay.py`, `test_importers.py`,
`test_wandb_importer.py`. Agent study referenced in `docs/agent_driven_project.md`.

**Missing.** The **50–69% agent-eval numbers are not reproduced by a committed
artifact** in this repo (no logged transcripts/script found under `scripts/` or
`tests/`); they are described, with small n, as illustrative. Replay's value is
demonstrated structurally but not on a large corpus of real projects.

**Verdict NOW: WEAK.** The interface and replay machinery are SUPPORTED and
tested; the **50–69% figure is illustrative and not currently reproducible from
the repo** — it must be reported as such (small n, no committed artifact) or
backed by committed transcripts.

---

## C7 — (Explicitly NOT YET) real-world generalization

**Statement.** *These gains transfer to real ML research projects and real
researchers at scale.*

- type: empirical · importance: 0.9 · reviewer_risk: 0.9 · depends_on: C1, C6

**Supports now.** Only indirect: replay machinery + a small agent study + the
fact that scenarios were designed to mirror real failure modes (over-replication,
missing baselines, expensive branches).

**Missing.** A controlled human study; replay on a large corpus of real,
externally-sourced projects; calibration on real (not self-generated) effects.

**Verdict NOW: NOT YET.** This is deliberately *not* a dependency of C0; the
paper must scope C0 to "systems + synthetic + small agent/replay evidence" and
list C7 as the central future work. Claiming C7 now would violate the honesty
principle.

---

## Readiness summary (self-assessment)

| claim | verdict NOW | the honest gap |
|---|---|---|
| C0 main | WEAK (systems+synthetic defensible) | no real-world human study |
| C1 efficiency | **SUPPORTED** | only on our 7 scenarios / shared readout |
| C2 formulation | **SUPPORTED** | pragmatic, not canonical |
| C3 VoI+calibration | WEAK | 0.011 over 200k not repo-reproducible; myopic |
| C4 research actions | SUPPORTED (capability) | benefit not measured |
| C5 auditable plane | **SUPPORTED** | — |
| C6 agent iface+replay | WEAK | 50–69% not repo-reproducible, small n |
| C7 real-world | **NOT YET** | the whole external study |

**Most dangerous reviewer attacks (ranked by reviewer_risk × importance):**
1. C3/C6 — headline numbers (ECE ~= 0.011 (reproduce with `uv run python scripts/calibration.py`) / agent 50–69%) cited but **not
   reproducible from committed artifacts**. *Fix before submission:* commit the
   200k-draw calibration script and the agent-eval transcripts, or restate the
   numbers as the committed-test property (600 draws) and an illustrative pilot.
2. C0/C7 — overreading "for real researchers." *Fix:* scope C0 explicitly.
3. C1 — "rigged synthetic benchmark." *Fix:* lead with worst-case-vs-oracle and
   replay; publish generators (already done).

**Paper-ready?** As a systems + synthetic-evaluation + pilot paper for a
tools/automation venue: **close, pending the two reproducibility fixes above.**
As a "validated for real ML research" claim: **not yet.**

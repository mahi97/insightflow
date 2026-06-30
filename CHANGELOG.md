# Changelog

All notable changes to InsightFlow are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [0.3.0] — unreleased

Reframed as a **claim-centered research decision layer** (not an experiment
scheduler): decide which evidence to acquire next to reach defensible *claim
verdicts* under cost, uncertainty, and reviewer risk.

### Added
- **Claim graph.** Claims gain `type`
  (main/empirical/mechanism/efficiency/robustness/theory/limitation/negative/auxiliary),
  `depends_on`, `blocks`, and `evidence_requirements`; a new `blocked` status. Config
  models are now `extra="forbid"` so YAML typos are rejected with an actionable
  message; claim-graph edges and cycles are validated.
- **Paper-readiness assessment** (`readiness.py`, `insightflow readiness`, MCP tool):
  per-claim own-vs-effective status (a main claim is *blocked* when a supporting
  subclaim is unmet; a meta-claim is derived from its subgraph), ranked reviewer
  attacks, missing baselines, thin generality, insufficient seeds, and recommended
  next research actions.
- **First-class research actions** (`actions.py`, `actions.yaml`): literature search,
  reviewer attack, theorem attempt, claim refinement, ablation/stress/negative-control,
  etc. — auto-generated from the evidence and/or user-defined, scored against
  experiments so the planner can say "do a literature search before spending compute".
- **Faithful Expected Value of Information** for new-condition actions: a deterministic
  Gauss–Hermite preposterior `EVI = U(current) − E_y[U(posterior|y)]` (replacing the
  point-at-the-mean estimate). Still a *myopic* one-step EVI per unit cost.
- **Stronger evaluation**: ablation policies (ablate_reviewer_risk / breadth_penalty /
  cost, uncertainty_only) and a `baseline_first` policy; a `mixed_multi_claim` scenario
  (one supported + one refuted claim, both must be decided); multi-policy offline replay
  (actual / insightflow / grid / random / cheap_first / seeds_first).
- Paper package (`paper/`) and positioning / related-work / limitations / evaluation /
  examples docs.

## [0.2.0] — unreleased

### Added
- **Calibrated Bayesian claim model + value-of-information scoring** (opt-in via
  `policy.confidence_model: bayes`). A deterministic, finite-population
  Normal–Normal posterior on the population effect; actions scored by expected
  reduction in decision uncertainty. Adversarially verified (math, code) and
  calibrated (Expected Calibration Error 0.011 over 200k draws). The heuristic
  model remains the default.
- **Freeze-thaw learning-curve extrapolation** (`curves.py`): the partial-run
  policy now decides continue/stop/promote on the *projected* final value of a
  run (saturating-exponential fit), not just the current value.
- **Local launcher** (`insightflow run [--execute]`): runs an experiment's
  `command` locally, captures metrics from a JSON stdout line (or
  `$INSIGHTFLOW_METRICS_FILE`), and records the result.
- **CSV / JSONL / MLflow importers** (`import-csv`, `import-mlflow`) alongside the
  existing W&B importer; all mockable/testable without live services.
- **Offline replay evaluation** (`insightflow replay`): counterfactually replays
  a project's known results and reports how many runs InsightFlow would have
  saved to reach the full-history decision.
- **Multi-scenario benchmark** (`benchmark --all-scenarios`) with six task types
  including `refuted` (the method genuinely does not beat the baseline), plus a
  robustness summary vs the oracle.
- **Claude Code plugin** (`.claude-plugin/`): installable skill pack
  (adaptive-experiment-scheduler, define-claims, interpret-results,
  writeup-from-ledger), a guard hook, and `/insightflow-*` slash commands.
- Agent-driven-project guide, autonomous-research-loop prompt, and an
  install-and-use guide.

### Changed
- Documentation updated to reflect the Bayesian model, the launcher, and the new
  importers/replay. Scoring/scheduler thresholds are value-of-information-aware in
  Bayesian mode.

## [0.1.0]

### Added
- Typed domain model; deterministic heuristic scoring engine and scheduler;
  SQLite + JSONL ledger; seed-allocation and partial-run policies; synthetic
  simulator + benchmark; W&B importer with mocked tests; Markdown/JSON reports;
  the `insightflow` CLI (init, validate, state, plan, explain, demo,
  simulate-step, benchmark, import-wandb, log-result); CLAUDE.md / AGENTS.md and
  prompt templates.

# Changelog

All notable changes to InsightFlow are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [0.2.0] — unreleased

### Added
- **Calibrated Bayesian claim model + value-of-information scoring** (opt-in via
  `policy.confidence_model: bayes`). A deterministic, finite-population
  Normal–Normal posterior on the population effect; actions scored by expected
  reduction in decision uncertainty. Adversarially verified (math, code) and
  calibrated (Expected Calibration Error 0.0119 over 200k draws). The heuristic
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

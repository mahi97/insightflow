# Master Prompt for Claude Code: Build InsightFlow End-to-End

You are Claude Code acting as the principal engineer, research-systems architect, and test engineer for a new open-source project called **InsightFlow**.

This is not a toy, not a sample, not a sketch, and not a partially working demo. Build a real, usable v0.1 project from scratch with production-quality structure, tests, documentation, and a working CLI.

## Product goal

InsightFlow is an adaptive experiment scheduler for machine learning and AI research. It optimizes **time-to-insight**, not hyperparameter tuning and not final validation accuracy.

The system helps researchers decide:

- what experiment to run next
- what run to postpone
- what run to avoid
- when to add seeds
- when to broaden across new conditions
- when a partial run should continue, pause, or stop
- which missing result is most dangerous for the paper
- which claims are sufficiently supported
- which claims are weak or should be revised

It must work as a practical tool researchers can use inside a real repository with Claude Code, W&B, uv, and local files. The first version should be CLI-first and agent-native, with clean internal APIs so it can later become a server, dashboard, and MCP tool.

## Non-negotiable requirements

1. Use `uv` for all tasks.
2. Include W&B import support.
3. Build a real Python package with a CLI.
4. Include a deterministic scheduler, not only LLM prompts.
5. Include tests.
6. Include documentation.
7. Include example configs.
8. Include a synthetic simulator and benchmark so the tool can be tested without a real research project.
9. Do not require a dashboard or server in v0.1, but design the core so those can be added later.
10. Do not make the AI agent the source of truth. The CLI and ledger are the source of truth. The agent only interfaces with them.
11. Do not stop until the project passes the acceptance tests in `ACCEPTANCE_TESTS.md`.
12. Every important command must work through `uv run ...`.
13. No hardcoded absolute paths.
14. No hidden external services required except optional W&B import.
15. All external integrations must degrade gracefully when credentials or dependencies are unavailable.
16. Avoid placeholder code. If something is not implemented, mark it clearly as future work and do not claim it works.

## Build philosophy

This is not AutoML. This is not HPO. This is not experiment tracking.

It is **adaptive evidence acquisition over research claims**.

The central scheduling objective is:

```text
priority(action) =
    expected decision value
  + expected uncertainty reduction
  + dependency unlock value
  + reviewer-risk reduction
  - redundancy penalty
  - premature-replication penalty
  ---------------------------------
    expected wall-clock time + lambda * expected compute cost
```

A run is valuable only if it can affect a claim, reduce uncertainty, unlock decisions, reduce reviewer risk, or prevent expensive waste.

## Expected repository structure

Create this repository structure. Adjust only if there is a strong engineering reason.

```text
insightflow/
  pyproject.toml
  README.md
  QUICKSTART.md
  LICENSE
  CLAUDE.md
  AGENTS.md
  .gitignore

  configs/
    claims.yaml
    experiments.yaml
    resources.yaml
    policy.yaml

  examples/
    toy_project/
      claims.yaml
      experiments.yaml
      resources.yaml
      README.md
    train_stub.py
    wandb_import_example.md

  src/
    insightflow/
      __init__.py
      cli.py
      schemas.py
      ledger.py
      scoring.py
      scheduler.py
      simulator.py
      benchmark.py
      reports.py
      explain.py
      partial.py
      seed_policy.py
      wandb_importer.py
      config.py
      utils.py
      errors.py

  tests/
    test_schemas.py
    test_ledger.py
    test_scoring.py
    test_scheduler.py
    test_seed_policy.py
    test_simulator.py
    test_benchmark.py
    test_cli_smoke.py
    test_wandb_importer.py

  docs/
    architecture.md
    concepts.md
    scheduling_policy.md
    wandb.md
    agent_workflow.md
    roadmap.md

  prompts/
    claude_research_agent_prompt.md
    replanning_prompt.md
    review_plan_prompt.md

  scripts/
    dev_check.sh
```

## Core domain model

Implement typed models using Pydantic or dataclasses with validation. Prefer Pydantic if it fits cleanly.

Minimum entities:

### Claim

Fields:

- id
- statement
- priority or importance
- target_metric
- desired_direction: higher/lower
- minimum_effect_size
- required_seeds
- reviewer_risk
- status: unknown/supported/weak/refuted/needs_more_evidence
- notes

### Experiment

Fields:

- id
- command or config
- method
- baseline
- dataset
- model
- condition
- seed
- claim_links
- dependencies
- expected_cost
- expected_time
- resource_type
- status: pending/running/completed/failed/postponed/avoided
- tags
- notes

### RunResult

Fields:

- run_id
- experiment_id
- seed
- metrics
- cost
- wall_time
- status
- started_at
- finished_at
- source: manual/wandb/simulator/import
- partial_history
- notes

### PlanAction

Fields:

- experiment_id
- action_type: launch/continue/pause/stop/postpone/add_seed/add_experiment/avoid
- score
- affected_claims
- rationale
- expected_decision_value
- expected_uncertainty_reduction
- expected_cost
- expected_time
- risk
- checkpoint

### Plan

Fields:

- id
- created_at
- actions
- summary
- warnings
- assumptions
- state_hash

## CLI requirements

Implement a CLI named `insightflow` and also alias `insight` if convenient.

Required commands:

```bash
uv run insightflow init
uv run insightflow state
uv run insightflow plan
uv run insightflow explain --plan PLAN_ID
uv run insightflow demo --force
uv run insightflow simulate-step
uv run insightflow benchmark --steps 20
uv run insightflow import-wandb --entity ENTITY --project PROJECT --metric METRIC --limit 200
uv run insightflow log-result --experiment-id EXP --metric accuracy=0.72 --status completed
uv run insightflow validate
```

The CLI must produce human-readable Markdown output and optionally JSON output:

```bash
uv run insightflow plan --format json
```

## Ledger requirements

Implement a local persistent ledger.

Preferred for v0.1:

- SQLite for structured state
- JSONL decision log for auditability

Minimum ledger functions:

- initialize project
- load configs
- store runs
- store plans
- store decision logs
- compute state hash
- list pending/completed/running experiments
- merge W&B imported runs
- export state to Markdown and JSON

## Scheduler requirements

Implement a deterministic heuristic scheduler first.

The scheduler must rank pending experiments using:

1. claim priority
2. uncertainty around linked claims
3. claim-criticality
4. reviewer-risk reduction
5. dependency unlock value
6. estimated cost
7. estimated wall-clock time
8. redundancy penalty
9. premature replication penalty
10. seed value
11. partial-result urgency

It must explicitly compare:

- new condition versus extra seed
- cheap proxy versus expensive full run
- strong baseline versus method-only continuation
- broad scan versus replication

It must produce:

- immediate queue
- postponed experiments
- avoided experiments
- warnings
- claim-confidence table
- rationale for every high-priority action

## Seed allocation policy

Implement a seed policy that does not blindly run all seeds.

Add seeds only when at least one of these is true:

- the result is claim-critical
- current effect size is borderline
- seed variance is high
- result is surprising
- result affects main paper table
- current evidence is under required seed threshold and claim confidence is near decision boundary

Otherwise prefer broad coverage.

## Partial result policy

Implement partial-run monitoring logic.

Given partial learning curves or intermediate metrics, recommend:

- continue
- pause
- stop
- promote
- add seed
- launch baseline

Base this on decision impact, not only current performance.

## W&B importer

Implement W&B import gracefully.

Requirements:

- Use optional dependency or normal dependency, but imports must not crash if W&B is unavailable unless the command is called.
- Import runs from entity/project.
- Accept metric name.
- Map W&B config fields into Experiment fields when available.
- Map summary/history metrics into RunResult.
- Support limit.
- Print clear errors for missing login, missing project, or missing metric.
- Include tests that mock W&B API so tests do not require live W&B.

## Simulator requirements

Build a synthetic research-project simulator.

It should generate fake projects with:

- multiple claims
- multiple datasets
- multiple methods
- baselines
- seeds
- expected costs
- hidden true effects
- seed noise
- expensive branches
- cheap proxy tasks
- dependencies
- partial curves

The simulator should allow comparison between policies:

- insightflow scheduler
- grid order
- all-seeds-first
- all-tasks-first
- random
- cheap-first
- fastest-first
- oracle-like upper bound if simple enough

## Benchmark metrics

Implement benchmark output with:

- time to correct decision
- cost to correct decision
- number of runs launched
- unnecessary runs avoided
- wrong-decision rate, if possible in simulation
- claim confidence evolution, if implemented
- final summary table

For v0.1, a simplified approximation is acceptable, but it must be real and documented.

## Reports

Generate Markdown reports:

- `reports/state.md`
- `reports/plan_latest.md`
- `reports/claim_confidence.md`
- `reports/benchmark.md`

The `plan` command should write a report and print a summary.

## Claude Code integration

Create `CLAUDE.md` and `AGENTS.md` that tell Claude:

- always use `uv`
- do not bypass the ledger
- use `uv run insightflow state` before making scheduling recommendations
- use `uv run insightflow plan` before proposing new runs
- optimize time-to-insight, not grid completion
- explain recommendations in terms of claims and decisions
- never launch expensive runs without showing the plan

Create prompts in `prompts/` for:

- research agent scheduling
- replanning after new results
- reviewing a generated plan

## Documentation requirements

README must include:

- what InsightFlow is
- what it is not
- installation with uv
- quick demo
- W&B import
- config examples
- CLI examples
- Claude Code workflow
- current limitations

Docs must explain:

- architecture
- concept model
- scheduling objective
- seed allocation
- W&B integration
- roadmap

## Testing requirements

Use pytest.

Tests must cover:

- config parsing
- schema validation
- ledger initialization
- scoring behavior
- scheduler ordering
- seed policy
- simulator runs
- benchmark smoke test
- CLI smoke test
- W&B importer with mocks

All tests must pass with:

```bash
uv run pytest
```

Also create:

```bash
uv run ruff check .
uv run mypy src
```

If mypy is too strict for v0.1, configure it reasonably. Do not ignore all errors blindly.

## Acceptance criteria

Before final response, run:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run insightflow demo --force
uv run insightflow state
uv run insightflow plan
uv run insightflow benchmark --steps 5
```

Fix all failures.

Then provide:

1. What was built.
2. How to run it.
3. Key design decisions.
4. Tests passed.
5. Known limitations.
6. Next steps for v0.2.

Do not say the project is complete unless the acceptance tests pass.

## Expected final behavior

After you finish, a user should be able to run:

```bash
uv sync
uv run insightflow demo --force
uv run insightflow plan
```

and receive a useful recommendation like:

```text
Top recommendation:
Run method_a on cifar100 alpha=0.1 seed=0.
Reason: main uncertainty is external validity, not seed variance.
This run affects claim C1, has high decision value, and should be run before adding more CIFAR-10 seeds.

Postpone:
method_a cifar10 seed=4.
Reason: extra replication has low decision value until generality is checked.
```

Build the project now.

# InsightFlow Architecture

## Design Principle

The CLI and ledger are the source of truth. The AI agent (Claude Code) is the
interface. The agent never invents or guesses state — it calls the CLI, which
reads and writes the ledger.

```text
Researcher
  -> Claude Code (agent interface)
    -> insightflow CLI  (typer, --format md|json)
      -> config layer   (YAML definitions)
      -> ledger layer   (SQLite + JSONL, dynamic state)
        -> scoring engine
          -> scheduler
            -> reports / explain
```

## Layers and Responsibilities

### 1. Schemas (`schemas.py`)

All domain types are Pydantic models. They are the contract between every
layer: YAML is parsed into them, the ledger persists them, the scheduler
reasons over them, and the CLI serialises them to Markdown or JSON. Pydantic
validates types and ranges strictly; unknown keys are silently dropped
(`extra="ignore"`), so a YAML typo surfaces as a validation error rather than
being silently swallowed.

Key models: `Claim`, `Experiment`, `RunResult`, `PlanAction`, `Plan`,
`ClaimConfidence`, `Policy`, `State`.

`State` is the single snapshot the scheduler operates on: it holds all claims,
experiments, results, policy, and resources.

### 2. Config layer (`config.py`)

Reads four YAML files from `configs/`:

| File | Purpose |
|---|---|
| `claims.yaml` | Research claims and their decision rules |
| `experiments.yaml` | The runnable experiment grid |
| `resources.yaml` | Available compute pools and budget |
| `policy.yaml` | Scheduler weights and thresholds (optional) |

These files describe *definitions* only. Dynamic state (run results, status
changes, plans) never lives in config files. `config.py` also validates
semantic constraints at load time: missing IDs, dangling claim links, impossible
costs, duplicate IDs, and dependency cycles.

### 3. Ledger layer (`ledger.py`)

The ledger is the persistent, append-only store for all dynamic state. It lives
at `<project>/.insightflow/`:

```text
.insightflow/
    ledger.db         SQLite — structured, queryable state
    decisions.jsonl   Append-only audit log — every material event
```

**What lives in SQLite (`ledger.db`)**

| Table | Contents |
|---|---|
| `meta` | Key/value metadata (e.g. `created_at`) |
| `results` | `RunResult` records (one row per run, JSON payload) |
| `experiments` | Imported or dynamically added experiment definitions |
| `experiment_status` | Status overrides keyed by experiment ID |
| `plans` | Saved `Plan` objects (JSON payload, indexed by plan ID and timestamp) |

**Why SQLite and not plain JSON?** SQLite gives atomic writes, concurrent
read-safety, and cheap ordered queries (e.g. latest plan). The JSON payload
column preserves the full Pydantic model without a rigid column schema, so
adding fields to a model does not require a migration.

**What lives in `decisions.jsonl`**

Every material event — import, demo setup, CLI-triggered action — is appended
as a timestamped JSON line. This is a human-readable, grep-able audit trail. It
is write-only at runtime; nothing reads it for correctness (SQLite holds the
queryable truth).

**Source-of-truth principle**: The agent never edits ledger files directly. All
writes go through the CLI (`insightflow record`, `insightflow import-wandb`,
etc.), which calls `Ledger` methods, which use transactions. This guarantees
that any `insightflow state` or `insightflow plan` invocation sees a consistent
view.

**State reconstruction**: `Ledger.load_state()` combines configs with ledger
data to produce a `State`. Config experiments and imported experiments are
merged (config wins on ID collision). Experiment statuses are resolved in
priority order: explicit status override in `experiment_status` table >
inferred-completed (a completed `RunResult` exists) > inferred-running (a
running/partial result exists) > the config default.

### 4. Scoring engine (`scoring.py`)

A pure-function layer: given `State`, it computes a score for every candidate
action. The same state always produces the same scores. Each score term is
stored in `PlanAction.factors` so `explain` can render a transparent breakdown.

The central function `compute_claim_evidence(state)` builds a `ClaimEvidence`
record per claim, then `Scorer` uses those records to compute the multi-term
objective for launch and add-seed actions.

See `docs/scheduling_policy.md` for the exact objective and term definitions.

### 5. Seed policy (`seed_policy.py`)

A single function, `decide_seed(exp, evidence, policy)`, answers the question:
"is this extra-seed run worth scheduling now, or should the worker pursue
breadth instead?" It returns a `SeedDecision` with an `add` flag, an urgency
scalar, and a textual reason. The scheduler calls this whenever it detects that
the candidate experiment's cell has already been observed.

### 6. Partial-run monitor (`partial.py`)

`monitor_partial(result, exp, state, evidence, policy)` inspects the
`partial_history` of an in-flight `RunResult` and recommends one of:
`continue`, `pause`, `stop`, `promote`, `add_seed`, or `launch_baseline`. The
guiding principle is decision impact, not raw performance. A run beating the
baseline on a critical, under-seeded condition gets `continue`; a run trailing
the baseline with no upward trend gets `stop`.

`monitor_all` produces `PlanAction` records for all in-flight runs and feeds
them into the scheduler's scored list.

### 7. Scheduler (`scheduler.py`)

`Scheduler.plan()` ties everything together:

1. Calls `compute_claim_evidence` and constructs a `Scorer`.
2. Iterates pending/postponed experiments; classifies each as a
   **new-condition launch** (cell unobserved) or **extra-seed** (cell already
   observed), scoring accordingly.
3. Calls `monitor_all` to include in-flight run recommendations.
4. Sorts all scored actions by score descending.
5. Classifies into immediate queue / postponed / avoided via `_classify`,
   which applies score thresholds and a diversification rule (at most one run
   per cell+role in the immediate queue).
6. Generates warnings, a human-readable summary, and a list of assumptions.
7. Computes `state_hash` — a stable hash of experiment statuses and result
   identities — and sets `Plan.id = "plan_{state_hash}"`.

**Determinism guarantee**: given the same ledger contents and the same
`policy.yaml`, `build_plan` always returns the same `Plan`. There is no
randomness in the scheduler.

### 8. Reports and explain (`reports.py`, `explain.py`)

All Markdown reports are regenerated from ledger state; they are never
hand-edited. The `plan` command writes `reports/plan_latest.md` and
`reports/claim_confidence.md`; `state` writes `reports/state.md`; `benchmark`
writes `reports/benchmark.md`.

`explain_plan` renders every action's `factors` dict as a Markdown table and
surfaces canonical trade-off comparisons (new condition vs extra seed, baseline
vs method continuation, cheap vs expensive run).

### 9. CLI (`cli.py`)

The Typer-based CLI is the single entry point for the agent and for humans.
Project location resolves in order: `--project-dir` > `$INSIGHTFLOW_HOME` >
current working directory. Output format is Markdown by default; `--format
json` is available for scripting. The CLI never mutates state directly — it
goes through `Ledger`.

### 10. Simulator and benchmark (`simulator.py`, `benchmark.py`)

These are deliberately separate from the core pipeline. The simulator generates
synthetic `RunResult` records for a given `Experiment` (used by `demo` and
tests); the benchmark runs multi-step scheduling simulations to evaluate how
quickly the scheduler resolves claims. Neither component is on the critical path
for production use.

### 11. W&B importer (`wandb_importer.py`)

Pulls completed and in-progress runs from a W&B project, maps them onto
`RunResult` records, and writes them to the ledger via
`Ledger.merge_imported_runs`. Experiment definitions inferred from W&B are
stored in the `experiments` table so they survive across imports.

## ASCII Data-Flow Diagram

```text
configs/
  claims.yaml ------\
  experiments.yaml --+---> config.py (load + validate) ----\
  resources.yaml ----/                                       |
  policy.yaml ------/                                       |
                                                            v
wandb / manual runs --> ledger.py (Ledger) <----------> State
                             |                              |
                             |                         scoring.py
                             |                         seed_policy.py
                             |                         partial.py
                             |                              |
                             |                        scheduler.py
                             |                         (Plan)
                             |                              |
                             +<-- save_plan() <------------+
                             |
                    reports.py / explain.py
                             |
                          reports/
                    plan_latest.md
                    claim_confidence.md
                    state.md
```

## Extensibility for v0.2

The core is designed so that a FastAPI server, MCP server, or web dashboard can
be added without rewriting the pipeline:

- `Ledger.load_state()` is the single point of truth assembly; a server
  endpoint can call it on every request with no additional state management.
- `build_plan(state)` is a pure function; it can be called from an HTTP handler
  or an MCP tool with no CLI involvement.
- `render_plan_md` and `render_claim_confidence_md` are stateless renderers;
  the same functions serve the CLI and could serve HTTP responses.
- `decisions.jsonl` provides an audit trail that a dashboard can tail without
  touching SQLite.
- The `Policy` model centralises all tunable weights; a settings UI just needs
  to write a new `policy.yaml`.

The only coupling between layers is the `State` type and the `Ledger` class.
Neither has UI dependencies, so new frontends are additive.

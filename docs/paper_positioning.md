# Positioning: A Claim-Centered Research Decision Layer

> **InsightFlow is a claim-centered research decision layer for AI-assisted ML
> research. It helps researchers and coding agents decide which evidence to
> acquire next, when to stop, what to postpone, what to avoid, and which claims
> are currently supported, refuted, weak, or still uncertain.**

This document states the sharp positioning of InsightFlow: what it is, what it is
not, and why it is a distinct layer rather than a feature that a coding agent's
skills could absorb. The related-work boundary lives in
[`docs/related_work.md`](related_work.md); the honest boundaries of the current
implementation live in [`docs/limitations.md`](limitations.md).

---

## The core thesis

A modern ML paper is not a model; it is a small set of **falsifiable claims**
("our method beats the baseline across these datasets", "the gain comes from this
mechanism", "it is robust under this shift") together with the **evidence** that
makes each claim defensible. The expensive, error-prone part of research is not
running any single experiment — it is *deciding which evidence to acquire next*
so that those claims become defensible at the lowest cost, and *knowing when to
stop*.

Existing infrastructure does not target that decision. AutoML and HPO optimize a
metric on a fixed task. Experiment trackers record what already happened.
Bayesian optimal experimental design and value-of-information methods optimize a
single estimation/selection target, not a graph of paper claims with reviewer
risk. Coding agents can *act*, but they have no durable, typed record of which
claim each result speaks to, and no principled, replayable rule for what to do
next.

InsightFlow fills exactly that gap. It makes the **claim** the first-class object,
links every experiment and result to the claim(s) it bears on, scores candidate
actions by an explicit value-of-information-inspired objective per unit cost, and
reports paper readiness over the claim graph. It is the **decision and audit
layer** that sits between the researcher (or agent) and the compute.

**Position it as:**

- an **auditable research control plane** — a deterministic, replayable record of
  what was decided and why;
- a **claim-evidence ledger** — typed state linking claims, experiments, results,
  and verdicts ([`src/insightflow/ledger.py`](../src/insightflow/ledger.py),
  [`src/insightflow/schemas.py`](../src/insightflow/schemas.py));
- a **value-of-information-inspired scheduler** — actions ranked by expected
  decision value per unit cost
  ([`src/insightflow/scoring.py`](../src/insightflow/scoring.py),
  [`src/insightflow/scheduler.py`](../src/insightflow/scheduler.py));
- a **practical decision layer for human and AI research agents** — exposed
  identically through a CLI, a library, and an MCP server
  ([`src/insightflow/cli.py`](../src/insightflow/cli.py),
  [`src/insightflow/mcp_server.py`](../src/insightflow/mcp_server.py)).

**Do not position it as** another AutoML system, an HPO scheduler, an experiment
tracker, an AI Scientist, a fully autonomous researcher, or a guaranteed-optimal
planner. It is none of these (see "What this is NOT" below).

### What is actually new (and what is not)

The novelty is the **integration and the objective**, not new mathematics:

- claim-level state with `supported / weak / refuted / needs_more_evidence /
  blocked / unknown` statuses
  ([`schemas.py:ClaimStatus`](../src/insightflow/schemas.py));
- per-claim evidence requirements and a **claim graph** (`depends_on` / `blocks`)
  that lets a main claim be reported as *blocked* by an unmet subclaim
  ([`readiness.py`](../src/insightflow/readiness.py));
- **reviewer-risk-aware** scheduling — high-risk claims that lack baselines get
  pushed up the queue
  ([`scoring.py:_launch_terms`](../src/insightflow/scoring.py));
- explicit **breadth-vs-replication** handling — a new condition outranks an
  extra seed on an already-covered cell until generality is established;
- a **ledger-backed agent interface** so an agent calls the same grounded planner
  a human uses, rather than inventing a schedule;
- **replay evaluation** for research trajectories — would InsightFlow have decided
  the claims in fewer runs than the order they were actually run in?
  ([`replay.py`](../src/insightflow/replay.py));
- **paper-readiness reporting** over the claim graph
  ([`readiness.py`](../src/insightflow/readiness.py)).

We explicitly **do not** claim the math is new, and we **do not** claim global
optimality. The value-of-information scorer is a **myopic, one-step approximate
EVI per unit cost**, computed with deterministic 5-point Gauss-Hermite quadrature
([`bayes.py:expected_voi_new_cell`](../src/insightflow/bayes.py)) — not a
multi-step optimal plan. The Bayesian-mode claim confidence is a **calibrated
probability** (measured Expected Calibration Error 0.011 over 200k draws) *under
the model's stated assumptions* (a finite-population Normal-Normal model); the
default heuristic mode is a **ranking score, not a probability**. These boundaries
are not caveats bolted on — they are part of the positioning, and are detailed in
[`docs/limitations.md`](limitations.md).

---

## What this is

- A **claim-centered decision layer**: the unit of optimization is a falsifiable
  paper claim, not a metric value.
- An **auditable ledger** of claims, experiments, results, plans, and decisions
  (SQLite + JSONL), so every recommendation is reproducible and explainable.
- A **deterministic scheduler** that, given the same ledger and policy, always
  produces the same plan — a queue of what to run next, what to postpone, and
  what to avoid, each with a transparent score breakdown.
- A **value-of-information-inspired scorer** in two modes: a transparent heuristic
  (default) and an opt-in calibrated Bayesian / one-step EVI scorer.
- A **paper-readiness reporter** that says which claims are supported, refuted,
  weak, blocked, or still uncertain; which reviewer attacks are most dangerous;
  which baselines are missing; and what to do next.
- A **representation and scorer for research actions beyond runs** — literature
  search, reviewer attack, theorem attempt, claim refinement, baseline design —
  ranked against experiments by value per unit cost
  ([`actions.py`](../src/insightflow/actions.py)).
- A **single grounded interface** for both humans and agents: CLI, Python
  library, and MCP server, plus a Claude Code plugin (skills + commands), all
  reading and writing the same ledger.
- A **benchmark and replay harness** to evaluate scheduling *policies* on
  synthetic projects and on imported real histories
  ([`simulator.py`](../src/insightflow/simulator.py),
  [`benchmark.py`](../src/insightflow/benchmark.py),
  [`replay.py`](../src/insightflow/replay.py)).

---

## What this is NOT

- **Not another AI Scientist.** It does not generate papers, ideas, or
  hypotheses end-to-end. It is a decision and audit layer for the evidence behind
  claims a human or agent has stated.
- **Not a fully autonomous researcher.** The default posture is advisor mode:
  InsightFlow recommends; a human (or a launcher the human invokes) runs. Most
  non-run research actions are *represented and scored*, not executed.
- **Not AutoML or HPO.** It does not tune hyperparameters or search architectures;
  it schedules across configurations you define, toward claim verdicts.
- **Not an experiment tracker.** It does not replace W&B or MLflow. It *imports*
  from them ([`wandb_importer.py`](../src/insightflow/wandb_importer.py),
  [`importers.py`](../src/insightflow/importers.py)) and tells you what to run
  next.
- **Not a cluster launcher / live-monitoring server / dashboard.** There is a
  local launcher ([`launcher.py`](../src/insightflow/launcher.py)) for running an
  experiment on the spot, but no Slurm/Ray submission, no live run monitoring
  service, and no web dashboard.
- **Not a guaranteed-optimal planner.** The scorer is a myopic one-step
  approximation; it has good *empirical* worst-case behavior on the benchmark, not
  a global-optimality guarantee.
- **Not a guarantee of truth.** A "supported" verdict is a statement about the
  evidence under stated assumptions, not proof that a claim is true, and never a
  replacement for human judgment.

---

## Why not just Claude Code skills?

A natural objection: *coding agents already have skills and tools — why not just
write a "decide what to run next" skill and let Claude or Codex do it directly?*

Because **skills are interfaces, not a substrate.** A skill is a prompt-shaped
capability the agent invokes; it does not, by itself, give the agent the things a
research decision layer must have:

- **A durable source of truth.** Skills are stateless between invocations. A
  claim-evidence ledger (SQLite + JSONL) is persistent, typed, and shared across
  the human, the CLI, and every agent that touches the project. The schedule is
  computed *from* that state, not re-improvised each turn.
- **Deterministic scheduling.** The same ledger + policy always yields the same
  plan ([`scheduler.py:compute_state_hash`](../src/insightflow/scheduler.py)). An
  LLM asked "what next?" is not reproducible, not auditable, and cannot be
  benchmarked. Determinism is what makes the plan defensible in a methods section.
- **Typed state.** Claims, experiments, results, and policies are validated
  Pydantic models with `extra="forbid"` on config inputs, so a YAML typo surfaces
  as an error instead of silently changing behavior
  ([`schemas.py`](../src/insightflow/schemas.py)). An agent free-typing JSON has
  no such contract.
- **Replayable decisions.** Every plan and decision is logged, so you can replay a
  trajectory and ask counterfactuals ("would we have decided in fewer runs?")
  ([`replay.py`](../src/insightflow/replay.py)). A chat transcript is not a
  replayable decision log.
- **Benchmarkable policies.** Scheduling here is a *policy* you can ablate and
  compare against grid, all-seeds-first, oracle, and component-ablation baselines
  ([`simulator.py`](../src/insightflow/simulator.py)). You cannot ablate a vibe.
- **Auditable claim-evidence links.** Every result is linked to the claim(s) it
  bears on, and every verdict is derived deterministically from those links
  ([`scoring.py`](../src/insightflow/scoring.py),
  [`readiness.py`](../src/insightflow/readiness.py)). The agent inherits this; it
  does not have to (and should not) reconstruct it from memory.

So the relationship is not competition but composition. **Claude / Codex should
CALL InsightFlow, not replace the planner.** The agent is the actor and the
interface; InsightFlow is the typed, deterministic, auditable substrate the agent
reasons over. The Claude Code plugin and MCP server
([`mcp_server.py`](../src/insightflow/mcp_server.py), `skills/`, `commands/`) are
exactly this: thin interfaces that expose the ledger-backed planner and readiness
report to the agent, so the agent's actions are grounded in durable state rather
than in a transient prompt.

---

## The architecture arrow

The layering that the rest of this document implies, in one line:

```
agent
  -> skill / MCP tool            (interface: how Claude/Codex reaches in)
    -> CLI / library             (grounded entry points; same logic both ways)
      -> ledger                  (durable, typed source of truth: SQLite + JSONL)
       + claim graph             (claims, depends_on/blocks, evidence requirements)
       + scheduler               (deterministic action enumeration + classification)
       + VoI model               (heuristic or calibrated one-step EVI per unit cost)
        -> auditable plan        (ranked queue / postpone / avoid, with rationale)
         + readiness report      (supported/refuted/weak/blocked, attacks, next actions)
```

Read it as: the agent never touches compute or invents a schedule directly. It
goes through a skill or MCP tool, which calls the same CLI/library a human uses,
which reads and writes the ledger. The claim graph, scheduler, and
value-of-information model turn that durable state into two auditable artifacts —
a **plan** (what to do next) and a **readiness report** (where the claims stand) —
both of which are deterministic functions of the ledger and therefore replayable,
explainable, and benchmarkable.

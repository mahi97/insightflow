# Related Work

InsightFlow optimizes the **acquisition of evidence required for falsifiable
paper claims**, with auditable state and explicit claim-evidence linkage. That
objective is different from what the neighboring fields optimize. Below is one
short, honest paragraph per area: what *they* optimize, and what *InsightFlow*
optimizes instead. The headline distinction recurs throughout — those systems
optimize model performance, allocate compute to arms/configs, automate paper
generation, or track experiments; InsightFlow decides which evidence to acquire
next to make a *claim graph* defensible, and reports where each claim stands.

For the sharp positioning and the "why not just a skill?" argument, see
[`docs/paper_positioning.md`](paper_positioning.md). For the honest boundaries of
the current implementation, see [`docs/limitations.md`](limitations.md). A longer,
method-by-method treatment also appears in [`docs/concepts.md`](concepts.md).

---

### AutoML

AutoML systems (e.g. Auto-sklearn, AutoGluon, automated pipeline search) optimize
an end-to-end model pipeline — preprocessing, model family, and hyperparameters —
to maximize a validation metric on a given task with minimal human input. Their
output is a trained model and its score. InsightFlow does not search or tune
pipelines at all; it takes the configurations *you* defined and decides which of
them to run next so that a set of human-stated paper claims becomes defensible.
The optimization target is a claim verdict, not a model.

### Hyperparameter optimization (HPO)

Classical HPO (random/grid search, Bayesian optimization à la GP-EI, TPE, SMAC)
allocates a search budget to find the configuration that maximizes a single
objective on a single task. It answers "which config is best?" InsightFlow answers
a different question — "which experiment, seed, or baseline next moves a *claim*
from uncertain to decided, per unit cost?" — and treats generality across
conditions and the presence of baselines as first-class, not as a scalar score.
HPO and InsightFlow compose: use HPO to find a good config, then InsightFlow to
decide which datasets and baselines turn that config into a paper claim.

### Hyperband / ASHA / BOHB

These multi-fidelity bandit schedulers (Hyperband, ASHA, BOHB) allocate compute
across many configurations by early-stopping the weak ones, optimizing the
best-final-performance-per-budget on one task. The "arm" is a config and the
reward is its metric. InsightFlow's arms are *experiments linked to claims*, and
the reward is reduction in **decision uncertainty about a claim** (including
breadth across conditions and reviewer-risk coverage), not a config's validation
score. It does, in a much simpler hand-coded form, monitor partial runs
([`partial.py`](../src/insightflow/partial.py)), but its purpose is to advance a
claim decision, not to win a fidelity-vs-performance race among configs.

### Freeze-thaw Bayesian optimization

Freeze-thaw BO (Swersky et al., 2014) models learning curves with a GP to decide
which paused run to resume and which to abandon, again maximizing final
performance per unit compute over a set of configurations. InsightFlow's
`partial.py` does analogous continue/stop reasoning but with a transparent
heuristic over the partial-history curve, and — critically — the decision is
framed by *which claim the run bears on* rather than by raw expected final
metric. A full freeze-thaw-style curve posterior is named as future work, not a
current capability.

### Bayesian optimal experimental design (OED)

Bayesian OED chooses the next experiment that maximizes the expected information
gain about model parameters (or a posterior of interest), often via mutual
information. It is the closest *formal* cousin to InsightFlow's objective.
InsightFlow's Bayesian mode applies the same spirit — score an action by expected
reduction in decision uncertainty — but specializes the target to a
**finite-population claim verdict** (P(effect ≥ δ) over a defined set of K
conditions) and to a research-cost denominator, and it does so myopically
(one step ahead, deterministic quadrature), not as a globally optimal design.
OED optimizes information about parameters; InsightFlow optimizes information
about a *claim* per unit research cost.

### Optimal Computing Budget Allocation (OCBA)

OCBA (Chen et al.) allocates a finite simulation budget across competing
alternatives to maximize the probability of correctly selecting the best one. Its
target is ranking-and-selection: get the *best arm* right. InsightFlow is not
selecting a single best arm; it is deciding the *verdict* on each of several
claims (supported / refuted / weak), where a refuted claim is a perfectly good and
desirable outcome and where breadth and baseline-coverage matter as much as point
estimates. The accounting unit is a claim decision, not a correct selection among
arms.

### Knowledge Gradient

The Knowledge Gradient (Frazier et al.) scores each measurement by the expected
improvement in the value of the best decision after taking it — a one-step
look-ahead value-of-information rule for ranking/optimization. InsightFlow's
opt-in Bayesian scorer is a Knowledge-Gradient-style, one-step look-ahead rule,
but applied to claim verdicts rather than to selecting the best alternative, and
normalized per unit research cost. The mathematical machinery is borrowed and
acknowledged as such; what is specialized is the *decision* being valued (a
falsifiable claim) and the cost it is traded against (time-to-insight).

### Self-driving labs

Self-driving / autonomous-experimentation labs (closed-loop systems in chemistry,
materials, biology) couple a planner to physical robotics to run, measure, and
iterate experiments automatically, optimizing toward a target property. They
optimize a physical objective and *execute* in the loop. InsightFlow shares the
"decide the next experiment" framing but is an advisory decision layer for ML
papers: it represents and scores actions, and runs at most a *local* experiment
on request — it does not drive instruments, a cluster, or a closed physical loop,
and its target is a paper claim, not a synthesized material.

### AI Scientist systems

End-to-end "AI Scientist" systems generate hypotheses, write and run code, and
draft papers autonomously, optimizing for a complete generated manuscript with
minimal human input. InsightFlow is deliberately *not* this: it does not generate
ideas, code, or prose, and it does not aim for autonomy. It is the auditable
decision-and-evidence substrate underneath — the layer that says which evidence a
claim still needs and whether the claims are ready — which such a system (or a
human, or a coding agent) can call rather than reinvent.

### Experiment trackers (Weights & Biases, MLflow)

W&B and MLflow record what happened — metrics, configs, artifacts, runs — and make
it searchable and comparable. They are systems of record; they do not decide what
to run next or whether a claim is supported. InsightFlow is complementary: it
*imports* run histories from W&B, MLflow, and CSV/JSONL
([`wandb_importer.py`](../src/insightflow/wandb_importer.py),
[`importers.py`](../src/insightflow/importers.py)), links those results to claims,
and adds the decision layer trackers lack — what to acquire next, when to stop,
and where each claim stands.

### Generic coding agents

Coding agents (Claude Code, Codex, and similar) can read code, run commands, and
take actions; they optimize for completing the task the user phrased, turn by
turn. What they lack for *research* decisions is a durable, typed source of truth,
deterministic and replayable scheduling, benchmarkable policies, and auditable
claim-evidence links — they re-improvise state each turn. InsightFlow supplies
exactly that substrate and exposes it through a CLI, library, and MCP server, so
the agent should *call* the planner rather than replace it (the argument is made
in full in [`docs/paper_positioning.md`](paper_positioning.md)).

"""Typed domain model for InsightFlow.

These Pydantic models are the contract between every layer: configs are parsed
into them, the ledger persists them, the scheduler reasons over them, and the
CLI serializes them to Markdown or JSON.

Design notes
------------
* Models are permissive about *extra* inputs being dropped but strict about the
  *types and ranges* of known fields, so a typo in a YAML key surfaces as a
  validation error rather than silently doing nothing where it matters.
* ``condition_key`` on :class:`Experiment` defines what counts as "the same
  condition" (method x dataset x condition label). Two experiments that differ
  only by seed share a condition key; this is what lets the scheduler tell an
  *extra seed* apart from a *new condition*.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class DesiredDirection(str, Enum):
    higher = "higher"
    lower = "lower"  # type: ignore[assignment]  # shadows str.lower; intentional value name


class ClaimStatus(str, Enum):
    unknown = "unknown"
    supported = "supported"
    weak = "weak"
    refuted = "refuted"
    needs_more_evidence = "needs_more_evidence"


class ExperimentStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    postponed = "postponed"
    avoided = "avoided"


class RunStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    partial = "partial"


class RunSource(str, Enum):
    manual = "manual"
    wandb = "wandb"
    simulator = "simulator"
    import_ = "import"


class ActionType(str, Enum):
    launch = "launch"
    add_seed = "add_seed"
    add_experiment = "add_experiment"
    continue_ = "continue"
    pause = "pause"
    stop = "stop"
    promote = "promote"
    launch_baseline = "launch_baseline"
    postpone = "postpone"
    avoid = "avoid"


# --------------------------------------------------------------------------- #
# Core entities
# --------------------------------------------------------------------------- #
class Claim(BaseModel):
    """A research claim we are trying to support, weaken, or refute.

    ``importance`` (a.k.a. priority) and ``reviewer_risk`` are in [0, 1].
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    statement: str = ""
    importance: float = Field(0.5, ge=0.0, le=1.0)
    target_metric: str = "accuracy"
    desired_direction: DesiredDirection = DesiredDirection.higher
    minimum_effect_size: float = Field(0.0, ge=0.0)
    required_seeds: int = Field(3, ge=1)
    reviewer_risk: float = Field(0.5, ge=0.0, le=1.0)
    status: ClaimStatus = ClaimStatus.unknown
    notes: str = ""

    @field_validator("importance", mode="before")
    @classmethod
    def _coerce_priority_words(cls, v: Any) -> Any:
        """Allow ``importance: high`` style YAML in addition to numbers."""
        words = {"low": 0.25, "medium": 0.5, "med": 0.5, "high": 0.85, "critical": 1.0}
        if isinstance(v, str) and v.lower() in words:
            return words[v.lower()]
        return v


class Experiment(BaseModel):
    """One runnable unit of evidence: a (method, dataset, condition, seed) cell."""

    model_config = ConfigDict(extra="ignore")

    id: str
    command: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    method: str = "method"
    baseline: str | None = None
    dataset: str = "dataset"
    model: str | None = None
    condition: str = "default"
    seed: int = Field(0, ge=0)
    claim_links: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    expected_cost: float = Field(1.0, ge=0.0)
    expected_time: float = Field(1.0, gt=0.0)
    resource_type: str = "gpu"
    status: ExperimentStatus = ExperimentStatus.pending
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def condition_key(self) -> str:
        """Identity of the *condition* (ignoring seed).

        Experiments differing only by seed share this key.
        """
        return f"{self.method}|{self.dataset}|{self.condition}"

    @property
    def cell_key(self) -> str:
        """Identity of the experimental *cell* (dataset x condition), ignoring
        method and seed. Used to line a method up against its baseline, since
        both occupy the same cell of the results table.
        """
        return f"{self.dataset}|{self.condition}"

    @property
    def is_baseline(self) -> bool:
        """True if *this* experiment is itself a baseline run.

        Note: the ``baseline`` field names the baseline a *method* run is compared
        against, so it must NOT be used here - otherwise method runs that declare
        their baseline would be misread as baselines themselves.
        """
        return "baseline" in self.tags or self.method.startswith("baseline")


class RunResult(BaseModel):
    """The outcome (or partial outcome) of executing an experiment once."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    experiment_id: str
    seed: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    cost: float = 0.0
    wall_time: float = 0.0
    status: RunStatus = RunStatus.completed
    started_at: str | None = None
    finished_at: str | None = None
    source: RunSource = RunSource.manual
    partial_history: list[dict[str, float]] = Field(default_factory=list)
    notes: str = ""

    def metric(self, name: str) -> float | None:
        """Return a metric value, falling back to the last partial-history point."""
        if name in self.metrics:
            return self.metrics[name]
        for point in reversed(self.partial_history):
            if name in point:
                return float(point[name])
        return None


class PlanAction(BaseModel):
    """A single recommended action with its score breakdown and rationale."""

    model_config = ConfigDict(extra="ignore")

    experiment_id: str
    action_type: ActionType
    score: float = 0.0
    affected_claims: list[str] = Field(default_factory=list)
    rationale: str = ""
    expected_decision_value: float = 0.0
    expected_uncertainty_reduction: float = 0.0
    expected_cost: float = 0.0
    expected_time: float = 0.0
    risk: float = 0.0
    checkpoint: str | None = None
    # Transparent breakdown of every scoring term; used by `explain`.
    factors: dict[str, float] = Field(default_factory=dict)
    label: str = ""  # human-friendly description, e.g. "method_a / cifar100 / seed=0"


class ClaimConfidence(BaseModel):
    """Heuristic evidence summary for one claim at the current state."""

    model_config = ConfigDict(extra="ignore")

    claim_id: str
    status: ClaimStatus = ClaimStatus.unknown
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    n_conditions_observed: int = 0
    n_seeds_observed: int = 0
    observed_effect: float | None = None
    required_effect: float = 0.0
    seed_variance: float = 0.0
    near_boundary: bool = False
    note: str = ""


class Plan(BaseModel):
    """A ranked plan: immediate queue plus postponed/avoided actions and context."""

    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: str = ""
    actions: list[PlanAction] = Field(default_factory=list)  # the immediate queue
    postponed: list[PlanAction] = Field(default_factory=list)
    avoided: list[PlanAction] = Field(default_factory=list)
    claim_confidence: list[ClaimConfidence] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    state_hash: str = ""


# --------------------------------------------------------------------------- #
# Policy & resources (configuration with safe defaults)
# --------------------------------------------------------------------------- #
class Policy(BaseModel):
    """Scheduler weights and thresholds.

    Defaults are chosen so the tool behaves sensibly with an empty ``policy.yaml``.
    Every weight maps directly onto a term of the scheduling objective documented
    in ``docs/scheduling_policy.md``.
    """

    model_config = ConfigDict(extra="ignore")

    # Objective weights (numerator terms)
    weight_decision_value: float = 1.0
    weight_uncertainty: float = 0.8
    weight_dependency: float = 0.6
    weight_reviewer_risk: float = 0.7
    # Penalties (subtracted in the numerator)
    weight_redundancy_penalty: float = 0.9
    weight_premature_replication_penalty: float = 1.0
    weight_seed_value: float = 0.5
    # Cost term (denominator): time + lambda * cost
    lambda_cost: float = 0.3

    # Classification thresholds on the final score
    queue_threshold: float = 0.15
    avoid_threshold: float = 0.03
    top_k: int = 5

    # Claim-confidence heuristics
    decision_boundary: float = 0.5
    boundary_margin: float = 0.15
    high_variance_threshold: float = 0.4  # relative to minimum effect size
    surprise_threshold: float = 0.5
    support_margin: float = 0.25  # how far past the boundary counts as "supported"

    # Seed policy
    prefer_breadth: bool = True

    # Confidence model: "heuristic" (default, v0.1) or "bayes" (v0.2 calibrated
    # Normal-Normal hierarchical posterior + value-of-information scoring).
    confidence_model: str = "heuristic"
    prior_effect_mean: float = 0.0
    prior_effect_var: float = 1.0
    between_condition_sd: float = 0.05  # how much the effect can vary across conditions
    # (so a single dataset cannot, by itself, establish cross-condition generality)
    within_seed_sd: float = 0.02  # default per-seed noise when it can't be estimated
    decision_prob_threshold: float = 0.9  # P(supported)/P(refuted) needed to decide


class ResourcePool(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "gpu"
    count: int = Field(1, ge=0)
    cost_per_hour: float = Field(0.0, ge=0.0)


class Resources(BaseModel):
    """Available compute. Used for cost estimates and budget warnings."""

    model_config = ConfigDict(extra="ignore")

    pools: list[ResourcePool] = Field(default_factory=list)
    budget_gpu_hours: float | None = None
    deadline: str | None = None

    def total_workers(self) -> int:
        return sum(p.count for p in self.pools) or 1


class State(BaseModel):
    """Everything the scheduler needs: definitions, evidence, and policy."""

    model_config = ConfigDict(extra="ignore")

    claims: list[Claim] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    results: list[RunResult] = Field(default_factory=list)
    policy: Policy = Field(default_factory=Policy)
    resources: Resources = Field(default_factory=Resources)

    # -- convenience lookups -------------------------------------------------
    def claim(self, claim_id: str) -> Claim | None:
        return next((c for c in self.claims if c.id == claim_id), None)

    def experiment(self, exp_id: str) -> Experiment | None:
        return next((e for e in self.experiments if e.id == exp_id), None)

    def results_for(self, exp_id: str) -> list[RunResult]:
        return [r for r in self.results if r.experiment_id == exp_id]

    def completed_experiment_ids(self) -> set[str]:
        done = {ExperimentStatus.completed}
        ids = {e.id for e in self.experiments if e.status in done}
        # An experiment is also "done" if it has a completed run result.
        ids |= {r.experiment_id for r in self.results if r.status == RunStatus.completed}
        return ids

    def experiments_for_claim(self, claim_id: str) -> list[Experiment]:
        return [e for e in self.experiments if claim_id in e.claim_links]

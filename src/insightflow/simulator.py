"""Synthetic research-project simulator.

Two jobs:

1. **Generate** controlled fake projects with *hidden ground truth* (true
   per-cell means, seed noise, costs, dependencies, expensive branches, cheap
   proxies) so the scheduler can be tested without a real project.
2. **Compare policies** by replaying a project under InsightFlow's scheduler and
   a set of baselines (grid, all-seeds-first, all-tasks-first, random,
   cheap-first, fastest-first, oracle) and measuring time/cost to the correct
   research decision.

Everything is deterministic given the project seed: results are sampled from a
``random.Random`` keyed by ``(project_seed, experiment_id)``.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from .scheduler import build_plan
from .schemas import (
    ActionType,
    Claim,
    ClaimStatus,
    Experiment,
    ExperimentStatus,
    Policy,
    Resources,
    RunResult,
    RunSource,
    RunStatus,
    State,
)
from .scoring import compute_claim_confidence
from .utils import stable_hash


@dataclass
class CellTruth:
    mean: float
    sigma: float


@dataclass
class SimProject:
    """A synthetic project with hidden ground truth."""

    seed: int
    name: str
    claims: list[Claim]
    experiments: list[Experiment]
    truth: dict[tuple[str, str], CellTruth]  # (method, cell_key) -> truth
    policy: Policy = field(default_factory=Policy)
    resources: Resources = field(default_factory=Resources)

    # -- execution ----------------------------------------------------------
    def execute(self, exp: Experiment) -> RunResult:
        """Sample a (deterministic) run result from hidden truth."""
        rng = random.Random(int(stable_hash((self.seed, exp.id, "exec"), 12), 16))
        key = (exp.method, exp.cell_key)
        truth = self.truth.get(key, CellTruth(mean=0.7, sigma=0.02))
        final = truth.mean + rng.gauss(0.0, truth.sigma)
        metric = self._metric_name()
        # Build a short rising learning curve toward the final value.
        history = []
        for i in range(1, 6):
            frac = i / 5.0
            value = 0.5 * truth.mean + 0.5 * final * frac + rng.gauss(0.0, truth.sigma * 0.3)
            history.append({"step": float(i), metric: round(value, 4)})
        return RunResult(
            run_id=f"sim-{exp.id}-{self.seed}",
            experiment_id=exp.id,
            seed=exp.seed,
            metrics={metric: round(final, 4)},
            cost=exp.expected_cost,
            wall_time=exp.expected_time,
            status=RunStatus.completed,
            source=RunSource.simulator,
            partial_history=history,
        )

    def _metric_name(self) -> str:
        return self.claims[0].target_metric if self.claims else "accuracy"

    # -- ground truth -------------------------------------------------------
    def ground_truth_statuses(self) -> dict[str, ClaimStatus]:
        out: dict[str, ClaimStatus] = {}
        for claim in self.claims:
            method = next(
                (e.method for e in self.experiments if claim.id in e.claim_links and not e.is_baseline),
                None,
            )
            if method is None:
                out[claim.id] = ClaimStatus.unknown
                continue
            cells = {
                e.cell_key
                for e in self.experiments
                if claim.id in e.claim_links and not e.is_baseline
            }
            effects = []
            for cell in cells:
                m = self.truth.get((method, cell))
                b = self.truth.get(("baseline_a", cell)) or self.truth.get((f"baseline_{method}", cell))
                if m and b:
                    eff = m.mean - b.mean
                    if claim.desired_direction.value == "lower":
                        eff = -eff
                    effects.append(eff)
            if not effects:
                out[claim.id] = ClaimStatus.unknown
                continue
            mean_eff = sum(effects) / len(effects)
            if mean_eff >= claim.minimum_effect_size:
                out[claim.id] = ClaimStatus.supported
            elif mean_eff <= 0:
                out[claim.id] = ClaimStatus.refuted
            else:
                out[claim.id] = ClaimStatus.weak
        return out

    def state_with(self, results: list[RunResult], completed: set[str]) -> State:
        exps = [
            e.model_copy(update={"status": ExperimentStatus.completed})
            if e.id in completed
            else e
            for e in self.experiments
        ]
        return State(
            claims=list(self.claims),
            experiments=exps,
            results=list(results),
            policy=self.policy,
            resources=self.resources,
        )


# --------------------------------------------------------------------------- #
# Project generators
# --------------------------------------------------------------------------- #
def generate_project(seed: int = 0, name: str = "synthetic") -> SimProject:
    """Default 'breadth beats replication' project.

    A generalization claim across several datasets: the method truly beats the
    baseline everywhere, so the correct decision (C1 = supported) needs *breadth*
    (one method+baseline pair per dataset), not many seeds on one dataset.
    """
    datasets = ["cifar10", "cifar100", "svhn"]
    claims = [
        Claim(
            id="C1",
            statement="method_a improves accuracy over baseline_a across datasets.",
            importance=0.9,
            target_metric="accuracy",
            minimum_effect_size=0.02,
            required_seeds=3,
            reviewer_risk=0.7,
        ),
    ]
    experiments: list[Experiment] = []
    truth: dict[tuple[str, str], CellTruth] = {}
    base_acc = {"cifar10": 0.72, "cifar100": 0.55, "svhn": 0.88}
    effect = {"cifar10": 0.06, "cifar100": 0.06, "svhn": 0.05}
    sigma = {"cifar10": 0.004, "cifar100": 0.005, "svhn": 0.008}
    for ds in datasets:
        cell = f"{ds}|default"
        truth[("method_a", cell)] = CellTruth(mean=base_acc[ds] + effect[ds], sigma=sigma[ds])
        truth[("baseline_a", cell)] = CellTruth(mean=base_acc[ds], sigma=sigma[ds] * 0.7)
        # 4 method seeds (depth available) + 2 baseline seeds per dataset.
        for s in range(4):
            experiments.append(
                Experiment(
                    id=f"method_a_{ds}_s{s}",
                    method="method_a",
                    baseline="baseline_a",
                    dataset=ds,
                    condition="default",
                    seed=s,
                    claim_links=["C1"],
                    expected_cost=1.0 if ds != "cifar100" else 1.2,
                    expected_time=1.0,
                    tags=["method"],
                )
            )
        for s in range(2):
            experiments.append(
                Experiment(
                    id=f"baseline_a_{ds}_s{s}",
                    method="baseline_a",
                    dataset=ds,
                    condition="default",
                    seed=s,
                    claim_links=["C1"],
                    expected_cost=0.8,
                    expected_time=0.8,
                    tags=["baseline"],
                )
            )
    return SimProject(seed=seed, name=name, claims=claims, experiments=experiments, truth=truth)


# --------------------------------------------------------------------------- #
# Additional scenarios — each stresses a different scheduling capability so the
# benchmark can show *where* InsightFlow's gains come from, not just an average.
# --------------------------------------------------------------------------- #
def _set_cell(truth: dict, ds: str, base: float, eff: float, sig: float) -> None:
    cell = f"{ds}|default"
    truth[("method_a", cell)] = CellTruth(mean=base + eff, sigma=sig)
    truth[("baseline_a", cell)] = CellTruth(mean=base, sigma=sig * 0.7)


def _method(
    ds: str, s: int, claims: list[str], cost: float, time: float, deps: list[str] | None = None
) -> Experiment:
    return Experiment(
        id=f"method_a_{ds}_s{s}", method="method_a", baseline="baseline_a", dataset=ds,
        condition="default", seed=s, claim_links=claims, dependencies=deps or [],
        expected_cost=cost, expected_time=time, tags=["method"],
    )


def _baseline(
    ds: str, s: int, claims: list[str], cost: float, time: float, deps: list[str] | None = None
) -> Experiment:
    return Experiment(
        id=f"baseline_a_{ds}_s{s}", method="baseline_a", dataset=ds, condition="default",
        seed=s, claim_links=claims, dependencies=deps or [], expected_cost=cost,
        expected_time=time, tags=["baseline"],
    )


def generate_expensive_branch(seed: int = 0, name: str = "expensive_branch") -> SimProject:
    """One dataset is 5x more expensive; cheaper datasets decide the claim just as
    well. A cost-blind policy spends compute on the expensive cell unnecessarily;
    InsightFlow (cost in the denominator) reaches the same decision far cheaper."""
    claim = Claim(id="C1", statement="method_a generalizes across datasets.", importance=0.9,
                  minimum_effect_size=0.02, required_seeds=3, reviewer_risk=0.7)
    truth: dict[tuple[str, str], CellTruth] = {}
    exps: list[Experiment] = []
    # The expensive dataset is listed first, so grid-order hits it early.
    specs = [("tinyimagenet", 0.40, 5.0, 4.0), ("cifar10", 0.72, 1.0, 1.0), ("cifar100", 0.55, 1.0, 1.0)]
    for ds, base, mcost, mtime in specs:
        _set_cell(truth, ds, base, 0.06, 0.004)
        for s in range(3):
            exps.append(_method(ds, s, ["C1"], mcost, mtime))
        exps.append(_baseline(ds, 0, ["C1"], mcost * 0.8, mtime * 0.8))
    return SimProject(seed=seed, name=name, claims=[claim], experiments=exps, truth=truth)


def generate_dependency_unlock(seed: int = 0, name: str = "dependency_unlock") -> SimProject:
    """A single cheap ablation unlocks the experiments that actually decide the
    claim; several distractor runs carry no decision value. InsightFlow runs the
    unlocker first (dependency-unlock value); order-/random-based policies waste
    steps on distractors before discovering the unlocked runs."""
    claim = Claim(id="C1", statement="method_a beats baseline once enabled.", importance=0.95,
                  minimum_effect_size=0.02, required_seeds=2, reviewer_risk=0.6)
    truth: dict[tuple[str, str], CellTruth] = {}
    exps: list[Experiment] = []
    # Distractors first in the list (no claim links -> no decision value).
    for i in range(4):
        exps.append(Experiment(id=f"distractor_{i}", method="probe", dataset=f"misc{i}",
                               condition="default", seed=0, claim_links=[], expected_cost=1.0,
                               expected_time=1.0, tags=["method"]))
    # The cheap unlocker.
    exps.append(Experiment(id="ablation_unlock", method="method_a", dataset="ablation",
                           condition="default", seed=0, claim_links=[], expected_cost=0.5,
                           expected_time=0.5, tags=["method"]))
    # Downstream deciding runs depend on the unlocker.
    for ds, base in [("dsA", 0.70), ("dsB", 0.60)]:
        _set_cell(truth, ds, base, 0.06, 0.004)
        exps.append(_method(ds, 0, ["C1"], 1.0, 1.0, deps=["ablation_unlock"]))
        exps.append(_baseline(ds, 0, ["C1"], 0.8, 0.8, deps=["ablation_unlock"]))
    return SimProject(seed=seed, name=name, claims=[claim], experiments=exps, truth=truth)


def generate_reviewer_baseline(seed: int = 0, name: str = "reviewer_baseline") -> SimProject:
    """The method has many seeds available but the claim cannot be decided without
    a baseline. InsightFlow runs method+baseline pairs (reviewer-risk value);
    all-seeds-first/grid pile method seeds first and decide much later."""
    claim = Claim(id="C1", statement="method_a beats baseline_a.", importance=0.9,
                  minimum_effect_size=0.02, required_seeds=2, reviewer_risk=0.9)
    truth: dict[tuple[str, str], CellTruth] = {}
    exps: list[Experiment] = []
    for ds, base in [("cifar10", 0.72), ("cifar100", 0.55)]:
        _set_cell(truth, ds, base, 0.06, 0.004)
        for s in range(5):  # lots of method seeds available (temptation to over-run)
            exps.append(_method(ds, s, ["C1"], 1.0, 1.0))
        exps.append(_baseline(ds, 0, ["C1"], 0.8, 0.8))
    return SimProject(seed=seed, name=name, claims=[claim], experiments=exps, truth=truth)


def generate_noisy_seeds(seed: int = 0, name: str = "noisy_seeds") -> SimProject:
    """Two datasets: one clean, one high-variance with a smaller effect. Deciding
    the noisy one needs replication; the clean one does not. InsightFlow adds seeds
    where variance/borderline-ness warrants (seed policy); all-tasks-first
    under-seeds the noisy cell, all-seeds-first over-seeds the clean one."""
    claim = Claim(id="C1", statement="method_a beats baseline on both datasets.", importance=0.9,
                  minimum_effect_size=0.02, required_seeds=4, reviewer_risk=0.6)
    truth: dict[tuple[str, str], CellTruth] = {}
    exps: list[Experiment] = []
    _set_cell(truth, "clean", 0.72, 0.06, 0.003)
    _set_cell(truth, "noisy", 0.55, 0.045, 0.035)  # smaller effect, high variance
    for ds in ("clean", "noisy"):
        for s in range(6):
            exps.append(_method(ds, s, ["C1"], 1.0, 1.0))
        for s in range(2):
            exps.append(_baseline(ds, s, ["C1"], 0.8, 0.8))
    return SimProject(seed=seed, name=name, claims=[claim], experiments=exps, truth=truth)


def generate_refuted(seed: int = 0, name: str = "refuted") -> SimProject:
    """The method genuinely does NOT beat the baseline (true effect ~ -0.05). The
    correct decision is 'refuted'; the scheduler should reach it efficiently
    instead of chasing a non-existent improvement."""
    claim = Claim(id="C1", statement="method_a beats baseline_a across datasets.", importance=0.9,
                  minimum_effect_size=0.02, required_seeds=3, reviewer_risk=0.7)
    truth: dict[tuple[str, str], CellTruth] = {}
    exps: list[Experiment] = []
    for ds, base in [("cifar10", 0.72), ("cifar100", 0.55), ("svhn", 0.88)]:
        _set_cell(truth, ds, base, -0.05, 0.006)  # method WORSE than baseline
        for s in range(4):
            exps.append(_method(ds, s, ["C1"], 1.0, 1.0))
        exps.append(_baseline(ds, 0, ["C1"], 0.8, 0.8))
    return SimProject(seed=seed, name=name, claims=[claim], experiments=exps, truth=truth)


def generate_mixed_multi_claim(seed: int = 0, name: str = "mixed_multi_claim") -> SimProject:
    """Two claims with different evidence needs in one project: C1 (accuracy, truly
    supported across datasets) and C2 (a second method's robustness, truly refuted).
    The correct project verdict requires deciding BOTH — supporting C1 while not
    overclaiming C2. A single-objective scheduler that chases C1 alone, or treats
    all claims alike, wastes runs."""
    c1 = Claim(id="C1", statement="method_a beats baseline_a (accuracy).", importance=0.9,
               minimum_effect_size=0.02, required_seeds=3, reviewer_risk=0.7)
    c2 = Claim(id="C2", statement="method_b is more robust than baseline_a.", importance=0.7,
               minimum_effect_size=0.02, required_seeds=3, reviewer_risk=0.6)
    truth: dict[tuple[str, str], CellTruth] = {}
    exps: list[Experiment] = []
    for ds, base in [("cifar10", 0.72), ("cifar100", 0.55)]:
        _set_cell(truth, ds, base, 0.06, 0.005)  # method_a clearly better -> C1 supported
        for s in range(4):
            exps.append(_method(ds, s, ["C1"], 1.0, 1.0))
        exps.append(_baseline(ds, 0, ["C1"], 0.8, 0.8))
    for ds, base in [("svhn", 0.88), ("stl10", 0.70)]:
        cell = f"{ds}|default"
        truth[("method_b", cell)] = CellTruth(mean=base - 0.05, sigma=0.006)  # method_b worse -> C2 refuted
        truth[("baseline_a", cell)] = CellTruth(mean=base, sigma=0.004)
        for s in range(4):
            exps.append(Experiment(id=f"method_b_{ds}_s{s}", method="method_b", baseline="baseline_a",
                                   dataset=ds, condition="default", seed=s, claim_links=["C2"],
                                   expected_cost=1.0, expected_time=1.0, tags=["method"]))
        exps.append(_baseline(ds, 0, ["C2"], 0.8, 0.8))
    return SimProject(seed=seed, name=name, claims=[c1, c2], experiments=exps, truth=truth)


SCENARIOS: dict[str, Callable[[int, str], SimProject]] = {
    "breadth": generate_project,
    "expensive_branch": generate_expensive_branch,
    "dependency_unlock": generate_dependency_unlock,
    "reviewer_baseline": generate_reviewer_baseline,
    "noisy_seeds": generate_noisy_seeds,
    "refuted": generate_refuted,
    "mixed_multi_claim": generate_mixed_multi_claim,
}


# --------------------------------------------------------------------------- #
# Policies (orderings)
# --------------------------------------------------------------------------- #
PolicyFn = Callable[[State, SimProject, "RunnerContext"], str | None]


@dataclass
class RunnerContext:
    rng: random.Random


def _pending(state: State, completed: set[str]) -> list[Experiment]:
    out = []
    for e in state.experiments:
        if e.id in completed:
            continue
        if all(d in completed for d in e.dependencies):
            out.append(e)
    return out


def _pick_insightflow(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    plan = build_plan(state)
    for action in plan.actions:
        if action.action_type in (ActionType.launch, ActionType.add_seed, ActionType.launch_baseline):
            return action.experiment_id
    return None


def _pick_grid(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    return pend[0].id if pend else None


def _pick_all_seeds_first(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    pend.sort(key=lambda e: (e.cell_key, e.is_baseline, e.seed))
    return pend[0].id if pend else None


def _pick_all_tasks_first(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    pend.sort(key=lambda e: (e.seed, e.is_baseline, e.cell_key))
    return pend[0].id if pend else None


def _pick_random(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    return ctx.rng.choice(pend).id if pend else None


def _pick_cheap_first(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    pend.sort(key=lambda e: (e.expected_cost, e.id))
    return pend[0].id if pend else None


def _pick_fastest_first(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    pend.sort(key=lambda e: (e.expected_time, e.id))
    return pend[0].id if pend else None


def _pick_oracle(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    """Upper bound: knows ground truth and decides claims with the fewest runs by
    *completing cells* (a method+baseline pair) to maximize breadth fastest."""
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    if not pend:
        return None
    truth = project.ground_truth_statuses()
    conf = compute_claim_confidence(state)
    inferred = {c.claim_id: c.status for c in conf.values()}
    undecided = [c for c in project.claims if inferred.get(c.id) != truth.get(c.id)]
    undecided.sort(key=lambda c: -c.importance)

    # Which cells already have a method / baseline result?
    method_done: set[str] = set()
    baseline_done: set[str] = set()
    for e in state.experiments:
        if e.id in completed:
            (baseline_done if e.is_baseline else method_done).add(e.cell_key)

    def priority(e: Experiment) -> tuple[int, float]:
        cell = e.cell_key
        if e.is_baseline:
            completes = cell in method_done and cell not in baseline_done
            starts = cell not in method_done and cell not in baseline_done
        else:
            completes = cell in baseline_done and cell not in method_done
            starts = cell not in method_done and cell not in baseline_done
        rank = 3 if completes else (2 if starts else 1)
        return (rank, -e.expected_cost)

    for claim in undecided:
        cand = [e for e in pend if claim.id in e.claim_links]
        if cand:
            return max(cand, key=priority).id
    return max(pend, key=priority).id


def _pick_baseline_first(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
    completed = state.completed_experiment_ids()
    pend = _pending(state, completed)
    pend.sort(key=lambda e: (not e.is_baseline, e.cell_key, e.seed))
    return pend[0].id if pend else None


def _insightflow_with(mods: dict) -> PolicyFn:
    """An InsightFlow variant whose policy is modified (for ablations)."""

    def pick(state: State, project: SimProject, ctx: RunnerContext) -> str | None:
        s = state.model_copy(update={"policy": state.policy.model_copy(update=mods)})
        plan = build_plan(s)
        for action in plan.actions:
            if action.action_type in (
                ActionType.launch, ActionType.add_seed, ActionType.launch_baseline
            ):
                return action.experiment_id
        return None

    return pick


POLICIES: dict[str, PolicyFn] = {
    "insightflow": _pick_insightflow,
    "grid": _pick_grid,
    "all_seeds_first": _pick_all_seeds_first,
    "all_tasks_first": _pick_all_tasks_first,
    "random": _pick_random,
    "cheap_first": _pick_cheap_first,
    "fastest_first": _pick_fastest_first,
    "baseline_first": _pick_baseline_first,
    "oracle": _pick_oracle,
    # Ablations: InsightFlow with one component disabled (for the ablation table).
    "ablate_reviewer_risk": _insightflow_with({"weight_reviewer_risk": 0.0}),
    "ablate_breadth_penalty": _insightflow_with({"weight_premature_replication_penalty": 0.0}),
    "ablate_cost": _insightflow_with({"lambda_cost": 0.0}),
    "uncertainty_only": _insightflow_with({
        "weight_decision_value": 0.0, "weight_dependency": 0.0, "weight_reviewer_risk": 0.0,
        "weight_redundancy_penalty": 0.0, "weight_premature_replication_penalty": 0.0,
        "weight_seed_value": 0.0,
    }),
}


@dataclass
class PolicyRun:
    policy: str
    steps: int
    decided_step: int | None
    cost_at_decision: float | None
    total_cost: float
    runs_launched: int
    confidence_evolution: list[float]
    correct: bool
    wrong_decisions: int


def _decided(state: State, truth: dict[str, ClaimStatus]) -> tuple[bool, int]:
    conf = compute_claim_confidence(state)
    inferred = {c.claim_id: c.status for c in conf.values()}
    wrong = 0
    all_decided = True
    for cid, true_status in truth.items():
        got = inferred.get(cid, ClaimStatus.unknown)
        if true_status in (ClaimStatus.supported, ClaimStatus.refuted):
            if got != true_status:
                all_decided = False
            if got in (ClaimStatus.supported, ClaimStatus.refuted) and got != true_status:
                wrong += 1
    return all_decided, wrong


def run_policy(project: SimProject, policy_name: str, max_steps: int) -> PolicyRun:
    """Replay ``project`` under one policy until the correct decision or max_steps."""
    if policy_name not in POLICIES:
        raise KeyError(f"Unknown policy '{policy_name}'.")
    pick = POLICIES[policy_name]
    ctx = RunnerContext(rng=random.Random(int(stable_hash((project.seed, policy_name), 12), 16)))
    truth = project.ground_truth_statuses()

    results: list[RunResult] = []
    completed: set[str] = set()
    confidence_evolution: list[float] = []
    decided_step: int | None = None
    cost_at_decision: float | None = None
    total_cost = 0.0

    for step in range(1, max_steps + 1):
        state = project.state_with(results, completed)
        exp_id = pick(state, project, ctx)
        if exp_id is None:
            break
        exp = state.experiment(exp_id)
        if exp is None:
            break
        result = project.execute(exp)
        results.append(result)
        completed.add(exp_id)
        total_cost += result.cost

        new_state = project.state_with(results, completed)
        conf = compute_claim_confidence(new_state)
        confidence_evolution.append(
            round(sum(c.confidence for c in conf.values()) / max(1, len(conf)), 4)
        )
        all_decided, _ = _decided(new_state, truth)
        if all_decided and decided_step is None:
            decided_step = step
            cost_at_decision = round(total_cost, 3)
            break

    final_state = project.state_with(results, completed)
    _, wrong = _decided(final_state, truth)
    return PolicyRun(
        policy=policy_name,
        steps=len(results),
        decided_step=decided_step,
        cost_at_decision=cost_at_decision,
        total_cost=round(total_cost, 3),
        runs_launched=len(results),
        confidence_evolution=confidence_evolution,
        correct=decided_step is not None,
        wrong_decisions=wrong,
    )


def simulate_result_for(exp: Experiment, project_seed: int = 0) -> RunResult:
    """Synthesize a plausible result for an arbitrary experiment (used by the
    ``simulate-step`` CLI command on real/demo projects).

    Deterministic: method experiments score a few points above a dataset-dependent
    baseline, with small noise and a short learning curve.
    """
    rng = random.Random(int(stable_hash((project_seed, exp.id, "cli-sim"), 12), 16))
    dataset_offset = {"cifar10": 0.06, "cifar100": -0.10, "svhn": 0.15}.get(exp.dataset, 0.0)
    base = 0.70 + dataset_offset
    bonus = 0.05 if not exp.is_baseline else 0.0
    final = base + bonus + rng.gauss(0.0, 0.01)
    history = [
        {"step": float(i), "accuracy": round(0.5 * base + 0.5 * final * (i / 5.0), 4)}
        for i in range(1, 6)
    ]
    return RunResult(
        run_id=f"sim-{exp.id}-{project_seed}-{rng.randint(0, 9999)}",
        experiment_id=exp.id,
        seed=exp.seed,
        metrics={"accuracy": round(final, 4)},
        cost=exp.expected_cost,
        wall_time=exp.expected_time,
        status=RunStatus.completed,
        source=RunSource.simulator,
        partial_history=history,
    )

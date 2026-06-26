"""Shared fixtures and builders for the test suite."""

from __future__ import annotations

import pytest

from insightflow.schemas import (
    Claim,
    Experiment,
    ExperimentStatus,
    Policy,
    RunResult,
    RunSource,
    RunStatus,
    State,
)


def make_claim(cid: str = "C1", **kw) -> Claim:
    base = {
        "id": cid,
        "statement": f"claim {cid}",
        "importance": 0.9,
        "target_metric": "accuracy",
        "minimum_effect_size": 0.02,
        "required_seeds": 3,
        "reviewer_risk": 0.7,
    }
    base.update(kw)
    return Claim(**base)


def make_method(dataset: str, seed: int = 0, claims=("C1",), **kw) -> Experiment:
    base = {
        "id": f"method_a_{dataset}_s{seed}",
        "method": "method_a",
        "baseline": "baseline_a",
        "dataset": dataset,
        "condition": "default",
        "seed": seed,
        "claim_links": list(claims),
        "expected_cost": 1.0,
        "expected_time": 1.0,
        "tags": ["method"],
    }
    base.update(kw)
    return Experiment(**base)


def make_baseline(dataset: str, seed: int = 0, claims=("C1",), **kw) -> Experiment:
    base = {
        "id": f"baseline_a_{dataset}_s{seed}",
        "method": "baseline_a",
        "dataset": dataset,
        "condition": "default",
        "seed": seed,
        "claim_links": list(claims),
        "expected_cost": 0.8,
        "expected_time": 0.8,
        "tags": ["baseline"],
    }
    base.update(kw)
    return Experiment(**base)


def make_result(exp: Experiment, accuracy: float, status: RunStatus = RunStatus.completed) -> RunResult:
    return RunResult(
        run_id=f"r-{exp.id}",
        experiment_id=exp.id,
        seed=exp.seed,
        metrics={"accuracy": accuracy},
        cost=exp.expected_cost,
        wall_time=exp.expected_time,
        status=status,
        source=RunSource.manual,
    )


@pytest.fixture
def cifar10_observed_state() -> State:
    """CIFAR-10 method+baseline observed (effect ~0.06); CIFAR-100 + SVHN pending.

    The interesting decision is generality, not seed variance.
    """
    claims = [make_claim("C1", required_seeds=3)]
    experiments: list[Experiment] = []
    results: list[RunResult] = []

    # CIFAR-10 observed: 3 method seeds @0.78, 2 baseline seeds @0.72.
    for s in range(3):
        e = make_method("cifar10", s, status=ExperimentStatus.completed)
        experiments.append(e)
        results.append(make_result(e, 0.78))
    for s in range(2):
        e = make_baseline("cifar10", s, status=ExperimentStatus.completed)
        experiments.append(e)
        results.append(make_result(e, 0.72))
    # Extra CIFAR-10 method seeds (replication, pending).
    for s in range(3, 5):
        experiments.append(make_method("cifar10", s))
    # New conditions pending.
    for ds in ("cifar100", "svhn"):
        for s in range(2):
            experiments.append(make_method(ds, s))
        experiments.append(make_baseline(ds, 0))

    return State(claims=claims, experiments=experiments, results=results, policy=Policy())

"""Partial-run monitoring tests (freeze-thaw projection)."""

from __future__ import annotations

from insightflow.partial import monitor_partial
from insightflow.schemas import (
    ActionType,
    ExperimentStatus,
    Policy,
    RunResult,
    RunStatus,
    State,
)
from insightflow.scoring import compute_claim_evidence
from tests.conftest import make_baseline, make_claim, make_method, make_result


def _rising_history(metric, start, end, n=8):
    # A saturating rise from start to ~end.
    out = []
    for i in range(1, n + 1):
        frac = 1 - 0.7 ** i
        out.append({"step": float(i), metric: round(start + (end - start) * frac, 4)})
    return out


def _state_with_running(method_proj, baseline_val=None, near_boundary=True):
    """Build a state with one running method run (partial curve) and an optional
    completed baseline. ``near_boundary`` toggles whether the claim is decided."""
    claim = make_claim("C1", required_seeds=3, importance=0.9)
    exps, results = [], []

    running = make_method("cifar10", 0, status=ExperimentStatus.running)
    exps.append(running)
    results.append(
        RunResult(
            run_id="run-running",
            experiment_id=running.id,
            metrics={},
            status=RunStatus.running,
            partial_history=_rising_history("accuracy", 0.5, method_proj),
        )
    )
    if baseline_val is not None:
        b = make_baseline("cifar10", 0, status=ExperimentStatus.completed)
        exps.append(b)
        results.append(make_result(b, baseline_val))
        # add a couple other observed datasets so the claim is decided when asked
    if not near_boundary:
        # Make the claim decided: observe method+baseline on two more datasets clearly.
        for ds in ("cifar100", "svhn"):
            m = make_method(ds, 0, status=ExperimentStatus.completed)
            bb = make_baseline(ds, 0, status=ExperimentStatus.completed)
            exps += [m, bb]
            results += [make_result(m, 0.80), make_result(bb, 0.70)]
        m0 = make_method("cifar10", 1, status=ExperimentStatus.completed)
        b0 = make_baseline("cifar10", 1, status=ExperimentStatus.completed)
        exps += [m0, b0]
        results += [make_result(m0, 0.80), make_result(b0, 0.70)]

    return State(claims=[claim], experiments=exps, results=results, policy=Policy())


def _decide(state):
    ev = compute_claim_evidence(state)
    running = next(r for r in state.results if r.status == RunStatus.running)
    exp = state.experiment(running.experiment_id)
    return monitor_partial(running, exp, state, ev, state.policy)


def test_projected_below_baseline_stops():
    state = _state_with_running(method_proj=0.66, baseline_val=0.72)
    d = _decide(state)
    assert d.action_type == ActionType.stop
    assert "trails the baseline" in d.reason


def test_projected_above_baseline_promotes_or_continues():
    state = _state_with_running(method_proj=0.82, baseline_val=0.72)
    d = _decide(state)
    assert d.action_type in (ActionType.promote, ActionType.continue_)


def test_no_baseline_rising_launches_baseline():
    state = _state_with_running(method_proj=0.82, baseline_val=None)
    d = _decide(state)
    assert d.action_type == ActionType.launch_baseline


def test_decided_claim_stops_the_run():
    state = _state_with_running(method_proj=0.82, baseline_val=0.72, near_boundary=False)
    d = _decide(state)
    assert d.action_type == ActionType.stop
    assert "already decided" in d.reason


def test_factors_include_projection():
    state = _state_with_running(method_proj=0.82, baseline_val=0.72)
    d = _decide(state)
    assert "projected_final" in d.factors


def test_projected_tie_does_not_promote():
    # Projected equals the baseline -> not a "clear beat"; must not promote.
    state = _state_with_running(method_proj=0.72, baseline_val=0.72)
    d = _decide(state)
    assert d.action_type != ActionType.promote


def test_sub_minimum_effect_does_not_promote():
    # Projected beats the baseline by < minimum_effect_size (0.02) -> continue.
    state = _state_with_running(method_proj=0.735, baseline_val=0.72)
    d = _decide(state)
    assert d.action_type != ActionType.promote

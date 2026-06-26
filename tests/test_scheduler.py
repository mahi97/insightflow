"""Scheduler / plan-construction tests."""

from __future__ import annotations

from insightflow.scheduler import build_plan, compute_state_hash
from insightflow.schemas import ActionType


def _cell(action) -> str:
    # label is "method / dataset / condition / seed=N"
    parts = [p.strip() for p in action.label.split("/")]
    return f"{parts[1]}|{parts[2]}"


def test_plan_has_queue_postponed_and_claim_table(cifar10_observed_state):
    plan = build_plan(cifar10_observed_state)
    assert plan.actions, "expected a non-empty immediate queue"
    assert plan.claim_confidence, "expected a claim-confidence table"
    assert plan.id.startswith("plan_")


def test_top_action_is_a_new_condition_not_extra_seed(cifar10_observed_state):
    plan = build_plan(cifar10_observed_state)
    top = plan.actions[0]
    # The top recommendation must be a new dataset (cifar100/svhn), not CIFAR-10.
    assert "cifar10 /" not in top.label
    assert top.action_type in (ActionType.launch, ActionType.launch_baseline)


def test_extra_cifar10_seeds_are_not_in_top_queue(cifar10_observed_state):
    plan = build_plan(cifar10_observed_state)
    queue_labels = " ".join(a.label for a in plan.actions[:2])
    assert "cifar10 / default / seed=3" not in queue_labels
    assert "cifar10 / default / seed=4" not in queue_labels
    # They should appear among postponed/avoided instead.
    other = plan.postponed + plan.avoided
    assert any("cifar10 / default / seed=3" in a.label for a in other)


def test_queue_diversifies_across_conditions(cifar10_observed_state):
    plan = build_plan(cifar10_observed_state)
    # No (cell, role) should appear twice among the method launches in the queue.
    method_cells = [_cell(a) for a in plan.actions if "baseline" not in a.label]
    assert len(method_cells) == len(set(method_cells)), "queue stacked seeds of one condition"


def test_generality_warning_present(cifar10_observed_state):
    plan = build_plan(cifar10_observed_state)
    assert any("Generality" in w for w in plan.warnings)


def test_plan_is_deterministic(cifar10_observed_state):
    p1 = build_plan(cifar10_observed_state)
    p2 = build_plan(cifar10_observed_state)
    assert p1.state_hash == p2.state_hash == compute_state_hash(cifar10_observed_state)
    assert [a.experiment_id for a in p1.actions] == [a.experiment_id for a in p2.actions]

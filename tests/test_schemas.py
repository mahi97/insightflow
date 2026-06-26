"""Schema validation and config-parsing tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydValidationError

from insightflow.config import validate_configs
from insightflow.schemas import Claim, Experiment, RunResult, RunStatus


def test_claim_importance_word_coercion():
    assert Claim(id="C1", importance="high").importance == 0.85
    assert Claim(id="C2", importance="low").importance == 0.25
    assert Claim(id="C3", importance=0.42).importance == 0.42


def test_claim_range_validation():
    with pytest.raises(PydValidationError):
        Claim(id="C", reviewer_risk=2.0)
    with pytest.raises(PydValidationError):
        Claim(id="C", required_seeds=0)


def test_experiment_time_must_be_positive():
    with pytest.raises(PydValidationError):
        Experiment(id="e", expected_time=0.0)


def test_condition_and_cell_keys():
    e = Experiment(id="e", method="m", dataset="cifar10", condition="alpha=0.1", seed=3)
    assert e.condition_key == "m|cifar10|alpha=0.1"
    assert e.cell_key == "cifar10|alpha=0.1"  # method- and seed-agnostic


def test_is_baseline_does_not_trigger_on_baseline_reference():
    """A method that *declares* its baseline must not be read as a baseline."""
    method = Experiment(id="m", method="method_a", baseline="baseline_a", tags=["method"])
    assert method.is_baseline is False
    base_by_tag = Experiment(id="b", method="baseline_a", tags=["baseline"])
    assert base_by_tag.is_baseline is True
    base_by_name = Experiment(id="b2", method="baseline_x")
    assert base_by_name.is_baseline is True


def test_runresult_metric_falls_back_to_history():
    r = RunResult(
        run_id="r",
        experiment_id="e",
        status=RunStatus.partial,
        partial_history=[{"step": 1, "accuracy": 0.5}, {"step": 2, "accuracy": 0.6}],
    )
    assert r.metric("accuracy") == 0.6
    assert r.metric("missing") is None


def test_validate_detects_bad_links_and_duplicates_and_cycles():
    claims = [Claim(id="C1")]
    experiments = [
        Experiment(id="e1", claim_links=["C1", "C_missing"], dependencies=["e2"]),
        Experiment(id="e2", dependencies=["e1"]),  # cycle e1<->e2
        Experiment(id="e3"),
        Experiment(id="e3"),  # duplicate id
    ]
    issues = validate_configs(claims, experiments)
    joined = " ".join(issues)
    assert "unknown claim 'C_missing'" in joined
    assert "Duplicate experiment id 'e3'" in joined
    assert "cycle" in joined.lower()


def test_validate_clean_config_has_no_issues():
    claims = [Claim(id="C1")]
    experiments = [Experiment(id="e1", claim_links=["C1"])]
    assert validate_configs(claims, experiments) == []

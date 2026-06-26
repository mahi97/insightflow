"""Local launcher tests."""

from __future__ import annotations

import sys

import pytest

from insightflow.errors import InsightFlowError
from insightflow.launcher import LocalLauncher, _parse_metrics_from_stdout
from insightflow.schemas import RunStatus
from tests.conftest import make_method


def test_parse_metrics_picks_last_json_object():
    out = "starting\nepoch 1\n{\"accuracy\": 0.5}\nnoise\n{\"accuracy\": 0.81, \"loss\": 0.3}\n"
    assert _parse_metrics_from_stdout(out) == {"accuracy": 0.81, "loss": 0.3}


def test_parse_metrics_ignores_non_numeric_and_booleans():
    assert _parse_metrics_from_stdout('{"name": "x", "ok": true, "acc": 0.9}') == {"acc": 0.9}


def test_run_captures_metrics_and_records_completed():
    exp = make_method("cifar10", 0)
    # A command that prints a JSON metrics line.
    exp = exp.model_copy(
        update={"command": f'{sys.executable} -c "print(\'{{\\\"accuracy\\\": 0.77}}\')"'}
    )
    result = LocalLauncher().run(exp)
    assert result.status == RunStatus.completed
    assert result.metrics == {"accuracy": 0.77}
    assert result.wall_time >= 0.0


def test_run_without_metrics_is_failed_not_dropped():
    exp = make_method("cifar10", 0)
    exp = exp.model_copy(update={"command": f'{sys.executable} -c "print(\'no metrics here\')"'})
    result = LocalLauncher().run(exp)
    assert result.status == RunStatus.failed
    assert result.metrics == {}


def test_nonzero_exit_is_failed():
    exp = make_method("cifar10", 0)
    exp = exp.model_copy(update={"command": f'{sys.executable} -c "import sys; sys.exit(3)"'})
    result = LocalLauncher().run(exp)
    assert result.status == RunStatus.failed


def test_missing_command_raises():
    exp = make_method("cifar10", 0)
    exp = exp.model_copy(update={"command": None})
    with pytest.raises(InsightFlowError):
        LocalLauncher().run(exp)

"""The agent-vs-ledger environment must be deterministic and grade correctly."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "eval" / "agent_env.py"


def _run(args, cwd):
    return subprocess.run([sys.executable, str(ENV), *args], cwd=cwd, capture_output=True,
                          text=True, check=True)


def test_breadth_env_grades_correct_verdict(tmp_path):
    d = str(tmp_path / "proj")
    _run(["setup", "--scenario", "breadth", "--seed", "0", "--dir", d], REPO)
    for e in ("method_a_cifar10_s0", "baseline_a_cifar10_s0", "method_a_cifar100_s0",
              "baseline_a_cifar100_s0", "method_a_svhn_s0", "baseline_a_svhn_s0"):
        _run(["run", "--dir", d, "--exp", e], REPO)
    _run(["decide", "--dir", d, "--claim", "C1", "--verdict", "supported"], REPO)
    report = json.loads(_run(["score", "--dir", d], REPO).stdout)
    assert report["all_correct"] is True
    assert report["runs_used"] == 6
    assert report["wrong_decisions"] == 0


def test_rerun_does_not_double_charge(tmp_path):
    d = str(tmp_path / "proj")
    _run(["setup", "--scenario", "breadth", "--seed", "0", "--dir", d], REPO)
    _run(["run", "--dir", d, "--exp", "method_a_cifar10_s0"], REPO)
    _run(["run", "--dir", d, "--exp", "method_a_cifar10_s0"], REPO)  # same again
    report = json.loads(_run(["score", "--dir", d], REPO).stdout)
    assert report["runs_used"] == 1  # no double charge

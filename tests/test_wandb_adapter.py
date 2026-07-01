"""Offline test of the W&B->replay adapter's `build` step (no network)."""
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADAPTER = REPO / "eval" / "wandb_to_replay.py"


def _synth_rows(path: Path):
    rows = []
    base = {"sst2": 0.90, "mrpc": 0.85}
    for i, (t, b) in enumerate(base.items()):
        for s in (42, 3407):
            rows.append({"project": "x", "method": "gfa", "task": t, "group": "1", "seed": s,
                         "metric": "eval/accuracy", "value": b + 0.03, "runtime": 10,
                         "created_at": f"2024-01-0{i + 1}T0{s % 9}:00:00",
                         "run_id": f"g{t}{s}", "name": f"gfa-{t}-r1-s{s}"})
            rows.append({"project": "x", "method": "lora", "task": t, "group": "1", "seed": s,
                         "metric": "eval/accuracy", "value": b, "runtime": 10,
                         "created_at": f"2024-01-0{i + 1}T0{s % 9}:30:00",
                         "run_id": f"l{t}{s}", "name": f"lora-{t}-r1-s{s}"})
    path.write_text(json.dumps(rows))


def test_build_emits_configs_and_ordered_csv(tmp_path):
    rows = tmp_path / "rows.json"
    _synth_rows(rows)
    out = tmp_path / "case"
    r = subprocess.run(
        [sys.executable, str(ADAPTER), "build", "--rows", str(rows), "--method", "gfa",
         "--baseline", "lora", "--group", "1", "--min-effect", "0.01", "--out", str(out)],
        capture_output=True, text=True, check=True, cwd=REPO,
    )
    assert "SUPPORTED" in r.stdout  # pooled +0.03 >= 0.01
    assert (out / "configs" / "claims.yaml").exists()
    assert (out / "configs" / "experiments.yaml").exists()
    with (out / "runs.csv").open() as fh:
        reader = list(csv.reader(fh))
    assert reader[0] == ["id", "created_at", "score"]
    body = reader[1:]
    assert len(body) == 8  # 2 tasks x 2 seeds x {method, baseline}
    assert [row[1] for row in body] == sorted(row[1] for row in body)  # arrival order


def test_build_auto_selects_both_covered_tasks(tmp_path):
    rows = tmp_path / "rows.json"
    _synth_rows(rows)
    # add a task with ONLY the baseline -> must be excluded by auto-selection
    data = json.loads(rows.read_text())
    data.append({"project": "x", "method": "lora", "task": "rte", "group": "1", "seed": 42,
                 "metric": "eval/accuracy", "value": 0.6, "runtime": 10,
                 "created_at": "2024-02-01T00:00:00", "run_id": "lrte", "name": "lora-rte-r1-s42"})
    rows.write_text(json.dumps(data))
    out = tmp_path / "case2"
    r = subprocess.run(
        [sys.executable, str(ADAPTER), "build", "--rows", str(rows), "--method", "gfa",
         "--baseline", "lora", "--group", "1", "--out", str(out)],
        capture_output=True, text=True, check=True, cwd=REPO,
    )
    assert "rte" not in r.stdout  # only baseline ran rte -> excluded
    assert "sst2" in r.stdout and "mrpc" in r.stdout

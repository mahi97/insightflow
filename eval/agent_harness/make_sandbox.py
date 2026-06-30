"""Set up one evaluation sandbox: configs + ledger + an oracle the agent calls.

Usage: python make_sandbox.py <scenario> <seed> <sandbox_dir>

The agent only ever sees results by RUNNING an experiment via run_exp.py, which
samples from the scenario's hidden truth and records it in the ledger. The hidden
truth lives in the package, not in the sandbox; agents are instructed not to peek.
"""

import json
import sys
from pathlib import Path

from insightflow.ledger import Ledger
from insightflow.simulator import SCENARIOS
from insightflow.utils import write_yaml

scenario, seed_s, sandbox = sys.argv[1], int(sys.argv[2]), sys.argv[3]
proj = SCENARIOS[scenario](seed_s, scenario)
sb = Path(sandbox)
(sb / "configs").mkdir(parents=True, exist_ok=True)

claims = [
    {
        "id": c.id,
        "statement": c.statement,
        "importance": c.importance,
        "target_metric": c.target_metric,
        "desired_direction": c.desired_direction.value,
        "minimum_effect_size": c.minimum_effect_size,
        "required_seeds": c.required_seeds,
        "reviewer_risk": c.reviewer_risk,
    }
    for c in proj.claims
]
exps = [
    {
        "id": e.id,
        "method": e.method,
        "baseline": e.baseline,
        "dataset": e.dataset,
        "condition": e.condition,
        "seed": e.seed,
        "claim_links": e.claim_links,
        "dependencies": e.dependencies,
        "expected_cost": e.expected_cost,
        "expected_time": e.expected_time,
        "tags": e.tags,
    }
    for e in proj.experiments
]
write_yaml(sb / "configs/claims.yaml", {"claims": claims})
write_yaml(sb / "configs/experiments.yaml", {"experiments": exps})
write_yaml(sb / "configs/resources.yaml", {"pools": [{"type": "gpu", "count": 4}], "budget_gpu_hours": 60})
Ledger(sandbox).initialize(force=True)

run_exp = f'''import json, sys
from insightflow.ledger import Ledger
from insightflow.simulator import SCENARIOS
proj = SCENARIOS[{scenario!r}]({seed_s}, {scenario!r})
eid = sys.argv[1] if len(sys.argv) > 1 else ""
exp = next((e for e in proj.experiments if e.id == eid), None)
if exp is None:
    print("ERROR: unknown experiment id:", eid)
    print("valid ids:", ", ".join(e.id for e in proj.experiments))
    sys.exit(1)
res = proj.execute(exp)              # samples the (hidden) ground truth
Ledger({sandbox!r}).add_result(res)  # records into the ledger
print(json.dumps({{"experiment": eid, "metrics": res.metrics, "cost": round(res.cost, 2)}}))
'''
(sb / "run_exp.py").write_text(run_exp)

show = f'''from insightflow.ledger import Ledger
st = Ledger({sandbox!r}).load_state()
print(f"completed runs: {{len(st.results)}}")
for r in sorted(st.results, key=lambda r: r.experiment_id):
    print(" ", r.experiment_id, r.metrics, "cost=", round(r.cost, 2))
print("total compute cost:", round(sum(r.cost for r in st.results), 2))
'''
(sb / "show_results.py").write_text(show)

print(json.dumps({
    "scenario": scenario,
    "sandbox": sandbox,
    "ground_truth": {k: v.value for k, v in proj.ground_truth_statuses().items()},
    "n_experiments": len(exps),
}))

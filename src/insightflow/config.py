"""Loading and validation of InsightFlow YAML configuration.

The four config files describe the *definitions* of a project:

* ``claims.yaml``      - research claims and their decision rules
* ``experiments.yaml`` - the runnable experiment grid
* ``resources.yaml``   - available compute
* ``policy.yaml``      - scheduler weights/thresholds (optional)

Run *results* live in the ledger, not in configs. ``validate`` performs the
semantic checks the architecture spec calls for: missing IDs, bad claim links,
impossible costs, and duplicate experiments.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from .errors import ConfigError, ValidationError
from .schemas import Claim, Experiment, Policy, Resources
from .utils import read_yaml, write_yaml

CONFIG_FILES = {
    "claims": "claims.yaml",
    "experiments": "experiments.yaml",
    "resources": "resources.yaml",
    "policy": "policy.yaml",
}


def config_dir(project_dir: str | Path) -> Path:
    return Path(project_dir) / "configs"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _load_list(path: Path, key: str) -> list[dict]:
    """Load a YAML file that is either a top-level list or ``{key: [...]}``."""
    if not path.exists():
        return []
    data = read_yaml(path)
    if isinstance(data, dict) and key in data:
        data = data[key]
    if data in (None, {}):
        return []
    if not isinstance(data, list):
        raise ConfigError(f"{path.name}: expected a list of {key} (got {type(data).__name__}).")
    return data


def load_claims(project_dir: str | Path) -> list[Claim]:
    raw = _load_list(config_dir(project_dir) / CONFIG_FILES["claims"], "claims")
    out = []
    for i, item in enumerate(raw):
        try:
            out.append(Claim(**item))
        except PydanticValidationError as exc:
            raise ConfigError(f"claims.yaml entry #{i + 1} is invalid: {exc}") from exc
    return out


def load_experiments(project_dir: str | Path) -> list[Experiment]:
    raw = _load_list(config_dir(project_dir) / CONFIG_FILES["experiments"], "experiments")
    out = []
    for i, item in enumerate(raw):
        try:
            out.append(Experiment(**item))
        except PydanticValidationError as exc:
            raise ConfigError(f"experiments.yaml entry #{i + 1} is invalid: {exc}") from exc
    return out


def load_resources(project_dir: str | Path) -> Resources:
    path = config_dir(project_dir) / CONFIG_FILES["resources"]
    if not path.exists():
        return Resources()
    data = read_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError("resources.yaml: expected a mapping.")
    try:
        return Resources(**data)
    except PydanticValidationError as exc:
        raise ConfigError(f"resources.yaml is invalid: {exc}") from exc


def load_policy(project_dir: str | Path) -> Policy:
    path = config_dir(project_dir) / CONFIG_FILES["policy"]
    if not path.exists():
        return Policy()
    data = read_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError("policy.yaml: expected a mapping.")
    try:
        return Policy(**data)
    except PydanticValidationError as exc:
        raise ConfigError(f"policy.yaml is invalid: {exc}") from exc


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_configs(
    claims: list[Claim],
    experiments: list[Experiment],
) -> list[str]:
    """Return a list of human-readable issues. Empty list means valid."""
    issues: list[str] = []

    # Duplicate claim IDs
    claim_ids = [c.id for c in claims]
    for cid in _duplicates(claim_ids):
        issues.append(f"Duplicate claim id '{cid}'.")
    for c in claims:
        if not c.id:
            issues.append("A claim is missing an 'id'.")

    # Duplicate experiment IDs
    exp_ids = [e.id for e in experiments]
    for eid in _duplicates(exp_ids):
        issues.append(f"Duplicate experiment id '{eid}'.")

    exp_id_set = set(exp_ids)
    claim_id_set = set(claim_ids)
    for e in experiments:
        if not e.id:
            issues.append("An experiment is missing an 'id'.")
        # Bad claim links
        for link in e.claim_links:
            if link not in claim_id_set:
                issues.append(f"Experiment '{e.id}' links to unknown claim '{link}'.")
        # Bad dependencies
        for dep in e.dependencies:
            if dep not in exp_id_set:
                issues.append(f"Experiment '{e.id}' depends on unknown experiment '{dep}'.")
            if dep == e.id:
                issues.append(f"Experiment '{e.id}' depends on itself.")
        # Impossible costs/times (pydantic already enforces >=0 / >0, but flag zeros)
        if e.expected_time <= 0:
            issues.append(f"Experiment '{e.id}' has non-positive expected_time.")
        if e.expected_cost < 0:
            issues.append(f"Experiment '{e.id}' has negative expected_cost.")

    # Dependency cycles
    issues.extend(_cycle_issues(experiments))

    return issues


def validate_or_raise(claims: list[Claim], experiments: list[Experiment]) -> None:
    issues = validate_configs(claims, experiments)
    if issues:
        raise ValidationError(issues)


def _duplicates(items: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for it in items:
        if it in seen and it not in dupes:
            dupes.append(it)
        seen.add(it)
    return dupes


def _cycle_issues(experiments: list[Experiment]) -> list[str]:
    """Detect dependency cycles via DFS; report one issue per cycle found."""
    graph = {e.id: [d for d in e.dependencies if d != e.id] for e in experiments}
    issues: list[str] = []
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph, WHITE)

    def visit(node: str, stack: list[str]) -> None:
        color[node] = GREY
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == GREY:
                cycle = " -> ".join(stack[stack.index(nxt):] + [nxt])
                issues.append(f"Dependency cycle detected: {cycle}.")
            elif color[nxt] == WHITE:
                visit(nxt, stack + [nxt])
        color[node] = BLACK

    for n in graph:
        if color[n] == WHITE:
            visit(n, [n])
    return issues


# --------------------------------------------------------------------------- #
# Writing defaults (used by `init`)
# --------------------------------------------------------------------------- #
def write_default_configs(project_dir: str | Path, overwrite: bool = False) -> list[Path]:
    """Write minimal starter configs. Returns the paths written."""
    cdir = config_dir(project_dir)
    written: list[Path] = []
    defaults = {
        "claims": {
            "claims": [
                {
                    "id": "C1",
                    "statement": "The proposed method improves the target metric over the baseline.",
                    "importance": "high",
                    "target_metric": "accuracy",
                    "desired_direction": "higher",
                    "minimum_effect_size": 0.02,
                    "required_seeds": 3,
                    "reviewer_risk": 0.6,
                    "notes": "Edit this to describe your real claim.",
                }
            ]
        },
        "experiments": {
            "experiments": [
                {
                    "id": "method_dataset_seed0",
                    "method": "method_a",
                    "baseline": "baseline_a",
                    "dataset": "dataset_a",
                    "condition": "default",
                    "seed": 0,
                    "claim_links": ["C1"],
                    "dependencies": [],
                    "expected_cost": 1.0,
                    "expected_time": 1.0,
                    "resource_type": "gpu",
                    "command": "python train.py --method method_a --dataset dataset_a --seed 0",
                }
            ]
        },
        "resources": {
            "pools": [{"type": "gpu", "count": 4, "cost_per_hour": 2.0}],
            "budget_gpu_hours": 200,
        },
        "policy": Policy().model_dump(),
    }
    for key, fname in CONFIG_FILES.items():
        path = cdir / fname
        if path.exists() and not overwrite:
            continue
        write_yaml(path, defaults[key])
        written.append(path)
    return written

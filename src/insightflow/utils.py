"""Small, dependency-light helpers shared across InsightFlow.

Everything here is deterministic (no global RNG, no wall-clock in IDs unless
asked) so that scoring, hashing, and reports are reproducible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) if needed and return it as a ``Path``."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def stable_json(obj: Any) -> str:
    """Serialize ``obj`` to JSON with sorted keys for stable hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(obj: Any, length: int = 12) -> str:
    """Deterministic short hash of any JSON-serializable object."""
    digest = hashlib.sha256(stable_json(obj).encode("utf-8")).hexdigest()
    return digest[:length]


def read_yaml(path: str | Path) -> Any:
    """Load a YAML file, returning ``{}`` for an empty file."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if data is not None else {}


def write_yaml(path: str | Path, data: Any) -> None:
    """Write ``data`` to ``path`` as readable YAML."""
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False)


def write_text(path: str | Path, text: str) -> None:
    """Write ``text`` to ``path``, creating parent directories."""
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp ``value`` into the ``[low, high]`` interval."""
    return max(low, min(high, value))


def mean(values: Iterable[float]) -> float:
    """Arithmetic mean, returning 0.0 for an empty iterable."""
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0


def pstdev(values: Iterable[float]) -> float:
    """Population standard deviation, returning 0.0 for fewer than 2 values."""
    vals = list(values)
    if len(vals) < 2:
        return 0.0
    mu = mean(vals)
    var = sum((v - mu) ** 2 for v in vals) / len(vals)
    return var**0.5


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a GitHub-flavored Markdown table.

    Cells are stringified; floats are not specially formatted here so callers
    keep control over precision.
    """
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join("" if c is None else str(c) for c in row) + " |"
        for row in rows
    ]
    return "\n".join([head, sep, *body])


def fmt(value: float, digits: int = 3) -> str:
    """Format a float compactly with a fixed number of digits."""
    return f"{value:.{digits}f}"


def merge_dicts(*dicts: Mapping[str, Any]) -> dict[str, Any]:
    """Shallow-merge mappings; later mappings win."""
    out: dict[str, Any] = {}
    for d in dicts:
        out.update(d)
    return out

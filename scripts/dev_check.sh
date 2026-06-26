#!/usr/bin/env bash
# Run the full local check suite the way CI / acceptance does.
# Usage: bash scripts/dev_check.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> uv sync"
uv sync

echo "==> ruff check ."
uv run ruff check .

echo "==> mypy src"
uv run mypy src

echo "==> pytest"
uv run pytest

echo "==> smoke: demo + plan + benchmark"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
uv run insightflow demo --force -C "$TMP" >/dev/null
uv run insightflow validate -C "$TMP" >/dev/null
uv run insightflow plan -C "$TMP" >/dev/null
uv run insightflow benchmark --steps 5 --projects 1 -C "$TMP" >/dev/null

echo "All checks passed."

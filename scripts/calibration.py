"""Reproduce the calibration (Expected Calibration Error) of the Bayesian model.

This is the committed artifact behind the "ECE ~= 0.011 over 200k draws" figure
in the docs. Thin CLI wrapper over ``insightflow.calibration.measure_calibration``.

    uv run python scripts/calibration.py            # N = 200,000
    uv run python scripts/calibration.py 5000        # quicker

A small-N property + ECE-bound version is asserted in tests/test_bayes.py.
"""

from __future__ import annotations

import sys

from insightflow.calibration import measure_calibration


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
    r = measure_calibration(n)
    print(f"N={r.n}  base_rate(supported)={r.base_rate:.4f}")
    print(f"{'bin':>12} {'count':>8} {'mean_pred':>10} {'emp_freq':>9} {'|gap|':>7}")
    for lo, count, mp, ef in r.bins:
        print(f"[{lo:.1f},{lo + 0.1:.1f}) {count:>8} {mp:>10.4f} {ef:>9.4f} {abs(mp - ef):>7.4f}")
    print(f"\nExpected Calibration Error (ECE) = {r.ece:.4f}")


if __name__ == "__main__":
    main()

"""Deterministic learning-curve extrapolation (freeze-thaw style).

Given a partial learning curve ``(step_i, value_i)`` we fit a saturating
exponential and read off the projected final value (the asymptote):

    y(t) = a + b * exp(-c * t)

``a`` is the asymptote (projected final), ``c > 0`` the decay rate, and ``b`` of
either sign (negative for a rising accuracy curve, positive for a falling loss
curve). For a fixed ``c`` the model is *linear* in ``(a, b)``, so we grid-search
``c`` on a fixed log-spaced grid and solve closed-form least squares for
``(a, b)`` at each — fully deterministic, no RNG, no SciPy.

This replaces the v0.1 slope heuristic in ``partial.py`` with an actual
projection of where a run will end up, which is what freeze-thaw Bayesian
optimisation uses to decide continue / stop / promote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Fixed, deterministic grid of decay rates to search.
_C_GRID = [0.02 * (1.25**i) for i in range(28)]  # ~0.02 .. ~9.3


@dataclass
class CurveFit:
    a: float  # asymptote = projected final value
    b: float
    c: float
    sse: float  # sum of squared errors of the fit
    n: int
    projected_final: float
    last_value: float
    trend: float  # signed: (projected_final - last_value), how much improvement remains

    @property
    def ok(self) -> bool:
        return self.n >= 3


def _fit_for_c(ts: list[float], ys: list[float], c: float) -> tuple[float, float, float]:
    """Closed-form least squares for y = a + b*exp(-c t) at fixed c."""
    n = len(ts)
    xs = [math.exp(-c * t) for t in ts]
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        a = sy / n
        b = 0.0
    else:
        b = (n * sxy - sx * sy) / denom
        a = (sy - b * sx) / n
    sse = sum((a + b * x - y) ** 2 for x, y in zip(xs, ys, strict=True))
    return a, b, sse


def fit_learning_curve(steps: list[float], values: list[float]) -> CurveFit:
    """Fit a saturating exponential and return the projected final value.

    With fewer than 3 points the projection falls back to the last value (no
    extrapolation), and ``ok`` is False.
    """
    pts = [(float(s), float(v)) for s, v in zip(steps, values, strict=True)]
    n = len(pts)
    last = pts[-1][1] if pts else 0.0
    if n < 3:
        return CurveFit(a=last, b=0.0, c=0.0, sse=0.0, n=n, projected_final=last,
                        last_value=last, trend=0.0)

    ts = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    best = None
    for c in _C_GRID:
        a, b, sse = _fit_for_c(ts, ys, c)
        if best is None or sse < best[2]:
            best = (a, b, sse, c)
    a, b, sse, c = best  # type: ignore[misc]

    # The asymptote a is the t->inf projection. Guard against a degenerate fit
    # (flat/!decaying) by falling back to the last observed value.
    projected = a if c > 0 and abs(b) > 1e-9 else last
    # Keep the projection within a sane band of the observed range so a wild
    # extrapolation never dominates a decision.
    lo = min(ys) - (max(ys) - min(ys) + 1e-6)
    hi = max(ys) + (max(ys) - min(ys) + 1e-6)
    projected = max(lo, min(hi, projected))

    return CurveFit(a=a, b=b, c=c, sse=sse, n=n, projected_final=projected,
                    last_value=last, trend=projected - last)

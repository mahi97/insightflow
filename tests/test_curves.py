"""Learning-curve extrapolation tests."""

from __future__ import annotations

import math

from insightflow.curves import fit_learning_curve


def _curve(a, b, c, n):
    steps = list(range(1, n + 1))
    values = [a + b * math.exp(-c * t) for t in steps]
    return steps, values


def test_recovers_asymptote_of_a_rising_curve():
    # Accuracy rising from ~0.5 toward 0.8 (a=0.8, b=-0.3).
    steps, values = _curve(0.8, -0.3, 0.5, 12)
    fit = fit_learning_curve(steps, values)
    assert fit.ok
    assert abs(fit.projected_final - 0.8) < 0.02
    assert fit.projected_final > values[-1]  # projects further improvement
    assert fit.trend > 0


def test_recovers_asymptote_of_a_falling_loss_curve():
    # Loss falling from ~1.5 toward 0.3 (a=0.3, b=1.2).
    steps, values = _curve(0.3, 1.2, 0.4, 12)
    fit = fit_learning_curve(steps, values)
    assert abs(fit.projected_final - 0.3) < 0.03
    assert fit.projected_final < values[-1]


def test_too_few_points_falls_back_to_last_value():
    fit = fit_learning_curve([1, 2], [0.5, 0.55])
    assert not fit.ok
    assert fit.projected_final == 0.55
    assert fit.trend == 0.0


def test_projection_is_bounded_near_observed_range():
    # A noisy near-flat curve should not project wildly outside the observed band.
    steps = list(range(1, 8))
    values = [0.70, 0.71, 0.70, 0.72, 0.71, 0.72, 0.71]
    fit = fit_learning_curve(steps, values)
    assert 0.68 <= fit.projected_final <= 0.74


def test_deterministic():
    steps, values = _curve(0.8, -0.3, 0.5, 10)
    assert fit_learning_curve(steps, values) == fit_learning_curve(steps, values)

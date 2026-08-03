#!/usr/bin/env python3
"""Integration tests for cumulative impact behavior of the Grid IPCC FMU."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

fmpy = pytest.importorskip("fmpy")
simulate_fmu = fmpy.simulate_fmu


ROOT = Path(__file__).resolve().parents[1]
GRID_FMU = ROOT / "fmu" / "Grid_Ipcc_v1.0.fmu"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def grid_fmu_path() -> Path:
    if not GRID_FMU.exists():
        pytest.skip(f"Required FMU not found: {GRID_FMU}")
    return GRID_FMU


def _simulate_grid(fmu_path: Path, input_signal: np.ndarray, stop_time: float = 3600.0):
    return simulate_fmu(
        filename=str(fmu_path),
        start_time=0.0,
        stop_time=stop_time,
        step_size=60.0,
        input=input_signal,
        output=["time", "u", "y"],
    )


def _series_value_at_or_after(time: np.ndarray, values: np.ndarray, t: float) -> float:
    idx = int(np.searchsorted(time, t, side="left"))
    if idx >= len(time):
        idx = len(time) - 1
    return float(values[idx])


def test_constant_power_is_monotonic_and_linear(grid_fmu_path: Path) -> None:
    input_signal = np.array(
        [(0.0, 100.0), (3600.0, 100.0)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    result = _simulate_grid(grid_fmu_path, input_signal)
    time = np.array(result["time"], dtype=np.float64)
    impact = np.array(result["y"], dtype=np.float64)

    diffs = np.diff(impact)
    assert np.all(diffs >= -1e-10), "Cumulative impact should not decrease"

    coeffs = np.polyfit(time, impact, 1)
    linear_fit = np.polyval(coeffs, time)
    ss_res = float(np.sum((impact - linear_fit) ** 2))
    ss_tot = float(np.sum((impact - np.mean(impact)) ** 2))
    r_squared = 1.0 if ss_tot == 0 else 1 - (ss_res / ss_tot)
    assert r_squared > 0.995, f"Expected near-linear growth, got R^2={r_squared:.6f}"


def test_step_power_changes_slope_proportionally(grid_fmu_path: Path) -> None:
    input_signal = np.array(
        [(0.0, 50.0), (1799.999, 50.0), (1800.0, 150.0), (3600.0, 150.0)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    result = _simulate_grid(grid_fmu_path, input_signal)
    time = np.array(result["time"], dtype=np.float64)
    impact = np.array(result["y"], dtype=np.float64)

    y0 = _series_value_at_or_after(time, impact, 0.0)
    y1 = _series_value_at_or_after(time, impact, 1800.0)
    y2 = _series_value_at_or_after(time, impact, 3600.0)

    slope1 = (y1 - y0) / 1800.0
    slope2 = (y2 - y1) / 1800.0

    assert slope1 > 0, "First phase slope should be positive"
    ratio = slope2 / slope1
    assert ratio == pytest.approx(3.0, rel=0.1), f"Expected slope ratio near 3.0, got {ratio:.3f}"


def test_zero_power_window_has_near_flat_growth(grid_fmu_path: Path) -> None:
    input_signal = np.array(
        [
            (0.0, 100.0),
            (1199.999, 100.0),
            (1200.0, 0.0),
            (2399.999, 0.0),
            (2400.0, 100.0),
            (3600.0, 100.0),
        ],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    result = _simulate_grid(grid_fmu_path, input_signal)
    time = np.array(result["time"], dtype=np.float64)
    impact = np.array(result["y"], dtype=np.float64)

    y_20m = _series_value_at_or_after(time, impact, 1200.0)
    y_40m = _series_value_at_or_after(time, impact, 2400.0)
    y_60m = _series_value_at_or_after(time, impact, 3600.0)
    y_0m = _series_value_at_or_after(time, impact, 0.0)

    delta_power_before = y_20m - y_0m
    delta_zero_window = y_40m - y_20m
    delta_power_after = y_60m - y_40m

    assert delta_power_before > 0
    assert delta_power_after > 0

    # This FMU can still show tiny residual growth at u=0. Require it to be
    # negligible relative to powered periods instead of exactly flat.
    zero_vs_before = abs(delta_zero_window) / abs(delta_power_before)
    zero_vs_after = abs(delta_zero_window) / abs(delta_power_after)

    assert zero_vs_before <= 0.01, (
        "Zero-power window growth should be <=1% of the powered window; "
        f"observed ratio={zero_vs_before:.6g}"
    )
    assert zero_vs_after <= 0.01, (
        "Zero-power window growth should be <=1% of the powered window; "
        f"observed ratio={zero_vs_after:.6g}"
    )

#!/usr/bin/env python3
"""Tests for reusable co-simulation helpers in scripts.run_fmu."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

pytest.importorskip("fmpy")

from scripts import run_fmu


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_FMU = ROOT / "fmu" / "PV_System_WECC.fmu"
LCA_FMU = ROOT / "fmu" / "PvWecc_Ipcc_v1.0.fmu"
PLOT_OUT = ROOT / "results" / "test_cosimulation.png"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def cosim_fmu_paths() -> tuple[Path, Path]:
    if not SYSTEM_FMU.exists():
        pytest.skip(f"Required system FMU not found: {SYSTEM_FMU}")
    if not LCA_FMU.exists():
        pytest.skip(f"Required LCA FMU not found: {LCA_FMU}")
    return SYSTEM_FMU, LCA_FMU


def test_sequential_cosim_real_fmus_1day(cosim_fmu_paths: tuple[Path, Path]) -> None:
    system_fmu, lca_fmu = cosim_fmu_paths

    one_day_s = 24.0 * 3600.0
    try:
        system_res, lca_res = run_fmu.sequential_cosim(
            system_fmu=system_fmu,
            lca_fmu=lca_fmu,
            start_s=0.0,
            stop_s=one_day_s,
            system_output="gri.P.real",
            lca_input="u",
            lca_output="y",
            parameter_name="n_pv",
            parameter_value=1.0,
            output_interval_s=900.0,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "cannot be simulated on the current platform" in msg:
            pytest.skip(f"Skipping cosimulation integration test due to FMU platform mismatch: {exc}")
        raise

    assert list(system_res.dtype.names) == ["time", "gri.P.real"]
    assert list(lca_res.dtype.names) == ["time", "u", "y"]
    assert len(system_res) > 2
    assert len(lca_res) > 2

    time_s = np.array(lca_res["time"], dtype=np.float64)
    power_u = np.array(lca_res["u"], dtype=np.float64)
    impact_y = np.array(lca_res["y"], dtype=np.float64)

    assert np.all(np.isfinite(time_s))
    assert np.all(np.isfinite(power_u))
    assert np.all(np.isfinite(impact_y))
    assert np.all(np.diff(time_s) >= 0.0)

    energy_mwh = float(getattr(np, "trapezoid", np.trapz)(power_u, time_s) / 3.6e9)
    print("1-day co-simulation verification")
    print(f"System FMU: {system_fmu}")
    print(f"LCA FMU: {lca_fmu}")
    print(f"Samples: {len(lca_res)}")
    print(f"Final cumulative y: {impact_y[-1]:.6f}")
    print(f"Integrated energy from u: {energy_mwh:.6f} MWh")

    PLOT_OUT.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    time_h = time_s / 3600.0

    ax1.plot(time_h, power_u, color="tab:blue", linewidth=1.8)
    ax1.set_ylabel("u (W)")
    ax1.set_title("1-Day Sequential Co-Simulation")
    ax1.grid(True, alpha=0.25)

    ax2.plot(time_h, impact_y, color="tab:green", linewidth=1.8)
    ax2.set_xlabel("Time (hours)")
    ax2.set_ylabel("y")
    ax2.grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(PLOT_OUT, dpi=150)
    plt.close(fig)
    print(f"Saved verification plot: {PLOT_OUT}")

    assert PLOT_OUT.exists()


def test_parse_key_value_pairs_parses_multiple_entries() -> None:
    parsed = run_fmu._parse_key_value_pairs(
        ["n_pv=2", "loss_factor=0.125"],
        "--system-start-value",
    )
    assert parsed == {"n_pv": 2.0, "loss_factor": 0.125}


def test_parse_key_value_pairs_rejects_invalid_format() -> None:
    with pytest.raises(ValueError, match="key=value"):
        run_fmu._parse_key_value_pairs(["invalid"], "--lca-start-value")


def test_sequential_cosim_requires_parameter_value_with_parameter_name(
    cosim_fmu_paths: tuple[Path, Path],
) -> None:
    system_fmu, lca_fmu = cosim_fmu_paths

    with pytest.raises(ValueError, match="parameter_value is required"):
        run_fmu.sequential_cosim(
            system_fmu=system_fmu,
            lca_fmu=lca_fmu,
            start_s=0.0,
            stop_s=1.0,
            parameter_name="n_pv",
        )

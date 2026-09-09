#!/usr/bin/env python3
"""Parity test: native Brightway result should match FMU output for example IPCC."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fmpy import simulate_fmu

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from reference_parser import parse_reference_file


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lca_engine import run_lca_energy  # noqa: E402


REFERENCE_FILE = ROOT / "tests" / "reference_results" / "example_ipcc_native_vs_fmu.txt"
FMU_NATIVE_REL_TOL = 0.2


def _should_skip_for_missing_ecoinvent(error_text: str) -> bool:
    text = error_text.lower()
    return (
        "no brightway project found" in text
        or "ecoinvent" in text
        or "database" in text and "not found" in text
    )


def _extract_first_total_score(results: dict) -> float:
    """Extract first total_score from run_lca_energy output."""
    if "error" in results:
        err = str(results["error"])
        if _should_skip_for_missing_ecoinvent(err):
            pytest.skip(
                "Skipping ecoinvent parity test: required private Brightway/ecoinvent "
                f"database is not available in this environment ({err})."
            )
        raise AssertionError(f"run_lca_energy failed: {err}")

    impact_results = results.get("impact_results", {})
    for data in impact_results.values():
        if isinstance(data, dict) and "total_score" in data:
            return float(data["total_score"])

    raise AssertionError("No total_score found in impact_results")


def _build_example_fmu() -> Path:
    """Build Example IPCC FMU using current project code."""
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "create_fmu.py"),
        "example",
        "--method",
        "ipcc",
        "--blackbox-policy",
        "off",
    ]
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise AssertionError(
            "FMU build failed for example/ipcc.\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
        )

    fmu_path = ROOT / "fmu" / "Example_Ipcc_v0.0.1.fmu"
    if not fmu_path.exists():
        raise AssertionError(f"Expected FMU was not created: {fmu_path}")
    return fmu_path


@pytest.mark.ecoinvent
def test_example_native_matches_fmu_reference() -> None:
    """Validate native and FMU paths against a shared text reference baseline."""
    ref = parse_reference_file(REFERENCE_FILE)

    inventory = ROOT / str(ref["inventory"])
    method_keyword = str(ref["method_keyword"])
    baseline_energy_mj = float(ref["baseline_energy_mj"])
    start_time = float(ref["simulation_start_s"])
    stop_time = float(ref["simulation_stop_s"])
    step_size = float(ref["simulation_step_s"])
    abs_tol = float(ref["abs_tolerance"])
    rel_tol = float(ref["rel_tolerance"])

    native_results = run_lca_energy(
        lci_file=str(inventory),
        lcia_methods=[method_keyword],
        functional_unit={},
        energy_amount_mj=baseline_energy_mj,
    )
    native_total = _extract_first_total_score(native_results)

    fmu_path = _build_example_fmu()
    duration_s = stop_time - start_time
    if duration_s <= 0:
        raise AssertionError("Reference config must have simulation_stop_s > simulation_start_s")

    # 1 MW == 1 MJ/s, so this power profile delivers baseline_energy_mj over duration_s.
    power_mw = baseline_energy_mj / duration_s
    input_signal = np.array(
        [(start_time, power_mw), (stop_time, power_mw)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    sim = simulate_fmu(
        filename=str(fmu_path),
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        input=input_signal,
        output=["time", "y"],
    )
    fmu_total = float(sim["y"][-1])

    assert native_total > 0.0
    assert fmu_total > 0.0
    assert fmu_total == pytest.approx(native_total, rel=FMU_NATIVE_REL_TOL, abs=abs_tol), (
        "FMU and native totals diverged more than expected for the example IPCC case. "
        f"native={native_total:.6f}, fmu={fmu_total:.6f}, rel_tol={FMU_NATIVE_REL_TOL}"
    )
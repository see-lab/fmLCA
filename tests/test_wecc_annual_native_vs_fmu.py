#!/usr/bin/env python3
"""Parity test: WECC annual native Brightway result should match FMU output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fmpy import simulate_fmu

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lca_engine import run_lca_energy  # noqa: E402


INVENTORY = ROOT / "data" / "inventory" / "wecc-static.json"
METHOD = "IPCC 2021 climate change total excl biogenic GWP100"
YEAR_SECONDS = 365.0 * 24.0 * 3600.0
STEP_SECONDS = 3600.0
ABS_TOL = 1e-3
REL_TOL = 1e-6


def _should_skip_for_missing_ecoinvent(error_text: str) -> bool:
    text = error_text.lower()
    return (
        "no brightway project found" in text
        or "ecoinvent" in text
        or "database" in text and "not found" in text
    )


def _extract_first_total_score(results: dict) -> float:
    if "error" in results:
        err = str(results["error"])
        if _should_skip_for_missing_ecoinvent(err):
            pytest.skip(
                "Skipping WECC annual parity test: required private Brightway/ecoinvent "
                f"database is not available in this environment ({err})."
            )
        raise AssertionError(f"run_lca_energy failed: {err}")

    impact_results = results.get("impact_results", {})
    for data in impact_results.values():
        if isinstance(data, dict) and "total_score" in data:
            return float(data["total_score"])

    raise AssertionError("No total_score found in impact_results")


def _build_wecc_fmu() -> Path:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "create_fmu.py"),
        "wecc-static",
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
            "FMU build failed for wecc-static/ipcc.\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
        )

    default_path = ROOT / "fmu" / "Wecc-static_Ipcc_v1.0.fmu"
    if default_path.exists():
        return default_path

    candidates = sorted((ROOT / "fmu").glob("*wecc*Ipcc*.fmu")) + sorted(
        (ROOT / "fmu").glob("*Wecc*Ipcc*.fmu")
    )
    if not candidates:
        raise AssertionError("Expected WECC FMU was not created in fmu/")
    return candidates[-1]


@pytest.mark.ecoinvent
def test_wecc_annual_native_matches_fmu() -> None:
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    baseline_energy_mj = float(data["energy_metadata"]["primary_input"]["value"])

    native_results = run_lca_energy(
        lci_file=str(INVENTORY),
        lcia_methods=[METHOD],
        functional_unit={},
        energy_amount_mj=baseline_energy_mj,
    )
    native_total = _extract_first_total_score(native_results)

    fmu_path = _build_wecc_fmu()

    # 1 MW == 1 MJ/s, so this power profile delivers baseline_energy_mj over one year.
    power_mw = baseline_energy_mj / YEAR_SECONDS
    input_signal = np.array(
        [(0.0, power_mw), (YEAR_SECONDS, power_mw)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    sim = simulate_fmu(
        filename=str(fmu_path),
        start_time=0.0,
        stop_time=YEAR_SECONDS,
        step_size=STEP_SECONDS,
        input=input_signal,
        output=["time", "y"],
    )
    fmu_total = float(sim["y"][-1])

    assert fmu_total == pytest.approx(native_total, rel=REL_TOL, abs=ABS_TOL)

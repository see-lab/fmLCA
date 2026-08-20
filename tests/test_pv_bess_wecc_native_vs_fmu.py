#!/usr/bin/env python3
"""Integration parity test: pv_bess_wecc FMU vs native parameterized LCA."""

from __future__ import annotations

import argparse
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

from lca_engine import run_lca  # noqa: E402


INVENTORY = ROOT / "data" / "inventory" / "pv_bess_wecc_312.json"
METHOD = "IPCC 2021 climate change total excl biogenic GWP100"
FMU_NAME = "PvBessWecc312_ParityTest"
START_TIME = 0.0
STOP_TIME = 3600.0
STEP_SIZE = 60.0
REL_TOL = 2e-2
ABS_TOL = 1e-3

PARAMETER_CASES = [
    {"n_pv": 1.0, "n_bess": 1.0},
    {"n_pv": 2.0, "n_bess": 1.0},
    {"n_pv": 1.0, "n_bess": 2.0},
    {"n_pv": 3.0, "n_bess": 2.0},
]
SMOKE_CASE = {"n_pv": 2.0, "n_bess": 1.0}


def _to_mj(value: float, unit: str) -> float:
    factors = {
        "mj": 1.0,
        "kj": 0.001,
        "gj": 1000.0,
        "tj": 1_000_000.0,
        "kwh": 3.6,
        "mwh": 3600.0,
        "wh": 0.0036,
    }
    factor = factors.get(unit.strip().lower())
    if factor is None:
        raise AssertionError(f"Unsupported energy unit in inventory metadata: {unit}")
    return value * factor


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
                "Skipping pv_bess_wecc parity test: required private Brightway/ecoinvent "
                f"database is not available in this environment ({err})."
            )
        raise AssertionError(f"run_lca failed: {err}")

    impact_results = results.get("impact_results", {})
    for data in impact_results.values():
        if isinstance(data, dict) and "total_score" in data:
            return float(data["total_score"])

    raise AssertionError("No total_score found in impact_results")


def _build_pv_bess_wecc_fmu() -> Path:
    fmu_path = ROOT / "fmu" / f"{FMU_NAME}.fmu"
    if fmu_path.exists():
        return fmu_path

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "create_fmu.py"),
        "pv_bess_wecc_312",
        "--method",
        "ipcc",
        "--name",
        FMU_NAME,
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
        merged = f"{completed.stdout}\n{completed.stderr}"
        if _should_skip_for_missing_ecoinvent(merged):
            pytest.skip(
                "Skipping pv_bess_wecc parity test: FMU build requires private "
                f"Brightway/ecoinvent database ({merged.strip()[:300]}...)."
            )
        raise AssertionError(
            "FMU build failed for pv_bess_wecc_312/ipcc.\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
        )

    if not fmu_path.exists():
        raise AssertionError(f"Expected FMU was not created: {fmu_path}")
    return fmu_path


def _prepare_run_context() -> tuple[float, np.ndarray, Path]:
    if not INVENTORY.exists():
        pytest.skip(f"Inventory not found: {INVENTORY}")

    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    primary = data["energy_metadata"]["primary_input"]
    baseline_energy_mj = _to_mj(float(primary["value"]), str(primary.get("unit", "MJ")))

    duration_s = STOP_TIME - START_TIME
    power_w = (baseline_energy_mj / duration_s) * 1_000_000.0
    input_signal = np.array(
        [(START_TIME, power_w), (STOP_TIME, power_w)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )
    fmu_path = _build_pv_bess_wecc_fmu()
    return baseline_energy_mj, input_signal, fmu_path


def _compare_case(
    params: dict[str, float],
    baseline_energy_mj: float,
    input_signal: np.ndarray,
    fmu_path: Path,
) -> tuple[float, float, float]:
    native_results = run_lca(
        lci_file=str(INVENTORY),
        lcia_methods=[METHOD],
        parameter_values=params,
        functional_unit={},
        energy_amount_mj=baseline_energy_mj,
    )
    native_total = _extract_first_total_score(native_results)

    sim = simulate_fmu(
        filename=str(fmu_path),
        start_time=START_TIME,
        stop_time=STOP_TIME,
        step_size=STEP_SIZE,
        input=input_signal,
        start_values=params,
        output=["time", "y"],
    )
    fmu_total = float(sim["y"][-1])
    rel_err = abs(fmu_total - native_total) / max(abs(native_total), 1e-12)
    return native_total, fmu_total, rel_err


def _run_parity_cases(cases: list[dict[str, float]], label: str) -> list[tuple[dict[str, float], float, float, float]]:
    baseline_energy_mj, input_signal, fmu_path = _prepare_run_context()
    case_rows: list[tuple[dict[str, float], float, float, float]] = []

    for params in cases:
        native_total, fmu_total, rel_err = _compare_case(
            params,
            baseline_energy_mj,
            input_signal,
            fmu_path,
        )
        case_rows.append((params, native_total, fmu_total, rel_err))

        assert fmu_total == pytest.approx(native_total, rel=REL_TOL, abs=ABS_TOL), (
            f"{label} parity failed for parameter case "
            f"{params}. native={native_total:.6f}, fmu={fmu_total:.6f}, rel_err={rel_err:.6e}, "
            f"rel_tol={REL_TOL}, abs_tol={ABS_TOL}"
        )

    return case_rows


@pytest.mark.integration
@pytest.mark.ecoinvent
def test_pv_bess_wecc_smoke_native_matches_fmu() -> None:
    """Fast smoke check using one representative parameter setting."""
    _run_parity_cases([SMOKE_CASE], label="Smoke")


@pytest.mark.integration
@pytest.mark.ecoinvent
def test_pv_bess_wecc_parameterized_native_matches_fmu() -> None:
    case_rows = _run_parity_cases(PARAMETER_CASES, label="Full")

    max_row = max(case_rows, key=lambda r: r[3])
    print(
        "\nPV+BESS+WECC parity summary: max rel error "
        f"{max_row[3]:.6e} at params={max_row[0]} "
        f"(native={max_row[1]:.6f}, fmu={max_row[2]:.6f})"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pv_bess_wecc FMU vs native LCA parity checks without pytest."
    )
    parser.add_argument(
        "--mode",
        choices=["smoke", "full", "both"],
        default="smoke",
        help="Which parity suite to run (default: smoke).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.mode in ("smoke", "both"):
            smoke_rows = _run_parity_cases([SMOKE_CASE], label="Smoke")
            row = smoke_rows[0]
            print(
                "✅ Smoke parity passed "
                f"for params={row[0]} (native={row[1]:.6f}, fmu={row[2]:.6f}, rel_err={row[3]:.6e})"
            )

        if args.mode in ("full", "both"):
            full_rows = _run_parity_cases(PARAMETER_CASES, label="Full")
            max_row = max(full_rows, key=lambda r: r[3])
            print(
                "✅ Full parity passed: max rel error "
                f"{max_row[3]:.6e} at params={max_row[0]} "
                f"(native={max_row[1]:.6f}, fmu={max_row[2]:.6f})"
            )

        return 0
    except pytest.skip.Exception as exc:
        print(f"⚠️  Skipped: {exc}")
        return 0
    except Exception as exc:
        print(f"❌ Parity run failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

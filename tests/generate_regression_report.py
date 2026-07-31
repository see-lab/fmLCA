#!/usr/bin/env python3
"""Generate Modelica-style regression summary tables and difference plots.

This script compares simulated outputs against text reference baselines and writes:
- HTML summary with green/orange/red status rows
- PNG plots showing reference vs simulated traces and difference curves

Usage:
    python tests/generate_regression_report.py
    python tests/generate_regression_report.py --skip-rebuild-fmu
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from fmpy import simulate_fmu

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lca_engine import run_lca_energy  # noqa: E402
from reference_parser import parse_reference_file  # noqa: E402


REFERENCE_DIR = ROOT / "tests" / "reference_results"
REPORT_DIR = ROOT / "tests" / "reports"
PLOT_DIR = REPORT_DIR / "plots"

PROFILE_REF_FILE = REFERENCE_DIR / "example_fmu_profiles.txt"
NATIVE_REF_FILE = REFERENCE_DIR / "example_ipcc_native_vs_fmu.txt"
FMU_PATH = ROOT / "fmu" / "Example_Ipcc_v1.0.fmu"


@dataclass
class StatusRow:
    name: str
    ref_file: str
    metric: str
    reference_value: float
    simulated_value: float
    abs_diff: float
    rel_diff: float
    abs_tol: float
    rel_tol: float
    status: str


def _status_from_diff(abs_diff: float, rel_diff: float, abs_tol: float, rel_tol: float) -> str:
    if abs_diff <= abs_tol and rel_diff <= rel_tol:
        return "green"
    if abs_diff <= abs_tol * 10 and rel_diff <= rel_tol * 10:
        return "orange"
    return "red"


def _simulate(profile: np.ndarray) -> np.ndarray:
    return simulate_fmu(
        filename=str(FMU_PATH),
        start_time=0.0,
        stop_time=3600.0,
        step_size=60.0,
        input=profile,
        output=["time", "y"],
    )


def _build_example_fmu() -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "create_fmu.py"),
        "example",
        "--method",
        "ipcc",
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
        raise RuntimeError(
            "Failed to build Example FMU for report.\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
        )


def _profile_constant(value: float) -> np.ndarray:
    return np.array(
        [(0.0, value), (3600.0, value)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )


def _profile_step_50_150() -> np.ndarray:
    return np.array(
        [(0.0, 50.0), (1799.999, 50.0), (1800.0, 150.0), (3600.0, 150.0)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )


def _profile_zero_middle() -> np.ndarray:
    return np.array(
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


def _sample_at_times(sim: np.ndarray, times: list[float]) -> list[float]:
    return [float(sim["y"][int(t / 60.0)]) for t in times]


def _collect_profile_rows_and_plots() -> tuple[list[StatusRow], list[str]]:
    ref = parse_reference_file(PROFILE_REF_FILE)
    abs_tol = float(ref["abs_tolerance"])
    rel_tol = float(ref["rel_tolerance"])
    times = [float(x) for x in ref["time_s"]]

    cases: list[tuple[str, np.ndarray, list[float]]] = [
        ("case.constant_100_mw", _profile_constant(100.0), [float(v) for v in ref["case.constant_100_mw.y"]]),
        ("case.step_50_150_mw", _profile_step_50_150(), [float(v) for v in ref["case.step_50_150_mw.y"]]),
        ("case.zero_middle", _profile_zero_middle(), [float(v) for v in ref["case.zero_middle.y"]]),
    ]

    rows: list[StatusRow] = []
    plot_paths: list[str] = []

    for case_name, profile, reference_series in cases:
        sim = _simulate(profile)
        sim_series = _sample_at_times(sim, times)
        diffs = [abs(a - b) for a, b in zip(sim_series, reference_series)]

        max_abs = max(diffs)
        ref_scale = max(abs(v) for v in reference_series) if reference_series else 1.0
        max_rel = max_abs / ref_scale if ref_scale else 0.0
        status = _status_from_diff(max_abs, max_rel, abs_tol, rel_tol)

        rows.append(
            StatusRow(
                name=case_name,
                ref_file=PROFILE_REF_FILE.name,
                metric="max(y_diff)",
                reference_value=max(reference_series),
                simulated_value=max(sim_series),
                abs_diff=max_abs,
                rel_diff=max_rel,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
                status=status,
            )
        )

        # Plot reference vs simulated and signed difference.
        fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
        axes[0].plot(times, reference_series, "o-", label="reference", linewidth=1.8)
        axes[0].plot(times, sim_series, "x--", label="simulated", linewidth=1.6)
        axes[0].set_ylabel("y")
        axes[0].set_title(f"{case_name}: simulated vs reference")
        axes[0].grid(True, alpha=0.3)
        axes[0].legend()

        signed = [s - r for s, r in zip(sim_series, reference_series)]
        axes[1].axhline(0.0, color="black", linewidth=1.0)
        axes[1].plot(times, signed, "o-", color="tab:red")
        axes[1].set_xlabel("time [s]")
        axes[1].set_ylabel("sim-ref")
        axes[1].grid(True, alpha=0.3)

        fig.tight_layout()
        out_png = PLOT_DIR / f"{case_name}_diff.png"
        fig.savefig(out_png, dpi=160)
        plt.close(fig)
        plot_paths.append(str(out_png.relative_to(REPORT_DIR)).replace("\\", "/"))

    return rows, plot_paths


def _collect_native_vs_fmu_rows_and_plot() -> tuple[list[StatusRow], str]:
    ref = parse_reference_file(NATIVE_REF_FILE)

    inventory = ROOT / str(ref["inventory"])
    method_keyword = str(ref["method_keyword"])
    baseline_energy_mj = float(ref["baseline_energy_mj"])
    start_time = float(ref["simulation_start_s"])
    stop_time = float(ref["simulation_stop_s"])
    step_size = float(ref["simulation_step_s"])
    expected_total = float(ref["expected_total_score_kg_co2_eq"])
    abs_tol = float(ref["abs_tolerance"])
    rel_tol = float(ref["rel_tolerance"])

    native_results = run_lca_energy(
        lci_file=str(inventory),
        lcia_methods=[method_keyword],
        functional_unit={},
        energy_amount_mj=baseline_energy_mj,
    )

    if "error" in native_results:
        raise RuntimeError(f"run_lca_energy failed: {native_results['error']}")

    native_total = None
    for data in native_results.get("impact_results", {}).values():
        if isinstance(data, dict) and "total_score" in data:
            native_total = float(data["total_score"])
            break
    if native_total is None:
        raise RuntimeError("Could not extract native total score")

    duration_s = stop_time - start_time
    power_mw = baseline_energy_mj / duration_s
    input_signal = np.array(
        [(start_time, power_mw), (stop_time, power_mw)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    sim = simulate_fmu(
        filename=str(FMU_PATH),
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        input=input_signal,
        output=["time", "y"],
    )
    fmu_total = float(sim["y"][-1])

    rows: list[StatusRow] = []
    for name, value in (("native_total", native_total), ("fmu_total", fmu_total)):
        abs_diff = abs(value - expected_total)
        rel_diff = abs_diff / abs(expected_total) if expected_total else 0.0
        rows.append(
            StatusRow(
                name=name,
                ref_file=NATIVE_REF_FILE.name,
                metric="total_score",
                reference_value=expected_total,
                simulated_value=value,
                abs_diff=abs_diff,
                rel_diff=rel_diff,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
                status=_status_from_diff(abs_diff, rel_diff, abs_tol, rel_tol),
            )
        )

    # Native/FMU parity row.
    abs_diff_pair = abs(native_total - fmu_total)
    rel_diff_pair = abs_diff_pair / abs(native_total) if native_total else 0.0
    rows.append(
        StatusRow(
            name="native_vs_fmu",
            ref_file=NATIVE_REF_FILE.name,
            metric="pair_diff",
            reference_value=native_total,
            simulated_value=fmu_total,
            abs_diff=abs_diff_pair,
            rel_diff=rel_diff_pair,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
            status=_status_from_diff(abs_diff_pair, rel_diff_pair, abs_tol, rel_tol),
        )
    )

    fig, ax = plt.subplots(figsize=(8, 4.8))
    labels = ["reference", "native", "fmu"]
    values = [expected_total, native_total, fmu_total]
    ax.bar(labels, values, color=["#777777", "#1f77b4", "#2ca02c"])
    ax.set_ylabel("kg CO2-eq")
    ax.set_title("Example IPCC: reference vs native vs FMU")
    ax.grid(True, axis="y", alpha=0.3)
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.6f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()

    out_png = PLOT_DIR / "native_vs_fmu_diff.png"
    fig.savefig(out_png, dpi=160)
    plt.close(fig)

    return rows, str(out_png.relative_to(REPORT_DIR)).replace("\\", "/")


def _status_color(status: str) -> str:
    if status == "green":
        return "#d8f5d0"
    if status == "orange":
        return "#ffe5bf"
    return "#ffd2d2"


def _render_summary(rows: Iterable[StatusRow], plots: list[str]) -> str:
    rows_html = []
    for row in rows:
        rows_html.append(
            "<tr style='background:{}'>".format(_status_color(row.status))
            + f"<td>{row.name}</td>"
            + f"<td>{row.ref_file}</td>"
            + f"<td>{row.metric}</td>"
            + f"<td>{row.reference_value:.10g}</td>"
            + f"<td>{row.simulated_value:.10g}</td>"
            + f"<td>{row.abs_diff:.3e}</td>"
            + f"<td>{row.rel_diff:.3e}</td>"
            + f"<td>{row.abs_tol:.3e}</td>"
            + f"<td>{row.rel_tol:.3e}</td>"
            + f"<td>{row.status}</td>"
            + "</tr>"
        )

    plot_html = "\n".join(
        f"<div><img src='{p}' style='max-width:100%; border:1px solid #ddd;'/><p>{p}</p></div>"
        for p in plots
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>Regression Summary</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #cccccc; padding: 6px 8px; font-size: 13px; }}
    th {{ background: #f3f3f3; text-align: left; }}
    .legend {{ display: flex; gap: 12px; margin: 10px 0 18px 0; }}
    .badge {{ padding: 4px 10px; border: 1px solid #bbb; border-radius: 4px; font-size: 12px; }}
    .green {{ background: #d8f5d0; }}
    .orange {{ background: #ffe5bf; }}
    .red {{ background: #ffd2d2; }}
  </style>
</head>
<body>
  <h1>Regression Summary</h1>
  <p>Generated: {date.today().isoformat()}</p>

  <div class='legend'>
    <span class='badge green'>green: pass</span>
    <span class='badge orange'>orange: warning (within 10x tolerance)</span>
    <span class='badge red'>red: fail</span>
  </div>

  <table>
    <thead>
      <tr>
        <th>Case</th>
        <th>Reference File</th>
        <th>Metric</th>
        <th>Reference</th>
        <th>Simulated</th>
        <th>Abs Diff</th>
        <th>Rel Diff</th>
        <th>Abs Tol</th>
        <th>Rel Tol</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>

  <h2>Difference Plots</h2>
  {plot_html}
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate regression status summary and difference plots.")
    parser.add_argument("--skip-rebuild-fmu", action="store_true", help="Use existing FMU without rebuilding")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_rebuild_fmu:
        _build_example_fmu()

    if not FMU_PATH.exists():
        raise FileNotFoundError(f"FMU not found: {FMU_PATH}")

    profile_rows, profile_plots = _collect_profile_rows_and_plots()
    native_rows, native_plot = _collect_native_vs_fmu_rows_and_plot()

    all_rows = profile_rows + native_rows
    all_plots = profile_plots + [native_plot]

    html = _render_summary(all_rows, all_plots)
    out_file = REPORT_DIR / "regression_summary.html"
    out_file.write_text(html, encoding="utf-8")

    print(f"Wrote summary: {out_file}")
    for plot in all_plots:
        print(f"Wrote plot: {REPORT_DIR / plot}")

    has_red = any(r.status == "red" for r in all_rows)
    return 1 if has_red else 0


if __name__ == "__main__":
    raise SystemExit(main())

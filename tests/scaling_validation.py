#!/usr/bin/env python3
"""Scaling validation for PvBessWecc312 FMU vs native Brightway evaluation.

Computes accuracy and runtime over a parameter grid, with sweep values formed
from two ranges per parameter:
    - 0 to 1 (inclusive)
    - 1 to 10 (inclusive)

Outputs:
- One combined figure with two side-by-side subplots:
    - Accuracy scatter (native on x-axis, FMU on y-axis)
    - Log-log computational performance vs parameter value
- CSV data suitable for reuse to bypass repeated LCA calculations
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from fmpy import simulate_fmu
from matplotlib.colors import to_rgba
from matplotlib.ticker import FixedLocator, SymmetricalLogLocator

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lca_engine import run_lca  # noqa: E402


DEFAULT_INVENTORY = ROOT / "data" / "inventory" / "pv_wecc_bess.json"
DEFAULT_FMU = ROOT / "fmu" / "PvBessWecc312_Ipcc_v1.0.fmu"
DEFAULT_METHOD = "IPCC 2021 climate change total excl biogenic GWP100"

DEFAULT_LOW_POINTS = 6
DEFAULT_HIGH_POINTS = 6

START_TIME = 0.0
STOP_TIME = 3600.0
STEP_SIZE = 60.0

DEFAULT_RESULTS_CSV = ROOT / "results" / "scaling_validation_results.csv"
DEFAULT_PLOT_PNG = ROOT / "results" / "scaling_validation.png"
DEFAULT_PLOT_SVG = ROOT / "results" / "scaling_validation.svg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate FMU scaling accuracy and runtime against native LCA."
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--fmu", type=Path, default=DEFAULT_FMU)
    parser.add_argument("--method", type=str, default=DEFAULT_METHOD)
    parser.add_argument(
        "--single-case",
        action="store_true",
        help="Run only one case defined by --n-pv and --n-bess (default full grid).",
    )
    parser.add_argument("--n-pv", type=float, default=1.0, help="n_pv for --single-case")
    parser.add_argument("--n-bess", type=float, default=1.0, help="n_bess for --single-case")
    parser.add_argument(
        "--low-points",
        type=int,
        default=DEFAULT_LOW_POINTS,
        help="Number of sweep points in [0,1] for each parameter (recommended 5-10).",
    )
    parser.add_argument(
        "--high-points",
        type=int,
        default=DEFAULT_HIGH_POINTS,
        help="Number of sweep points in [1,10] for each parameter (recommended 5-10).",
    )
    parser.add_argument(
        "--reuse-csv",
        dest="reuse_csv",
        action="store_true",
        help="Reuse --out-csv when it contains all requested parameter cases.",
    )
    parser.add_argument(
        "--no-reuse-csv",
        dest="reuse_csv",
        action="store_false",
        help="Ignore cached CSV and recompute all requested parameter cases.",
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Use only rows from --out-csv and never run native/FMU calculations.",
    )
    parser.set_defaults(reuse_csv=True)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_RESULTS_CSV)
    parser.add_argument("--plot-png", type=Path, default=DEFAULT_PLOT_PNG)
    parser.add_argument("--plot-svg", type=Path, default=DEFAULT_PLOT_SVG)
    return parser.parse_args()


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
        raise ValueError(f"Unsupported energy unit in inventory metadata: {unit}")
    return value * factor


def _load_energy_mj(inventory_path: Path) -> float:
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    primary = data["energy_metadata"]["primary_input"]
    return _to_mj(float(primary["value"]), str(primary.get("unit", "MJ")))


def _extract_total_score(results: dict[str, Any]) -> float:
    if "error" in results:
        raise RuntimeError(f"Native LCA failed: {results['error']}")

    impact_results = results.get("impact_results", {})
    for data in impact_results.values():
        if isinstance(data, dict) and "total_score" in data:
            return float(data["total_score"])

    raise RuntimeError("No total_score found in native LCA impact_results")


def _build_input_signal(energy_mj: float) -> np.ndarray:
    duration_s = STOP_TIME - START_TIME
    power_w = (energy_mj / duration_s) * 1_000_000.0
    return np.array(
        [(START_TIME, power_w), (STOP_TIME, power_w)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )


def evaluate_case(
    inventory_path: Path,
    method: str,
    fmu_path: Path,
    energy_mj: float,
    input_signal: np.ndarray,
    n_pv: float,
    n_bess: float,
) -> dict[str, float]:
    params = {"n_pv": n_pv, "n_bess": n_bess}

    t0 = time.perf_counter()
    native_results = run_lca(
        lci_file=str(inventory_path),
        lcia_methods=[method],
        parameter_values=params,
        functional_unit={},
        energy_amount_mj=energy_mj,
    )
    native_time_s = time.perf_counter() - t0
    native_total = _extract_total_score(native_results)

    t1 = time.perf_counter()
    sim = simulate_fmu(
        filename=str(fmu_path),
        start_time=START_TIME,
        stop_time=STOP_TIME,
        step_size=STEP_SIZE,
        input=input_signal,
        start_values=params,
        output=["y"],
    )
    fmu_time_s = time.perf_counter() - t1
    fmu_total = float(sim["y"][-1])

    abs_err = abs(fmu_total - native_total)
    rel_err = abs_err / max(abs(native_total), 1e-12)

    return {
        "n_pv": n_pv,
        "n_bess": n_bess,
        "native_total": native_total,
        "fmu_total": fmu_total,
        "abs_error": abs_err,
        "rel_error": rel_err,
        "native_time_s": native_time_s,
        "fmu_time_s": fmu_time_s,
    }


def write_csv(rows: list[dict[str, float]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "n_pv",
        "n_bess",
        "native_total",
        "fmu_total",
        "abs_error",
        "rel_error",
        "native_time_s",
        "fmu_time_s",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(in_csv: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with in_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "n_pv": float(row["n_pv"]),
                    "n_bess": float(row["n_bess"]),
                    "native_total": float(row["native_total"]),
                    "fmu_total": float(row["fmu_total"]),
                    "abs_error": float(row["abs_error"]),
                    "rel_error": float(row["rel_error"]),
                    "native_time_s": float(row["native_time_s"]),
                    "fmu_time_s": float(row["fmu_time_s"]),
                }
            )
    return rows


def build_sweep_values(low_points: int, high_points: int) -> list[float]:
    if low_points < 2 or high_points < 2:
        raise ValueError("low_points and high_points must each be >= 2")

    low = np.linspace(0.0, 1.0, num=low_points)
    high = np.linspace(1.0, 10.0, num=high_points)

    values: list[float] = []
    for val in np.concatenate([low, high]):
        rounded = float(np.round(val, 10))
        if rounded not in values:
            values.append(rounded)
    return values


def _case_key(n_pv: float, n_bess: float) -> tuple[float, float]:
    return (float(np.round(n_pv, 10)), float(np.round(n_bess, 10)))


def select_cached_rows(rows: list[dict[str, float]], cases: list[tuple[float, float]]) -> list[dict[str, float]]:
    lookup = {_case_key(r["n_pv"], r["n_bess"]): r for r in rows}
    selected: list[dict[str, float]] = []
    for n_pv, n_bess in cases:
        row = lookup.get(_case_key(n_pv, n_bess))
        if row is None:
            return []
        selected.append(row)
    return selected


def _mean_by_key(rows: list[dict[str, float]], key: str, time_key: str) -> tuple[np.ndarray, np.ndarray]:
    buckets: dict[float, list[float]] = {}
    for row in rows:
        k = float(row[key])
        buckets.setdefault(k, []).append(float(row[time_key]))

    xs = np.array(sorted(buckets.keys()), dtype=float)
    ys = np.array([float(np.mean(buckets[x])) for x in xs], dtype=float)
    return xs, ys


def plot_overview(rows: list[dict[str, float]], out_png: Path, out_svg: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_svg.parent.mkdir(parents=True, exist_ok=True)

    npv_x, npv_native = _mean_by_key(rows, "n_pv", "native_time_s")
    _, npv_fmu = _mean_by_key(rows, "n_pv", "fmu_time_s")

    nbess_x, nbess_native = _mean_by_key(rows, "n_bess", "native_time_s")
    _, nbess_fmu = _mean_by_key(rows, "n_bess", "fmu_time_s")

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(8.0, 4),
        gridspec_kw={"width_ratios": [1, 1]},
    )

    # Accuracy subplot: scatter (x=native, y=FMU) with ideal y=x line.
    pv_color = "#1F618D"
    bess_color = "#C0392B"
    low_region_x = [
        r["native_total"]
        for r in rows
        if max(r["n_pv"], r["n_bess"]) <= 1.0 and r["native_total"] > 0.0 and r["fmu_total"] > 0.0
    ]
    low_region_y = [
        r["fmu_total"]
        for r in rows
        if max(r["n_pv"], r["n_bess"]) <= 1.0 and r["native_total"] > 0.0 and r["fmu_total"] > 0.0
    ]
    high_region_x = [
        r["native_total"]
        for r in rows
        if max(r["n_pv"], r["n_bess"]) > 1.0 and r["native_total"] > 0.0 and r["fmu_total"] > 0.0
    ]
    high_region_y = [
        r["fmu_total"]
        for r in rows
        if max(r["n_pv"], r["n_bess"]) > 1.0 and r["native_total"] > 0.0 and r["fmu_total"] > 0.0
    ]

    if low_region_x:
        ax1.scatter(
            low_region_x,
            low_region_y,
            s=26,
            marker="o",
            label="Cases with n_pv,n_bess in [0,1]",
            facecolors=to_rgba(bess_color, 0.45),
            edgecolors=to_rgba(bess_color, 1.0),
            linewidths=0.8,
            zorder=3,
        )

    if high_region_x:
        ax1.scatter(
            high_region_x,
            high_region_y,
            s=26,
            marker="o",
            label="Cases with n_pv or n_bess > 1",
            facecolors=to_rgba(pv_color, 0.45),
            edgecolors=to_rgba(pv_color, 1.0),
            linewidths=0.8,
            zorder=3,
        )

    positive_scores = [
        value
        for r in rows
        for value in (r["native_total"], r["fmu_total"])
        if value > 0.0
    ]
    if not positive_scores:
        raise RuntimeError("No positive-valued rows available for log-log accuracy plotting.")

    min_positive = min(positive_scores)
    max_positive = max(positive_scores)
    diag_min = 10 ** math.floor(math.log10(min_positive))
    diag_max = max_positive * 1.05

    ax1.plot(
        [diag_min, diag_max],
        [diag_min, diag_max],
        linestyle="--",
        color="#797B7E",
        linewidth=1.0,
        label="_nolegend_",
        zorder=1,
    )

    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlim(diag_min, diag_max)
    ax1.set_ylim(diag_min, diag_max)
    ax1.set_xlabel("Native Impact Score (kg CO2-eq)")
    ax1.set_ylabel("FMU Impact Score (kg CO2-eq)")
    ax1.set_title("Accuracy Validation")
    ax1.grid(False)
    ax1.tick_params(which="both", direction="in")
    ax1.legend(loc="best", fontsize=8)

    # Timing subplot: symlog x-axis keeps x=0 visible while preserving log-like scaling.
    ax2.plot(
        npv_x,
        npv_native,
        "o-",
        color=pv_color,
        label="PV - Native",
        markerfacecolor=to_rgba(pv_color, 0.5),
        markeredgecolor=pv_color,
        markeredgewidth=0.9,
    )
    ax2.plot(
        npv_x,
        npv_fmu,
        "s-",
        color=pv_color,
        label="PV - FMU",
        markerfacecolor=to_rgba(pv_color, 0.5),
        markeredgecolor=pv_color,
        markeredgewidth=0.9,
    )
    ax2.plot(
        nbess_x,
        nbess_native,
        "o-",
        color=bess_color,
        label="BESS - Native",
        markerfacecolor=to_rgba(bess_color, 0.5),
        markeredgecolor=bess_color,
        markeredgewidth=0.9,
    )
    ax2.plot(
        nbess_x,
        nbess_fmu,
        "s-",
        color=bess_color,
        label="BESS - FMU",
        markerfacecolor=to_rgba(bess_color, 0.5),
        markeredgecolor=bess_color,
        markeredgewidth=0.9,
    )
    ax2.set_xlabel("Parameter Value")
    ax2.set_ylabel("CPU Time (s)")
    ax2.set_title("Computational Performance")
    ax2.set_xscale("symlog", linthresh=1.0)
    ax2.grid(False)
    ax2.xaxis.set_minor_locator(
        SymmetricalLogLocator(base=10, linthresh=1.0, subs=np.arange(2, 10))
    )
    ax2.tick_params(which="both", direction="in")
    ax2.tick_params(axis="x", which="minor", length=3)
    ax2.legend(loc="best", fontsize=8)
    x_points = np.concatenate((npv_x, nbess_x)).tolist()
    if x_points:
        x_min = -0.1 # min(x_points)
        x_max = 12 # max(x_points) * 1.05
        if abs(x_max - x_min) < 1e-12:
            x_max = x_min + 1.0
        ax2.set_xlim(x_min, x_max)

        # Add dense minor hashes in the linear symlog region (0-1)
        # and keep symlog-style minor ticks for x > 1.
        linear_minor = np.arange(0.1, 1.0, 0.1).tolist()
        symlog_minor = SymmetricalLogLocator(
            base=10,
            linthresh=1.0,
            subs=np.arange(2, 10),
        ).tick_values(x_min, x_max).tolist()
        major_ticks = {float(np.round(t, 10)) for t in ax2.get_xticks(minor=False)}

        combined_minor: list[float] = []
        for tick in linear_minor + symlog_minor:
            rounded = float(np.round(tick, 10))
            if x_min < rounded < x_max and rounded not in major_ticks and rounded > 0.0:
                combined_minor.append(rounded)

        if combined_minor:
            ax2.xaxis.set_minor_locator(FixedLocator(sorted(set(combined_minor))))

    fig.tight_layout()
    fig.savefig(out_png, dpi=180)
    fig.savefig(out_svg)
    plt.close(fig)


def main() -> int:
    args = parse_args()

    if args.csv_only:
        if not args.out_csv.exists():
            print(f"❌ CSV not found for --csv-only: {args.out_csv}")
            return 1

        rows = read_csv(args.out_csv)
        if not rows:
            print(f"❌ CSV is empty: {args.out_csv}")
            return 1

        plot_overview(rows, args.plot_png, args.plot_svg)

        max_rel_err = max(r["rel_error"] for r in rows)
        mean_native_time = float(np.mean([r["native_time_s"] for r in rows]))
        mean_fmu_time = float(np.mean([r["fmu_time_s"] for r in rows]))
        speedup = mean_native_time / max(mean_fmu_time, 1e-12)

        print("♻️ CSV-only mode: skipped native/FMU calculations")
        print("\n📊 Scaling validation summary")
        print(f"  cases           : {len(rows)}")
        print(f"  max rel error   : {max_rel_err:.3e}")
        print(f"  mean native time: {mean_native_time:.4f} s")
        print(f"  mean fmu time   : {mean_fmu_time:.4f} s")
        print(f"  speedup (native/fmu): {speedup:.2f}x")
        print(f"  CSV             : {args.out_csv}")
        print(f"  plot (png)      : {args.plot_png}")
        print(f"  plot (svg)      : {args.plot_svg}")
        return 0

    inventory_path = args.inventory if args.inventory.is_absolute() else ROOT / args.inventory
    fmu_path = args.fmu if args.fmu.is_absolute() else ROOT / args.fmu

    if not inventory_path.exists():
        print(f"❌ Inventory not found: {inventory_path}")
        return 1
    if not fmu_path.exists():
        print(f"❌ FMU not found: {fmu_path}")
        return 1

    try:
        energy_mj = _load_energy_mj(inventory_path)
        input_signal = _build_input_signal(energy_mj)

        if args.single_case:
            cases = [(float(args.n_pv), float(args.n_bess))]
        else:
            sweep_values = build_sweep_values(args.low_points, args.high_points)
            cases = [(pv, bess) for pv in sweep_values for bess in sweep_values]

        rows: list[dict[str, float]]
        reused = False
        if args.reuse_csv and args.out_csv.exists():
            cached_rows = read_csv(args.out_csv)
            selected_rows = select_cached_rows(cached_rows, cases)
            if selected_rows:
                rows = selected_rows
                reused = True
                print(f"♻️ Reused cached CSV results from {args.out_csv} ({len(rows)} cases)")
            else:
                print("ℹ️ Cached CSV does not contain all requested cases; recomputing.")
                rows = []
        else:
            rows = []

        if not rows:
            for n_pv, n_bess in cases:
                row = evaluate_case(
                    inventory_path=inventory_path,
                    method=args.method,
                    fmu_path=fmu_path,
                    energy_mj=energy_mj,
                    input_signal=input_signal,
                    n_pv=n_pv,
                    n_bess=n_bess,
                )
                rows.append(row)
                print(
                    "✅ case "
                    f"(n_pv={n_pv:.3g}, n_bess={n_bess:.3g}) "
                    f"native={row['native_total']:.6f}, fmu={row['fmu_total']:.6f}, "
                    f"rel_err={row['rel_error']:.3e}, "
                    f"t_native={row['native_time_s']:.3f}s, t_fmu={row['fmu_time_s']:.3f}s"
                )

            write_csv(rows, args.out_csv)

        if reused:
            # Refresh CSV ordering to match the requested sweep/case sequence.
            write_csv(rows, args.out_csv)

        plot_overview(rows, args.plot_png, args.plot_svg)

        max_rel_err = max(r["rel_error"] for r in rows)
        mean_native_time = float(np.mean([r["native_time_s"] for r in rows]))
        mean_fmu_time = float(np.mean([r["fmu_time_s"] for r in rows]))
        speedup = mean_native_time / max(mean_fmu_time, 1e-12)

        print("\n📊 Scaling validation summary")
        print(f"  cases           : {len(rows)}")
        print(f"  max rel error   : {max_rel_err:.3e}")
        print(f"  mean native time: {mean_native_time:.4f} s")
        print(f"  mean fmu time   : {mean_fmu_time:.4f} s")
        print(f"  speedup (native/fmu): {speedup:.2f}x")
        print(f"  CSV             : {args.out_csv}")
        print(f"  plot (png)      : {args.plot_png}")
        print(f"  plot (svg)      : {args.plot_svg}")
        return 0

    except Exception as exc:
        print(f"❌ Scaling validation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

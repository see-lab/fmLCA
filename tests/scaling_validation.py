#!/usr/bin/env python3
"""Scaling validation for PvBessWecc312 FMU vs native Brightway evaluation.

Computes accuracy and runtime over a parameter grid:
        n_pv   in {1,2,4,6,8,10}
        n_bess in {1,2,4,6,8,10}

Outputs:
- One combined figure with two side-by-side subplots:
    - Accuracy vs parameter value
    - Log-log computational performance vs parameter value
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from fmpy import simulate_fmu
from matplotlib.colors import to_rgba

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lca_engine import run_lca  # noqa: E402


DEFAULT_INVENTORY = ROOT / "data" / "inventory" / "pv_bess_wecc_312.json"
DEFAULT_FMU = ROOT / "fmu" / "PvBessWecc312_Ipcc_v1.0.fmu"
DEFAULT_METHOD = "IPCC 2021 climate change total excl biogenic GWP100"

DEFAULT_VALUES = [1.0, 2.0, 4.0, 6.0, 8.0, 10.0]

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


def _mean_by_key(rows: list[dict[str, float]], key: str, time_key: str) -> tuple[np.ndarray, np.ndarray]:
    buckets: dict[float, list[float]] = {}
    for row in rows:
        k = float(row[key])
        buckets.setdefault(k, []).append(float(row[time_key]))

    xs = np.array(sorted(buckets.keys()), dtype=float)
    ys = np.array([float(np.mean(buckets[x])) for x in xs], dtype=float)
    return xs, ys


def _mean_scores_by_key(rows: list[dict[str, float]], key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    native_buckets: dict[float, list[float]] = {}
    fmu_buckets: dict[float, list[float]] = {}
    for row in rows:
        k = float(row[key])
        native_buckets.setdefault(k, []).append(float(row["native_total"]))
        fmu_buckets.setdefault(k, []).append(float(row["fmu_total"]))

    xs = np.array(sorted(native_buckets.keys()), dtype=float)
    native_y = np.array([float(np.mean(native_buckets[x])) for x in xs], dtype=float)
    fmu_y = np.array([float(np.mean(fmu_buckets[x])) for x in xs], dtype=float)
    return xs, native_y, fmu_y


def plot_overview(rows: list[dict[str, float]], out_png: Path, out_svg: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_svg.parent.mkdir(parents=True, exist_ok=True)

    npv_score_x, npv_native_score, npv_fmu_score = _mean_scores_by_key(rows, "n_pv")
    nbess_score_x, nbess_native_score, nbess_fmu_score = _mean_scores_by_key(rows, "n_bess")

    npv_x, npv_native = _mean_by_key(rows, "n_pv", "native_time_s")
    _, npv_fmu = _mean_by_key(rows, "n_pv", "fmu_time_s")

    nbess_x, nbess_native = _mean_by_key(rows, "n_bess", "native_time_s")
    _, nbess_fmu = _mean_by_key(rows, "n_bess", "fmu_time_s")

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(11.0, 4.6),
        gridspec_kw={"width_ratios": [1, 1]},
    )

    # Accuracy subplot: x is parameter value, color encodes PV/BESS, marker encodes native/FMU.
    pv_color = "#1F618D"
    bess_color = "#C0392B"

    ax1.plot(
        npv_score_x,
        npv_native_score,
        "o-",
        color=pv_color,
        label="PV - Native",
        markerfacecolor=to_rgba(pv_color, 0.5),
        markeredgecolor=pv_color,
        markeredgewidth=0.9,
    )
    ax1.plot(
        npv_score_x,
        npv_fmu_score,
        "s-",
        color=pv_color,
        label="PV - FMU",
        markerfacecolor=to_rgba(pv_color, 0.5),
        markeredgecolor=pv_color,
        markeredgewidth=0.9,
    )
    ax1.plot(
        nbess_score_x,
        nbess_native_score,
        "o-",
        color=bess_color,
        label="BESS - Native",
        markerfacecolor=to_rgba(bess_color, 0.5),
        markeredgecolor=bess_color,
        markeredgewidth=0.9,
    )
    ax1.plot(
        nbess_score_x,
        nbess_fmu_score,
        "s-",
        color=bess_color,
        label="BESS - FMU",
        markerfacecolor=to_rgba(bess_color, 0.5),
        markeredgecolor=bess_color,
        markeredgewidth=0.9,
    )
    ax1.set_xlabel("Parameter Value (n_pv or n_bess)")
    ax1.set_ylabel("Impact Score (kg CO2-eq)")
    ax1.set_title("Accuracy")
    ax1.grid(True, alpha=0.25)
    ax1.tick_params(which="both", direction="in")
    ax1.legend(loc="best", fontsize=8)

    # Timing subplot: log-log y-scale with same visual encoding.
    ax2.loglog(
        npv_x,
        npv_native,
        "o-",
        color=pv_color,
        label="PV - Native",
        markerfacecolor=to_rgba(pv_color, 0.5),
        markeredgecolor=pv_color,
        markeredgewidth=0.9,
    )
    ax2.loglog(
        npv_x,
        npv_fmu,
        "s-",
        color=pv_color,
        label="PV - FMU",
        markerfacecolor=to_rgba(pv_color, 0.5),
        markeredgecolor=pv_color,
        markeredgewidth=0.9,
    )
    ax2.loglog(
        nbess_x,
        nbess_native,
        "o-",
        color=bess_color,
        label="BESS - Native",
        markerfacecolor=to_rgba(bess_color, 0.5),
        markeredgecolor=bess_color,
        markeredgewidth=0.9,
    )
    ax2.loglog(
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
    ax2.grid(True, which="both", alpha=0.25)
    ax2.tick_params(which="both", direction="in")
    ax2.legend(loc="best", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_png, dpi=180)
    fig.savefig(out_svg)
    plt.close(fig)


def main() -> int:
    args = parse_args()

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
            cases = [(pv, bess) for pv in DEFAULT_VALUES for bess in DEFAULT_VALUES]

        rows: list[dict[str, float]] = []
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

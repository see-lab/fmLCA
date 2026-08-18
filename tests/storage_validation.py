#!/usr/bin/env python3
"""Validate staged impacts for bess, propane, and sandTes against SimaPro references.

Computes stage-wise percent difference as:
    (LCA-FMU - SimaPro) / SimaPro * 100

Produces one scatter marker per product+stage pair and shades an approximate
±0.5% parity band around y=x.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any
import matplotlib
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgba

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_METHODS = ROOT / "data" / "methods" / "ipccv1.03.json"
DEFAULT_OUT_PNG = ROOT / "results" / "storage_validation_percent_diff.png"
DEFAULT_OUT_SVG = ROOT / "results" / "storage_validation_percent_diff.svg"
DEFAULT_OUT_CSV = ROOT / "results" / "storage_validation_percent_diff.csv"
DEFAULT_PRODUCTS = ["bess", "propane", "sandTes"]

STAGE_ORDER = ["Total Impacts", "Production", "Transport", "Use", "EOL"]
STAGE_MARKERS = {
    "Total Impacts": "o",
    "Production": "^",
    "Transport": "v",
    "Use": "s",
    "EOL": "X",
}
PRODUCT_COLORS = {
    "bess": "#4B9C79",
    "propane": "#7470AE",
    "sandTes": "#CA6627",
}


def canonical_stage(raw: str) -> str:
    value = (raw or "").strip()
    lower = value.lower().replace("_", "-")
    if lower in {"total", "total impacts", "total impact", "overall", "sum"}:
        return "Total Impacts"
    if lower in {"end-of-life", "end of life", "eol", "end-of life"}:
        return "EOL"
    if lower == "production":
        return "Production"
    if lower == "transport":
        return "Transport"
    if lower == "use":
        return "Use"
    return value or "Unassigned"


def parse_number(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_method_tuple(methods_path: Path) -> tuple[str, ...]:
    payload = json.loads(methods_path.read_text(encoding="utf-8"))
    entries = payload.get("lcia_methods") or []
    if not entries:
        raise ValueError(f"No lcia_methods found in {methods_path}")

    method_tuple = entries[0].get("brightway_tuple")
    if not method_tuple:
        raise ValueError(f"Missing brightway_tuple in first lcia_methods entry of {methods_path}")
    return tuple(method_tuple)


def ensure_ipcc_v103_method(selected_method_tuple: tuple[str, ...]) -> None:
    ipcc_tuple = load_method_tuple(DEFAULT_METHODS)
    if selected_method_tuple != ipcc_tuple:
        raise ValueError(
            "storage_validation.py is restricted to IPCC v1.03. "
            f"Expected method tuple {ipcc_tuple}, got {selected_method_tuple}."
        )


def to_mj(value: float, unit: str) -> float:
    factors = {
        "mj": 1.0,
        "kj": 0.001,
        "gj": 1000.0,
        "tj": 1_000_000.0,
        "kwh": 3.6,
        "mwh": 3600.0,
        "wh": 0.0036,
    }
    factor = factors.get((unit or "mj").strip().lower())
    if factor is None:
        raise ValueError(f"Unsupported energy unit in inventory metadata: {unit}")
    return value * factor


def get_inventory_energy_mj(inventory_json: Path) -> float:
    data = json.loads(inventory_json.read_text(encoding="utf-8"))
    primary = ((data.get("energy_metadata") or {}).get("primary_input") or {})
    value = primary.get("value")
    unit = primary.get("unit", "MJ")
    if value is None:
        return 180.0
    return to_mj(float(value), str(unit))


def read_simapro_stage_scores(path: Path) -> dict[str, float]:
    lines = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    header_idx = None
    for i, line in enumerate(lines):
        if "Damage category" in line and "Total" in line:
            header_idx = i
            break
    if header_idx is None or header_idx + 1 >= len(lines):
        raise ValueError(f"Could not find SimaPro stage table in {path}")

    header = [c.strip() for c in lines[header_idx].split("\t")]
    values = [c.strip() for c in lines[header_idx + 1].split("\t")]
    if len(values) < len(header):
        values += [""] * (len(header) - len(values))

    stage_scores: dict[str, float] = {}
    for col_name, col_value in zip(header[3:], values[3:]):
        stage_key = col_name.split("_")[-1]
        stage = canonical_stage(stage_key)
        numeric = parse_number(col_value)
        if numeric is not None:
            stage_scores[stage] = numeric

    return stage_scores


def run_lca_stage_scores(inventory_json: Path, method_tuple: tuple[str, ...]) -> dict[str, float]:
    from src.lca_engine import run_lca_energy

    energy_mj = get_inventory_energy_mj(inventory_json)
    result = run_lca_energy(str(inventory_json), [method_tuple], {}, energy_mj)
    if "error" in result:
        raise RuntimeError(f"LCA calculation failed for {inventory_json.name}: {result['error']}")

    stage_breakdown = result.get("stage_breakdown") or {}
    method_key = str(method_tuple)
    stage_map = stage_breakdown.get(method_key)
    if stage_map is None and stage_breakdown:
        stage_map = stage_breakdown[next(iter(stage_breakdown.keys()))]
    if not stage_map:
        raise RuntimeError(f"No stage breakdown returned for {inventory_json.name}")

    parsed: dict[str, float] = {}
    for stage_name, info in stage_map.items():
        score = info.get("score") if isinstance(info, dict) else None
        if score is not None:
            parsed[canonical_stage(stage_name)] = float(score)
    return parsed


def load_cached_lca_stage_scores(
    product: str,
    method_tuple: tuple[str, ...],
) -> tuple[dict[str, float] | None, str | None]:
    results_dir = ROOT / "results"
    if not results_dir.exists():
        return None, None

    product_prefix = f"{product.lower()}_"
    result_json_candidates = [
        p
        for p in results_dir.glob("*_result.json")
        if p.name.lower().startswith(product_prefix) and "ipcc" in p.name.lower()
    ]
    result_json_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    method_key = str(method_tuple)

    for result_json in result_json_candidates:
        payload = json.loads(result_json.read_text(encoding="utf-8"))

        stage_breakdown = payload.get("stage_breakdown") or {}
        stage_map = stage_breakdown.get(method_key)
        if not stage_map:
            print(
                f"⚠️ Skipping cached file {result_json.name}: "
                "no exact IPCC v1.03 stage_breakdown entry found."
            )
            continue

        parsed: dict[str, float] = {}
        for stage_name, info in stage_map.items():
            score = info.get("score") if isinstance(info, dict) else None
            if score is not None:
                parsed[canonical_stage(stage_name)] = float(score)

        impact_results = payload.get("impact_results") or {}
        method_result = impact_results.get(method_key)
        if method_result is None:
            print(
                f"⚠️ Skipping cached file {result_json.name}: "
                "no exact IPCC v1.03 impact_results entry found."
            )
            continue
        if isinstance(method_result, dict) and method_result.get("total_score") is not None:
            parsed["Total Impacts"] = float(method_result["total_score"])

        if parsed:
            return parsed, result_json.name

    return None, None


def build_points(
    product_order: list[str],
    lca_by_product: dict[str, dict[str, float]],
    simapro_by_product: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for product in product_order:
        lca_stage = lca_by_product.get(product, {})
        sim_stage = simapro_by_product.get(product, {})
        for stage in STAGE_ORDER:
            lca_val = lca_stage.get(stage)
            sim_val = sim_stage.get(stage)

            if lca_val is None or sim_val is None:
                continue
            if lca_val == 0.0 and sim_val == 0.0:
                continue
            if sim_val == 0.0:
                continue

            pct = ((lca_val - sim_val) / sim_val) * 100.0
            points.append(
                {
                    "product": product,
                    "stage": stage,
                    "lca_fmu": lca_val,
                    "simapro": sim_val,
                    "percent_diff": pct,
                    "label": f"{product}:{stage}",
                }
            )
    return points


def plot_points(points: list[dict[str, Any]], output_png: Path, output_svg: Path) -> None:
    if not points:
        raise RuntimeError("No comparable non-zero product+stage points to plot.")

    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(4, 4))

    # Log-log scatter requires strictly positive coordinates.
    plot_points_data = [p for p in points if p["simapro"] > 0.0 and p["lca_fmu"] > 0.0]
    if not plot_points_data:
        raise RuntimeError("No positive-valued points available for log-log plotting.")

    x_values = [p["simapro"] for p in plot_points_data]
    y_values = [p["lca_fmu"] for p in plot_points_data]

    min_positive = min(x_values + y_values)
    # Use a decade floor below the smallest point so sub-1 impacts (e.g., EOL)
    # remain visible on log axes.
    plot_min = 10 ** math.floor(math.log10(min_positive))
    plot_max = max(100000.0, max(x_values + y_values) * 1.05)

    line_x = [plot_min, plot_max]
    ax.plot(line_x, line_x, color="#797B7E", linestyle="--", linewidth=1.0, zorder=1)

    stage_marker_sizes = {
        "Total Impacts": 72,
        "Production": 96,
        "Transport": 96,
        "Use": 72,
        "EOL": 80,
    }

    for point in plot_points_data:
        product = point["product"]
        color = PRODUCT_COLORS.get(product, "#475569")
        stage = point["stage"]
        marker = STAGE_MARKERS.get(stage, "o")
        scatter_kwargs: dict[str, Any] = {
            "s": stage_marker_sizes.get(stage, 72),
            "marker": marker,
            "facecolors": to_rgba(color, 0.5),
            "linewidths": 0.8,
            "zorder": 3,
            "edgecolors": to_rgba(color, 1.0),
        }

        ax.scatter(
            point["simapro"],
            point["lca_fmu"],
            **scatter_kwargs,
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(plot_min, plot_max)
    ax.set_ylim(plot_min, plot_max)
    ax.set_xlabel("SimaPro Score (kg CO2-eq)")
    ax.set_ylabel("Brightway Score via LCA-FMU (kg CO2-eq)")
    ax.grid(False)
    ax.minorticks_on()
    ax.tick_params(which="major", direction="in")
    ax.tick_params(which="minor", direction="in")

    legend_marker_size = 8
    product_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=color,
            markeredgecolor=color,
            markeredgewidth=0.8,
            markersize=legend_marker_size,
            label=label,
        )
        for label, color in [
            ("BESS", PRODUCT_COLORS["bess"]),
            ("Propane", PRODUCT_COLORS["propane"]),
            ("Sand", PRODUCT_COLORS["sandTes"]),
        ]
    ]
    stage_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="None",
            color="none",
            markerfacecolor=to_rgba("#1F2937", 0.5),
            markeredgecolor=to_rgba("#1F2937", 1.0),
            markeredgewidth=0.8,
            markersize=legend_marker_size,
            label=stage,
        )
        for stage, marker in STAGE_MARKERS.items()
        if stage != "Total Impacts"
    ]

    tech_legend = ax.legend(handles=product_handles, title="Technology", loc="upper left")
    ax.add_artist(tech_legend)
    ax.legend(handles=stage_handles, title="Life Cycle Stage", loc="lower right")

    fig.tight_layout()
    fig.savefig(output_png, dpi=300)
    fig.savefig(output_svg)
    plt.close(fig)


def build_technology_totals(product_order: list[str], points: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    totals: list[dict[str, float | str]] = []
    for product in product_order:
        product_points = [p for p in points if p["product"] == product and p["stage"] != "Total Impacts"]
        if not product_points:
            continue

        lca_total = sum(float(p["lca_fmu"]) for p in product_points)
        sim_total = sum(float(p["simapro"]) for p in product_points)
        if sim_total == 0.0:
            continue

        pct = ((lca_total - sim_total) / sim_total) * 100.0
        totals.append(
            {
                "product": product,
                "stage": "Total (sum stages)",
                "lca_fmu": lca_total,
                "simapro": sim_total,
                "percent_diff": pct,
            }
        )
    return totals


def write_table(
    points: list[dict[str, Any]],
    technology_totals: list[dict[str, float | str]],
    output_csv: Path,
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Product", "Stage", "LCA_FMU", "SimaPro", "Percent_Difference"])
        for p in points:
            writer.writerow([p["product"], p["stage"], p["lca_fmu"], p["simapro"], p["percent_diff"]])
        for t in technology_totals:
            writer.writerow([t["product"], t["stage"], t["lca_fmu"], t["simapro"], t["percent_diff"]])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate staged impacts for bess, propane, and sandTes",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--products",
        nargs="+",
        default=DEFAULT_PRODUCTS,
        help="Product names (expects data/inventory/<name>.json and tests/reference_results/<name>-simapro.csv)",
    )
    parser.add_argument("--methods", default=str(DEFAULT_METHODS), help="Path to methods JSON")
    parser.add_argument("--out", default=str(DEFAULT_OUT_PNG), help="Output scatter PNG")
    parser.add_argument("--out-svg", default=str(DEFAULT_OUT_SVG), help="Output scatter SVG")
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV), help="Output summary CSV")
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Recompute LCAs even when reusable stage results exist in results/",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    methods_path = Path(args.methods) if Path(args.methods).is_absolute() else ROOT / args.methods
    method_tuple = load_method_tuple(methods_path)
    ensure_ipcc_v103_method(method_tuple)

    lca_by_product: dict[str, dict[str, float]] = {}
    simapro_by_product: dict[str, dict[str, float]] = {}

    for product in args.products:
        inventory_json = ROOT / "data" / "inventory" / f"{product}.json"
        simapro_csv = ROOT / "tests" / "reference_results" / f"{product}-simapro.csv"

        if not inventory_json.exists():
            raise FileNotFoundError(
                f"Inventory JSON not found: {inventory_json}. "
                f"Generate it first from data/inventory/{product}.csv"
            )
        if not simapro_csv.exists():
            raise FileNotFoundError(f"SimaPro reference CSV not found: {simapro_csv}")

        print(f"\n=== {product} ===")
        cached_scores: dict[str, float] | None = None
        cached_source: str | None = None
        if not args.force_rerun:
            cached_scores, cached_source = load_cached_lca_stage_scores(product, method_tuple)

        if cached_scores:
            print(f"♻️ Reusing cached LCA stage scores from results/{cached_source}")
            lca_by_product[product] = cached_scores
        else:
            lca_by_product[product] = run_lca_stage_scores(inventory_json, method_tuple)
        simapro_by_product[product] = read_simapro_stage_scores(simapro_csv)

    points = build_points(args.products, lca_by_product, simapro_by_product)
    technology_totals = build_technology_totals(args.products, points)

    out_png = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out_svg = Path(args.out_svg) if Path(args.out_svg).is_absolute() else ROOT / args.out_svg
    out_csv = Path(args.out_csv) if Path(args.out_csv).is_absolute() else ROOT / args.out_csv

    plot_points(points, out_png, out_svg)
    write_table(points, technology_totals, out_csv)

    print(f"\nmethods={methods_path}")
    print(f"products={args.products}")
    print(f"points={len(points)}")
    print(f"plot={out_png}")
    print(f"plot_svg={out_svg}")
    print(f"table={out_csv}")
    print("technology_total_percent_diff=")
    for t in technology_totals:
        print(
            f"  {t['product']}: "
            f"LCA={float(t['lca_fmu']):.6f}, "
            f"SimaPro={float(t['simapro']):.6f}, "
            f"pct={float(t['percent_diff']):.6f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

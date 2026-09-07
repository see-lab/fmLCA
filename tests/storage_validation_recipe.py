#!/usr/bin/env python3
"""Validate ReCiPe single-score stage impacts for storage technologies.

Compares fmLCA native ReCiPe outputs against SimaPro *-simapro-recipe.csv
Single score references for:
- bess310
- propane
- sandTes

Percent difference is computed as:
    (fmLCA - SimaPro) / SimaPro * 100
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
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_METHODS = ROOT / "data" / "methods" / "recipe_endpoint_ha.json"
DEFAULT_OUT_PNG = ROOT / "results" / "storage_validation_recipe_percent_diff.png"
DEFAULT_OUT_SVG = ROOT / "results" / "storage_validation_recipe_percent_diff.svg"
DEFAULT_OUT_CSV = ROOT / "results" / "storage_validation_recipe_percent_diff.csv"
DEFAULT_PRODUCTS = ["bess310", "propane", "sandTes"]

STAGE_ORDER = ["Total Impacts", "Production", "Transport", "Use", "EOL"]
STAGE_MARKERS = {
    "Total Impacts": "o",
    "Production": "^",
    "Transport": "v",
    "Use": "s",
    "EOL": "X",
}
PRODUCT_COLORS = {
    "bess310": "#4B9C79",
    "propane": "#7470AE",
    "sandTes": "#CA6627",
}


def canonical_stage(raw: str) -> str:
    value = (raw or "").strip()
    lower = value.lower().replace("_", "-")
    if lower in {"total", "total impacts", "total impact", "overall", "sum"}:
        return "Total Impacts"
    if lower in {"end-of-life", "end of life", "eol", "end-of life", "end-of-life"}:
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


def to_mj(value: float, unit: str) -> float:
    factors = {
        "mj": 1.0,
        "kj": 0.001,
        "gj": 1000.0,
        "tj": 1_000_000.0,
        "kwh": 3.6,
        "mwh": 3600.0,
        "wh": 0.0036,
        "j": 1.0e-6,
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


def load_methods(methods_path: Path) -> list[Any]:
    payload = json.loads(methods_path.read_text(encoding="utf-8"))
    entries = payload.get("lcia_methods") or []
    if not entries:
        raise ValueError(f"No lcia_methods found in {methods_path}")

    method_list: list[Any] = []
    for entry in entries:
        if isinstance(entry, str):
            method_list.append(entry)
        elif isinstance(entry, dict):
            bw_tuple = entry.get("brightway_tuple") or entry.get("brightway_tuple_hint")
            name = entry.get("name")
            method_list.append(tuple(bw_tuple) if bw_tuple else name)
    method_list = [m for m in method_list if m]
    if not method_list:
        raise ValueError(f"No usable methods in {methods_path}")
    return method_list


def _single_score_factor(unit_text: str) -> float:
    unit_lower = (unit_text or "").strip().lower()
    if unit_lower == "kpt":
        return 1000.0
    return 1.0


def read_simapro_single_score_pt(path: Path) -> dict[str, float]:
    lines = path.read_text(encoding="utf-8").splitlines()

    single_score_start = None
    for idx, line in enumerate(lines):
        if "Indicator:" in line and "Single score" in line:
            single_score_start = idx
            break
    if single_score_start is None:
        raise ValueError(f"No 'Indicator: Single score' section found in {path}")

    header_idx = None
    for idx in range(single_score_start, len(lines)):
        line = lines[idx]
        if "Damage category" in line and "Total" in line:
            header_idx = idx
            break
    if header_idx is None or header_idx + 1 >= len(lines):
        raise ValueError(f"Could not find single-score table header in {path}")

    header = [c.strip() for c in lines[header_idx].split("\t")]
    scores: dict[str, float] = {}

    for row_idx in range(header_idx + 1, len(lines)):
        row_line = lines[row_idx]
        if not row_line.strip():
            break

        row = [c.strip() for c in row_line.split("\t")]
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))

        category = row[0].lower()
        if category != "total":
            continue

        factor = _single_score_factor(row[1])
        total_val = parse_number(row[2])
        if total_val is not None:
            scores["Total Impacts"] = total_val * factor

        for col_name, col_val in zip(header[3:], row[3:]):
            stage_key = col_name.split("_")[-1]
            stage = canonical_stage(stage_key)
            numeric = parse_number(col_val)
            if numeric is not None:
                scores[stage] = numeric * factor

    if not scores:
        raise ValueError(f"No single-score totals parsed from {path}")

    return scores


def run_lca_single_score_pt(
    inventory_json: Path,
    method_list: list[Any],
) -> tuple[dict[str, float], bool, list[str]]:
    from src.lca_engine import run_lca_energy

    energy_mj = get_inventory_energy_mj(inventory_json)
    result = run_lca_energy(str(inventory_json), method_list, {}, energy_mj)
    if "error" in result:
        raise RuntimeError(f"LCA calculation failed for {inventory_json.name}: {result['error']}")

    impact_results = result.get("impact_results") or {}
    stage_breakdown = result.get("stage_breakdown") or {}

    totals: dict[str, float] = {stage: 0.0 for stage in STAGE_ORDER if stage != "Total Impacts"}
    total_impacts_pt = 0.0

    is_native_single_score = True
    notes: list[str] = []

    for method_key, method_result in impact_results.items():
        if not isinstance(method_result, dict):
            continue

        method_unit = str(method_result.get("unit", "")).strip()
        score_pt = method_result.get("score_pt")

        if score_pt is None:
            if method_unit == "Pt":
                score_pt = method_result.get("total_score")
            else:
                is_native_single_score = False
                notes.append(f"{method_key}: unit={method_unit or '<empty>'}, missing score_pt")
                continue

        total_impacts_pt += float(score_pt)

        method_stage_map = stage_breakdown.get(method_key) or {}
        for stage_name, info in method_stage_map.items():
            stage = canonical_stage(stage_name)
            if stage == "Total Impacts":
                continue
            if stage not in totals:
                totals[stage] = 0.0

            if isinstance(info, dict):
                stage_score = float(info.get("score", 0.0))
                stage_unit = str(info.get("unit", "")).strip()
                if stage_unit and stage_unit != "Pt":
                    is_native_single_score = False
                    notes.append(f"{method_key}:{stage} uses unit={stage_unit}")
            else:
                stage_score = float(info)
                is_native_single_score = False
                notes.append(f"{method_key}:{stage} returned non-dict stage payload")

            totals[stage] += stage_score

    totals["Total Impacts"] = total_impacts_pt
    return totals, is_native_single_score, notes


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
                }
            )
    return points


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


def plot_points(points: list[dict[str, Any]], output_png: Path, output_svg: Path) -> None:
    if not points:
        raise RuntimeError("No comparable non-zero product+stage points to plot.")

    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(4, 4))

    plot_points_data = [p for p in points if p["simapro"] > 0.0 and p["lca_fmu"] > 0.0]
    if not plot_points_data:
        raise RuntimeError("No positive-valued points available for log-log plotting.")

    x_values = [p["simapro"] for p in plot_points_data]
    y_values = [p["lca_fmu"] for p in plot_points_data]

    min_positive = min(x_values + y_values)
    plot_min = 10 ** math.floor(math.log10(min_positive))
    plot_max = max(max(x_values + y_values) * 1.05, plot_min * 10.0)

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
        stage = point["stage"]
        color = PRODUCT_COLORS.get(product, "#475569")
        marker = STAGE_MARKERS.get(stage, "o")

        ax.scatter(
            point["simapro"],
            point["lca_fmu"],
            s=stage_marker_sizes.get(stage, 72),
            marker=marker,
            facecolors=to_rgba(color, 0.5),
            edgecolors=to_rgba(color, 1.0),
            linewidths=0.8,
            zorder=3,
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(plot_min, plot_max)
    ax.set_ylim(plot_min, plot_max)
    ax.set_xlabel("SimaPro ReCiPe H/A (Pt)")
    ax.set_ylabel("Brightway ReCiPe H/A via fmLCA (Pt)")
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
            ("BESS", PRODUCT_COLORS["bess310"]),
            ("Propane", PRODUCT_COLORS["propane"]),
            ("SandTES", PRODUCT_COLORS["sandTes"]),
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


def write_table(
    points: list[dict[str, Any]],
    technology_totals: list[dict[str, float | str]],
    output_csv: Path,
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Product", "Stage", "LCA_FMU_Pt", "SimaPro_Pt", "Percent_Difference"])
        for p in points:
            writer.writerow([p["product"], p["stage"], p["lca_fmu"], p["simapro"], p["percent_diff"]])
        for t in technology_totals:
            writer.writerow([t["product"], t["stage"], t["lca_fmu"], t["simapro"], t["percent_diff"]])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate ReCiPe single-score stage impacts for bess310, propane, and sandTes",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--products",
        nargs="+",
        default=DEFAULT_PRODUCTS,
        help="Product names (expects data/inventory/<name>.json and tests/reference_results/<name>-simapro-recipe.csv)",
    )
    parser.add_argument("--methods", default=str(DEFAULT_METHODS), help="Path to methods JSON")
    parser.add_argument("--out", default=str(DEFAULT_OUT_PNG), help="Output scatter PNG")
    parser.add_argument("--out-svg", default=str(DEFAULT_OUT_SVG), help="Output scatter SVG")
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV), help="Output summary CSV")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    methods_path = Path(args.methods) if Path(args.methods).is_absolute() else ROOT / args.methods
    method_list = load_methods(methods_path)

    lca_by_product: dict[str, dict[str, float]] = {}
    simapro_by_product: dict[str, dict[str, float]] = {}

    all_native_single_score = True

    for product in args.products:
        inventory_json = ROOT / "data" / "inventory" / f"{product}.json"
        simapro_csv = ROOT / "tests" / "reference_results" / f"{product}-simapro-recipe.csv"

        if not inventory_json.exists():
            raise FileNotFoundError(
                f"Inventory JSON not found: {inventory_json}. "
                f"Generate it first from data/inventory/{product}.csv"
            )
        if not simapro_csv.exists():
            raise FileNotFoundError(f"SimaPro reference CSV not found: {simapro_csv}")

        print(f"\n=== {product} ===")

        lca_scores, native_single_score, native_notes = run_lca_single_score_pt(
            inventory_json=inventory_json,
            method_list=method_list,
        )
        simapro_scores = read_simapro_single_score_pt(simapro_csv)

        lca_by_product[product] = lca_scores
        simapro_by_product[product] = simapro_scores

        print(f"Native output interpreted as single score Pt: {'YES' if native_single_score else 'NO'}")
        if native_notes:
            for note in native_notes:
                print(f"  - {note}")

        all_native_single_score = all_native_single_score and native_single_score

    points = build_points(args.products, lca_by_product, simapro_by_product)
    technology_totals = build_technology_totals(args.products, points)

    out_png = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out_svg = Path(args.out_svg) if Path(args.out_svg).is_absolute() else ROOT / args.out_svg
    out_csv = Path(args.out_csv) if Path(args.out_csv).is_absolute() else ROOT / args.out_csv

    plot_points(points, out_png, out_svg)
    write_table(points, technology_totals, out_csv)

    print("\n=== Summary ===")
    print(f"methods={methods_path}")
    print(f"products={args.products}")
    print(f"points={len(points)}")
    print(f"plot={out_png}")
    print(f"plot_svg={out_svg}")
    print(f"table={out_csv}")
    print(f"native_single_score_pt_all_products={all_native_single_score}")

    print("technology_total_percent_diff=")
    for t in technology_totals:
        print(
            f"  {t['product']}: "
            f"LCA={float(t['lca_fmu']):.6f} Pt, "
            f"SimaPro={float(t['simapro']):.6f} Pt, "
            f"pct={float(t['percent_diff']):.6f}%"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

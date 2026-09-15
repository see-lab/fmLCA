#!/usr/bin/env python3
"""Scale validation benchmark for native Brightway vs FMU execution.

Workflow:
1. Generate scale{n}.json inventories across fixed-quantile sizes.
2. Build one IPCC FMU per inventory size.
3. Run native and FMU simulations with repeated timing per size.
4. Cache/reuse existing results and plot median CPU time vs n.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from fmpy import simulate_fmu

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fmlca.create_fmu import build_lca_fmu  # noqa: E402
from fmlca.lca_engine import run_lca  # noqa: E402

DEFAULT_METHOD = "IPCC 2021 climate change total excl biogenic GWP100"
DEFAULT_INVENTORY_DIR = ROOT / "data" / "inventory" / "scaling_validation"
DEFAULT_FMU_DIR = ROOT / "fmu" / "scaling_validation"
DEFAULT_RESULTS_CSV = ROOT / "results" / "scaling_validation_results.csv"
DEFAULT_SUMMARY_CSV = ROOT / "results" / "scaling_validation_summary_by_size.csv"
DEFAULT_PLOT_PNG = ROOT / "results" / "scaling_validation_cpu_loglog.png"
DEFAULT_PLOT_SVG = ROOT / "results" / "scaling_validation_cpu_loglog.svg"

STAGES = ("Production", "Transport", "Use", "EOL")
START_TIME = 0.0
STOP_TIME = 3600.0
STEP_SIZE = 60.0
DEFAULT_LINEAR_REGIME_MIN = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate scale inventories, build FMUs, and benchmark runtime."
    )
    parser.add_argument("--n-lci", type=int, default=15)
    parser.add_argument("--min-lines", type=int, default=1)
    parser.add_argument("--max-lines", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--linear-regime-min", type=int, default=DEFAULT_LINEAR_REGIME_MIN)
    parser.add_argument("--seed", type=int, default=312)
    parser.add_argument("--method", type=str, default=DEFAULT_METHOD)
    parser.add_argument("--inventory-dir", type=Path, default=DEFAULT_INVENTORY_DIR)
    parser.add_argument("--fmu-dir", type=Path, default=DEFAULT_FMU_DIR)
    parser.add_argument(
        "--reuse-results",
        dest="reuse_results",
        action="store_true",
        help="Reuse rows from --out-csv and only run missing case/repeat combinations.",
    )
    parser.add_argument(
        "--no-reuse-results",
        dest="reuse_results",
        action="store_false",
        help="Ignore any existing --out-csv and rerun all simulations.",
    )
    parser.set_defaults(reuse_results=True)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_RESULTS_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
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


def _extract_total_score(results: dict[str, Any]) -> float:
    if "error" in results:
        raise RuntimeError(str(results["error"]))

    impact_results = results.get("impact_results", {})
    for data in impact_results.values():
        if isinstance(data, dict) and "total_score" in data:
            return float(data["total_score"])
    raise RuntimeError("No total_score found in impact_results")


def _discover_exchange_pool() -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGES}
    inventory_dir = ROOT / "data" / "inventory"
    for path in sorted(inventory_dir.glob("*.json")):
        if path.parent.name == "scaling_validation":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for exc in payload.get("exchanges", []):
            if exc.get("type") != "technosphere":
                continue
            stage = str(exc.get("life_cycle_stage", "")).strip()
            if stage not in STAGES:
                continue
            inp = exc.get("input")
            if not isinstance(inp, list) or len(inp) < 2:
                continue
            if str(inp[0]) != "ecoinvent-3.12-cutoff":
                continue
            pool[stage].append(exc)

    missing = [stage for stage, items in pool.items() if not items]
    if missing:
        raise RuntimeError(f"Missing ecoinvent-3.12 examples for stages: {missing}")
    return pool


def _choose_line_counts(n_lci: int, min_lines: int, max_lines: int, seed: int) -> list[int]:
    del seed  # Fixed-quantile mode is deterministic and does not use randomness.

    if n_lci < 1:
        raise ValueError("n_lci must be >= 1")
    if min_lines < 1:
        raise ValueError("min_lines must be >= 1")
    if max_lines < min_lines:
        raise ValueError("max_lines must be >= min_lines")
    effective_min = max(min_lines, len(STAGES))
    if max_lines < effective_min:
        raise ValueError(
            f"max_lines must be >= {effective_min} when all {len(STAGES)} life-cycle stages are required"
        )
    choices = list(range(effective_min, max_lines + 1))
    if n_lci > len(choices):
        raise ValueError("n_lci exceeds the number of unique line-item counts available")

    if n_lci == 1:
        return [effective_min]

    span = max_lines - effective_min
    raw_values = [
        int(round(effective_min + (span * i) / (n_lci - 1)))
        for i in range(n_lci)
    ]

    # Enforce strictly increasing unique counts while staying in bounds.
    selected: list[int] = []
    last = effective_min - 1
    for value in raw_values:
        clamped = min(max(value, effective_min), max_lines)
        if clamped <= last:
            clamped = last + 1
        if clamped > max_lines:
            break
        selected.append(clamped)
        last = clamped

    if len(selected) < n_lci:
        selected = choices[-n_lci:]

    selected[0] = effective_min
    selected[-1] = max_lines
    return selected


def _clone_exchange(template: dict[str, Any], name: str) -> dict[str, Any]:
    cloned = dict(template)
    cloned["name"] = name
    cloned["amount"] = 1.0
    if "amount_ref" in cloned:
        del cloned["amount_ref"]
    return cloned


def _build_inventory_payload(n_lines: int, pool: dict[str, list[dict[str, Any]]], seed: int) -> dict[str, Any]:
    rng = random.Random(seed + n_lines)
    target_items = max(n_lines, len(STAGES))
    selected: list[dict[str, Any]] = []

    for stage in STAGES:
        selected.append(rng.choice(pool[stage]))

    all_items = [item for stage_items in pool.values() for item in stage_items]
    while len(selected) < target_items:
        selected.append(rng.choice(all_items))

    exchanges = [
        {
            "name": f"scale{n_lines}",
            "amount": 1.0,
            "unit": "unit",
            "type": "production",
            "input": ["Scale_System_DB", f"scale{n_lines}"],
        }
    ]

    stage_map: dict[str, list[str]] = {stage: [] for stage in STAGES}
    for idx, item in enumerate(selected, start=1):
        stage = str(item["life_cycle_stage"])
        line_name = f"{item['name']} [{idx}]"
        line = _clone_exchange(item, line_name)
        line["life_cycle_stage"] = stage
        exchanges.append(line)
        stage_map[stage].append(line_name)

    return {
        "name": f"scale{n_lines}",
        "unit": "unit",
        "location": "GLO",
        "categories": ["technosphere", "scaling validation"],
        "type": "process",
        "exchanges": exchanges,
        "parameters": {},
        "life_cycle_stages": {
            stage: {
                "description": f"{stage} stage processes",
                "exchanges": stage_map[stage],
            }
            for stage in STAGES
        },
        "energy_metadata": {
            "energy_processes": 1,
            "primary_input": {
                "name": "energy_input",
                "unit": "MJ",
                "description": "Benchmark energy input",
                "value": 1.0,
            },
        },
        "unlinked_exchanges": [],
    }


def _write_inventory(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_energy_mj(inventory_path: Path) -> float:
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    primary = payload["energy_metadata"]["primary_input"]
    return _to_mj(float(primary["value"]), str(primary.get("unit", "MJ")))


def _build_input_signal(energy_mj: float) -> np.ndarray:
    duration_s = STOP_TIME - START_TIME
    power_w = (energy_mj / duration_s) * 1_000_000.0
    return np.array(
        [(START_TIME, power_w), (STOP_TIME, power_w)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )


def _build_fmu(inventory_path: Path, fmu_dir: Path) -> Path:
    result = build_lca_fmu(
        lci_file=inventory_path,
        method="ipcc",
        version="1.0.0",
        output_dir=fmu_dir,
        name=inventory_path.stem,
        export_mode="bytecode",
        blackbox_policy="off",
        validate=True,
        verify_linearity=False,
        verbose=False,
    )
    return result.final_fmu_path


def _ensure_fmu(inventory_path: Path, fmu_dir: Path) -> Path:
    expected = fmu_dir / f"{inventory_path.stem}.fmu"
    if expected.exists():
        return expected
    return _build_fmu(inventory_path, fmu_dir)


def _evaluate_case(inventory_path: Path, fmu_path: Path, method: str) -> dict[str, Any]:
    energy_mj = _load_energy_mj(inventory_path)
    input_signal = _build_input_signal(energy_mj)

    t0 = time.perf_counter()
    native_result = run_lca(
        lci_file=str(inventory_path),
        lcia_methods=[method],
        parameter_values={},
        functional_unit={},
        energy_amount_mj=energy_mj,
    )
    native_cpu_s = time.perf_counter() - t0
    native_score = _extract_total_score(native_result)

    t1 = time.perf_counter()
    sim = simulate_fmu(
        filename=str(fmu_path),
        start_time=START_TIME,
        stop_time=STOP_TIME,
        step_size=STEP_SIZE,
        input=input_signal,
        output=["y"],
    )
    fmu_cpu_s = time.perf_counter() - t1
    fmu_score = float(sim["y"][-1])

    rel_error = abs(fmu_score - native_score) / max(abs(native_score), 1e-12)
    n_line_items = len(json.loads(inventory_path.read_text(encoding="utf-8"))["exchanges"]) - 1
    return {
        "method": method,
        "inventory": inventory_path.name,
        "fmu": fmu_path.name,
        "n_line_items": n_line_items,
        "native_score": native_score,
        "fmu_score": fmu_score,
        "rel_error": rel_error,
        "native_cpu_s": native_cpu_s,
        "fmu_cpu_s": fmu_cpu_s,
    }


def _load_existing_results(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if df.empty:
        return df

    if "repeat_idx" not in df.columns:
        df["repeat_idx"] = 1
    df["repeat_idx"] = df["repeat_idx"].astype(int)
    df["n_line_items"] = df["n_line_items"].astype(int)
    return df


def _plot_cpu_loglog(
    df: pd.DataFrame,
    out_png: Path,
    out_svg: Path,
    linear_regime_min: int,
) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_svg.parent.mkdir(parents=True, exist_ok=True)

    ordered = df.sort_values("n_line_items")
    fig, ax = plt.subplots(figsize=(6.0, 6.0))
    ax.loglog(
        ordered["n_line_items"],
        ordered["native_cpu_s_median"],
        "o-",
        label="Native (lca_engine), median of repeats",
    )
    ax.loglog(
        ordered["n_line_items"],
        ordered["fmu_cpu_s_median"],
        "s-",
        label="FMU (run_fmu path), median of repeats",
    )
    ax.set_xlabel("n line items")
    ax.set_ylabel("CPU time (s)")
    ax.set_title("Scaling CPU Time vs Inventory Size")
    ax.grid(True, which="both", linestyle=":", linewidth=0.7)
    if linear_regime_min > 0:
        ax.axvline(linear_regime_min, linestyle="--", linewidth=1.0, color="#777777")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_png, dpi=180)
    fig.savefig(out_svg)
    plt.close(fig)


def _build_summary_by_size(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("n_line_items", as_index=False)
        .agg(
            repeats=("repeat_idx", "count"),
            native_cpu_s_median=("native_cpu_s", "median"),
            native_cpu_s_mean=("native_cpu_s", "mean"),
            native_cpu_s_std=("native_cpu_s", "std"),
            native_cpu_s_min=("native_cpu_s", "min"),
            native_cpu_s_max=("native_cpu_s", "max"),
            fmu_cpu_s_median=("fmu_cpu_s", "median"),
            fmu_cpu_s_mean=("fmu_cpu_s", "mean"),
            fmu_cpu_s_std=("fmu_cpu_s", "std"),
            fmu_cpu_s_min=("fmu_cpu_s", "min"),
            fmu_cpu_s_max=("fmu_cpu_s", "max"),
            native_score_median=("native_score", "median"),
            native_score_mean=("native_score", "mean"),
            native_score_std=("native_score", "std"),
            native_score_min=("native_score", "min"),
            native_score_max=("native_score", "max"),
            fmu_score_median=("fmu_score", "median"),
            fmu_score_mean=("fmu_score", "mean"),
            fmu_score_std=("fmu_score", "std"),
            fmu_score_min=("fmu_score", "min"),
            fmu_score_max=("fmu_score", "max"),
            rel_error_median=("rel_error", "median"),
            rel_error_mean=("rel_error", "mean"),
            rel_error_std=("rel_error", "std"),
            rel_error_min=("rel_error", "min"),
            rel_error_max=("rel_error", "max"),
        )
        .sort_values("n_line_items")
    )


def _looks_like_missing_ecoinvent(error_text: str) -> bool:
    text = error_text.lower()
    return (
        "no brightway project found" in text
        or "ecoinvent" in text
        or ("database" in text and "not found" in text)
    )


def main() -> int:
    args = parse_args()

    try:
        if args.repeats < 1:
            raise ValueError("repeats must be >= 1")

        pool = _discover_exchange_pool()
        line_counts = _choose_line_counts(args.n_lci, args.min_lines, args.max_lines, args.seed)

        existing_df = _load_existing_results(args.out_csv) if args.reuse_results else pd.DataFrame()
        existing_map: dict[tuple[str, int], dict[Any, Any]] = {}
        if not existing_df.empty:
            for row in existing_df.to_dict(orient="records"):
                method_name = str(row.get("method", DEFAULT_METHOD))
                if method_name != args.method:
                    continue
                inventory_name = str(row.get("inventory", ""))
                if not inventory_name:
                    continue
                key = (inventory_name, int(row["repeat_idx"]))
                existing_map[key] = dict(row)

        rows: list[dict[str, Any]] = []
        args.inventory_dir.mkdir(parents=True, exist_ok=True)
        args.fmu_dir.mkdir(parents=True, exist_ok=True)

        reused = 0
        executed = 0

        for n_lines in line_counts:
            stem = f"scale{n_lines}"
            inventory_path = args.inventory_dir / f"{stem}.json"
            if not inventory_path.exists():
                payload = _build_inventory_payload(n_lines, pool, args.seed)
                _write_inventory(inventory_path, payload)

            fmu_path = _ensure_fmu(inventory_path, args.fmu_dir)

            for repeat_idx in range(1, args.repeats + 1):
                cache_key = (inventory_path.name, repeat_idx)
                cached = existing_map.get(cache_key)
                if cached is not None:
                    rows.append(cached)
                    reused += 1
                    print(f"case={stem:>8s} repeat={repeat_idx} reused")
                    continue

                row = _evaluate_case(inventory_path, fmu_path, args.method)
                row["repeat_idx"] = repeat_idx
                rows.append(row)
                executed += 1

                print(
                    f"case={stem:>8s} repeat={repeat_idx} n={row['n_line_items']:>4d} "
                    f"native={row['native_cpu_s']:.4f}s fmu={row['fmu_cpu_s']:.4f}s "
                    f"rel_err={row['rel_error']:.3e}"
                )

        df = pd.DataFrame(rows).sort_values(["n_line_items", "repeat_idx"]).reset_index(drop=True)
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out_csv, index=False)

        grouped = _build_summary_by_size(df)
        args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
        grouped.to_csv(args.summary_csv, index=False)
        _plot_cpu_loglog(grouped, args.plot_png, args.plot_svg, args.linear_regime_min)

        linear_df = grouped[grouped["n_line_items"] >= int(args.linear_regime_min)]

        print("\nScaling benchmark complete")
        print(f"sizes           : {len(grouped)}")
        print(f"repeats/size    : {args.repeats}")
        print(f"rows            : {len(df)}")
        print(f"executed rows   : {executed}")
        print(f"reused rows     : {reused}")
        print(f"mean native cpu : {grouped['native_cpu_s_median'].mean():.4f} s")
        print(f"mean fmu cpu    : {grouped['fmu_cpu_s_median'].mean():.4f} s")
        print(f"max rel error   : {grouped['rel_error_median'].max():.3e}")
        if not linear_df.empty:
            print(f"linear n >=     : {int(args.linear_regime_min)}")
            print(f"linear points   : {len(linear_df)}")
            print(f"linear native   : {linear_df['native_cpu_s_median'].mean():.4f} s")
            print(f"linear fmu      : {linear_df['fmu_cpu_s_median'].mean():.4f} s")
        print(f"results csv     : {args.out_csv}")
        print(f"summary csv     : {args.summary_csv}")
        print(f"plot png        : {args.plot_png}")
        print(f"plot svg        : {args.plot_svg}")
        return 0
    except Exception as exc:
        err = str(exc)
        if _looks_like_missing_ecoinvent(err):
            print(f"Skipping scaling validation: {err}")
            return 0
        print(f"Scaling validation failed: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Co-simulation between a Modelica FMU and the Brightway LCA FMU -- *sequential* coupling of renewable sources to grid impact.

Coupling:
  fmu_modelica output (default: gri.P.real) -> fmu_brightway input (u)

Implementation:
  1) Simulate the Modelica FMU on a communication grid.
  2) Feed that output trajectory into the Brightway FMU as input u.

Because this coupling is one-way (no feedback from Brightway to Modelica),
this produces the same input-driven result as stepwise co-simulation.
"""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from fmpy import read_model_description, simulate_fmu


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEATHER_DIR = ROOT / "tests" / "resources" / "weatherdata"


@dataclass(frozen=True)
class CosimConfig:
    modelica_fmu: Path
    brightway_fmu: Path
    modelica_output: str
    brightway_input: str
    brightway_output: str
    weather_dir: Path
    start_time: float
    stop_time: float
    solver: str
    relative_tolerance: float
    power_scale: float
    save_plot: Path | None
    no_show: bool


def parse_args() -> CosimConfig:
    parser = argparse.ArgumentParser(
        description="Co-simulate Modelica and Brightway FMUs with one-way coupling."
    )
    parser.add_argument(
        "--modelica-fmu",
        type=Path,
        default=ROOT / "fmu" / "Buildings_Electrical_Examples_RenewableSources.fmu",
        help="Path to source Modelica FMU",
    )
    parser.add_argument(
        "--brightway-fmu",
        type=Path,
        default=ROOT / "fmu" / "Grid_Ipcc_v0.0.1.fmu",
        help="Path to target Brightway FMU",
    )
    parser.add_argument(
        "--modelica-output",
        default="gri.P.real",
        help="Modelica output variable name to feed into Brightway input",
    )
    parser.add_argument(
        "--brightway-input",
        default="u",
        help="Brightway input variable name",
    )
    parser.add_argument(
        "--brightway-output",
        default="y",
        help="Brightway output variable name",
    )
    parser.add_argument(
        "--weather-dir",
        type=Path,
        default=DEFAULT_WEATHER_DIR,
        help="Directory with weather files to inject into Modelica FMU resources/",
    )
    parser.add_argument("--start-time", type=float, default=0.0)
    parser.add_argument("--stop-time", type=float, default=24 * 3600.0)
    parser.add_argument(
        "--solver",
        type=str,
        default="cvode",
        help="Solver name passed to fmpy simulate_fmu for Modelica FMU (default: cvode)",
    )
    parser.add_argument(
        "--relative-tolerance",
        type=float,
        default=1e-6,
        help="Relative numerical tolerance for simulations (default: 1e-6)",
    )
    parser.add_argument(
        "--power-scale",
        type=float,
        default=1.0,
        help=(
            "Scale factor applied before setting Brightway input: "
            "u = modelica_output * power_scale"
        ),
    )
    parser.add_argument("--save-plot", type=Path, default=None)
    parser.add_argument("--no-show", action="store_true")

    args = parser.parse_args()

    modelica_fmu = args.modelica_fmu if args.modelica_fmu.is_absolute() else ROOT / args.modelica_fmu
    brightway_fmu = args.brightway_fmu if args.brightway_fmu.is_absolute() else ROOT / args.brightway_fmu
    weather_dir = args.weather_dir if args.weather_dir.is_absolute() else ROOT / args.weather_dir

    return CosimConfig(
        modelica_fmu=modelica_fmu,
        brightway_fmu=brightway_fmu,
        modelica_output=args.modelica_output,
        brightway_input=args.brightway_input,
        brightway_output=args.brightway_output,
        weather_dir=weather_dir,
        start_time=args.start_time,
        stop_time=args.stop_time,
        solver=args.solver,
        relative_tolerance=args.relative_tolerance,
        power_scale=args.power_scale,
        save_plot=args.save_plot,
        no_show=args.no_show,
    )


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def _build_temp_fmu_with_weather(fmu_path: Path, weather_dir: Path) -> Path:
    if not weather_dir.exists():
        raise FileNotFoundError(f"Weather directory not found: {weather_dir}")

    tmp = Path(tempfile.mkdtemp(prefix="renewable_cosim_modelica_"))
    out_fmu = tmp / fmu_path.name

    with zipfile.ZipFile(fmu_path, "r") as zin, zipfile.ZipFile(out_fmu, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))

        for wf in weather_dir.glob("*"):
            if wf.is_file():
                zout.write(wf, f"resources/{wf.name}")

    return out_fmu


def _validate_real_variable(md, var_name: str, role: str, preferred_causality: str | None = None) -> None:
    vars_by_name = {v.name: v for v in md.modelVariables}
    if var_name not in vars_by_name:
        available = [v.name for v in md.modelVariables if v.type == "Real"]
        preview = ", ".join(available[:20])
        raise KeyError(
            f"{role} variable '{var_name}' not found. "
            f"Available Real variables (first 20): {preview}"
        )

    var = vars_by_name[var_name]
    if var.type != "Real":
        raise TypeError(f"{role} variable '{var_name}' must be Real, got {var.type}")

    if preferred_causality and var.causality != preferred_causality:
        raise ValueError(
            f"{role} variable '{var_name}' has causality={var.causality}, "
            f"expected {preferred_causality}"
        )


def run_cosim(cfg: CosimConfig) -> dict[str, np.ndarray]:
    _require_file(cfg.modelica_fmu, "Modelica FMU")
    _require_file(cfg.brightway_fmu, "Brightway FMU")

    print("=" * 80)
    print("Renewable Sources Co-Simulation")
    print("=" * 80)
    print(f"Modelica FMU : {cfg.modelica_fmu}")
    print(f"Brightway FMU: {cfg.brightway_fmu}")
    print(f"Coupling     : {cfg.modelica_output} -> {cfg.brightway_input}")
    print(f"Weather dir  : {cfg.weather_dir}")
    print(f"Solver       : {cfg.solver}")
    print(f"Tolerance    : {cfg.relative_tolerance}")
    print(f"Power scale  : {cfg.power_scale}")
    print(f"Time         : {cfg.start_time} .. {cfg.stop_time} s")
    print("=" * 80)

    md_modelica = read_model_description(str(cfg.modelica_fmu))
    md_brightway = read_model_description(str(cfg.brightway_fmu))

    _validate_real_variable(md_modelica, cfg.modelica_output, "Modelica output")
    _validate_real_variable(md_brightway, cfg.brightway_input, "Brightway input", preferred_causality="input")
    _validate_real_variable(md_brightway, cfg.brightway_output, "Brightway output", preferred_causality="output")

    patched_modelica_fmu = _build_temp_fmu_with_weather(cfg.modelica_fmu, cfg.weather_dir)
    solver_name = "CVode" if cfg.solver.lower() == "cvode" else cfg.solver

    modelica_res = simulate_fmu(
        filename=str(patched_modelica_fmu),
        start_time=cfg.start_time,
        stop_time=cfg.stop_time,
        solver=solver_name,
        relative_tolerance=cfg.relative_tolerance,
        output=["time", cfg.modelica_output],
    )

    time_vals = np.array(modelica_res["time"], dtype=np.float64)
    modelica_vals = np.array(modelica_res[cfg.modelica_output], dtype=np.float64)
    bw_input_vals = modelica_vals * cfg.power_scale

    input_signal = np.zeros(
        len(time_vals),
        dtype=[("time", np.float64), (cfg.brightway_input, np.float64)],
    )
    input_signal["time"] = time_vals
    input_signal[cfg.brightway_input] = bw_input_vals

    brightway_res = simulate_fmu(
        filename=str(cfg.brightway_fmu),
        start_time=cfg.start_time,
        stop_time=cfg.stop_time,
        relative_tolerance=cfg.relative_tolerance,
        input=input_signal,
        output=["time", cfg.brightway_input, cfg.brightway_output],
    )

    return {
        "time": np.array(brightway_res["time"], dtype=np.float64),
        "modelica_output": modelica_vals,
        "brightway_input": np.array(brightway_res[cfg.brightway_input], dtype=np.float64),
        "brightway_output": np.array(brightway_res[cfg.brightway_output], dtype=np.float64),
    }


def _format_brightway_output_label(cfg: CosimConfig) -> str:
    var_name = cfg.brightway_output
    var_lower = var_name.lower()
    fmu_stem_lower = cfg.brightway_fmu.stem.lower()

    # Common case: default Brightway FMU output variable "y".
    if var_lower == "y":
        if "ipcc" in fmu_stem_lower:
            return "IPCC GWP [kg CO2-eq]"
        if "endpoint" in fmu_stem_lower:
            return "Endpoint impact score"
        if "midpoint" in fmu_stem_lower:
            return "Midpoint impact score"
        return "Impact score"

    if "gwp" in var_lower:
        return f"{var_name} [kg CO2-eq]"

    return f"{var_name} (impact output)"


def plot_results(cfg: CosimConfig, result: dict[str, np.ndarray]) -> None:
    t = result["time"]
    p = result["modelica_output"]
    u = result["brightway_input"]
    y = result["brightway_output"]

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    axes[0].plot(t, p, color="tab:blue", linewidth=1.8)
    axes[0].set_ylabel(cfg.modelica_output)
    axes[0].set_title("Modelica -> Brightway Co-Simulation")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t, u, color="tab:orange", linewidth=1.8)
    axes[1].set_ylabel(f"{cfg.brightway_input} (scaled)")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(t, y, color="tab:green", linewidth=2.0)
    axes[2].set_ylabel(_format_brightway_output_label(cfg))
    axes[2].set_xlabel("time [s]")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()

    if cfg.save_plot is not None:
        out = cfg.save_plot if cfg.save_plot.is_absolute() else ROOT / cfg.save_plot
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=160)
        print(f"✅ Plot saved: {out}")

    if cfg.no_show:
        plt.close(fig)
    else:
        plt.show()


def main() -> int:
    cfg = parse_args()
    try:
        result = run_cosim(cfg)
        print("✅ Co-simulation complete")
        print(f"   Samples           : {len(result['time'])}")
        print(f"   Final {cfg.brightway_output}: {result['brightway_output'][-1]:.6g}")
        plot_results(cfg, result)
        return 0
    except Exception as exc:
        print(f"❌ Co-simulation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

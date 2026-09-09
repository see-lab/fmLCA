#!/usr/bin/env python3
"""
run_fmu.py - Simulate a PythonFMU-generated FMU and plot {u,y} over time.

** This is for LCA generated FMUs only with input 'u' and output 'y' variables. **

This script follows the project CLI style used in scripts/create_fmu.py:
- Clear parameter declaration
- Path handling with pathlib
- Explicit logging and failure messages

Notes:
    pythonfmu is used to build FMUs in this project.
    Runtime simulation is performed with fmpy (FMI-compliant simulator).

Usage:
    python scripts/run_fmu.py
    python scripts/run_fmu.py --fmu fmu/Grid_Ipcc_v1.0.fmu
    python scripts/run_fmu.py --start-time 0 --stop-time 3600 --step-size 60 --u0 100
    python scripts/run_fmu.py --mode cosim --system-fmu fmu/PV_System_WECC.fmu --lca-fmu fmu/PvWecc_Ipcc_v1.0.fmu
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from fmpy import read_model_description
from fmpy import simulate_fmu


# ── Defaults (clear simulation parameters) ──────────────────────────────────

ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_FMU = ROOT / "fmu" / "Example_Ipcc_v1.0.fmu"


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for a single FMU simulation run."""

    start_time: float = 0.0
    stop_time: float = 3600.0
    step_size: float = 60.0
    input_u: float = 100.0


def require_file(path: Path, label: str) -> None:
    """Raise a clear error when a required file does not exist."""
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Simulate an FMU from fmu/ and plot input u and output y over time."
    )
    parser.add_argument(
        "--mode",
        choices=["single", "cosim"],
        default="single",
        help="single: simulate one FMU; cosim: sequential system->LCA co-simulation",
    )
    parser.add_argument(
        "--fmu",
        type=Path,
        default=DEFAULT_FMU,
        help=f"Path to FMU file (default: {DEFAULT_FMU.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--system-fmu",
        type=Path,
        default=None,
        help="Path to system FMU for --mode cosim",
    )
    parser.add_argument(
        "--lca-fmu",
        type=Path,
        default=None,
        help="Path to LCA FMU for --mode cosim",
    )
    parser.add_argument("--start-time", type=float, default=SimulationConfig.start_time)
    parser.add_argument("--stop-time", type=float, default=SimulationConfig.stop_time)
    parser.add_argument("--step-size", type=float, default=SimulationConfig.step_size)
    parser.add_argument(
        "--output-interval",
        type=float,
        default=3600.0,
        help="Output communication interval for --mode cosim",
    )
    parser.add_argument("--u0", type=float, default=SimulationConfig.input_u, help="Constant input u")
    parser.add_argument(
        "--system-output",
        type=str,
        default="gri.P.real",
        help="System FMU output variable to feed into LCA input for --mode cosim",
    )
    parser.add_argument(
        "--lca-input",
        type=str,
        default="u",
        help="LCA FMU input variable name for --mode cosim",
    )
    parser.add_argument(
        "--lca-output",
        type=str,
        default="y",
        help="LCA FMU output variable name for --mode cosim",
    )
    parser.add_argument(
        "--parameter-name",
        type=str,
        default=None,
        help="Optional shared FMU parameter name for --mode cosim",
    )
    parser.add_argument(
        "--parameter-value",
        type=float,
        default=None,
        help="Optional shared FMU parameter value for --mode cosim",
    )
    parser.add_argument(
        "--system-start-value",
        action="append",
        default=[],
        help="Extra system FMU start value as key=value (repeatable)",
    )
    parser.add_argument(
        "--lca-start-value",
        action="append",
        default=[],
        help="Extra LCA FMU start value as key=value (repeatable)",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="CVode",
        help="Solver for system FMU simulation in --mode cosim",
    )
    parser.add_argument(
        "--save-plot",
        type=Path,
        default=None,
        help="Optional output path for PNG figure (e.g., results/fmu_u_y.png)",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open the interactive plot window",
    )
    return parser.parse_args()


def validate_config(cfg: SimulationConfig) -> None:
    """Validate simulation configuration."""
    if cfg.stop_time <= cfg.start_time:
        raise ValueError("stop_time must be greater than start_time")
    if cfg.step_size <= 0.0:
        raise ValueError("step_size must be > 0")


def preflight_validate_fmu(fmu_path: Path) -> None:
    """Validate FMU variables and capabilities before running simulation."""
    model_description = read_model_description(str(fmu_path))

    if model_description.coSimulation is None:
        raise ValueError(
            "FMU does not declare Co-Simulation capability. "
            "This script requires an FMI Co-Simulation FMU."
        )

    variables = {v.name: v for v in model_description.modelVariables}
    missing_vars = [name for name in ("u", "y") if name not in variables]
    if missing_vars:
        available = ", ".join(sorted(variables.keys())) if variables else "<none>"
        raise ValueError(
            "FMU is missing required variables: "
            f"{', '.join(missing_vars)}. Available variables: {available}"
        )

    u_var = variables["u"]
    y_var = variables["y"]

    if u_var.causality != "input":
        raise ValueError(
            f"Variable 'u' must have causality='input' but is '{u_var.causality}'."
        )
    if y_var.causality != "output":
        raise ValueError(
            f"Variable 'y' must have causality='output' but is '{y_var.causality}'."
        )

    if getattr(u_var, "type", None) != "Real" or getattr(y_var, "type", None) != "Real":
        raise ValueError(
            "Variables 'u' and 'y' must both be Real type for this runner script."
        )

    if not model_description.coSimulation.canHandleVariableCommunicationStepSize:
        print(
            "⚠️  FMU capability: canHandleVariableCommunicationStepSize = false. "
            "Fixed communication step runs may be limited by the FMU implementation."
        )

    print("✅ Preflight check passed")
    print("   FMI type      : Co-Simulation")
    print(f"   FMI version   : {model_description.fmiVersion}")
    print(f"   model name    : {model_description.modelName}")
    print(f"   input         : u ({u_var.type}, causality={u_var.causality})")
    print(f"   output        : y ({y_var.type}, causality={y_var.causality})")


def inspect_fmu(fmu_path: Path, max_vars: int = 20) -> None:
    """Print a compact summary of FMU variables for notebook use."""
    require_file(fmu_path, "FMU")
    md = read_model_description(str(fmu_path))

    print(f"\n=== {fmu_path.name} ===")
    print(f"Model name: {md.modelName}")
    print(f"FMI version: {md.fmiVersion}")
    print(f"Co-Simulation: {md.coSimulation is not None}")

    vars_io = [
        v for v in md.modelVariables if v.causality in ("input", "output", "parameter")
    ]
    print(f"I/O/parameter variables shown: {min(len(vars_io), max_vars)} of {len(vars_io)}")
    for var in vars_io[:max_vars]:
        print(f"  - {var.causality:9s} {var.name}")


def _validate_real_variable(
    model_description,
    variable_name: str,
    role: str,
    preferred_causality: str | None = None,
) -> None:
    """Validate that a named variable exists and is Real-valued."""
    vars_by_name = {v.name: v for v in model_description.modelVariables}
    if variable_name not in vars_by_name:
        available = [v.name for v in model_description.modelVariables if v.type == "Real"]
        preview = ", ".join(available[:20]) if available else "<none>"
        raise KeyError(
            f"{role} variable '{variable_name}' not found. "
            f"Available Real variables (first 20): {preview}"
        )

    var = vars_by_name[variable_name]
    if var.type != "Real":
        raise TypeError(f"{role} variable '{variable_name}' must be Real, got {var.type}")

    if preferred_causality and var.causality != preferred_causality:
        raise ValueError(
            f"{role} variable '{variable_name}' has causality={var.causality}, "
            f"expected {preferred_causality}"
        )


def _parse_key_value_pairs(pairs: list[str], argument_name: str) -> dict[str, float]:
    """Parse repeated key=value CLI args into a float-valued dict."""
    parsed: dict[str, float] = {}
    for raw_item in pairs:
        if "=" not in raw_item:
            raise ValueError(
                f"Invalid {argument_name} '{raw_item}'. Expected key=value format."
            )
        key, raw_value = raw_item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid {argument_name} '{raw_item}'. Key cannot be empty.")
        try:
            parsed[key] = float(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid numeric value in {argument_name} '{raw_item}'."
            ) from exc
    return parsed


def simulate_system_fmu(
    fmu_path: Path,
    start_s: float,
    stop_s: float,
    outputs: list[str],
    output_interval_s: float,
    start_values: dict[str, float] | None = None,
    solver: str = "CVode",
    relative_tolerance: float = 1e-6,
) -> np.ndarray:
    """Simulate one system FMU and return its trajectory."""
    require_file(fmu_path, "system FMU")
    return simulate_fmu(
        filename=str(fmu_path),
        start_time=start_s,
        stop_time=stop_s,
        solver=solver,
        relative_tolerance=relative_tolerance,
        output_interval=output_interval_s,
        start_values=start_values or {},
        output=["time", *outputs],
    )


def sequential_cosim(
    system_fmu: Path,
    lca_fmu: Path,
    start_s: float,
    stop_s: float,
    system_output: str = "gri.P.real",
    lca_input: str = "u",
    lca_output: str = "y",
    parameter_name: str | None = None,
    parameter_value: float | None = None,
    system_start_values: dict[str, float] | None = None,
    lca_start_values: dict[str, float] | None = None,
    n_pv: float | None = None,
    output_interval_s: float = 3600.0,
    solver: str = "CVode",
    relative_tolerance: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    """Run one-way sequential co-simulation (system output -> LCA input).

    Parameters can be passed in three ways:
    1) Generic single parameter via (parameter_name, parameter_value)
    2) Per-FMU dictionaries via system_start_values and lca_start_values
    3) Legacy compatibility via n_pv (mapped to parameter 'n_pv' when used)
    """
    require_file(system_fmu, "system FMU")
    require_file(lca_fmu, "LCA FMU")

    if parameter_value is not None and not parameter_name:
        raise ValueError("parameter_name is required when parameter_value is provided")

    common_start_values: dict[str, float] = {}

    if parameter_name is not None:
        if parameter_value is None:
            raise ValueError("parameter_value is required when parameter_name is provided")
        common_start_values[parameter_name] = float(parameter_value)

    if n_pv is not None:
        # Backward compatibility for existing notebooks/scripts.
        common_start_values.setdefault("n_pv", float(n_pv))

    resolved_system_start_values = dict(common_start_values)
    resolved_system_start_values.update(system_start_values or {})

    resolved_lca_start_values = dict(common_start_values)
    resolved_lca_start_values.update(lca_start_values or {})

    md_system = read_model_description(str(system_fmu))
    md_lca = read_model_description(str(lca_fmu))
    _validate_real_variable(md_system, system_output, "System output")
    _validate_real_variable(md_lca, lca_input, "LCA input", preferred_causality="input")
    _validate_real_variable(md_lca, lca_output, "LCA output", preferred_causality="output")

    system_res = simulate_fmu(
        filename=str(system_fmu),
        start_time=start_s,
        stop_time=stop_s,
        solver=solver,
        relative_tolerance=relative_tolerance,
        output_interval=output_interval_s,
        start_values=resolved_system_start_values,
        output=["time", system_output],
    )

    signal = np.zeros(
        len(system_res),
        dtype=[("time", np.float64), (lca_input, np.float64)],
    )
    signal["time"] = system_res["time"]
    signal[lca_input] = np.array(system_res[system_output], dtype=np.float64)

    lca_res = simulate_fmu(
        filename=str(lca_fmu),
        start_time=start_s,
        stop_time=stop_s,
        output_interval=output_interval_s,
        start_values=resolved_lca_start_values,
        input=signal,
        output=["time", lca_input, lca_output],
    )

    return system_res, lca_res


def run_simulation(fmu_path: Path, cfg: SimulationConfig) -> np.ndarray:
    """Run FMU simulation and return result array with time, u, y."""
    if not fmu_path.exists():
        raise FileNotFoundError(f"FMU file not found: {fmu_path}")

    effective_u = cfg.input_u

    print("\n" + "=" * 70)
    print("FMU Simulation")
    print("=" * 70)
    print(f"FMU        : {fmu_path}")
    print(f"start_time : {cfg.start_time}")
    print(f"stop_time  : {cfg.stop_time}")
    print(f"step_size  : {cfg.step_size}")
    print(f"u0         : {effective_u}")
    print("=" * 70)

    preflight_validate_fmu(fmu_path=fmu_path)

    # Provide input 'u' as a time trajectory. FMI runtimes generally treat
    # inputs as time-varying signals, not start values.
    input_signal = np.array(
        [
            (cfg.start_time, effective_u),
            (cfg.stop_time, effective_u),
        ],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    result = simulate_fmu(
        filename=str(fmu_path),
        start_time=cfg.start_time,
        stop_time=cfg.stop_time,
        step_size=cfg.step_size,
        input=input_signal,
        output=["time", "u", "y"],
    )

    return result


def plot_results(result: np.ndarray, save_plot: Path | None, no_show: bool) -> None:
    """Plot u and y over time."""
    time = result["time"]
    u = result["u"]
    y = result["y"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.plot(time, u, color="tab:blue", linewidth=2.0)
    ax1.set_ylabel("u (input)")
    ax1.set_title("FMU Input and Output Over Time")
    ax1.grid(True, alpha=0.3)

    ax2.plot(time, y, color="tab:green", linewidth=2.0)
    ax2.set_xlabel("time [s]")
    ax2.set_ylabel("y (output)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_plot is not None:
        save_plot.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_plot, dpi=150)
        print(f"✅ Plot saved: {save_plot}")

    if no_show:
        plt.close(fig)
    else:
        plt.show()


def plot_cosim_results(
    lca_result: np.ndarray,
    lca_input: str,
    lca_output: str,
    save_plot: Path | None,
    no_show: bool,
) -> None:
    """Plot selected LCA input and output trajectories for co-simulation mode."""
    time = lca_result["time"]
    input_values = lca_result[lca_input]
    output_values = lca_result[lca_output]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.plot(time, input_values, color="tab:blue", linewidth=2.0)
    ax1.set_ylabel(f"{lca_input} (input)")
    ax1.set_title("Sequential Co-Simulation: LCA Input and Output")
    ax1.grid(True, alpha=0.3)

    ax2.plot(time, output_values, color="tab:green", linewidth=2.0)
    ax2.set_xlabel("time [s]")
    ax2.set_ylabel(f"{lca_output} (output)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_plot is not None:
        save_plot.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_plot, dpi=150)
        print(f"Plot saved: {save_plot}")

    if no_show:
        plt.close(fig)
    else:
        plt.show()


def main() -> int:
    """CLI entry point."""
    args = parse_args()

    fmu_path = args.fmu if args.fmu.is_absolute() else ROOT / args.fmu
    cfg = SimulationConfig(
        start_time=args.start_time,
        stop_time=args.stop_time,
        step_size=args.step_size,
        input_u=args.u0,
    )

    try:
        if args.mode == "single":
            validate_config(cfg)

            result = run_simulation(fmu_path=fmu_path, cfg=cfg)

            # Report delivered energy to make power-vs-energy interpretation explicit.
            time = np.array(result["time"], dtype=np.float64)
            u = np.array(result["u"], dtype=np.float64)
            energy_mwh = float(getattr(np, "trapezoid", np.trapz)(u, time) / 3.6e9)  # W*s -> J -> MWh
            print(
                f"Simulation complete: {len(result['time'])} points, "
                f"y_final = {result['y'][-1]:.6g}"
            )
            print(f"Delivered energy: {energy_mwh:.6g} MWh")
            plot_results(result=result, save_plot=args.save_plot, no_show=args.no_show)
            return 0

        if args.system_fmu is None or args.lca_fmu is None:
            raise ValueError("--system-fmu and --lca-fmu are required for --mode cosim")

        system_fmu = args.system_fmu if args.system_fmu.is_absolute() else ROOT / args.system_fmu
        lca_fmu = args.lca_fmu if args.lca_fmu.is_absolute() else ROOT / args.lca_fmu

        system_start_values = _parse_key_value_pairs(
            args.system_start_value,
            "--system-start-value",
        )
        lca_start_values = _parse_key_value_pairs(
            args.lca_start_value,
            "--lca-start-value",
        )

        _, lca_result = sequential_cosim(
            system_fmu=system_fmu,
            lca_fmu=lca_fmu,
            start_s=args.start_time,
            stop_s=args.stop_time,
            system_output=args.system_output,
            lca_input=args.lca_input,
            lca_output=args.lca_output,
            parameter_name=args.parameter_name,
            parameter_value=args.parameter_value,
            system_start_values=system_start_values,
            lca_start_values=lca_start_values,
            output_interval_s=args.output_interval,
            solver=args.solver,
        )

        time = np.array(lca_result["time"], dtype=np.float64)
        input_values = np.array(lca_result[args.lca_input], dtype=np.float64)
        output_values = np.array(lca_result[args.lca_output], dtype=np.float64)
        energy_mwh = float(np.trapezoid(input_values, time) / 3.6e9)

        print(
            f"Co-simulation complete: {len(time)} points, "
            f"{args.lca_output}_final = {output_values[-1]:.6g}"
        )
        print(f"Delivered energy via {args.lca_input}: {energy_mwh:.6g} MWh")
        plot_cosim_results(
            lca_result=lca_result,
            lca_input=args.lca_input,
            lca_output=args.lca_output,
            save_plot=args.save_plot,
            no_show=args.no_show,
        )
        return 0

    except Exception as exc:
        print(f"Simulation failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

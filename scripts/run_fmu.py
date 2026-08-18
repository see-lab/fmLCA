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


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Simulate an FMU from fmu/ and plot input u and output y over time."
    )
    parser.add_argument(
        "--fmu",
        type=Path,
        default=DEFAULT_FMU,
        help=f"Path to FMU file (default: {DEFAULT_FMU.relative_to(ROOT)})",
    )
    parser.add_argument("--start-time", type=float, default=SimulationConfig.start_time)
    parser.add_argument("--stop-time", type=float, default=SimulationConfig.stop_time)
    parser.add_argument("--step-size", type=float, default=SimulationConfig.step_size)
    parser.add_argument("--u0", type=float, default=SimulationConfig.input_u, help="Constant input u")
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
        validate_config(cfg)

        result = run_simulation(fmu_path=fmu_path, cfg=cfg)

        # Report delivered energy to make power-vs-energy interpretation explicit.
        time = np.array(result["time"], dtype=np.float64)
        u = np.array(result["u"], dtype=np.float64)
        energy_mwh = float(np.trapezoid(u, time) / 3.6e9)  # W*s -> J -> MWh
        print(
            f"✅ Simulation complete: {len(result['time'])} points, "
            f"y_final = {result['y'][-1]:.6g}"
        )
        print(f"   Delivered energy: {energy_mwh:.6g} MWh")
        plot_results(result=result, save_plot=args.save_plot, no_show=args.no_show)
        return 0

    except Exception as exc:
        print(f"❌ Simulation failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

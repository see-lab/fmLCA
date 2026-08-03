#!/usr/bin/env python3
"""FMI-style standalone test for the Renewable Sources FMU.

Uses fmpy.simulate_fmu and injects required weather files into a temporary FMU
copy at runtime so the model can initialize consistently across machines.
"""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pytest
from fmpy import read_model_description, simulate_fmu

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FMU = ROOT / "fmu" / "Buildings_Electrical_Examples_RenewableSources.fmu"
DEFAULT_WEATHER_DIR = ROOT / "tests" / "resources" / "weatherdata"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Renewable Sources FMU standalone test.")
    p.add_argument("--fmu", type=Path, default=DEFAULT_FMU)
    p.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    p.add_argument("--start-time", type=float, default=0.0)
    p.add_argument("--stop-time", type=float, default=24.0 * 3600.0 * 7)
    p.add_argument(
        "--solver",
        type=str,
        default="cvode",
        help="Solver name passed to fmpy simulate_fmu (default: cvode)",
    )
    p.add_argument("--relative-tolerance", type=float, default=1e-6)
    p.add_argument("--outputs", nargs="+", default=["CPUtime", "weaBus.HGloHor", "gri.P.real"])
    p.add_argument("--save-plot", type=Path, default=ROOT / "results" / "renewable_sources_test.png")
    p.add_argument("--save-csv", type=Path, default=None)
    p.add_argument("--no-show", action="store_true")
    p.add_argument("--list-real-outputs", action="store_true")
    return p.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def real_outputs(md) -> list[str]:
    return [v.name for v in md.modelVariables if v.type == "Real" and v.causality == "output"]


def validate_outputs(md, outputs: list[str]) -> None:
    vars_by_name = {v.name: v for v in md.modelVariables}
    bad = [n for n in outputs if n not in vars_by_name or vars_by_name[n].type != "Real"]
    if bad:
        avail = ", ".join(real_outputs(md)[:25])
        raise ValueError(f"Invalid output(s): {bad}. Available Real outputs (first 25): {avail}")


def build_temp_fmu_with_weather(fmu_path: Path, weather_dir: Path) -> Path:
    if not weather_dir.exists():
        raise FileNotFoundError(f"Weather directory not found: {weather_dir}")

    tmp = Path(tempfile.mkdtemp(prefix="renewable_fmu_"))
    out_fmu = tmp / fmu_path.name

    with zipfile.ZipFile(fmu_path, "r") as zin, zipfile.ZipFile(out_fmu, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))

        for wf in weather_dir.glob("*"):
            if wf.is_file():
                zout.write(wf, f"resources/{wf.name}")

    return out_fmu


def simulate(args: argparse.Namespace) -> np.ndarray:
    fmu_path = resolve_path(args.fmu)
    weather_dir = resolve_path(args.weather_dir)

    if not fmu_path.exists():
        raise FileNotFoundError(f"FMU not found: {fmu_path}")

    md = read_model_description(str(fmu_path))
    if md.coSimulation is None:
        raise ValueError("FMU does not declare Co-Simulation capability")

    if args.list_real_outputs:
        print("Exported Real outputs:")
        for name in real_outputs(md):
            print(f"  - {name}")
        return np.array([])

    validate_outputs(md, args.outputs)

    patched_fmu = build_temp_fmu_with_weather(fmu_path, weather_dir)

    # fmpy expects canonical CVode casing.
    solver_name = "CVode" if args.solver.lower() == "cvode" else args.solver

    return simulate_fmu(
        filename=str(patched_fmu),
        start_time=args.start_time,
        stop_time=args.stop_time,
        solver=solver_name,
        relative_tolerance=args.relative_tolerance,
        output=["time", *args.outputs],
    )


def main() -> int:
    args = parse_args()

    try:
        result = simulate(args)
        if args.list_real_outputs:
            return 0

        print("✅ Simulation completed")
        print(f"samples: {len(result['time'])}")

        t = np.array(result["time"], dtype=np.float64)
        fig, axes = plt.subplots(len(args.outputs), 1, figsize=(11, 2.8 * len(args.outputs)), sharex=True)
        if len(args.outputs) == 1:
            axes = [axes]

        for ax, name in zip(axes, args.outputs):
            y = np.array(result[name], dtype=np.float64)
            print(f"  {name:20s} min={y.min():.6g} max={y.max():.6g} final={y[-1]:.6g}")
            ax.plot(t, y, linewidth=1.7)
            ax.set_ylabel(name)
            ax.grid(True, alpha=0.3)

        axes[-1].set_xlabel("time [s]")
        fig.suptitle("Renewable Sources FMU Standalone Test", fontsize=13)
        fig.tight_layout()

        if args.save_plot is not None:
            out = resolve_path(args.save_plot)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out, dpi=170)
            print(f"✅ Plot saved: {out}")

        if args.save_csv is not None:
            out_csv = resolve_path(args.save_csv)
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            data = np.column_stack([np.array(result["time"], dtype=np.float64)] + [np.array(result[n], dtype=np.float64) for n in args.outputs])
            np.savetxt(out_csv, data, delimiter=",", header=",".join(["time", *args.outputs]), comments="")
            print(f"✅ CSV saved: {out_csv}")

        if args.no_show:
            plt.close(fig)
        else:
            plt.show()

        return 0
    except Exception as exc:
        print(f"❌ Simulation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


def test_resolve_path_handles_relative_and_absolute(tmp_path: Path) -> None:
    rel = Path("results/out.png")
    assert resolve_path(rel) == ROOT / rel

    abs_path = tmp_path / "out.png"
    assert resolve_path(abs_path) == abs_path


def test_real_outputs_filters_only_real_outputs() -> None:
    md = SimpleNamespace(
        modelVariables=[
            SimpleNamespace(name="real_out", type="Real", causality="output"),
            SimpleNamespace(name="real_in", type="Real", causality="input"),
            SimpleNamespace(name="int_out", type="Integer", causality="output"),
        ]
    )
    assert real_outputs(md) == ["real_out"]


def test_validate_outputs_accepts_real_outputs() -> None:
    md = SimpleNamespace(
        modelVariables=[
            SimpleNamespace(name="CPUtime", type="Real", causality="output"),
            SimpleNamespace(name="gri.P.real", type="Real", causality="output"),
        ]
    )
    validate_outputs(md, ["CPUtime", "gri.P.real"])


def test_validate_outputs_rejects_non_real_or_unknown_output() -> None:
    md = SimpleNamespace(
        modelVariables=[
            SimpleNamespace(name="CPUtime", type="Real", causality="output"),
            SimpleNamespace(name="status", type="Integer", causality="output"),
        ]
    )

    with pytest.raises(ValueError, match="Invalid output"):
        validate_outputs(md, ["CPUtime", "status", "missing"])


def test_build_temp_fmu_with_weather_injects_resource_files(tmp_path: Path) -> None:
    fmu_path = tmp_path / "dummy.fmu"
    with zipfile.ZipFile(fmu_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modelDescription.xml", "<fmiModelDescription />")
        zf.writestr("binaries/win64/model.dll", "binary")

    weather_dir = tmp_path / "weather"
    weather_dir.mkdir()
    (weather_dir / "USA_CA_San.Francisco.epw").write_text("epw data", encoding="utf-8")
    (weather_dir / "USA_CA_San.Francisco.mos").write_text("mos data", encoding="utf-8")

    patched_fmu = build_temp_fmu_with_weather(fmu_path, weather_dir)

    with zipfile.ZipFile(patched_fmu, "r") as zf:
        names = set(zf.namelist())

    assert "modelDescription.xml" in names
    assert "binaries/win64/model.dll" in names
    assert "resources/USA_CA_San.Francisco.epw" in names
    assert "resources/USA_CA_San.Francisco.mos" in names


def test_build_temp_fmu_with_weather_requires_existing_weather_dir(tmp_path: Path) -> None:
    fmu_path = tmp_path / "dummy.fmu"
    with zipfile.ZipFile(fmu_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modelDescription.xml", "<fmiModelDescription />")

    with pytest.raises(FileNotFoundError, match="Weather directory not found"):
        build_temp_fmu_with_weather(fmu_path, tmp_path / "missing-weather")

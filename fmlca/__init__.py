from __future__ import annotations

from pathlib import Path
from typing import Any

from src import (
    BlackboxComplianceError,
    BuildOptions,
    BuildResult,
    FmuBuildError,
    FmuPackagingError,
    FmuValidationError,
    LcaRunError,
    LciFileNotFoundError,
    MethodConfigError,
    ParameterLinearityError,
    build_lca_fmu,
    build_lca_fmu_internal,
    create_fmu,
)


def csv_to_json_translator(
    csv_files: str | list[str],
    output_file: str | Path | None = None,
) -> dict[str, Any] | None:
    from scripts.csv_to_json_translator import convert_csv_to_lci_json

    return convert_csv_to_lci_json(csv_files, output_file)


def lca_engine(
    lci_file: str | Path,
    lcia_methods: list[str],
    parameter_values: dict[str, float] | None = None,
    functional_unit: dict[str, Any] | None = None,
    energy_amount_mj: float = 180.0,
    brightway_project: str | None = None,
    confirm_project_switch: bool = True,
) -> dict[str, Any]:
    from fmlca.lca_engine import run_lca

    return run_lca(
        lci_file=str(lci_file),
        lcia_methods=lcia_methods,
        parameter_values=parameter_values,
        functional_unit=functional_unit or {},
        energy_amount_mj=energy_amount_mj,
        brightway_project=brightway_project,
        confirm_project_switch=confirm_project_switch,
    )


def run_fmu(
    fmu_path: str | Path,
    start_time: float = 0.0,
    stop_time: float = 3600.0,
    step_size: float = 60.0,
    input_u: float = 100.0,
):
    from scripts.run_fmu import SimulationConfig, run_simulation

    cfg = SimulationConfig(
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        input_u=input_u,
    )
    return run_simulation(Path(fmu_path), cfg)


__all__ = [
    "build_lca_fmu",
    "build_lca_fmu_internal",
    "create_fmu",
    "BuildOptions",
    "BuildResult",
    "FmuBuildError",
    "LciFileNotFoundError",
    "MethodConfigError",
    "LcaRunError",
    "FmuPackagingError",
    "BlackboxComplianceError",
    "FmuValidationError",
    "ParameterLinearityError",
    "csv_to_json_translator",
    "lca_engine",
    "run_fmu",
]

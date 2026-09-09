from __future__ import annotations

import json
import math
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    from .fmu_generator import (
        audit_fmu_blackbox,
        build_fmu_with_pythonfmu,
        extract_emission_factors,
        extract_stage_impacts,
        fix_fmu_metadata,
        generate_fmu_class_code,
        package_fmu_as_bytecode,
        validate_fmu,
    )
    from .lca_utils import ensure_dir_exists, safe_classname
except ImportError:
    from fmu_generator import (
        audit_fmu_blackbox,
        build_fmu_with_pythonfmu,
        extract_emission_factors,
        extract_stage_impacts,
        fix_fmu_metadata,
        generate_fmu_class_code,
        package_fmu_as_bytecode,
        validate_fmu,
    )
    from lca_utils import ensure_dir_exists, safe_classname

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "fmu"

METHOD_CONFIG: dict[str, dict[str, Any]] = {
    "ipcc": {
        "keywords": ["IPCC 2021 climate change total excl biogenic GWP100"],
        "output_var": "climate_change_kg_co2_eq",
        "output_unit": "kg CO2-eq",
        "output_label": "Climate Change (IPCC 2021, excl. biogenic CO2)",
        "single_score": False,
    },
    "recipe_endpoint": {
        "keywords": [
            "ReCiPe 2016 endpoint (H) total human health",
            "ReCiPe 2016 endpoint (H) total ecosystem quality",
            "ReCiPe 2016 endpoint (H) total natural resources",
        ],
        "output_var": "single_score_pt",
        "output_unit": "Pt",
        "output_label": "ReCiPe 2016 Endpoint H/A Single Score",
        "single_score": True,
    },
}


class FmuBuildError(RuntimeError):
    """Base class for FMU build errors."""


class LciFileNotFoundError(FmuBuildError):
    """Raised when the LCI file is not found."""


class MethodConfigError(FmuBuildError):
    """Raised when the method configuration is invalid."""


class LcaRunError(FmuBuildError):
    """Raised when the LCA run fails."""


class FmuPackagingError(FmuBuildError):
    """Raised when FMU build/packaging fails."""


class BlackboxComplianceError(FmuBuildError):
    """Raised when black-box compliance fails under enforce policy."""


class FmuValidationError(FmuBuildError):
    """Raised when FMU validation fails."""


class ParameterLinearityError(FmuBuildError):
    """Raised when parameter linearity verification fails."""


@dataclass
class BuildOptions:
    method: Literal["ipcc", "recipe_endpoint"] = "ipcc"
    version: str = "0.0.1"
    name: str | None = None
    output_dir: Path | None = None
    target_tool: Literal["generic", "dymola"] = "generic"
    export_mode: Literal["source", "bytecode"] = "bytecode"
    blackbox_policy: Literal["enforce", "warn", "off"] = "enforce"
    default_step_size: float = 60.0
    parameter_values: dict[str, float] | None = None
    functional_unit: dict | None = None
    energy_amount_mj: float | None = None
    validate: bool = True
    verify_linearity: bool = True
    move_to_output_dir: bool = True
    verbose: bool = True
    brightway_project: str | None = None
    confirm_project_switch: bool = True


@dataclass
class BuildResult:
    ok: bool
    final_fmu_path: Path
    simulatable_fmu_path: Path | None
    method: str
    version: str
    class_name: str
    fmu_name: str
    output_var: str
    output_unit: str
    lca_method_keywords: list[str]
    stage_impacts: dict[str, float]
    factors: dict[str, float]
    parameter_defaults: dict[str, float]
    parameter_model: dict[str, Any]
    blackbox_ok: bool | None
    blackbox_message: str | None
    validation_ok: bool | None
    validation_message: str | None
    linearity_ok: bool | None
    linearity_message: str | None
    warnings: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


def _log(logs: list[str], message: str, verbose: bool) -> None:
    logs.append(message)
    if verbose:
        print(message)


def _resolve_lci_parameters(lci_data: dict[str, Any]) -> dict[str, float]:
    params = lci_data.get("parameters", {})
    resolved: dict[str, float] = {}
    for name, meta in params.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)):
            raise MethodConfigError(f"Unsupported parameter name '{name}' for FMU variable export")
        default = 1.0
        if isinstance(meta, dict):
            default = float(meta.get("default", 1.0))
        resolved[str(name)] = default
    return resolved


def _resolve_one_base_unit_mj(lci_data: dict[str, Any], default_mj: float = 1.0) -> tuple[float, str]:
    base_unit_raw = (
        lci_data.get("energy_metadata", {})
        .get("primary_input", {})
        .get("unit", "MJ")
    )
    base_unit = str(base_unit_raw or "MJ").strip().upper()

    unit_to_mj = {
        "J": 1.0e-6,
        "WH": 3.6e-3,
        "KWH": 3.6,
        "MWH": 3600.0,
        "MJ": 1.0,
        "GJ": 1000.0,
        "TJ": 1.0e6,
    }

    if base_unit not in unit_to_mj:
        return default_mj, "MJ"

    return unit_to_mj[base_unit], base_unit


def _run_lca_analysis(
    lci_file: Path,
    energy_mj: float,
    keywords: list[str],
    options: BuildOptions,
) -> dict[str, Any]:
    def _resolve_run_lca():
        try:
            from .lca_engine import run_lca as _run_lca
        except ImportError:
            from lca_engine import run_lca as _run_lca
        return _run_lca

    run_lca_fn = _resolve_run_lca()

    run_kwargs = {
        "lci_file": str(lci_file),
        "lcia_methods": keywords,
        "parameter_values": options.parameter_values,
        "functional_unit": options.functional_unit or {},
        "energy_amount_mj": energy_mj,
        "brightway_project": options.brightway_project,
        "confirm_project_switch": options.confirm_project_switch,
    }
    try:
        try:
            results = run_lca_fn(**run_kwargs)
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            run_kwargs.pop("brightway_project", None)
            run_kwargs.pop("confirm_project_switch", None)
            results = run_lca_fn(**run_kwargs)
    except Exception as exc:
        raise LcaRunError(f"LCA analysis execution failed: {exc}") from exc

    if isinstance(results, dict) and "error" in results:
        raise LcaRunError(str(results.get("error", "Unknown LCA error")))

    return results


def _build_parameter_model(
    lci_path: Path,
    method_cfg: dict[str, Any],
    unitary_energy_mj: float,
    baseline_factors: dict[str, Any],
    baseline_stage_impacts: dict[str, float],
    parameter_defaults: dict[str, float],
    options: BuildOptions,
) -> dict[str, Any]:
    if not parameter_defaults:
        return {"defaults": {}, "slopes": {}, "stability": {"kappa": 1.0, "ill_conditioned": False}}

    def _choose_safe_delta(default: float) -> float:
        magnitude = abs(default)
        delta = max(0.5 * magnitude, 0.25)
        cap = max(2.0 * magnitude, 2.0)
        delta = min(delta, cap)
        return max(delta, 1.0e-6)

    slopes = {
        "production": {},
        "transport": {},
        "eol": {},
        "use_rate_per_j": {},
    }

    baseline_use_rate = baseline_factors["energy_factor"] / 1.0e6

    for pname, default in parameter_defaults.items():
        delta = _choose_safe_delta(default)
        varied = default + delta
        if math.isclose(varied, default, rel_tol=0.0, abs_tol=1.0e-12):
            varied = default + 1.0

        overrides = dict(parameter_defaults)
        overrides[pname] = varied

        varied_options = BuildOptions(**{**options.__dict__, "parameter_values": overrides})
        varied_results = _run_lca_analysis(
            lci_path,
            unitary_energy_mj,
            method_cfg["keywords"],
            varied_options,
        )
        varied_factors = extract_emission_factors(varied_results, method_cfg, unitary_energy_mj)
        varied_stage = extract_stage_impacts(varied_results, method_cfg)

        denom = varied - default
        slopes["production"][pname] = (varied_stage["production"] - baseline_stage_impacts["production"]) / denom
        slopes["transport"][pname] = (varied_stage["transport"] - baseline_stage_impacts["transport"]) / denom
        slopes["eol"][pname] = (varied_stage["eol"] - baseline_stage_impacts["eol"]) / denom
        slopes["use_rate_per_j"][pname] = ((varied_factors["energy_factor"] / 1.0e6) - baseline_use_rate) / denom

    stability = {"kappa": 1.0, "ill_conditioned": False}
    try:
        import numpy as np

        ordered_params = list(parameter_defaults.keys())
        slope_matrix = np.array(
            [
                [slopes["production"][p] for p in ordered_params],
                [slopes["transport"][p] for p in ordered_params],
                [slopes["eol"][p] for p in ordered_params],
                [slopes["use_rate_per_j"][p] for p in ordered_params],
            ],
            dtype=float,
        )

        singular_values = np.linalg.svd(slope_matrix, compute_uv=False)
        if singular_values.size == 0:
            kappa = 1.0
        else:
            s_max = float(np.max(singular_values))
            positive = singular_values[singular_values > max(1.0e-14 * s_max, 1.0e-18)]
            s_min = float(np.min(positive)) if positive.size else 0.0
            kappa = float("inf") if s_min == 0.0 else s_max / s_min

        stability["kappa"] = kappa
        stability["ill_conditioned"] = bool(not np.isfinite(kappa) or kappa > 1.0e8)
    except Exception:
        pass

    return {
        "defaults": parameter_defaults,
        "slopes": slopes,
        "stability": stability,
    }


def _verify_fmu_parameter_linearity(
    fmu_path: Path,
    parameter_defaults: dict[str, float],
    tolerance: float = 1e-4,
) -> tuple[bool, str]:
    if not parameter_defaults:
        return True, "No LCI parameters found; linearity check skipped"

    import numpy as np
    from fmpy import simulate_fmu

    input_signal = np.array(
        [(0.0, 100.0), (3600.0, 100.0)],
        dtype=[("time", np.float64), ("u", np.float64)],
    )

    def _run(start_values: dict[str, float]) -> float:
        result = simulate_fmu(
            filename=str(fmu_path),
            start_time=0.0,
            stop_time=3600.0,
            step_size=60.0,
            input=input_signal,
            start_values=start_values,
            output=["y"],
        )
        return float(result["y"][-1])

    baseline_y = _run(dict(parameter_defaults))

    for pname, default in parameter_defaults.items():
        step = max(abs(default), 1.0)

        varied_values_1 = dict(parameter_defaults)
        varied_values_2 = dict(parameter_defaults)
        varied_values_1[pname] = default + step
        varied_values_2[pname] = default + 2.0 * step

        y1 = _run(varied_values_1)
        y2 = _run(varied_values_2)

        d1 = y1 - baseline_y
        d2 = y2 - y1
        resid = abs(d2 - d1)
        scale = max(abs(y2), abs(y1), abs(baseline_y), 1.0)
        rel_err = resid / scale

        if rel_err > tolerance:
            return False, (
                f"Parameter '{pname}' linearity check failed "
                f"(increment mismatch d1={d1:.6e}, d2={d2:.6e}, resid={resid:.3e}, "
                f"rel_error={rel_err:.3e}, tolerance={tolerance:.1e})"
            )

    return True, "FMU parameter linearity verified"


def build_lca_fmu_internal(lci_path: Path, options: BuildOptions) -> BuildResult:
    warnings: list[str] = []
    logs: list[str] = []

    lci_path = Path(lci_path)
    if not lci_path.exists():
        raise LciFileNotFoundError(f"LCI file not found: {lci_path}")

    method_cfg = METHOD_CONFIG.get(options.method)
    if method_cfg is None:
        raise MethodConfigError(
            f"Unsupported method '{options.method}'. Supported methods: {', '.join(METHOD_CONFIG.keys())}"
        )

    if options.default_step_size <= 0.0:
        raise MethodConfigError("default_step_size must be > 0")

    if options.export_mode == "source" and options.blackbox_policy == "enforce":
        raise MethodConfigError(
            "export_mode='source' conflicts with blackbox_policy='enforce'. "
            "Use blackbox_policy='warn' or 'off', or use export_mode='bytecode'."
        )

    try:
        with open(lci_path, "r", encoding="utf-8") as f:
            lci_data = json.load(f)
    except Exception as exc:
        raise LciFileNotFoundError(f"Failed to read LCI JSON '{lci_path}': {exc}") from exc

    output_dir = Path(options.output_dir) if options.output_dir is not None else DEFAULT_OUTPUT_DIR
    ensure_dir_exists(output_dir)

    stem = lci_path.stem
    method_label = options.method.replace("_", " ").title().replace(" ", "_")
    fmu_name = options.name or f"{safe_classname(stem)}_{method_label}_v{options.version}"
    class_name = safe_classname(fmu_name)

    unitary_energy_mj, base_energy_unit = _resolve_one_base_unit_mj(lci_data, default_mj=1.0)
    energy_mj = options.energy_amount_mj if options.energy_amount_mj is not None else unitary_energy_mj
    parameter_defaults = _resolve_lci_parameters(lci_data)

    _log(logs, f"Creating FMU: {fmu_name}", options.verbose)
    _log(logs, f"LCI file: {lci_path}", options.verbose)
    _log(logs, f"Method: {options.method}", options.verbose)

    lca_results = _run_lca_analysis(
        lci_file=lci_path,
        energy_mj=energy_mj,
        keywords=method_cfg["keywords"],
        options=options,
    )

    factors = extract_emission_factors(lca_results, method_cfg, energy_mj)
    stage_impacts = extract_stage_impacts(lca_results, method_cfg)

    parameter_model = _build_parameter_model(
        lci_path=lci_path,
        method_cfg=method_cfg,
        unitary_energy_mj=energy_mj,
        baseline_factors=factors,
        baseline_stage_impacts=stage_impacts,
        parameter_defaults=parameter_defaults,
        options=options,
    )

    simulatable_path = output_dir / f"{fmu_name}_Simulatable.fmu"
    final_path = output_dir / f"{fmu_name}.fmu"

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            class_code = generate_fmu_class_code(
                class_name=class_name,
                fmu_name=fmu_name,
                method_config=method_cfg,
                factors=factors,
                stage_impacts=stage_impacts,
                parameter_model=parameter_model,
                lci_path=lci_path,
            )
            python_file = tmp_dir_path / f"{class_name}.py"
            python_file.write_text(class_code, encoding="utf-8")

            build_fmu_with_pythonfmu(python_file, simulatable_path)

        fix_fmu_metadata(
            fmu_path=simulatable_path,
            output_path=final_path,
            output_var="y",
            output_unit=method_cfg["output_unit"],
            output_description=f"Cumulative {method_cfg['output_label']}",
            input_var="u",
            input_unit="W",
            default_step_size=options.default_step_size,
        )

        if options.export_mode == "bytecode":
            package_fmu_as_bytecode(final_path)
    except Exception as exc:
        raise FmuPackagingError(f"FMU build or packaging failed: {exc}") from exc

    blackbox_ok: bool | None = None
    blackbox_message: str | None = None
    if options.blackbox_policy != "off":
        blackbox_ok, blackbox_message = audit_fmu_blackbox(final_path)
        if not blackbox_ok and options.blackbox_policy == "enforce":
            try:
                final_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise BlackboxComplianceError(blackbox_message or "Black-box compliance failed")

    validation_ok: bool | None = None
    validation_message: str | None = None
    if options.validate:
        validation_ok, validation_message = validate_fmu(final_path)
        if not validation_ok:
            raise FmuValidationError(validation_message or "FMU validation failed")

    linearity_ok: bool | None = None
    linearity_message: str | None = None
    if options.verify_linearity:
        linearity_ok, linearity_message = _verify_fmu_parameter_linearity(final_path, parameter_defaults)
        if not linearity_ok:
            raise ParameterLinearityError(linearity_message or "FMU parameter linearity verification failed")

    try:
        simulatable_path.unlink(missing_ok=True)
        simulatable_out: Path | None = None
    except Exception as exc:
        simulatable_out = simulatable_path
        warning = f"Could not remove intermediate FMU '{simulatable_path.name}': {exc}"
        warnings.append(warning)
        _log(logs, warning, options.verbose)

    if options.output_dir is not None and not options.move_to_output_dir:
        warning = "move_to_output_dir=False is ignored when output_dir is provided by API contract"
        warnings.append(warning)
        _log(logs, warning, options.verbose)

    _log(
        logs,
        (
            f"Use rate: {(factors['energy_factor'] * unitary_energy_mj):.6e} "
            f"{method_cfg['output_unit']}/{base_energy_unit}"
        ),
        options.verbose,
    )

    return BuildResult(
        ok=True,
        final_fmu_path=final_path,
        simulatable_fmu_path=simulatable_out,
        method=options.method,
        version=options.version,
        class_name=class_name,
        fmu_name=fmu_name,
        output_var=method_cfg["output_var"],
        output_unit=method_cfg["output_unit"],
        lca_method_keywords=list(method_cfg["keywords"]),
        stage_impacts=stage_impacts,
        factors={
            "base_impact": float(factors.get("base_impact", 0.0)),
            "energy_factor": float(factors.get("energy_factor", 0.0)),
            "scaling_factor": float(factors.get("scaling_factor", 1.0)),
        },
        parameter_defaults=parameter_defaults,
        parameter_model=parameter_model,
        blackbox_ok=blackbox_ok,
        blackbox_message=blackbox_message,
        validation_ok=validation_ok,
        validation_message=validation_message,
        linearity_ok=linearity_ok,
        linearity_message=linearity_message,
        warnings=warnings,
        logs=logs,
    )


def build_lca_fmu(
    lci_file: str | Path,
    method: str = "ipcc",
    version: str = "0.0.1",
    output_dir: str | Path | None = None,
    name: str | None = None,
    target_tool: str = "generic",
    export_mode: str = "bytecode",
    blackbox_policy: str = "enforce",
    default_step_size: float = 60.0,
    parameter_values: dict[str, float] | None = None,
    functional_unit: dict | None = None,
    energy_amount_mj: float | None = None,
    validate: bool = True,
    verify_linearity: bool = True,
    move_to_output_dir: bool = True,
    verbose: bool = True,
    brightway_project: str | None = None,
    confirm_project_switch: bool = True,
) -> BuildResult:
    options = BuildOptions(
        method=method,  # type: ignore[arg-type]
        version=version,
        name=name,
        output_dir=Path(output_dir) if output_dir is not None else None,
        target_tool=target_tool,  # type: ignore[arg-type]
        export_mode=export_mode,  # type: ignore[arg-type]
        blackbox_policy=blackbox_policy,  # type: ignore[arg-type]
        default_step_size=default_step_size,
        parameter_values=parameter_values,
        functional_unit=functional_unit,
        energy_amount_mj=energy_amount_mj,
        validate=validate,
        verify_linearity=verify_linearity,
        move_to_output_dir=move_to_output_dir,
        verbose=verbose,
        brightway_project=brightway_project,
        confirm_project_switch=confirm_project_switch,
    )
    return build_lca_fmu_internal(Path(lci_file), options)


def create_fmu(
    lci_file: str | Path,
    output_dir: str | Path,
    method: str = "ipcc",
    version: str = "0.0.1",
    name: str | None = None,
) -> Path:
    result = build_lca_fmu(
        lci_file=lci_file,
        output_dir=output_dir,
        method=method,
        version=version,
        name=name,
        export_mode="bytecode",
        blackbox_policy="enforce",
        validate=True,
        verify_linearity=True,
        verbose=True,
    )
    return result.final_fmu_path

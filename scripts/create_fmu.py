#!/usr/bin/env python3
"""
create_fmu.py  –  CLI script to build production-ready LCA FMUs.

Creates FMUs with cumulative impact tracking using pre-computed emission factors.

Workflow
--------
1. Run the LCA engine against an LCI JSON file to extract emission factors.
2. Generate a PythonFMU secondary class from those factors.
3. Build the FMU with `pythonfmu build` (produces *_Simulatable.fmu).
4. Fix ModelDescription/InitialUnknowns (produces final FMU).
5. Optionally convert resource Python source into bytecode-only payload.
6. Run black-box compliance audit (enforce/warn/off policy).
7. Validate the final FMU with fmpy.
8. Delete the intermediate *_Simulatable.fmu so only the final FMU remains.

FMU Architecture
----------------
  The FMU uses pre-computed emission factors for fast calculation:
  - Factor = impact / energy (e.g., kg CO2-eq / MJ)
  - Converted to impact/MWh for power-based integration
  - Cumulative tracking: y = Production + Transport + ∫(Power × UseRate)dt + EOL
  - Trapezoidal integration for use-phase impacts

Usage
-----
    python scripts/create_fmu.py <lci_stem> [options]

LCIA Methods  (--method)
------------------------
  ipcc             IPCC 2021 GWP100, excl. biogenic CO2
                   Output variable: climate_change_kg_co2_eq  [kg CO2-eq]

  recipe_endpoint  ReCiPe 2016 Endpoint H/A — three damage-category totals
                   (Human Health, Ecosystem Quality, Natural Resources) are
                   converted to Pt and summed into a single score.
                   Output variable: single_score_pt  [Pt]

Examples
--------
    python scripts/create_fmu.py example
    python scripts/create_fmu.py example --method ipcc
    python scripts/create_fmu.py example --method recipe_endpoint
    python scripts/create_fmu.py example --name "Example_Climate" --version 0.0.1

Output
------
    fmu/<Name>.fmu   – production-ready FMU (only this file is kept)
"""

import argparse
import json
import sys
import tempfile
import textwrap
import re
import math
from typing import Any
from pathlib import Path

# Add src to path for library imports
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from lca_utils import safe_classname, ensure_dir_exists
from fmu_generator import (
    extract_emission_factors,
    extract_stage_impacts,
    generate_fmu_class_code,
    build_fmu_with_pythonfmu,
    fix_fmu_metadata,
    package_fmu_as_bytecode,
    audit_fmu_blackbox,
    validate_fmu
)
from fmu_api import BuildOptions, FmuBuildError, build_lca_fmu_internal


def configure_console_encoding() -> None:
    """Configure UTF-8 console streams where available (Windows-friendly)."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _arg_was_provided(option_name: str) -> bool:
    """Return True when a CLI option was explicitly provided by the user."""
    for arg in sys.argv[1:]:
        if arg == option_name or arg.startswith(option_name + "="):
            return True
    return False

# ── Configuration ────────────────────────────────────────────────────────────

DIST_FMU = ROOT / "fmu"
DIST_FMU_PROPRIETARY = DIST_FMU / "proprietary"

# Supported LCIA methods
METHOD_CONFIG = {
    "ipcc": {
        "keywords": ["IPCC 2021 climate change total excl biogenic GWP100"],
        "output_var": "climate_change_kg_co2_eq",
        "output_unit": "kg CO2-eq",
        "output_label": "Climate Change (IPCC 2021, excl. biogenic CO2)",
        "single_score": False,  # raw score used directly
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
        "single_score": True,  # sum score_pt across all three categories
    },
}


# ── LCA Analysis ─────────────────────────────────────────────────────────────

def run_lca_analysis(
    lci_file: Path,
    energy_mj: float,
    keywords: list,
    parameter_values: dict[str, float] | None = None,
    brightway_project: str | None = None,
    confirm_project_switch: bool = True,
) -> dict:
    """
    Run LCA analysis using the LCA engine.
    
    Args:
        lci_file: Path to LCI JSON file
        energy_mj: Energy amount in MJ
        keywords: LCIA method keywords
        
    Returns:
        LCA results dictionary
        
    Raises:
        RuntimeError: If LCA analysis fails
    """
    # Lazy import keeps '-h/--help' fast and avoids Brightway startup warnings.
    # Prefer local module import first to avoid collisions with unrelated installed "src" packages.
    try:
        from lca_engine import run_lca
    except ImportError:
        from fmlca.lca_engine import run_lca

    # Load LCI file to display metadata
    try:
        with open(lci_file, 'r') as f:
            lci_data = json.load(f)
    except Exception:
        lci_data = {}
    
    # Display analysis info
    energy_metadata = lci_data.get('energy_metadata', {})
    primary_input = energy_metadata.get('primary_input', {})
    
    print(f"\n{'='*60}")
    print(f"  Step 1 – Running LCA Analysis")
    print(f"    LCI    : {lci_file.name}")
    print(f"    Methods: {keywords}")
    if parameter_values:
        print(f"    Parameters: {parameter_values}")
    if primary_input:
        print(f"    Dynamic Input: {primary_input.get('description', 'Energy input')} "
              f"({primary_input.get('value', 0.0)} {primary_input.get('unit', 'MJ')} base)")
    print(f"{'='*60}")
    
    # Run LCA analysis
    try:
        run_kwargs = {
            "lci_file": str(lci_file),
            "lcia_methods": keywords,
            "parameter_values": parameter_values,
            "functional_unit": {},
            "energy_amount_mj": energy_mj,
            "brightway_project": brightway_project,
            "confirm_project_switch": confirm_project_switch,
        }
        try:
            results = run_lca(**run_kwargs)
        except TypeError as exc:
            # Backward-compatible retry for older run_lca signatures.
            if "unexpected keyword argument" not in str(exc):
                raise
            run_kwargs.pop("brightway_project", None)
            run_kwargs.pop("confirm_project_switch", None)
            results = run_lca(**run_kwargs)
        
        if "error" in results:
            err = str(results.get("error", "Unknown LCA error"))
            tb = str(results.get("traceback", ""))
            disk_full = (
                "database or disk is full" in err.lower()
                or "database or disk is full" in tb.lower()
                or "low disk space" in err.lower()
            )

            if disk_full:
                raise RuntimeError(
                    "LCA analysis failed due to low disk space in Brightway storage. "
                    "Free disk space and/or delete unused Brightway projects in your Brightway data directory, then retry."
                )

            raise RuntimeError(f"LCA analysis failed: {err}")
        
        print(f"  ✅ LCA analysis completed successfully")
        return results
        
    except Exception as e:
        raise RuntimeError(f"LCA analysis failed: {e}")


def _resolve_lci_parameters(lci_data: dict[str, Any]) -> dict[str, float]:
    """Resolve numeric parameter defaults from LCI JSON metadata."""
    params = lci_data.get("parameters", {})
    resolved: dict[str, float] = {}
    for name, meta in params.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)):
            raise ValueError(f"Unsupported parameter name '{name}' for FMU variable export")
        default = 1.0
        if isinstance(meta, dict):
            default = float(meta.get("default", 1.0))
        resolved[str(name)] = default
    return resolved


def _build_parameter_model(
    lci_path: Path,
    method_cfg: dict[str, Any],
    unitary_energy_mj: float,
    baseline_factors: dict[str, Any],
    baseline_stage_impacts: dict[str, float],
    parameter_defaults: dict[str, float],
    brightway_project: str | None = None,
    confirm_project_switch: bool = True,
) -> dict[str, Any]:
    """Build a linear parameter model from additional LCA runs around defaults."""
    if not parameter_defaults:
        return {"defaults": {}, "slopes": {}, "stability": {"kappa": 1.0, "ill_conditioned": False}}

    def _choose_safe_delta(default: float) -> float:
        """Choose a larger but safe perturbation delta for finite differences."""
        magnitude = abs(default)

        # Larger relative step improves signal-to-noise for LCA differencing.
        delta = max(0.5 * magnitude, 0.25)

        # Cap excessive perturbations to remain in a local linear neighborhood.
        cap = max(2.0 * magnitude, 2.0)
        delta = min(delta, cap)

        # Ensure non-trivial positive step.
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

        varied_results = run_lca_analysis(
            lci_path,
            unitary_energy_mj,
            method_cfg["keywords"],
            parameter_values=overrides,
            brightway_project=brightway_project,
            confirm_project_switch=confirm_project_switch,
        )
        varied_factors = extract_emission_factors(varied_results, method_cfg, unitary_energy_mj)
        varied_stage = extract_stage_impacts(varied_results, method_cfg)

        denom = varied - default
        slopes["production"][pname] = (varied_stage["production"] - baseline_stage_impacts["production"]) / denom
        slopes["transport"][pname] = (varied_stage["transport"] - baseline_stage_impacts["transport"]) / denom
        slopes["eol"][pname] = (varied_stage["eol"] - baseline_stage_impacts["eol"]) / denom
        slopes["use_rate_per_j"][pname] = ((varied_factors["energy_factor"] / 1.0e6) - baseline_use_rate) / denom

        print(
            f"  ✅ Parameter sensitivity: {pname} "
            f"(default={default}, varied={varied}, delta={denom})"
        )

    # Stability diagnostics: kappa ratio from singular values of the slope system.
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

        if stability["ill_conditioned"]:
            print(
                "  ⚠️  Numerical stability warning: parameter sensitivity system appears "
                f"ill-conditioned (kappa={kappa:.3e}). "
                "Consider narrowing parameter ranges, rescaling parameters, or validating "
                "linearity assumptions."
            )
        else:
            print(f"  ✅ Sensitivity system conditioning: kappa={kappa:.3e}")
    except Exception as exc:
        print(f"  ⚠️  Conditioning check unavailable: {exc}")

    return {
        "defaults": parameter_defaults,
        "slopes": slopes,
        "stability": stability,
    }


def verify_fmu_parameter_linearity(
    fmu_path: Path,
    parameter_defaults: dict[str, float],
    tolerance: float = 1e-4,
) -> tuple[bool, str]:
    """Run a short FMU simulation and verify affine linearity per parameter.

    We validate equal-step increment consistency while all other parameters are
    fixed at defaults:

        y(p0 + 2h) - y(p0 + h) ~= y(p0 + h) - y(p0)

    This is robust when the output includes a non-zero intercept, where a
    simple total-output ratio check is invalid.
    """
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

        print(
            f"  🔎 Linearity check {pname}: "
            f"d1={d1:.6e}, d2={d2:.6e}, resid={resid:.3e}, rel_error={rel_err:.3e}"
        )
        if rel_err > tolerance:
            return False, (
                f"Parameter '{pname}' linearity check failed "
                f"(increment mismatch d1={d1:.6e}, d2={d2:.6e}, resid={resid:.3e}, "
                f"rel_error={rel_err:.3e}, tolerance={tolerance:.1e})"
            )

    return True, "FMU parameter linearity verified"


def _resolve_lci_base_energy_mj(lci_data: dict[str, Any], default: float = 1.0) -> float:
    """Resolve base energy quantity from LCI energy_metadata.primary_input.value."""
    value = (
        lci_data.get("energy_metadata", {})
        .get("primary_input", {})
        .get("value", default)
    )
    try:
        base_energy_mj = float(value)
    except (TypeError, ValueError):
        base_energy_mj = default

    if base_energy_mj <= 0.0:
        return default
    return base_energy_mj


def _resolve_one_base_unit_mj(lci_data: dict[str, Any], default_mj: float = 1.0) -> tuple[float, str]:
    """Return the MJ equivalent of 1 inventory base energy unit and the normalized base unit label."""
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
        print(f"⚠️ Unsupported base energy unit '{base_unit_raw}', defaulting basis to 1 MJ")
        return default_mj, "MJ"

    return unit_to_mj[base_unit], base_unit


# ── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="Build a production-ready LCA FMU from an LCI JSON file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            FMU Behavior:
              The FMU tracks cumulative environmental impacts over time:
              - Input  u : Power [MW] - energy flow rate
              - Output y : Cumulative impact - total accumulated impact

              At t=start:  y = Production + Transport (embodied impacts)
              During run:  y += integral(Power * UseRate)dt  (use phase impacts)
              At t=stop:   y += End-of-Life  (disposal impacts)

            LCIA Methods (--method):
              ipcc             IPCC 2021 GWP100, excl. biogenic CO2
                               -> output: climate_change_kg_co2_eq_cumulative  [kg CO2-eq]

              recipe_endpoint  ReCiPe 2016 Endpoint H/A single score (Human Health +
                               Ecosystem Quality + Natural Resources, summed in Pt)
                               -> output: single_score_pt_cumulative  [Pt]

            Examples:
              python scripts/create_fmu.py example
              python scripts/create_fmu.py example --method ipcc
              python scripts/create_fmu.py example --method recipe_endpoint
              python scripts/create_fmu.py example --dymola --export-mode source --blackbox-policy warn
        """),
    )
    parser.add_argument(
        "lci_stem",
        help="Stem of the LCI JSON file in data/inventory/ (e.g. 'example' for example.json), "
        "or a full path to any .json file."
    )
    parser.add_argument(
        "--method",
        default="ipcc",
        choices=list(METHOD_CONFIG.keys()),
        help="LCIA method to use: 'ipcc' (GWP100, default) or 'recipe_endpoint' (single score Pt)"
    )
    parser.add_argument(
        "--target-tool",
        choices=["generic", "dymola"],
        default="generic",
        help=(
            "Importer compatibility preset. "
            "dymola selects source export defaults to avoid Python bytecode version lock-in "
            "and prints runtime guidance."
        )
    )
    parser.add_argument(
        "--dymola",
        action="store_true",
        help="Shorthand for --target-tool dymola"
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Custom FMU name prefix (default: derived from lci_stem + method)"
    )
    parser.add_argument(
        "--version",
        default="0.0.1",
        help="Version string embedded in the FMU name (default: 0.0.1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test configuration and file access without creating FMU"
    )
    parser.add_argument(
        "--blackbox-policy",
        choices=["enforce", "warn", "off"],
        default="enforce",
        help=(
            "Black-box compliance handling: "
            "enforce=fail build if readable source/data is packaged (default), "
            "warn=report but keep FMU, off=skip audit"
        )
    )
    parser.add_argument(
        "--export-mode",
        choices=["source", "bytecode"],
        default="bytecode",
        help=(
            "FMU packaging mode: source=keep Python resources/*.py, "
            "bytecode=compile implementation modules to .pyc and keep only a minimal loader stub (default)"
        )
    )
    parser.add_argument(
        "--default-step-size",
        type=float,
        default=60.0,
        help=(
            "FMI DefaultExperiment stepSize in seconds embedded in modelDescription.xml "
            "(used by some importers as a default communication step; default: 60.0)"
        )
    )
    parser.add_argument(
        "--bw-project",
        default=None,
        help=(
            "Explicit Brightway project to use for LCA lookup. "
            "Overrides auto-discovery and prevents accidental use of another project."
        )
    )
    parser.add_argument(
        "--no-confirm-project-switch",
        action="store_true",
        help=(
            "Disable interactive confirmation before automatic Brightway project switching. "
            "Use in CI/non-interactive runs with caution."
        )
    )

    args = parser.parse_args()

    if args.dymola:
        args.target_tool = "dymola"

    export_mode_overridden = _arg_was_provided("--export-mode")
    blackbox_policy_overridden = _arg_was_provided("--blackbox-policy")
    step_size_overridden = _arg_was_provided("--default-step-size")

    if args.target_tool == "dymola":
        print("\n🔧 Target preset: dymola")
        if not export_mode_overridden:
            args.export_mode = "source"
            print("   • export_mode set to source (improves runtime compatibility across Python versions)")
        if not blackbox_policy_overridden:
            args.blackbox_policy = "warn"
            print("   • blackbox_policy set to warn (source mode is not black-box compliant)")
        if not step_size_overridden:
            args.default_step_size = 60.0
            print("   • default_step_size set to 60.0 s")

    from lca_utils import get_inventory_dir

    lci_path = Path(args.lci_stem)
    if not lci_path.suffix:
        lci_path = get_inventory_dir() / (args.lci_stem + ".json")
    elif not lci_path.is_absolute():
        lci_path = Path.cwd() / lci_path

    if args.default_step_size <= 0.0:
        parser.error("--default-step-size must be > 0")

    if args.export_mode == "source" and args.blackbox_policy == "enforce":
        parser.error(
            "--export-mode source conflicts with --blackbox-policy enforce. "
            "Use --blackbox-policy warn/off for source mode, or switch to --export-mode bytecode."
        )

    if args.dry_run:
        if not lci_path.exists():
            parser.error(f"LCI file not found: {lci_path}")

        try:
            with open(lci_path, "r", encoding="utf-8") as f:
                lci_data = json.load(f)
        except Exception as exc:
            parser.error(f"Failed to read LCI JSON '{lci_path}': {exc}")

        from lci_data_manager import validate_inventory_format

        if not validate_inventory_format(lci_data):
            parser.error(f"Invalid LCI JSON structure: {lci_path}")

        print("🧪 DRY RUN MODE - configuration validated")
        print(f"LCI path: {lci_path}")
        print(f"Method: {args.method}")
        print(f"Target tool: {args.target_tool}")
        print(f"Export mode: {args.export_mode}")
        print(f"Black-box policy: {args.blackbox_policy}")
        return

    source_export_nonblackbox = (
        args.export_mode == "source"
        and args.blackbox_policy in {"warn", "off"}
    )
    output_dir = DIST_FMU_PROPRIETARY if (source_export_nonblackbox or args.target_tool == "dymola") else DIST_FMU

    options = BuildOptions(
        method=args.method,
        version=args.version,
        name=args.name,
        output_dir=output_dir,
        target_tool=args.target_tool,
        export_mode=args.export_mode,
        blackbox_policy=args.blackbox_policy,
        default_step_size=args.default_step_size,
        parameter_values=None,
        functional_unit={},
        energy_amount_mj=None,
        validate=True,
        verify_linearity=True,
        move_to_output_dir=True,
        verbose=True,
        brightway_project=args.bw_project,
        confirm_project_switch=not args.no_confirm_project_switch,
    )

    try:
        result = build_lca_fmu_internal(lci_path, options)
    except FmuBuildError as exc:
        print(f"\n❌ Error: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"\n❌ Unexpected error: {exc}")
        raise SystemExit(1) from exc

    print(f"\n{'='*60}")
    print("  FMU creation complete")
    print(f"  Output: {result.final_fmu_path}")
    print(f"  Method: {result.method}")
    print(f"  Validation: {'PASS' if (result.validation_ok in (None, True)) else 'FAIL'}")
    print(f"  Black-box: {'PASS' if (result.blackbox_ok in (None, True)) else 'FAIL'}")
    print(f"  Linearity: {'PASS' if (result.linearity_ok in (None, True)) else 'FAIL'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

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
    python scripts/create_fmu.py example --name "Example_Climate" --version 2.0

Output
------
    fmu/<Name>.fmu   – production-ready FMU (only this file is kept)
"""

import argparse
import json
import sys
import tempfile
import textwrap
from pathlib import Path

# Add src to path for library imports
ROOT = Path(__file__).parent.parent.resolve()
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

# ── Configuration ────────────────────────────────────────────────────────────

DIST_FMU = ROOT / "fmu"

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

def run_lca_analysis(lci_file: Path, energy_mj: float, keywords: list) -> dict:
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
    from lca_engine import run_lca_energy

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
    if primary_input:
        print(f"    Dynamic Input: {primary_input.get('description', 'Energy input')} "
              f"({primary_input.get('value', 0.0)} {primary_input.get('unit', 'MJ')} base)")
    print(f"{'='*60}")
    
    # Run LCA analysis
    try:
        results = run_lca_energy(
            lci_file=str(lci_file),
            lcia_methods=keywords,
            functional_unit={},
            energy_amount_mj=energy_mj
        )
        
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
              python scripts/create_fmu.py example --name "Example_Climate" --version 2.0
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
        "--name",
        default=None,
        help="Custom FMU name prefix (default: derived from lci_stem + method)"
    )
    parser.add_argument(
        "--version",
        default="1.0",
        help="Version string embedded in the FMU name (default: 1.0)"
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

    args = parser.parse_args()

    # ── Resolve LCI file ─────────────────────────────────────────────────────
    lci_path = Path(args.lci_stem)
    if not lci_path.suffix:
        lci_path = ROOT / "data" / "inventory" / (args.lci_stem + ".json")
    if not lci_path.is_absolute():
        lci_path = ROOT / lci_path
    if not lci_path.exists():
        parser.error(f"LCI file not found: {lci_path}")

    method_cfg = METHOD_CONFIG[args.method]

    # ── Generate names ───────────────────────────────────────────────────────
    stem = lci_path.stem
    method_label = args.method.replace("_", " ").title().replace(" ", "_")
    fmu_name = args.name or f"{safe_classname(stem)}_{method_label}_v{args.version}"
    class_name = safe_classname(fmu_name)

    # Baseline energy for factor calculation (not user-configurable)
    baseline_energy_mj = 180.0

    # ── Dry run mode ─────────────────────────────────────────────────────────
    if args.dry_run:
        print("🧪 DRY RUN MODE - Testing configuration")

        try:
            with open(lci_path, 'r') as f:
                lci_data = json.load(f)
            print(f"✅ LCI file valid: {lci_data.get('name', 'Unknown process')}")
        except Exception as e:
            print(f"❌ LCI file error: {e}")
            sys.exit(1)

        print(f"✅ Method configuration: {args.method} -> {method_cfg['output_label']}")
        print(f"✅ FMU name: {fmu_name}")
        print(f"✅ Class name: {class_name}")
        print(f"✅ Output variable: {method_cfg['output_var']} [{method_cfg['output_unit']}]")
        print("✅ Dry run completed successfully - ready for FMU creation")
        sys.exit(0)

    # ── Setup paths ──────────────────────────────────────────────────────────
    ensure_dir_exists(DIST_FMU)
    simulatable_path = DIST_FMU / f"{fmu_name}_Simulatable.fmu"
    final_path = DIST_FMU / f"{fmu_name}.fmu"

    print(f"\n🚀  Creating FMU: {fmu_name}")
    print(f"    LCI file   : {lci_path}")
    print(f"    Method     : {args.method}  →  {method_cfg['output_var']}  [{method_cfg['output_unit']}]")

    try:
        # ── Step 1: Run LCA analysis ─────────────────────────────────────────
        lca_results = run_lca_analysis(lci_path, baseline_energy_mj, method_cfg["keywords"])

        # ── Step 2: Extract factors and stage impacts ────────────────────────
        print(f"\n{'='*60}")
        print(f"  Step 2 – Extracting emission factors and stage impacts")
        print(f"{'='*60}")

        factors = extract_emission_factors(lca_results, method_cfg, baseline_energy_mj)
        stage_impacts = extract_stage_impacts(lca_results, method_cfg)

        # ── Step 3: Generate and build FMU ───────────────────────────────────
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir = Path(tmp_dir)

            # Generate Python class code
            class_code = generate_fmu_class_code(
                class_name=class_name,
                fmu_name=fmu_name,
                method_config=method_cfg,
                factors=factors,
                stage_impacts=stage_impacts,
                lci_path=lci_path
            )

            # Write to temporary file
            python_file = tmp_dir / f"{class_name}.py"
            python_file.write_text(class_code, encoding="utf-8")
            print(f"\n{'='*60}")
            print(f"  Step 3 – Generated FMU class code")
            print(f"    Class: {class_name}")
            print(f"    File:  {python_file.name}")
            print(f"{'='*60}")

            # Build FMU with pythonfmu
            build_fmu_with_pythonfmu(python_file, simulatable_path)

        # ── Step 4: Fix FMU metadata ─────────────────────────────────────────
        fix_fmu_metadata(
            fmu_path=simulatable_path,
            output_path=final_path,
            output_var="y",
            output_unit=method_cfg["output_unit"],
            output_description=f"Cumulative {method_cfg['output_label']}",
            default_step_size=args.default_step_size,
        )

        # ── Step 5: Optional bytecode packaging ──────────────────────────────
        if args.export_mode == "bytecode":
            package_fmu_as_bytecode(final_path)

        # ── Step 6: Black-box compliance audit ──────────────────────────────
        blackbox_ok = True
        blackbox_msg = "Black-box audit skipped"
        if args.blackbox_policy != "off":
            blackbox_ok, blackbox_msg = audit_fmu_blackbox(final_path)
            if blackbox_ok:
                print(f"\n  ✅ {blackbox_msg}")
            else:
                level = "❌" if args.blackbox_policy == "enforce" else "⚠️"
                print(f"\n  {level} {blackbox_msg}")

            if not blackbox_ok and args.blackbox_policy == "enforce":
                # Prevent accidental distribution of non-compliant FMUs.
                try:
                    final_path.unlink()
                    print(f"  🧹 Removed non-compliant FMU: {final_path.name}")
                except Exception as exc:
                    print(f"  ⚠️  Could not remove non-compliant FMU: {exc}")

                raise RuntimeError(
                    "Black-box compliance check failed. "
                    "Use --blackbox-policy warn/off only for local testing."
                )

        # ── Step 7: Validate FMU ─────────────────────────────────────────────
        is_valid, msg = validate_fmu(final_path)

        # ── Step 8: Clean up intermediate file ───────────────────────────────
        try:
            simulatable_path.unlink()
            print(f"\n  🧹 Removed intermediate: {simulatable_path.name}")
        except Exception as exc:
            print(f"\n  ⚠️  Could not remove intermediate file: {exc}")

        # ── Summary ──────────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        if is_valid:
            print(f"  🎉  FMU creation complete!")
        else:
            print(f"  ⚠️   FMU created but validation had issues: {msg}")
        print(f"  📁  Output : {final_path}")
        print(f"  🖥️   Platform: Windows 64-bit, Linux 64-bit")
        print(f"  📦  Export mode     : {args.export_mode}")
        print(f"  🔐  Black-box policy: {args.blackbox_policy}")
        print(f"  🔎  Black-box audit : {'PASS' if blackbox_ok else 'FAIL'}")
        print(f"")
        print(f"  🔄  Cumulative Impact Tracking:")
        print(f"     • Input  : u [MW]  (power_input_mw)")
        print(f"     • Output : y [{method_cfg['output_unit']}]  ({method_cfg['output_var']}_cumulative)")
        print(f"")
        print(f"  📊  Life Cycle Stages:")
        print(f"     • Production : {stage_impacts['production']:.4e} {method_cfg['output_unit']} (t=start)")
        print(f"     • Transport  : {stage_impacts['transport']:.4e} {method_cfg['output_unit']} (t=start)")
        print(f"     • Use rate   : {factors['energy_factor']*3600:.4e} {method_cfg['output_unit']}/MWh (∫P dt)")
        print(f"     • End-of-Life: {stage_impacts['eol']:.4e} {method_cfg['output_unit']} (t=stop)")
        print(f"{'='*60}\n")

        sys.exit(0 if is_valid else 1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

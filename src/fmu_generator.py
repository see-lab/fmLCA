#!/usr/bin/env python3
"""
fmu_generator.py - FMU generation logic for LCA-FMU

Library module for FMU generation. Import this module, do not run directly.

Extracted core functionality from create_fmu.py script.
Provides reusable FMU generation as a library.

Usage:
    from src.fmu_generator import generate_fmu_class_code, build_fmu_with_pythonfmu

Key features:
- Extract emission factors from LCA results
- Extract life cycle stage impacts
- Generate FMU Python class code  
- Build FMUs using pythonfmu
- Fix FMU XML metadata
- Validate FMUs with fmpy

Part of the LCA-FMU core library.
"""

import subprocess
import sys
import textwrap
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import py_compile
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Handle both relative and absolute imports
try:
    from .lca_utils import safe_classname, ensure_dir_exists
except ImportError:
    from lca_utils import safe_classname, ensure_dir_exists


# ── Factor Extraction ────────────────────────────────────────────────────────

def extract_emission_factors(lca_results: Dict[str, Any], 
                             method_config: Dict[str, Any],
                             energy_mj: float) -> Dict[str, Any]:
    """
    Extract emission factors from LCA results.
    
    For single_score methods (e.g., ReCiPe Endpoint):
        Sums score_pt across all damage categories to build a single-score Pt value,
        then derives a per-MJ Pt factor.
        
    For non-single_score methods (e.g., IPCC):
        Returns the raw total score and a per-MJ energy factor.
    
    Args:
        lca_results: LCA analysis results dictionary
        method_config: Method configuration dict with keys:
            - single_score: bool (whether to sum into single score)
            - output_unit: str (unit for output)
        energy_mj: Energy input in MJ
        
    Returns:
        Dict with:
            - base_impact: Total impact score
            - energy_factor: Impact per MJ
            - scaling_factor: LCA scaling factor
            - unit: Impact unit
            
    Examples:
        >>> factors = extract_emission_factors(results, method_cfg, 100.0)
        >>> factors['energy_factor']  # kg CO2-eq / MJ
        0.93234
    """
    impact_data = lca_results.get("impact_results", {})
    single_score = method_config["single_score"]
    out_unit = method_config["output_unit"]
    
    if single_score:
        # Sum endpoint totals for single-score methods.
        # Prefer score_pt if present, otherwise accept total_score from lca_engine.
        total_pt = 0.0
        found = 0
        for data in impact_data.values():
            if not isinstance(data, dict):
                continue
            if "score_pt" in data:
                total_pt += float(data["score_pt"])
                found += 1
            elif "total_score" in data:
                total_pt += float(data["total_score"])
                found += 1

        if found == 0:
            print("  ⚠️  No single-score totals found — using placeholder factors (0).")
            return {
                "base_impact": 0.0,
                "energy_factor": 0.0,
                "scaling_factor": 1.0,
                "unit": out_unit
            }

        # Prefer use-stage totals for the dynamic factor to avoid double counting
        # embodied stages that are already tracked as static terms in the FMU.
        use_total = 0.0
        use_found = 0
        stage_breakdown = lca_results.get("stage_breakdown", {})
        if isinstance(stage_breakdown, dict):
            for method_stages in stage_breakdown.values():
                if not isinstance(method_stages, dict):
                    continue
                use_stage = method_stages.get("Use")
                if isinstance(use_stage, dict) and isinstance(use_stage.get("score"), (int, float)):
                    use_total += float(use_stage["score"])
                    use_found += 1

        if use_found > 0:
            factor = use_total / energy_mj if energy_mj else 0.0
            print(
                f"  ✅ Single score: total = {total_pt:.4f} Pt "
                f"({found} categories), use = {use_total:.4e} Pt "
                f"({use_found} categories), factor/MJ = {factor:.4e} Pt/MJ"
            )
        else:
            factor = total_pt / energy_mj if energy_mj else 0.0
            print(
                f"  ✅ Single score: total = {total_pt:.4f} Pt "
                f"({found} categories), factor/MJ = {factor:.4e} Pt/MJ "
                "(fallback: total-based)"
            )

        return {
            "base_impact": total_pt,
            "energy_factor": factor,
            "scaling_factor": lca_results.get("scaling_factor", 1.0),
            "unit": out_unit
        }
    else:
        # Non-single score (e.g., IPCC): use the first result entry
        matched = None
        for data in impact_data.values():
            if isinstance(data, dict) and "total_score" in data:
                matched = data
                break
        
        if matched is None:
            print("  ⚠️  No LCA results found — using placeholder factors (0).")
            return {
                "base_impact": 0.0,
                "energy_factor": 0.0,
                "scaling_factor": 1.0,
                "unit": out_unit
            }
        
        total = matched["total_score"]
        unit = matched.get("unit", out_unit)

        # If stage breakdown contains a Use stage, derive the dynamic factor from
        # use-phase impact only. This avoids double counting because production /
        # transport / EOL are already added separately in the FMU state equation.
        use_score = None
        stage_breakdown = lca_results.get("stage_breakdown", {})
        if isinstance(stage_breakdown, dict) and stage_breakdown:
            first_method_stages = next(iter(stage_breakdown.values()), {})
            if isinstance(first_method_stages, dict):
                use_stage = first_method_stages.get("Use")
                if isinstance(use_stage, dict):
                    use_score = use_stage.get("score")

        if isinstance(use_score, (int, float)):
            factor = float(use_score) / energy_mj if energy_mj else 0.0
            print(
                f"  ✅ Extracted: total = {total:.4e} {unit}, "
                f"use = {float(use_score):.4e} {unit}, factor/MJ = {factor:.4e}"
            )
        else:
            factor = total / energy_mj if energy_mj else 0.0
            print(
                f"  ✅ Extracted: total = {total:.4e} {unit}, "
                f"factor/MJ = {factor:.4e} (fallback: total-based)"
            )
        
        return {
            "base_impact": total,
            "energy_factor": factor,
            "scaling_factor": lca_results.get("scaling_factor", 1.0),
            "unit": unit
        }


def extract_stage_impacts(lca_results: Dict[str, Any],
                         method_config: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract life cycle stage impacts from LCA results.
    
    Args:
        lca_results: LCA analysis results dictionary
        method_config: Method configuration dict
        
    Returns:
        Dict with keys: 'production', 'transport', 'use', 'eol'
        representing the impact contribution of each life cycle stage
        
    Examples:
        >>> stages = extract_stage_impacts(results, method_cfg)
        >>> stages['production']
        19000.147
    """
    stage_breakdown = lca_results.get("stage_breakdown", {})
    
    # Initialize stages
    stages = {
        'production': 0.0,
        'transport': 0.0,
        'use': 0.0,
        'eol': 0.0
    }
    
    if not stage_breakdown:
        print("  ⚠️  No stage breakdown found — using zero stage impacts")
        return stages
    
    # For single-score methods (e.g., ReCiPe endpoint), aggregate across all
    # selected endpoint categories. For non-single-score methods, process the
    # first method entry (legacy behavior).
    method_stage_sets = []
    if method_config.get("single_score", False):
        method_stage_sets = [m for m in stage_breakdown.values() if isinstance(m, dict)]
    else:
        first_method_stages = next(iter(stage_breakdown.values()), None)
        if isinstance(first_method_stages, dict):
            method_stage_sets = [first_method_stages]

    for method_stages in method_stage_sets:
        # Map LCA stage names to our standard names
        stage_mapping = {
            'Production': 'production',
            'Manufacturing': 'production',
            'Transport': 'transport',
            'Use': 'use',
            'EOL': 'eol',
            'End-of-Life': 'eol',
            'Disposal': 'eol'
        }
        
        for stage_name, stage_data in method_stages.items():
            if isinstance(stage_data, dict):
                score = stage_data.get('score', 0.0)
                # Map to standard stage name
                std_name = stage_mapping.get(stage_name, stage_name.lower())
                if std_name in stages:
                    stages[std_name] += score
    
    print(f"  ✅ Stage impacts extracted:")
    for stage, impact in stages.items():
        if impact > 0:
            print(f"     {stage.capitalize():12s}: {impact:.4e} {method_config['output_unit']}")
    
    return stages


# ── FMU Class Code Generation ────────────────────────────────────────────────

def generate_fmu_class_code(class_name: str,
                           fmu_name: str,
                           method_config: Dict[str, Any],
                           factors: Dict[str, Any],
                           stage_impacts: Dict[str, float],
                           parameter_model: Optional[Dict[str, Any]] = None,
                           lci_path: Optional[Path] = None) -> str:
    """
    Generate Python code for FMU class with cumulative impact tracking.
    
    Args:
        class_name: Python class name (CamelCase)
        fmu_name: FMU name for documentation
        method_config: Method configuration dict
        factors: Emission factors dict from extract_emission_factors()
        stage_impacts: Stage impacts dict from extract_stage_impacts()
        lci_path: Optional path to LCI file (for documentation)
        
    Returns:
        Python source code as string
    """
    out_var = method_config["output_var"]
    out_label = method_config["output_label"]
    out_unit = factors["unit"]
    use_rate_per_j = factors["energy_factor"] / 1.0e6  # Convert impact/MJ to impact/J

    param_defaults = (parameter_model or {}).get("defaults", {})
    param_slopes = (parameter_model or {}).get("slopes", {})
    param_decl_lines = []
    for pname, default in param_defaults.items():
        param_decl_lines.extend([
            f"                self.{pname} = {float(default):.8e}",
            "                self.register_variable(Real(",
            f"                    \"{pname}\",",
            f"                    start={float(default):.8e},",
            "                    causality=Fmi2Causality.parameter,",
            "                    variability=Fmi2Variability.tunable,",
            "                    initial=Fmi2Initial.exact,",
            f"                    description=\"LCI parameter override: {pname}\",",
            "                ))",
            "",
        ])
    param_decl = "\n".join(param_decl_lines).rstrip()

    metric_helper = "\n".join([
        "            def _metric(self, metric_name: str, baseline: float) -> float:",
        "                value = baseline",
        "                for pname, default in self._param_defaults.items():",
        "                    slope = self._param_slopes.get(metric_name, {}).get(pname, 0.0)",
        "                    value += slope * (getattr(self, pname) - default)",
        "                return value",
    ])
    
    code = textwrap.dedent(f'''\
        """
        Auto-generated LCA FMU: {fmu_name}
        Input  u : Power [W]  (power_input_w)
        Output y : Cumulative {out_label}  [{out_unit}]  ({out_var}_cumulative)
        
        This FMU tracks cumulative environmental impacts over time:
        - At t=start: Add production + transport embodied impacts
        - During operation: Integrate use phase impacts from energy in joules (power × time)
        - At t=stop: Add end-of-life impacts
        
        Uses pre-computed factors for fast calculation.
        Use rate: {use_rate_per_j:.4e} {out_unit}/J
        """
        from pythonfmu import Fmi2Slave, Fmi2Causality, Fmi2Variability, Fmi2Initial
        from pythonfmu.variables import Real

        class {class_name}(Fmi2Slave):
            """{fmu_name} – LCA FMU with Cumulative Impact Tracking"""

            def __init__(self, **kwargs):
                super().__init__(**kwargs)

                # State variables (must exist before register_variable so
                # pythonfmu auto-binds getters/setters).
                self.u = 0.0
                self.y = 0.0
                self._prev_u = 0.0
                self.use_phase_impact = 0.0
                self.eol_added = False
{param_decl}

                # u — power input in W (maps to: power_input_w)
                self.register_variable(Real(
                    "u",
                    start=0.0,
                    causality=Fmi2Causality.input,
                    variability=Fmi2Variability.continuous,
                    initial=Fmi2Initial.exact,
                    description="Power input [W] (power_input_w)",
                ))
                # y — cumulative impact output (maps to: {out_var}_cumulative)
                self.register_variable(Real(
                    "y",
                    causality=Fmi2Causality.output,
                    variability=Fmi2Variability.continuous,
                    initial=Fmi2Initial.calculated,
                    description="Cumulative {out_label} [{out_unit}] ({out_var}_cumulative)",
                ))

                # Life cycle stage impacts (embodied impacts)
                self.production_impact = {stage_impacts.get('production', 0.0):.8e}
                self.transport_impact = {stage_impacts.get('transport', 0.0):.8e}
                self.eol_impact = {stage_impacts.get('eol', 0.0):.8e}
                
                # Use phase rate: impact per joule
                self.use_rate_per_j = {factors["energy_factor"]:.8e} / 1.0e6  # {out_unit}/J

                self._param_defaults = {repr(param_defaults)}
                self._param_slopes = {repr(param_slopes)}

{metric_helper}

            def do_step(self, current_time: float, step_size: float) -> bool:
                try:
                    production_impact = self._metric("production", self.production_impact)
                    transport_impact = self._metric("transport", self.transport_impact)
                    eol_impact = self._metric("eol", self.eol_impact)
                    use_rate_per_j = self._metric("use_rate_per_j", self.use_rate_per_j)

                    # Input 'u' is already updated by FMI setReal.
                    power_prev = self._prev_u
                    power_curr = self.u
                    
                    # Trapezoidal integration where W*s = J.
                    avg_power = (power_prev + power_curr) / 2.0
                    step_energy_j = avg_power * step_size
                    step_impact = step_energy_j * use_rate_per_j
                    
                    self.use_phase_impact += step_impact
                    
                    # Update cumulative impact
                    self.y = (production_impact + 
                             transport_impact + 
                             self.use_phase_impact +
                             (eol_impact if self.eol_added else 0.0))

                    self._prev_u = power_curr
                    return True
                    
                except Exception as exc:
                    print(f"FMU step error: {{exc}}")
                    return False

            def exit_initialization_mode(self):
                # Initialize with embodied impacts
                production_impact = self._metric("production", self.production_impact)
                transport_impact = self._metric("transport", self.transport_impact)
                self.y = production_impact + transport_impact
                self.use_phase_impact = 0.0
                self.eol_added = False
                self._prev_u = self.u
                return True

            def terminate(self):
                # Add end-of-life impacts
                if not self.eol_added:
                    eol_impact = self._metric("eol", self.eol_impact)
                    self.eol_added = True
                    self.y += eol_impact
                return True
        ''')
    
    return code


# ── FMU Building ─────────────────────────────────────────────────────────────

def build_fmu_with_pythonfmu(python_file: Path,
                             output_fmu: Path) -> Path:
    """
    Build an FMU from a Python class file using pythonfmu.
    
    Args:
        python_file: Path to Python file with FMU class
        output_fmu: Path where FMU should be placed
        
    Returns:
        Path to built FMU (same as output_fmu)
        
    Raises:
        RuntimeError: If pythonfmu build fails
        FileNotFoundError: If pythonfmu produces no FMU
    """
    ensure_dir_exists(output_fmu.parent)
    
    print(f"\n{'='*60}")
    print(f"  Building FMU with pythonfmu...")
    print(f"{'='*60}")
    
    # Run pythonfmu build
    ret = subprocess.run(
        [sys.executable, "-m", "pythonfmu", "build", "-f", str(python_file)],
        cwd=str(python_file.parent),
        capture_output=True,
        text=True
    )
    
    if ret.returncode != 0:
        print(ret.stdout)
        print(ret.stderr)
        raise RuntimeError("pythonfmu build failed — see output above.")
    
    # pythonfmu drops the .fmu next to the Python file
    built_files = list(python_file.parent.glob("*.fmu"))
    if not built_files:
        raise FileNotFoundError("pythonfmu produced no .fmu file.")
    
    built_fmu = built_files[0]
    
    # Move to output location
    import shutil
    shutil.move(str(built_fmu), str(output_fmu))
    
    print(f"  ✅ FMU built → {output_fmu}")
    return output_fmu


# ── FMU XML Metadata Fixing ──────────────────────────────────────────────────

def _indent_xml(elem, level=0):
    """Add pretty-printing indentation to XML element tree."""
    pad = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = pad
        for child in elem:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = pad
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = pad


def _deduplicate_unknown_indices(parent_elem) -> None:
    """Remove duplicate <Unknown index="..."/> entries in-place."""
    if parent_elem is None:
        return

    seen = set()
    for unknown in list(parent_elem.findall("Unknown")):
        idx = unknown.get("index")
        if idx in seen:
            parent_elem.remove(unknown)
            continue
        seen.add(idx)


def _normalize_fmi_unit_name(unit_name: str) -> str:
    """Convert a display unit string to an FMI-safe unit token."""
    token = re.sub(r"[^A-Za-z0-9_]", "_", unit_name.strip())
    token = re.sub(r"_+", "_", token).strip("_")
    if not token:
        return "unitless"
    if token[0].isdigit():
        token = f"u_{token}"
    return token


def _resolve_fmi_var_metadata(input_unit: str, output_unit: str) -> Dict[str, Dict[str, Any]]:
    """Resolve FMI-compatible quantity/unit/displayUnit metadata for u and y."""
    in_unit_raw = (input_unit or "").strip()
    out_unit_raw = (output_unit or "").strip()

    # Input: normalize power signal metadata for better importer behavior.
    if in_unit_raw.upper() == "MW":
        u_meta = {
            "quantity": "Power",
            "unit": "W",
            "display_unit": "MW",
            "unit_def": {
                "name": "W",
                "base_unit": {"kg": "1", "m": "2", "s": "-3"},
                "display_units": [{"name": "MW", "factor": "1e6"}],
            },
        }
    elif in_unit_raw.upper() == "W":
        u_meta = {
            "quantity": "Power",
            "unit": "W",
            "display_unit": "W",
            "unit_def": {
                "name": "W",
                "base_unit": {"kg": "1", "m": "2", "s": "-3"},
                "display_units": [{"name": "W", "factor": "1"}],
            },
        }
    else:
        in_unit_name = _normalize_fmi_unit_name(in_unit_raw) if in_unit_raw else "1"
        u_meta = {
            "quantity": "Power",
            "unit": in_unit_name,
            "display_unit": in_unit_name,
            "unit_def": {
                "name": in_unit_name,
                "base_unit": None,
                "display_units": [],
            },
        }

    # Output: map LCIA display units to importer-friendly FMI metadata.
    out_lower = out_unit_raw.lower()
    if out_lower.startswith("kg"):
        y_meta = {
            "quantity": "Mass",
            "unit": "kg",
            "display_unit": "kg",
            "unit_def": {
                "name": "kg",
                "base_unit": {"kg": "1"},
                "display_units": [{"name": "kg", "factor": "1"}],
            },
        }
    elif out_lower == "pt":
        y_meta = {
            "quantity": "ImpactScore",
            "unit": "Pt",
            "display_unit": "Pt",
            "unit_def": {
                "name": "Pt",
                "base_unit": None,
                "display_units": [{"name": "Pt", "factor": "1"}],
            },
        }
    else:
        out_unit_name = _normalize_fmi_unit_name(out_unit_raw) if out_unit_raw else "1"
        y_meta = {
            "quantity": "ImpactScore",
            "unit": out_unit_name,
            "display_unit": out_unit_name,
            "unit_def": {
                "name": out_unit_name,
                "base_unit": None,
                "display_units": [{"name": out_unit_name, "factor": "1"}],
            },
        }

    return {"u": u_meta, "y": y_meta}


def _ensure_unit_definition(
    root,
    unit_name: str,
    base_unit: Optional[Dict[str, str]] = None,
    display_units: Optional[List[Dict[str, str]]] = None,
) -> None:
    """Ensure modelDescription contains a UnitDefinitions entry for unit_name."""
    if not unit_name:
        return

    unit_defs = root.find("UnitDefinitions")
    if unit_defs is None:
        children = list(root)
        insert_at = len(children)
        order_after = {
            "ModelExchange",
            "CoSimulation",
        }
        order_before = {
            "TypeDefinitions",
            "LogCategories",
            "DefaultExperiment",
            "VendorAnnotations",
            "ModelVariables",
            "ModelStructure",
        }
        for i, child in enumerate(children):
            if child.tag in order_before:
                insert_at = i
                break
            if child.tag in order_after:
                insert_at = i + 1
        unit_defs = ET.Element("UnitDefinitions")
        root.insert(insert_at, unit_defs)

    for unit_elem in unit_defs.findall("Unit"):
        if unit_elem.get("name") == unit_name:
            target_unit = unit_elem
            break
    else:
        target_unit = ET.SubElement(unit_defs, "Unit")
        target_unit.set("name", unit_name)

    if base_unit:
        existing_base = target_unit.find("BaseUnit")
        if existing_base is None:
            existing_base = ET.SubElement(target_unit, "BaseUnit")
        for key, val in base_unit.items():
            existing_base.set(key, str(val))

    if display_units:
        existing_names = {d.get("name") for d in target_unit.findall("DisplayUnit")}
        for disp in display_units:
            name = str(disp.get("name", "")).strip()
            if not name or name in existing_names:
                continue
            disp_elem = ET.SubElement(target_unit, "DisplayUnit")
            disp_elem.set("name", name)
            for attr in ("factor", "offset"):
                if attr in disp and disp[attr] is not None:
                    disp_elem.set(attr, str(disp[attr]))
            existing_names.add(name)


def fix_fmu_metadata(fmu_path: Path,
                    output_path: Path,
                    output_var: str,
                    output_unit: str,
                    output_description: str,
                    input_var: str = "u",
                    input_unit: str = "W",
                    default_step_size: Optional[float] = None) -> Path:
    """
    Fix FMU ModelDescription.xml metadata.
    
    Adds InitialUnknowns section and ensures proper ModelStructure.
    
    Args:
        fmu_path: Path to input FMU (from pythonfmu)
        output_path: Path for fixed FMU
        output_var: Output variable name (e.g., "y")
        output_unit: Output unit (e.g., "kg CO2-eq")
        output_description: Output description
        input_var: Input variable name (e.g., "u")
        input_unit: Input unit (e.g., "MW")
        default_step_size: Optional FMI DefaultExperiment stepSize in seconds
        
    Returns:
        Path to fixed FMU
        
    Raises:
        RuntimeError: If FMU fixing fails
    """
    print(f"\n{'='*60}")
    print(f"  Fixing FMU metadata...")
    print(f"{'='*60}")
    
    try:
        with zipfile.ZipFile(fmu_path, 'r') as zin:
            # Read ModelDescription.xml
            with zin.open('modelDescription.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
            
            # Find ModelStructure
            ms = root.find("ModelStructure")
            if ms is None:
                ms = ET.SubElement(root, "ModelStructure")

            # Provide a practical communication-step hint for importing tools.
            # This helps avoid extremely small default sample periods.
            if default_step_size is not None and default_step_size > 0.0:
                default_experiment = root.find("DefaultExperiment")
                if default_experiment is not None:
                    root.remove(default_experiment)
                default_experiment = ET.Element("DefaultExperiment")
                default_experiment.set("stepSize", f"{default_step_size:.12g}")

                # FMI 2.0 element order requires DefaultExperiment before ModelVariables.
                children = list(root)
                insert_at = len(children)
                for i, child in enumerate(children):
                    if child.tag == "ModelVariables":
                        insert_at = i
                        break
                root.insert(insert_at, default_experiment)
            
            # Ensure Outputs section exists
            outputs = ms.find("Outputs")
            if outputs is None:
                outputs = ET.SubElement(ms, "Outputs")
            
            # Find output variable reference
            model_vars = root.find("ModelVariables")
            output_ref = None
            var_meta = _resolve_fmi_var_metadata(input_unit=input_unit, output_unit=output_unit)
            assigned_units = set()
            if model_vars is not None:
                for idx, var in enumerate(model_vars.findall("ScalarVariable"), start=1):
                    name = var.get("name")
                    real = var.find("Real")

                    # Ensure explicit FMI unit fields for plotting/interoperability.
                    if real is not None:
                        if name == input_var:
                            u_meta = var_meta["u"]
                            real.set("unit", u_meta["unit"])
                            real.set("displayUnit", u_meta["display_unit"])
                            real.set("quantity", u_meta["quantity"])
                            _ensure_unit_definition(
                                root,
                                unit_name=u_meta["unit_def"]["name"],
                                base_unit=u_meta["unit_def"]["base_unit"],
                                display_units=u_meta["unit_def"]["display_units"],
                            )
                            assigned_units.add(u_meta["unit"])
                        if name == output_var:
                            y_meta = var_meta["y"]
                            real.set("unit", y_meta["unit"])
                            real.set("displayUnit", y_meta["display_unit"])
                            real.set("quantity", y_meta["quantity"])
                            _ensure_unit_definition(
                                root,
                                unit_name=y_meta["unit_def"]["name"],
                                base_unit=y_meta["unit_def"]["base_unit"],
                                display_units=y_meta["unit_def"]["display_units"],
                            )
                            assigned_units.add(y_meta["unit"])

                    if name == output_var:
                        output_ref = str(idx)

            # FMI requires unit references to be declared in UnitDefinitions.
            for unit_name in sorted(assigned_units):
                _ensure_unit_definition(root, unit_name)
            
            # Add Unknown element for output
            if output_ref and outputs.find(f"./Unknown[@index='{output_ref}']") is None:
                unknown = ET.SubElement(outputs, "Unknown")
                unknown.set("index", output_ref)
            
            # Add InitialUnknowns if not present
            init_unknowns = ms.find("InitialUnknowns")
            if init_unknowns is None and output_ref:
                init_unknowns = ET.SubElement(ms, "InitialUnknowns")
                unknown = ET.SubElement(init_unknowns, "Unknown")
                unknown.set("index", output_ref)

            # De-duplicate Unknown entries to avoid duplicated equations in importers.
            _deduplicate_unknown_indices(outputs)
            _deduplicate_unknown_indices(init_unknowns)
            
            # Pretty print
            _indent_xml(root)
            
            # Write fixed FMU
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                # Copy all files except modelDescription.xml
                for item in zin.infolist():
                    if item.filename != 'modelDescription.xml':
                        data = zin.read(item.filename)
                        zout.writestr(item, data)
                
                # Write fixed modelDescription.xml
                xml_str = ET.tostring(root, encoding='unicode', method='xml')
                xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
                zout.writestr('modelDescription.xml', xml_str)
        
        print(f"  ✅ FMU metadata fixed → {output_path}")
        return output_path
        
    except Exception as e:
        raise RuntimeError(f"Failed to fix FMU metadata: {e}")


def package_fmu_as_bytecode(fmu_path: Path,
                            output_path: Optional[Path] = None) -> Path:
    """
    Repackage an FMU by compiling resource Python sources to bytecode.

    This removes readable .py files under resources/ and replaces them with
    .pyc files, preserving FMU archive structure for distribution use cases.

    Args:
        fmu_path: Input FMU path
        output_path: Optional output FMU path (in-place if None)

    Returns:
        Path to repackaged FMU
    """
    if not fmu_path.exists():
        raise FileNotFoundError(f"FMU not found for bytecode packaging: {fmu_path}")

    if output_path is None:
        output_path = fmu_path

    print(f"\n{'='*60}")
    print("  Packaging FMU resources as bytecode...")
    print(f"{'='*60}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        extracted = tmp_dir_path / "fmu_extract"
        extracted.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(fmu_path, "r") as zin:
            zin.extractall(extracted)

        resources_dir = extracted / "resources"
        if not resources_dir.exists():
            raise RuntimeError("FMU has no resources/ directory to package")

        slavemodule_file = resources_dir / "slavemodule.txt"
        if not slavemodule_file.exists():
            raise RuntimeError("FMU resources/slavemodule.txt is missing")

        module_name = slavemodule_file.read_text(encoding="utf-8", errors="replace").strip()
        if not module_name:
            raise RuntimeError("FMU resources/slavemodule.txt is empty")

        model_py = resources_dir / f"{module_name}.py"
        if not model_py.exists():
            raise RuntimeError(
                f"Expected model source file is missing: resources/{module_name}.py"
            )

        model_source = model_py.read_text(encoding="utf-8", errors="replace")
        class_match = re.search(r"^\s*class\s+(\w+)\s*\(", model_source, re.MULTILINE)
        if not class_match:
            raise RuntimeError(
                f"Could not detect model class declaration in resources/{module_name}.py"
            )

        class_name = class_match.group(1)
        impl_module_name = f"{module_name}_impl"
        impl_py = resources_dir / f"{impl_module_name}.py"

        # Move full implementation to a separate module, then compile it.
        model_py.replace(impl_py)
        py_compile.compile(
            str(impl_py),
            cfile=str(resources_dir / f"{impl_module_name}.pyc"),
            doraise=True,
            optimize=2,
        )
        impl_py.unlink()

        # Keep a tiny source stub for pythonfmu entry loading behavior.
        # A wrapper class is resilient to repeated imports/instantiations.
        model_py.write_text(
            textwrap.dedent(
                f'''\
                from pythonfmu import Fmi2Slave

                class {class_name}(Fmi2Slave):
                    def __new__(cls, *args, **kwargs):
                        from {impl_module_name} import {class_name} as _Impl
                        return _Impl(*args, **kwargs)
                '''
            ),
            encoding="utf-8",
        )

        py_files = [
            p for p in resources_dir.rglob("*.py")
            if p.is_file() and p != model_py
        ]

        compiled_count = 0
        for py_file in py_files:
            pyc_file = Path(str(py_file) + "c")
            try:
                py_compile.compile(
                    str(py_file),
                    cfile=str(pyc_file),
                    doraise=True,
                    optimize=2,
                )
                py_file.unlink()
                compiled_count += 1
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to compile FMU resource {py_file}: {exc}"
                )

        compiled_count += 1  # Count compiled model implementation module.

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for file_path in extracted.rglob("*"):
                if not file_path.is_file():
                    continue
                arcname = file_path.relative_to(extracted).as_posix()
                zout.write(file_path, arcname)

    print(f"  ✅ Bytecode packaging complete ({compiled_count} modules + loader stub)")
    print(f"  ✅ Repackaged FMU → {output_path}")
    return output_path


def _is_allowed_loader_stub(path_name: str, content: bytes, module_name: str) -> bool:
    """Return True if file is the minimal allowed loader stub."""
    expected = f"resources/{module_name}.py"
    if path_name != expected:
        return False

    try:
        text = content.decode("utf-8", errors="strict")
    except Exception:
        return False

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Allowed minimal wrapper stub pattern.
    if len(lines) != 5:
        return False

    base_pat = re.compile(r"^from\s+pythonfmu\s+import\s+Fmi2Slave$")
    class_pat = re.compile(r"^class\s+\w+\(Fmi2Slave\):\s*$")
    new_pat = re.compile(r"^def\s+__new__\(cls,\s*\*args,\s*\*\*kwargs\):\s*$")
    import_pat = re.compile(
        rf"^from\s+{re.escape(module_name)}_impl\s+import\s+\w+\s+as\s+_Impl$"
    )
    return_pat = re.compile(r"^return\s+_Impl\(\*args,\s*\*\*kwargs\)$")

    return bool(
        base_pat.match(lines[0])
        and class_pat.match(lines[1])
        and new_pat.match(lines[2])
        and import_pat.match(lines[3])
        and return_pat.match(lines[4])
    )


# ── Compliance Audit ─────────────────────────────────────────────────────────

def audit_fmu_blackbox(fmu_path: Path) -> Tuple[bool, str]:
    """
    Audit FMU archive for black-box compliance.

        Compliance rule in this project:
        - Export FMUs must not contain readable implementation or data artifacts
            under resources/ (e.g., .json, .csv, .txt payloads).
        - A single minimal loader stub is allowed at resources/<slavemodule>.py if
            it only imports the compiled implementation module.
        - resources/slavemodule.txt is allowed for pythonfmu runtime wiring.

    Args:
        fmu_path: Path to FMU file

    Returns:
        (is_compliant, message)
    """
    if not fmu_path.exists():
        return False, f"FMU file not found: {fmu_path}"

    disallowed_exts = {
        ".py", ".pyi", ".json", ".csv", ".yaml", ".yml", ".toml", ".ini", ".txt"
    }
    allowed_text_files = {"resources/slavemodule.txt"}
    violations: List[str] = []

    try:
        with zipfile.ZipFile(fmu_path, "r") as zf:
            module_name = ""
            try:
                module_name = zf.read("resources/slavemodule.txt").decode("utf-8", errors="replace").strip()
            except Exception:
                module_name = ""

            for entry in zf.infolist():
                name = entry.filename.replace("\\", "/")
                lower_name = name.lower()

                # Skip directories
                if lower_name.endswith("/"):
                    continue

                # We only audit payload exposure here; modelDescription.xml is expected.
                if not lower_name.startswith("resources/"):
                    continue

                ext = Path(lower_name).suffix
                if ext in disallowed_exts:
                    if lower_name in allowed_text_files:
                        continue

                    if ext == ".py" and module_name:
                        try:
                            raw = zf.read(entry.filename)
                        except Exception:
                            raw = b""
                        if _is_allowed_loader_stub(name, raw, module_name):
                            continue

                    violations.append(name)

    except Exception as exc:
        return False, f"Compliance audit failed: {exc}"

    if violations:
        preview = ", ".join(violations[:8])
        more = "" if len(violations) <= 8 else f" (+{len(violations) - 8} more)"
        return (
            False,
            "Non-black-box FMU: readable resources detected: "
            f"{preview}{more}"
        )

    return True, "Black-box audit passed: no readable resource payloads detected"


# ── FMU Validation ───────────────────────────────────────────────────────────

def validate_fmu(fmu_path: Path) -> Tuple[bool, str]:
    """
    Validate an FMU using fmpy.
    
    Args:
        fmu_path: Path to FMU file
        
    Returns:
        Tuple of (is_valid, message)
        
    Examples:
        >>> valid, msg = validate_fmu(Path("Grid.fmu"))
        >>> if valid:
        ...     print("FMU is valid!")
    """
    try:
        import fmpy
        
        print(f"\n{'='*60}")
        print(f"  Validating FMU with fmpy...")
        print(f"{'='*60}")
        
        # Read model description
        model_desc = fmpy.read_model_description(str(fmu_path))
        
        # Check basic properties
        if not model_desc:
            return False, "Failed to read model description"
        
        print(f"  Model Name: {model_desc.modelName}")
        print(f"  FMI Version: {model_desc.fmiVersion}")
        print(f"  Variables: {len(model_desc.modelVariables)}")
        
        # List variables
        print(f"\n  Variables:")
        for var in model_desc.modelVariables:
            causality = getattr(var, 'causality', 'unknown')
            print(f"    {var.name:20s} [{causality:10s}]")
        
        print(f"\n  ✅ FMU validation successful!")
        return True, "FMU is valid"
        
    except ImportError:
        return False, "fmpy not installed"
    except Exception as e:
        return False, f"Validation failed: {e}"

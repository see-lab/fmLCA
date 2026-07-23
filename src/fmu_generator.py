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
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from .lca_utils import safe_classname, ensure_dir_exists


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
        # Sum score_pt from all endpoint results
        total_pt = 0.0
        found = 0
        for data in impact_data.values():
            if isinstance(data, dict) and "score_pt" in data:
                total_pt += data["score_pt"]
                found += 1
        
        if found == 0:
            print("  ⚠️  No Pt scores found — using placeholder factors (0).")
            return {
                "base_impact": 0.0,
                "energy_factor": 0.0,
                "scaling_factor": 1.0,
                "unit": out_unit
            }
        
        factor = total_pt / energy_mj if energy_mj else 0.0
        print(f"  ✅ Single score: {total_pt:.4f} Pt  ({found} damage categories), "
              f"factor/MJ = {factor:.4e} Pt/MJ")
        
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
        factor = total / energy_mj if energy_mj else 0.0
        
        print(f"  ✅ Extracted: total = {total:.4e} {unit}, factor/MJ = {factor:.4e}")
        
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
    
    # Get stage breakdown for the first method (should only be one)
    for method_stages in stage_breakdown.values():
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
        
        break  # Only process first method
    
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
    use_rate_mwh = factors["energy_factor"] * 3600.0  # Convert MJ to MWh
    
    code = textwrap.dedent(f'''\
        """
        Auto-generated LCA FMU: {fmu_name}
        Input  u : Power [MW]  (power_input_mw)
        Output y : Cumulative {out_label}  [{out_unit}]  ({out_var}_cumulative)
        
        This FMU tracks cumulative environmental impacts over time:
        - At t=start: Add production + transport embodied impacts
        - During operation: Integrate use phase impacts from power × time
        - At t=stop: Add end-of-life impacts
        
        Uses pre-computed factors for fast calculation.
        Use rate: {use_rate_mwh:.4e} {out_unit}/MWh
        """
        from pythonfmu import Fmi2Slave, Fmi2Causality, Fmi2Variability, Fmi2Initial
        from pythonfmu.variables import Real

        class {class_name}(Fmi2Slave):
            """{fmu_name} – LCA FMU with Cumulative Impact Tracking"""

            def __init__(self, **kwargs):
                super().__init__(**kwargs)

                # u — power input in MW (maps to: power_input_mw)
                self.register_variable(Real(
                    "u",
                    start=0.0,
                    causality=Fmi2Causality.input,
                    variability=Fmi2Variability.continuous,
                    initial=Fmi2Initial.exact,
                    description="Power input [MW] (power_input_mw)",
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
                
                # Use phase rate: impact per MWh
                self.use_rate_per_mwh = {factors["energy_factor"]:.8e} * 3600.0  # {out_unit}/MWh

                # State variables
                self.u = 0.0
                self.y = 0.0
                self.use_phase_impact = 0.0
                self.eol_added = False

            def do_step(self, current_time: float, step_size: float) -> bool:
                try:
                    # Get current power input
                    power_prev = self.u
                    self.u = self.get_real(["u"])[0]
                    power_curr = self.u
                    
                    # Trapezoidal integration
                    avg_power = (power_prev + power_curr) / 2.0
                    impact_rate = avg_power * self.use_rate_per_mwh
                    step_impact = impact_rate * (step_size / 3600.0)  # step_size in seconds → hours
                    
                    self.use_phase_impact += step_impact
                    
                    # Update cumulative impact
                    self.y = (self.production_impact + 
                             self.transport_impact + 
                             self.use_phase_impact +
                             (self.eol_impact if self.eol_added else 0.0))
                    
                    self.set_real(["y"], [self.y])
                    return True
                    
                except Exception as exc:
                    print(f"FMU step error: {{exc}}")
                    return False

            def exit_initialization_mode(self):
                # Initialize with embodied impacts
                self.y = self.production_impact + self.transport_impact
                self.use_phase_impact = 0.0
                self.eol_added = False
                self.set_real(["y"], [self.y])
                return True

            def terminate(self):
                # Add end-of-life impacts
                if not self.eol_added:
                    self.eol_added = True
                    self.y += self.eol_impact
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


def fix_fmu_metadata(fmu_path: Path,
                    output_path: Path,
                    output_var: str,
                    output_unit: str,
                    output_description: str) -> Path:
    """
    Fix FMU ModelDescription.xml metadata.
    
    Adds InitialUnknowns section and ensures proper ModelStructure.
    
    Args:
        fmu_path: Path to input FMU (from pythonfmu)
        output_path: Path for fixed FMU
        output_var: Output variable name (e.g., "y")
        output_unit: Output unit (e.g., "kg CO2-eq")
        output_description: Output description
        
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
            
            # Ensure Outputs section exists
            outputs = ms.find("Outputs")
            if outputs is None:
                outputs = ET.SubElement(ms, "Outputs")
            
            # Find output variable reference
            model_vars = root.find("ModelVariables")
            output_ref = None
            if model_vars is not None:
                for idx, var in enumerate(model_vars.findall("ScalarVariable"), start=1):
                    if var.get("name") == output_var:
                        output_ref = str(idx)
                        break
            
            # Add Unknown element for output
            if output_ref and not outputs.find(f".//Unknown[@index='{output_ref}']"):
                unknown = ET.SubElement(outputs, "Unknown")
                unknown.set("index", output_ref)
            
            # Add InitialUnknowns if not present
            init_unknowns = ms.find("InitialUnknowns")
            if init_unknowns is None and output_ref:
                init_unknowns = ET.SubElement(ms, "InitialUnknowns")
                unknown = ET.SubElement(init_unknowns, "Unknown")
                unknown.set("index", output_ref)
            
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

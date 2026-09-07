# LCA Analysis Engine - Redesigned for Energy Applications
# Flexible, configuration-driven LCA analysis with energy-based inputs
# Supports multiple databases, methods, and input parameters

import json
import ast
import tempfile
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import argparse
import traceback
import shutil
import re
from pathlib import Path

# Import Brightway components
from bw2data import projects, databases, Database, methods
from bw2calc import LCA
from bw2io import bw2setup

# Import new modular components - handle both relative and absolute imports
try:
    # Try relative imports first (when run as package)
    from .config_manager import get_config
    from .database_manager import DatabaseManager
    from .lci_data_manager import LCIDataManager
    from .lca_utils import get_inventory_dir, get_methods_dir
except ImportError:
    # Fall back to absolute imports (when run directly)
    import sys
    from pathlib import Path
    
    # Add src directory to path if not already there
    src_dir = Path(__file__).parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    from config_manager import get_config
    from database_manager import DatabaseManager
    from lci_data_manager import LCIDataManager
    from lca_utils import get_inventory_dir, get_methods_dir

# Initialize configuration
config = get_config()

# Projects directory and set up
print("🚀 LCA Analysis Engine - Energy Applications")
print(f"📁 Current project: {projects.current}")
print(f"🗂️  Projects directory: {projects.dir}")
print(f"📋 Available projects: {[str(p) for p in projects]}")

# ── LCIA Methods Loading ──────────────────────────────────────────────────────

def load_lcia_methods(methods_file):
    """
    Load LCIA methods from JSON file.
    Supports both formats:
    - Legacy: ["method1", "method2", ...]
    - Enhanced: [{"name": "method1", "description": "...", ...}, ...]
    - Brightway tuples: [{"name": "...", "brightway_tuple": ["tuple", "parts"], ...}, ...]
    
    Args:
        methods_file (str or Path): Path to methods JSON file
        
    Returns:
        tuple: (method_names: list, method_metadata: dict)
    """
    try:
        with open(methods_file, 'r') as f:
            data = json.load(f)
        
        methods_list = data.get("lcia_methods", [])
        method_names = []
        method_metadata = {}
        
        for item in methods_list:
            if isinstance(item, str):
                # Legacy format: just method name
                method_names.append(item)
            elif isinstance(item, dict):
                # Enhanced format: method with metadata
                name = item.get("name")
                brightway_tuple = item.get("brightway_tuple") or item.get("brightway_tuple_hint")
                
                # Use brightway_tuple if available, otherwise use name
                method_key = tuple(brightway_tuple) if brightway_tuple else name
                
                if method_key:
                    method_names.append(method_key)
                    method_metadata[str(method_key)] = {
                        "name": name,
                        "description": item.get("description", ""),
                        "category": item.get("category", ""),
                        "unit": item.get("unit", ""),
                        "endpoint": item.get("endpoint", False),
                        "midpoint": item.get("midpoint", False),
                        "aggregate": item.get("aggregate", False),
                        "time_horizon": item.get("time_horizon"),
                        "brightway_tuple": brightway_tuple
                    }
        
        return method_names, method_metadata
        
    except Exception as e:
        print(f"⚠️ Error loading methods file: {e}")
        return [], {}


def print_method_info(method_names, method_metadata):
    """Print information about loaded methods including descriptions."""
    if not method_names:
        return
    
    print(f"\n📋 Loaded {len(method_names)} LCIA method(s):")
    for method_key in method_names:
        str_key = str(method_key)
        if str_key in method_metadata:
            meta = method_metadata[str_key]
            name = meta.get("name", str_key)
            desc = meta.get("description", "")
            unit = meta.get("unit", "")
            print(f"  • {name}")
            if desc:
                print(f"    {desc}")
            if unit:
                print(f"    Unit: {unit}")
        else:
            # Handle simple string methods
            print(f"  • {method_key}")

# ──────────────────────────────────────────────────────────────────────────────

def find_and_setup_project():
    """
    Find available ecoinvent database in the current project
    
    Returns:
        str or None: Name of the ecoinvent database if found, None otherwise
    """
    available_dbs = list(databases)
    
    # Look for ecoinvent databases (in order of preference)
    ecoinvent_patterns = [
        'ecoinvent-3.12-cutoff',
        'ecoinvent-3.11-cutoff', 
        'ecoinvent-3.10-cutoff',
        'ecoinvent-3.9-cutoff',
        'ecoinvent-3.8-cutoff'
    ]
    
    for pattern in ecoinvent_patterns:
        if pattern in available_dbs:
            return pattern
    
    # Fallback: look for any database containing 'ecoinvent'
    for db_name in available_dbs:
        if 'ecoinvent' in db_name.lower():
            return db_name
    
    return None


# ---------------------------------------------------------------------------
# Persistent project name.
# ---------------------------------------------------------------------------
LCA_FMU_PROJECT = "fmLCA"

# Known source projects that can be copied from (ordered by preference)
_KNOWN_SOURCE_PROJECTS = [
    "Class 1",                     # has ecoinvent-3.12-cutoff
    "simapro-ecoinvent-import",    # has ecoinvent-3.10-cutoff
]


def switch_to_project_with_database(target_db_name):
    """
    Ensure we are in a Brightway project that contains *target_db_name*.

    Fast path:  switch to the persistent 'fmLCA' project (instant).
    Slow path:  if a different DB version is needed, copy from a source
                project that has it (one-time cost per version).

    Args:
        target_db_name: e.g. 'ecoinvent-3.12-cutoff'

    Returns:
        bool – True if the current project now contains the target DB.
    """
    # 1. Already in the right place?
    if target_db_name in list(databases.keys()):
        print(f"✅ Current project already has {target_db_name}")
        return True

    # 2. Try the persistent fmLCA project (fast path)
    all_projects = [str(p).replace("Project: ", "") for p in projects]
    if LCA_FMU_PROJECT in all_projects:
        try:
            projects.set_current(LCA_FMU_PROJECT)
            if target_db_name in list(databases.keys()):
                print(f"✅ Switched to persistent project '{LCA_FMU_PROJECT}' "
                      f"(has {target_db_name})")
                return True
        except Exception as e:
            print(f"⚠️ Could not use '{LCA_FMU_PROJECT}': {e}")

    # 3. Slow fallback – find a source project and copy it
    print(f"🔄 '{LCA_FMU_PROJECT}' does not have {target_db_name}, "
          f"searching other projects…")

    source_project = _find_source_project_for_db(target_db_name)
    if not source_project:
        print(f"❌ No project found with database '{target_db_name}'")
        return False

    print(f"📦 Found source project '{source_project}' with {target_db_name}")

    # Copying full ecoinvent projects is expensive and can fill local disk.
    # Prefer switching directly to the source project.
    try:
        projects.set_current(source_project)
        if target_db_name in list(databases.keys()):
            print(f"✅ Switched to source project '{source_project}' "
                  f"(has {target_db_name})")
            return True
        print(f"❌ Project '{source_project}' does not contain '{target_db_name}' after switch")
        return False
    except Exception as e:
        print(f"❌ Failed to switch to source project: {e}")
        return False


def _find_source_project_for_db(target_db_name):
    """Find an existing project that contains *target_db_name*."""
    # Try known-good projects first (avoids corrupt ones)
    for pname in _KNOWN_SOURCE_PROJECTS:
        try:
            projects.set_current(pname)
            if target_db_name in list(databases.keys()):
                return pname
        except Exception:
            continue

    # Fallback: iterate all projects
    for p in projects:
        pname = str(p).replace("Project: ", "")
        if pname in _KNOWN_SOURCE_PROJECTS:
            continue
        try:
            projects.set_current(pname)
            if target_db_name in list(databases.keys()):
                return pname
        except Exception:
            continue

    return None


RECIPE_ENDPOINT_SINGLE_SCORE_FACTORS = {
    "total human health": {
        "normalization_denom": 2.3983071517732924e-02,  # DALY
        "weight": 0.4,
        "damage_unit": "DALY",
    },
    "total ecosystem quality": {
        "normalization_denom": 1.4793022106342942e-03,  # species.yr
        "weight": 0.4,
        "damage_unit": "species.yr",
    },
    "total natural resources": {
        "normalization_denom": 2.8010825716165531e04,  # USD2013
        "weight": 0.2,
        "damage_unit": "USD2013",
    },
}


def _recipe_single_score_config(method_obj):
    """Return ReCiPe single-score conversion config for endpoint totals, else None."""
    method_text = str(method_obj).lower()
    method_norm = " ".join(re.sub(r"[^a-z0-9]+", " ", method_text).split())
    if "recipe 2016" not in method_text or "endpoint (h)" not in method_text:
        return None

    for key, cfg in RECIPE_ENDPOINT_SINGLE_SCORE_FACTORS.items():
        key_norm = " ".join(re.sub(r"[^a-z0-9]+", " ", key.lower()).split())
        if key_norm in method_norm:
            return cfg
    return None


def _damage_to_single_score_pt(damage_score, conversion_cfg):
    """Convert ReCiPe damage-level score to single-score points (Pt)."""
    normalization_denom = float(conversion_cfg["normalization_denom"])
    weight = float(conversion_cfg["weight"])

    normalized_score = float(damage_score) / normalization_denom if normalization_denom else 0.0
    score_kpt = normalized_score * weight
    score_pt = score_kpt * 1000.0

    return {
        "normalized_score": float(normalized_score),
        "score_kpt": float(score_kpt),
        "score_pt": float(score_pt),
    }


def _convert_stage_breakdown_to_recipe_pt(stage_breakdown, conversion_cfg):
    """Convert stage scores from ReCiPe damage units to single-score Pt."""
    converted = {}
    for stage_name, info in (stage_breakdown or {}).items():
        score = 0.0
        if isinstance(info, dict):
            score = float(info.get("score", 0.0))

        pt_data = _damage_to_single_score_pt(score, conversion_cfg)
        converted[stage_name] = {
            "score": pt_data["score_pt"],
            "unit": "Pt",
            "damage_score": score,
            "damage_unit": conversion_cfg.get("damage_unit", "impact units"),
            "normalized_score": pt_data["normalized_score"],
            "score_kpt": pt_data["score_kpt"],
            "score_pt": pt_data["score_pt"],
        }

    return converted


def run_lca_energy(lci_file, lcia_methods, functional_unit, energy_amount_mj=180.0):
    """
    Run LCA analysis with energy-based inputs using the new modular architecture
    
    Args:
        lci_file (str): Path to LCI JSON file
        lcia_methods (list): List of LCIA method names
        functional_unit (dict): Functional unit definition
        energy_amount_mj (float): Amount of energy input in MJ for primary process
    
    Returns:
        dict: LCIA results
    """
    temp_db_name = None
    try:
        # Pre-load LCI file to detect required database
        with open(lci_file, 'r') as f:
            lci_preview = json.load(f)
        
        # Find required ecoinvent database from exchanges
        required_db = None
        for exc in lci_preview.get('exchanges', []):
            inp = exc.get('input', [])
            if len(inp) >= 2 and 'ecoinvent' in inp[0].lower():
                required_db = inp[0]
                break
        
        if required_db:
            print(f"🔍 LCI file requires database: {required_db}")
            if not switch_to_project_with_database(required_db):
                return {"error": f"No Brightway project found with database '{required_db}'"}
        
        # Initialize managers
        db_manager = DatabaseManager()
        lci_manager = LCIDataManager()
        
        print(f"🔄 Loading LCI data from {lci_file}")
        
        # Load and process LCI data with new manager
        lci_data = lci_manager.import_data(lci_file)
        if not lci_data:
            return {"error": "Failed to load LCI data"}
        
        print(f"✅ LCI data loaded: {lci_data.get('name', 'Unknown process')}")
        
        # Setup database using database manager
        primary_db = db_manager.find_primary_database()
        if not primary_db:
            return {
                "error": "No compatible database found",
                "available_databases": list(databases.keys()),
                "note": "Please ensure ecoinvent or compatible database is imported"
            }
        
        print(f"✅ Using primary database: {primary_db}")
        
        # Process energy-based scaling in base Joules to avoid unit assumptions.
        primary_input = lci_data.get('energy_metadata', {}).get('primary_input', {})
        base_energy_value = float(primary_input.get('value', 180.0))
        base_energy_unit = str(primary_input.get('unit', 'MJ')).strip().upper()

        to_j_factor = {
            "J": 1.0,
            "WH": 3.6e3,
            "KWH": 3.6e6,
            "MWH": 3.6e9,
            "MJ": 1.0e6,
            "GJ": 1.0e9,
            "TJ": 1.0e12,
        }.get(base_energy_unit)

        if to_j_factor is None:
            return {"error": f"Unsupported energy metadata unit: {base_energy_unit}"}

        base_energy_j = base_energy_value * to_j_factor
        if base_energy_j == 0:
            return {"error": "Invalid energy metadata: primary_input.value is 0"}

        target_energy_j = float(energy_amount_mj) * 1.0e6
        scaling_factor = target_energy_j / base_energy_j
        
        # Create temporary database name
        process_name = lci_data.get('name', 'process').replace(' ', '_')
        temp_db_name = db_manager.create_temp_database(process_name)
        
        # Process inventory creation (simplified approach)
        process_data = create_simple_process_inventory(
            lci_data, 
            temp_db_name,
            primary_db,
            scaling_factor,
            db_manager
        )
        
        if not process_data:
            return {"error": "Failed to create process inventory"}
        
        # Write database (with low-disk fallback for SQLite VACUUM failures)
        db = Database(temp_db_name)
        _write_temp_database(db, process_data)
        print(f"✅ Created temporary database: {temp_db_name}")
        
        # Get main process for calculation - simplified approach
        main_process_code = list(process_data.keys())[0][1]
        main_process_name = lci_data.get('name', 'Unknown Process')
        
        print(f"✅ Main process ready: {main_process_name}")
        
        # Create a functional unit reference
        functional_unit_ref = (temp_db_name, main_process_code)
        
        # Perform LCIA calculations
        print("\n=== LCIA Calculations ===")
        results = {
            "setup": "complete",
            "database": temp_db_name,
            "main_process": main_process_name,
            "functional_unit": f"1 {lci_data.get('unit', 'unit')}",
            "energy_input": energy_amount_mj,
            "scaling_factor": scaling_factor,
            "impact_results": {},
            "stage_breakdown": {},
            "life_cycle_stages": lci_data.get('life_cycle_stages', {})
        }
        
        # Resolve LCIA methods
        resolved_methods = resolve_lcia_methods(lcia_methods)
        if not resolved_methods:
            print("⚠️ No methods resolved, using default climate change method")
            resolved_methods = get_default_climate_methods()
        
        # Calculate impacts - create proper functional unit
        from bw2data import get_activity
        try:
            main_activity = get_activity(functional_unit_ref)
            functional_unit_lca = {main_activity: 1}
        except:
            print("⚠️ Using fallback functional unit approach")
            functional_unit_lca = {functional_unit_ref: 1}
        
        for method in resolved_methods:
            try:
                simplified_name = simplify_method_name(str(method))
                method_unit = get_method_unit(str(method))
                print(f"\n🔄 Calculating: {simplified_name}")
                
                # Perform LCA calculation
                lca = LCA(functional_unit_lca, method)
                lca.lci()
                lca.lcia()
                
                impact_score = float(lca.score)

                # Calculate stage breakdown using actual LCA results.
                stage_breakdown = calculate_stage_breakdown_with_lca(
                    lci_data, lca, method_unit, temp_db_name
                )

                recipe_cfg = _recipe_single_score_config(method)
                if recipe_cfg is not None:
                    pt_data = _damage_to_single_score_pt(impact_score, recipe_cfg)
                    results["impact_results"][str(method)] = {
                        "total_score": pt_data["score_pt"],
                        "unit": "Pt",
                        "method_name": simplified_name,
                        "damage_score": impact_score,
                        "damage_unit": recipe_cfg.get("damage_unit", method_unit),
                        "normalized_score": pt_data["normalized_score"],
                        "score_kpt": pt_data["score_kpt"],
                        "score_pt": pt_data["score_pt"],
                    }

                    results["stage_breakdown"][str(method)] = _convert_stage_breakdown_to_recipe_pt(
                        stage_breakdown,
                        recipe_cfg,
                    )

                    print(
                        "  ✅ Total impact (single score): "
                        f"{pt_data['score_pt']:.6e} Pt "
                        f"[damage={impact_score:.6e} {recipe_cfg.get('damage_unit', method_unit)}, "
                        f"normalized={pt_data['normalized_score']:.6e}, "
                        f"weighted={pt_data['score_kpt']:.6e} kPt]"
                    )
                else:
                    results["impact_results"][str(method)] = {
                        "total_score": impact_score,
                        "unit": method_unit,
                        "method_name": simplified_name
                    }

                    results["stage_breakdown"][str(method)] = stage_breakdown
                    print(f"  ✅ Total impact: {impact_score:.6e} {method_unit}")
                
            except Exception as e:
                print(f"  ❌ Error with method {simplified_name}: {e}")
                results["impact_results"][str(method)] = {"error": str(e)}
        
        # Cleanup temporary database
        try:
            if temp_db_name in databases:
                del databases[temp_db_name]
                print(f"🧹 Cleaned up temporary database: {temp_db_name}")
        except Exception as e:
            print(f"⚠️ Could not cleanup database {temp_db_name}: {e}")
        
        # Cleanup temporary project (if we created one)
        current_project = str(projects.current)
        if current_project.startswith("LCA_tmp_"):
            try:
                projects.set_current("default")
                projects.delete_project(current_project, delete_dir=True)
                print(f"🧹 Cleaned up temporary project: {current_project}")
            except Exception as e:
                print(f"⚠️ Could not cleanup project {current_project}: {e}")
        
        print(f"\n✅ LCA calculation complete!")
        return results
        
    except Exception as e:
        import traceback
        print(f"❌ Error in run_lca_energy: {str(e)}")
        print("Traceback:")
        traceback.print_exc()

        # Best-effort cleanup even on failure.
        try:
            if temp_db_name and temp_db_name in databases:
                del databases[temp_db_name]
                print(f"🧹 Cleaned up temporary database after error: {temp_db_name}")
        except Exception as cleanup_err:
            print(f"⚠️ Cleanup warning (database): {cleanup_err}")

        try:
            current_project = str(projects.current)
            if current_project.startswith("LCA_tmp_"):
                projects.set_current("default")
                projects.delete_project(current_project, delete_dir=True)
                print(f"🧹 Cleaned up temporary project after error: {current_project}")
        except Exception as cleanup_err:
            print(f"⚠️ Cleanup warning (project): {cleanup_err}")

        return {"error": str(e), "traceback": traceback.format_exc()}


def run_lca(lci_file, lcia_methods, parameter_values=None, functional_unit=None, energy_amount_mj=180.0):
    """Run LCA with optional parameter overrides passed as direct input."""
    functional_unit = functional_unit or {}
    if not parameter_values:
        return run_lca_energy(lci_file, lcia_methods, functional_unit, energy_amount_mj)

    with open(lci_file, 'r', encoding='utf-8') as f:
        lci_data = json.load(f)

    for name, value in parameter_values.items():
        if name not in lci_data.get("parameters", {}):
            raise ValueError(f"Unknown parameter '{name}' in {lci_file}")
        lci_data["parameters"][name]["default"] = float(value)

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
    try:
        with temp_file:
            json.dump(lci_data, temp_file, indent=2)
        return run_lca_energy(temp_file.name, lcia_methods, functional_unit, energy_amount_mj)
    finally:
        try:
            Path(temp_file.name).unlink(missing_ok=True)
        except Exception:
            pass


def _write_temp_database(db, process_data):
    """Write a temporary Brightway DB and retry once without VACUUM on low-disk errors."""
    try:
        db.write(process_data)
        return
    except Exception as exc:
        err_text = str(exc).lower()
        tb_text = traceback.format_exc().lower()
        disk_full = (
            "database or disk is full" in err_text
            or "database or disk is full" in tb_text
            or "no space left" in err_text
            or "no space left" in tb_text
        )

        if not disk_full:
            raise

        print("⚠️ Disk-space issue detected during temporary DB write")
        print("   Retrying once with VACUUM temporarily disabled...")

        import bw2data.sqlite as bw_sqlite

        original_vacuum = bw_sqlite.SubstitutableDatabase.vacuum

        def _noop_vacuum(self):
            return None

        try:
            bw_sqlite.SubstitutableDatabase.vacuum = _noop_vacuum
            db.write(process_data)
            print("✅ Temporary DB write succeeded with low-disk fallback")
            return
        except Exception as retry_exc:
            free_gb, total_gb = _get_workspace_drive_space_gb()
            raise RuntimeError(
                "Brightway DB write failed due to low disk space even after fallback. "
                f"Drive free space: {free_gb:.2f} GB / {total_gb:.2f} GB. "
                "Free space or remove unused Brightway projects under "
                "your Brightway data directory (for example, user-local pylca/Brightway storage), then retry."
            ) from retry_exc
        finally:
            bw_sqlite.SubstitutableDatabase.vacuum = original_vacuum


def _get_workspace_drive_space_gb():
    """Return (free_gb, total_gb) for the workspace drive."""
    usage = shutil.disk_usage(str(Path.cwd()))
    gib = 1024 ** 3
    return usage.free / gib, usage.total / gib


def _resolve_exchange_input(exchange, primary_db):
    """
    Resolve the Brightway (database, code) key for a technosphere exchange.
    
    1. Try the explicit input codes from the JSON.
    2. If the code doesn't exist in the DB, fall back to name+location search.
    3. Uses 'process_match' field as preferred search name if available.
    
    Returns:
        tuple or None: (database, code) key, or None if unresolvable
    """
    from bw2data import get_activity
    
    inp = exchange.get('input', [])
    db_name = inp[0] if len(inp) >= 1 else primary_db
    code = inp[1] if len(inp) >= 2 else None
    
    # 1. Try the explicit code — verify it actually exists in the database
    if code:
        try:
            act = get_activity((db_name, code))
            # Double-check we got a real activity back
            if act and act.get('name'):
                return (db_name, code)
        except Exception:
            pass  # code invalid – fall through to name search
        print(f"   ⚠️ Code '{code}' not found in '{db_name}', trying name search...")
    
    # 2. Name-based search
    search_name = exchange.get('process_match') or exchange.get('name', '')
    target_location = exchange.get('location')
    
    if not search_name:
        return None
    
    try:
        db_obj = Database(db_name)
        # Search by name keywords
        candidates = [
            a for a in db_obj
            if search_name.lower() in a.get('name', '').lower()
        ]
        
        if not candidates:
            # Try individual keywords (at least 2 must match)
            keywords = search_name.lower().split()
            candidates = [
                a for a in db_obj
                if sum(1 for kw in keywords if kw in a.get('name', '').lower()) >= max(2, len(keywords) // 2)
            ]
        
        if candidates and target_location:
            # Prefer matching location
            loc_match = [a for a in candidates if a.get('location') == target_location]
            if loc_match:
                candidates = loc_match
        
        if candidates:
            selected = candidates[0]
            print(f"   🔄 Resolved '{search_name}' → '{selected.get('name')}' [{selected.get('location')}] (code: {selected.get('code')[:12]}…)")
            return (db_name, selected.get('code'))
    except Exception as e:
        print(f"   ⚠️ Name search failed for '{search_name}': {e}")
    
    return None


def create_simple_process_inventory(lci_data, db_name, primary_db, scaling_factor, db_manager):
    """
    Create process inventory with simplified approach
    """
    try:
        process_data = {}
        process_key = (db_name, lci_data.get('code', 'main_process'))
        
        # Create main process
        process_data[process_key] = {
            'name': lci_data.get('name', 'Unknown Process'),
            'unit': lci_data.get('unit', 'kg'),
            'location': lci_data.get('location', 'GLO'),
            'categories': tuple(lci_data.get('categories', [])),
            'type': 'process',
            'exchanges': []
        }
        
        # Add production exchange
        process_data[process_key]['exchanges'].append({
            'name': lci_data.get('name', 'Unknown Process'),
            'amount': 1.0,
            'unit': lci_data.get('unit', 'kg'),
            'type': 'production',
            'input': process_key
        })
        
        # Add technosphere exchanges
        exchanges = lci_data.get('exchanges', [])

        def _normalize_energy_unit(unit: str) -> str:
            u = str(unit or "").strip().lower()
            aliases = {
                "j": "J",
                "joule": "J",
                "joules": "J",
                "mj": "MJ",
                "megajoule": "MJ",
                "megajoules": "MJ",
                "mwh": "MWH",
                "megawatt hour": "MWH",
                "megawatt hours": "MWH",
                "kwh": "KWH",
                "kilowatt hour": "KWH",
                "kilowatt hours": "KWH",
                "wh": "WH",
                "watt hour": "WH",
                "watt hours": "WH",
                "gj": "GJ",
                "gigajoule": "GJ",
                "gigajoules": "GJ",
                "tj": "TJ",
                "terajoule": "TJ",
                "terajoules": "TJ",
            }
            return aliases.get(u, str(unit or "").upper())

        def _to_j_factor(unit: str) -> float:
            u = _normalize_energy_unit(unit)
            factors = {
                "J": 1.0,
                "WH": 3.6e3,
                "KWH": 3.6e6,
                "MWH": 3.6e9,
                "MJ": 1.0e6,
                "GJ": 1.0e9,
                "TJ": 1.0e12,
            }
            if u not in factors:
                raise ValueError(f"Unsupported energy unit for conversion: {unit}")
            return factors[u]

        parameter_defaults = {
            name: float(info.get("default", 1.0))
            for name, info in lci_data.get("parameters", {}).items()
            if isinstance(info, dict)
        }

        def _eval_amount_expression(raw_amount, exchange_name: str) -> float:
            if isinstance(raw_amount, (int, float)):
                return float(raw_amount)
            if raw_amount is None:
                return 1.0

            expr = str(raw_amount).strip()
            if not expr:
                return 1.0

            try:
                return float(expr)
            except ValueError:
                pass

            tree = ast.parse(expr, mode="eval")

            def _eval_node(node):
                if isinstance(node, ast.Expression):
                    return _eval_node(node.body)
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return float(node.value)
                if isinstance(node, ast.Name):
                    if node.id in parameter_defaults:
                        return float(parameter_defaults[node.id])
                    raise ValueError(f"Unknown parameter '{node.id}'")
                if isinstance(node, ast.BinOp):
                    left = _eval_node(node.left)
                    right = _eval_node(node.right)
                    if isinstance(node.op, ast.Add):
                        return left + right
                    if isinstance(node.op, ast.Sub):
                        return left - right
                    if isinstance(node.op, ast.Mult):
                        return left * right
                    if isinstance(node.op, ast.Div):
                        return left / right
                    if isinstance(node.op, ast.Pow):
                        return left ** right
                    raise ValueError("Unsupported math operator")
                if isinstance(node, ast.UnaryOp):
                    value = _eval_node(node.operand)
                    if isinstance(node.op, ast.UAdd):
                        return value
                    if isinstance(node.op, ast.USub):
                        return -value
                    raise ValueError("Unsupported unary operator")
                raise ValueError("Unsupported expression syntax")

            try:
                return float(_eval_node(tree))
            except Exception as exc:
                raise ValueError(
                    f"Invalid amount expression '{expr}' for exchange '{exchange_name}': {exc}"
                )
        
        for exchange in exchanges:
            if exchange.get('type') == 'technosphere':
                input_key = _resolve_exchange_input(exchange, primary_db)
                if input_key is None:
                    print(f"   ⚠️ Skipping unresolved process: {exchange.get('name', 'Unknown')}")
                    continue
                
                # Handle amount_ref (energy metadata reference) or direct amount
                if 'amount_ref' in exchange:
                    # Resolve the reference path (e.g., "energy_metadata.primary_input.value")
                    primary_input = lci_data.get('energy_metadata', {}).get('primary_input', {})
                    base_amount_raw = float(primary_input.get('value', 1.0))
                    base_unit_raw = str(primary_input.get('unit', 'MJ'))
                    exchange_multiplier = _eval_amount_expression(
                        exchange.get('amount', 1.0),
                        exchange.get('name', 'Unknown')
                    )

                    scaled_amount_raw = base_amount_raw * scaling_factor
                    scaled_amount_j = scaled_amount_raw * _to_j_factor(base_unit_raw)

                    # Prefer the linked Brightway activity unit to avoid mismatches.
                    exchange_unit_raw = exchange.get('unit')
                    activity_name = ''
                    try:
                        from bw2data import get_activity
                        act = get_activity(input_key)
                        activity_unit = str(act.get('unit', '') or '').strip()
                        activity_name = str(act.get('name', '') or '').strip()
                    except Exception:
                        activity_unit = ''

                    if activity_unit:
                        if exchange_unit_raw and _normalize_energy_unit(exchange_unit_raw) != _normalize_energy_unit(activity_unit):
                            print(
                                "   ⚠️ Unit mismatch in inventory entry: "
                                f"JSON unit '{exchange_unit_raw}' vs activity unit '{activity_unit}'. "
                                "Using activity unit for conversion."
                            )
                        exchange_unit_raw = activity_unit

                    if not exchange_unit_raw:
                        exchange_unit_raw = 'MJ'

                    base_unit_norm = _normalize_energy_unit(base_unit_raw)
                    exchange_unit_norm = _normalize_energy_unit(exchange_unit_raw)

                    # Convert via absolute Joule base, then to the activity exchange unit.
                    to_exchange_factor_j = _to_j_factor(exchange_unit_raw)
                    amount = (
                        (scaled_amount_j / to_exchange_factor_j if to_exchange_factor_j else scaled_amount_j)
                        * exchange_multiplier
                    )

                    # Verification-first logging: only print conversion details if unit change is required.
                    if base_unit_norm == exchange_unit_norm:
                        target_desc = activity_name if activity_name else exchange.get('name', 'Unknown')
                        print(
                            "   ✅ Energy unit verification: "
                            f"metadata unit {base_unit_norm} matches assigned inventory unit {exchange_unit_norm} "
                            f"for '{target_desc}'."
                        )
                    else:
                        # Print conversion using absolute dataset values (non-normalized).
                        base_amount_exchange_abs = (
                            (base_amount_raw * _to_j_factor(base_unit_raw)) / to_exchange_factor_j
                            if to_exchange_factor_j else base_amount_raw
                        )
                        unit_for_factor = exchange_unit_norm

                        print(
                            "⚡Energy unit conversion to base J: "
                            f"{base_amount_exchange_abs:.6e} {unit_for_factor} x "
                            f"{to_exchange_factor_j:.6e} J/{unit_for_factor} = "
                            f"{(base_amount_raw * _to_j_factor(base_unit_raw)):.6e} J"
                        )
                else:
                    # Direct amount (non-energy exchanges are not scaled)
                    amount = _eval_amount_expression(
                        exchange.get('amount', 1.0),
                        exchange.get('name', 'Unknown')
                    )
                
                process_data[process_key]['exchanges'].append({
                    'name': exchange.get('name', 'Unknown'),
                    'amount': amount,
                    'unit': exchange_unit_raw if 'amount_ref' in exchange else exchange.get('unit', 'kg'),
                    'type': 'technosphere',
                    'input': input_key
                })
                
                if 'amount_ref' not in exchange:
                    print(f"   ✅ Added: {exchange.get('name', 'Unknown')} ({amount:.3f} {exchange.get('unit', 'kg')})")
        
        return process_data
        
    except Exception as e:
        print(f"❌ Error creating process inventory: {e}")
        return None

def resolve_lcia_methods(method_names):
    """Resolve LCIA method names to actual method objects"""
    available_methods = list(methods)
    available_set = set(available_methods)
    resolved = []
    
    for method_name in method_names:
        # 1) Exact tuple/list methods (preferred when provided)
        if isinstance(method_name, (tuple, list)):
            candidate = tuple(method_name)
            if candidate in available_set:
                resolved.append(candidate)
                print(f"   ✅ Resolved (exact tuple): {simplify_method_name(str(candidate))}")
                continue

            # Fallback: tuple component search if exact tuple is unavailable
            keywords = [str(part).lower() for part in candidate if str(part).strip()]
        else:
            # 2) String keyword matching (legacy behavior)
            keywords = str(method_name).lower().split()
        
        # Find methods containing all keywords
        matching_methods = []
        for method in available_methods:
            method_str = str(method).lower()
            if all(keyword in method_str for keyword in keywords):
                matching_methods.append(method)
        
        if matching_methods:
            # Prefer methods without "no LT"
            preferred = [m for m in matching_methods if 'no lt' not in str(m).lower()]
            selected = preferred[0] if preferred else matching_methods[0]
            resolved.append(selected)
            print(f"   ✅ Resolved: {simplify_method_name(str(selected))}")
        else:
            print(f"   ❌ Could not resolve: {method_name}")
    
    return resolved

def get_default_climate_methods():
    """Get default climate change methods"""
    available_methods = list(methods)
    climate_methods = [m for m in available_methods if 'climate change' in str(m).lower()]
    
    if climate_methods:
        return [climate_methods[0]]
    else:
        print("⚠️ No climate change methods found")
        return []

def calculate_stage_breakdown_with_lca(lci_data, lca_obj, method_unit, temp_db_name):
    """
    Calculate life cycle stage breakdown using actual LCA contribution analysis.
    Groups exchange contributions by their life_cycle_stage tag.
    """
    stage_breakdown = {}
    lc_stages = lci_data.get('life_cycle_stages', {})
    
    # Initialize all stages
    for stage_name in lc_stages.keys():
        stage_breakdown[stage_name] = {"score": 0.0, "unit": method_unit}
    
    try:
        def _norm(text):
            return " ".join(str(text or "").lower().split())

        # Build robust mappings from original LCI exchanges.
        input_to_stage = {}
        process_match_to_stage = {}
        name_to_stage = {}
        for exc in lci_data.get('exchanges', []):
            if exc.get('type') != 'technosphere':
                continue

            stage = exc.get('life_cycle_stage')
            if not stage:
                continue

            inp = exc.get('input') or []
            if len(inp) >= 2 and inp[0] and inp[1]:
                input_to_stage[(inp[0], inp[1])] = stage

            process_match = _norm(exc.get('process_match'))
            if process_match:
                process_match_to_stage[process_match] = stage

            exc_name = _norm(exc.get('name'))
            if exc_name:
                name_to_stage[exc_name] = stage
        
        # Get the main process activity
        from bw2data import get_activity
        main_act = get_activity((temp_db_name, lci_data.get('code', 'main_process')))
        
        # Iterate over technosphere exchanges and get their contribution
        for exc in main_act.technosphere():
            inp_act = exc.input
            inp_name = inp_act.get('name', '')

            # Find which stage this exchange belongs to
            matched_stage = None

            # 1) Preferred: exact input (database, code) match
            inp_key = None
            try:
                inp_key = tuple(inp_act.key)
            except Exception:
                try:
                    inp_key = (inp_act.get('database'), inp_act.get('code'))
                except Exception:
                    inp_key = None

            if inp_key and inp_key in input_to_stage:
                matched_stage = input_to_stage[inp_key]

            # 2) Fallback: process_match name against Brightway activity name
            if not matched_stage:
                norm_inp_name = _norm(inp_name)
                for pm_name, stage_name in process_match_to_stage.items():
                    if pm_name and (pm_name in norm_inp_name or norm_inp_name in pm_name):
                        matched_stage = stage_name
                        break

            # 3) Last fallback: item/display name matching
            if not matched_stage:
                norm_inp_name = _norm(inp_name)
                for exc_name, stage_name in name_to_stage.items():
                    if exc_name and (exc_name in norm_inp_name or norm_inp_name in exc_name):
                        matched_stage = stage_name
                        break
            
            if not matched_stage:
                matched_stage = 'Unassigned'
            
            if matched_stage not in stage_breakdown:
                stage_breakdown[matched_stage] = {"score": 0.0, "unit": method_unit}
            
            # Calculate contribution of this exchange
            try:
                # Create a new LCA for just this input
                single_lca = LCA({inp_act: exc.amount}, lca_obj.method)
                single_lca.lci()
                single_lca.lcia()
                stage_breakdown[matched_stage]["score"] += single_lca.score
            except Exception:
                pass
    
    except Exception as e:
        print(f"⚠️ Error in stage breakdown calculation: {e}")
        # Fall back to simple proportional breakdown
        return calculate_stage_breakdown_simple(lci_data, method_unit)
    
    return stage_breakdown


def calculate_stage_breakdown_simple(lci_data, method_unit):
    """
    Simple life cycle stage breakdown based on LCI data
    """
    stage_breakdown = {}
    
    try:
        # Initialize stages from LCI data
        lc_stages = lci_data.get('life_cycle_stages', {})
        for stage_name in lc_stages.keys():
            stage_breakdown[stage_name] = {
                "score": 0.0,
                "unit": method_unit
            }
        
        # Add basic stage assignments
        exchanges = lci_data.get('exchanges', [])
        for exchange in exchanges:
            stage = exchange.get('life_cycle_stage', 'Unassigned')
            if stage not in stage_breakdown:
                stage_breakdown[stage] = {
                    "score": 0.0,
                    "unit": method_unit
                }
    
    except Exception as e:
        print(f"⚠️ Error in simple stage breakdown: {e}")
    
    return stage_breakdown

def get_method_unit(method_str):
    """
    Get the proper unit for an LCIA method
    
    Args:
        method_str (str): Full method string
        
    Returns:
        str: Proper unit for the method
    """
    try:
        method_lower = method_str.lower()
        
        # Climate change methods
        if 'climate change' in method_lower:
            return 'kg CO2-eq'
        
        # Acidification methods
        elif 'acidification' in method_lower:
            return 'mol H+-eq'
        
        # Eutrophication methods
        elif 'eutrophication: freshwater' in method_lower:
            return 'kg P-eq'
        elif 'eutrophication: marine' in method_lower:
            return 'kg N-eq'
        
        # Ozone depletion
        elif 'ozone depletion' in method_lower:
            return 'kg CFC11-eq'
        
        # Ecotoxicity methods
        elif 'ecotoxicity' in method_lower:
            return 'CTUe'  # Comparative Toxic Units for ecosystems
        
        # Human toxicity methods
        elif 'human toxicity' in method_lower:
            return 'CTUh'  # Comparative Toxic Units for humans
        
        # Particulate matter
        elif 'particulate matter formation' in method_lower:
            return 'kg PM2.5-eq'
        
        # Photochemical oxidant formation
        elif 'photochemical oxidant formation' in method_lower:
            return 'kg NOx-eq'
        
        # Ionising radiation
        elif 'ionising radiation' in method_lower:
            return 'kBq Co-60-eq'
        
        # Land use
        elif 'land use' in method_lower:
            return 'm2*year'
        
        # Material resources
        elif 'material resources' in method_lower:
            return 'kg Cu-eq'
        
        # Energy resources
        elif 'energy resources' in method_lower:
            return 'MJ'
        
        # Water use
        elif 'water use' in method_lower:
            return 'm3 water-eq'
        
        else:
            return 'impact units'  # fallback
            
    except:
        return 'impact units'

def simplify_method_name(method_str):
    """
    Extract simplified method name including main method source from full method tuple string
    
    Args:
        method_str (str): Full method string
        
    Returns:
        str: Simplified method name with main method source
    """
    try:
        method_lower = str(method_str).lower()

        # Keep ReCiPe endpoint totals distinct in plots and CSV exports.
        if "recipe 2016" in method_lower and "endpoint (h)" in method_lower:
            if "total: ecosystem quality" in method_lower or "total ecosystem quality" in method_lower:
                return "ReCiPe endpoint, ecosystems"
            if "total: human health" in method_lower or "total human health" in method_lower:
                return "ReCiPe endpoint, human health"
            if "total: natural resources" in method_lower or "total natural resources" in method_lower:
                return "ReCiPe endpoint, resources"

        # Determine the main method source
        method_source = ""
        if 'IPCC 2021' in method_str:
            method_source = "IPCC"
        elif 'ReCiPe 2016 v1.03, midpoint (H)' in method_str:
            method_source = "ReCiPe H"
        elif 'ReCiPe 2016' in method_str:
            method_source = "ReCiPe"
        elif 'CML' in method_str:
            method_source = "CML"
        else:
            # Extract method from first part of tuple
            parts = method_str.split(',')
            if len(parts) > 1:
                first_part = parts[1].strip().strip("'")
                if 'IPCC' in first_part:
                    method_source = "IPCC"
                elif 'ReCiPe' in first_part:
                    method_source = "ReCiPe"
                elif 'CML' in first_part:
                    method_source = "CML"
        
        # Extract the impact category name and combine with method source
        if 'climate change' in method_str:
            category = 'climate change'
        elif 'acidification' in method_str:
            category = 'acidification'
        elif 'eutrophication: freshwater' in method_str:
            category = 'eutrophication (freshwater)'
        elif 'eutrophication: marine' in method_str:
            category = 'eutrophication (marine)'
        elif 'ozone depletion' in method_str:
            category = 'ozone depletion'
        elif 'ecotoxicity: freshwater' in method_str:
            category = 'ecotoxicity (freshwater)'
        elif 'ecotoxicity: marine' in method_str:
            category = 'ecotoxicity (marine)'
        elif 'ecotoxicity: terrestrial' in method_str:
            category = 'ecotoxicity (terrestrial)'
        elif 'human toxicity: carcinogenic' in method_str:
            category = 'human toxicity (carcinogenic)'
        elif 'human toxicity: non-carcinogenic' in method_str:
            category = 'human toxicity (non-carcinogenic)'
        elif 'particulate matter formation' in method_str:
            category = 'particulate matter'
        elif 'photochemical oxidant formation: human health' in method_str:
            category = 'photochemical oxidation (human)'
        elif 'photochemical oxidant formation: terrestrial' in method_str:
            category = 'photochemical oxidation (ecosystems)'
        elif 'ionising radiation' in method_str:
            category = 'ionising radiation'
        elif 'land use' in method_str:
            category = 'land use'
        elif 'material resources' in method_str:
            category = 'material resources'
        elif 'energy resources' in method_str:
            category = 'energy resources'
        elif 'water use' in method_str:
            category = 'water use'
        else:
            # Fallback: use first part before comma
            category = method_str.split(',')[2].strip().strip("'") if len(method_str.split(',')) > 2 else "unknown"
        
        # Combine method source and category
        if method_source:
            return f"{method_source} {category}"
        else:
            return category
            
    except:
        return method_str[:30] + "..." if len(method_str) > 30 else method_str


def _energy_to_mj(value, unit):
    """Convert an energy value to MJ for run_lca_energy input semantics."""
    factors_to_mj = {
        "J": 1.0e-6,
        "WH": 3.6e-3,
        "KWH": 3.6,
        "MWH": 3600.0,
        "MJ": 1.0,
        "GJ": 1000.0,
        "TJ": 1.0e6,
    }
    norm = str(unit or "MJ").strip().upper()
    if norm not in factors_to_mj:
        raise ValueError(f"Unsupported energy unit: {unit}")
    return float(value) * factors_to_mj[norm]


def _parse_param_assignments(assignments):
    """Parse repeated CLI parameter assignments like key=value or key:value."""
    parsed = {}
    for raw in assignments or []:
        text = str(raw).strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
        elif ":" in text:
            key, value = text.split(":", 1)
        else:
            raise ValueError(f"Invalid --param '{raw}'. Use name=value")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid --param '{raw}'. Missing parameter name")
        parsed[key] = float(value)
    return parsed


def resolve_parameter_values(param_args=None, params_json=None, params_file=None):
    """Resolve parameter overrides from CLI inputs and merge with last-write-wins precedence."""
    values = {}
    values.update(_parse_param_assignments(param_args))

    if params_json:
        json_values = json.loads(params_json)
        if not isinstance(json_values, dict):
            raise ValueError("--params-json must decode to an object/dict")
        values.update({str(k): float(v) for k, v in json_values.items()})

    if params_file:
        with open(params_file, 'r', encoding='utf-8') as f:
            file_values = json.load(f)
        if not isinstance(file_values, dict):
            raise ValueError("--params-file must contain a JSON object/dict")
        values.update({str(k): float(v) for k, v in file_values.items()})

    return values

def create_visualization(results, output_file="lca_results.png"):
    """
    Create a stacked bar chart visualization showing life cycle stage breakdown for each impact method
    
    Args:
        results (dict): LCA results
        output_file (str): Output file path
    """
    try:
        # Extract impact results and stage data
        if "impact_results" not in results or "stage_breakdown" not in results:
            print("No impact results or stage breakdown found in results")
            return
        
        impact_data = results["impact_results"]
        stage_data = results["stage_breakdown"]
        
        if not impact_data or not stage_data:
            print("Impact results or stage data are empty")
            return
        
        # Prepare data for stacked bar chart
        methods = []
        units = []
        stage_names = []
        
        # Get all unique stage names
        for method_stages in stage_data.values():
            for stage_name, stage_info in method_stages.items():
                if stage_info["score"] > 0 and stage_name not in stage_names:
                    stage_names.append(stage_name)
        
        # If no stages found, exit
        if not stage_names:
            print("No life cycle stages with contributions found")
            return
        
        # Prepare data structure
        stage_values = {stage: [] for stage in stage_names}
        
        for method, data in impact_data.items():
            if isinstance(data, dict) and "total_score" in data:
                simplified_name = simplify_method_name(method)
                unit = data.get("unit", "impact units")
                methods.append(simplified_name)
                units.append(unit)
                
                # Get stage values for this method
                method_stages = stage_data.get(method, {})
                for stage in stage_names:
                    stage_info = method_stages.get(stage, {"score": 0.0})
                    stage_values[stage].append(stage_info["score"])
        
        if not methods:
            print("No valid methods found for visualization")
            return
        
        # Create stacked bar chart
        fig, ax = plt.subplots(figsize=(12, max(8, len(methods) * 0.8)))
        
        # Define colors for each stage
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57', '#FF9FF3', '#54A0FF']
        
        # Create stacked bars
        bottoms = [0] * len(methods)
        y_pos = np.arange(len(methods))
        
        bars_by_stage = {}
        for i, stage in enumerate(stage_names):
            if any(val > 0 for val in stage_values[stage]):  # Only plot stages with contributions
                bars = ax.barh(y_pos, stage_values[stage], left=bottoms, 
                              label=stage, color=colors[i % len(colors)])
                bars_by_stage[stage] = bars
                
                # Update bottoms for next stage
                bottoms = [b + v for b, v in zip(bottoms, stage_values[stage])]
        
        # Customize the plot
        ax.set_title(f'LCA Results by Life Cycle Stage\n{results.get("main_process", "PVC Pipe Production")}', 
                    fontsize=14, fontweight='bold')
        ax.set_xlabel('Impact Score', fontsize=12)
        ax.set_ylabel('Impact Method', fontsize=12)
        ax.set_yticks(y_pos)
        ax.set_yticklabels([f"{m} ({u})" for m, u in zip(methods, units)], fontsize=10)
        
        # Add legend
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # Add value labels on bars
        for method_idx in range(len(methods)):
            total_value = bottoms[method_idx]
            current_left = 0
            
            for stage in stage_names:
                stage_value = stage_values[stage][method_idx]
                if stage_value > 0:
                    # Calculate percentage
                    percentage = (stage_value / total_value * 100) if total_value != 0 else 0
                    
                    # Only show label if the segment is large enough (>5% of total)
                    if percentage > 5:
                        # Position text in center of segment
                        text_x = current_left + stage_value / 2
                        
                        # Format the percentage
                        if percentage >= 10:
                            text = f'{percentage:.0f}%'
                        else:
                            text = f'{percentage:.1f}%'
                        
                        ax.text(text_x, method_idx, text, ha='center', va='center', 
                               fontsize=9, fontweight='bold', color='white')
                    
                    current_left += stage_value
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.show()
        print(f"Visualization saved to {output_file}")
        
    except Exception as e:
        print(f"Error creating visualization: {str(e)}")
        import traceback
        traceback.print_exc()

def save_results_csv(results, output_file="lca_results.csv"):
    """
    Save LCA results to CSV file including life cycle stage breakdown
    
    Args:
        results (dict): LCA results
        output_file (str): Output file path
    """
    try:
        # Extract impact results
        if "impact_results" not in results:
            print("No impact results found in results")
            return
        
        impact_data = results["impact_results"]
        stage_data = results.get("stage_breakdown", {})
        
        if not impact_data:
            print("Impact results are empty")
            return
        
        # Create separate CSV files for total results and stage breakdown
        base_name = output_file.rsplit('.', 1)[0]
        
        # 1. Total Results CSV
        csv_data = []
        for method, data in impact_data.items():
            if isinstance(data, dict) and "total_score" in data:
                simplified_name = data.get("method_name") or simplify_method_name(method)
                csv_data.append({
                    'Impact_Category': simplified_name,
                    'Total_Score': data["total_score"],
                    'Unit': data.get("unit", "unknown")
                })
        
        if csv_data:
            df = pd.DataFrame(csv_data)
            df.to_csv(output_file, index=False)
            print(f"Total results saved to {output_file}")
        
        # 2. Life Cycle Stage Breakdown CSV
        if stage_data:
            stage_csv_data = []
            for method, stages in stage_data.items():
                method_data = impact_data.get(method, {}) if isinstance(impact_data, dict) else {}
                simplified_method = method_data.get("method_name") or simplify_method_name(method)
                method_unit = None
                
                # Get the unit from impact_data
                if method in impact_data:
                    method_unit = impact_data[method].get("unit", "unknown")
                
                for stage_name, stage_info in stages.items():
                    if stage_info["score"] > 0:  # Only include stages with contributions
                        stage_csv_data.append({
                            'Impact_Method': simplified_method,
                            'Life_Cycle_Stage': stage_name,
                            'Stage_Score': stage_info["score"],
                            'Unit': stage_info.get("unit", method_unit or "unknown")
                        })
            
            if stage_csv_data:
                stage_df = pd.DataFrame(stage_csv_data)
                stage_file = f"{base_name}_stages.csv"
                stage_df.to_csv(stage_file, index=False)
                print(f"Stage breakdown saved to {stage_file}")
        
    except Exception as e:
        print(f"Error saving CSV: {str(e)}")

# Main execution
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Run LCA analysis with configurable methods',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using inventory file stem (looks in data/inventory/)
  python src/lca_engine.py example
  python src/lca_engine.py example --methods ipcc
  
  # Using full or relative paths
  python src/lca_engine.py --lci-file data/inventory/example.json
  python src/lca_engine.py --lci-file data/inventory/example.json --methods ipcc
  
  # Specifying both positional and named arguments
  python src/lca_engine.py example --methods midpoints

    # Parameter overrides (repeat --param, or provide JSON)
    python src/lca_engine.py example --param n_units=10
    python src/lca_engine.py example --param n_pv=2 --param n_bess=3
    python src/lca_engine.py example --params-json '{"n_units": 5}'
    python src/lca_engine.py example --params-file data/inventory/params.json
        """
    )
    
    parser.add_argument('lci_stem', nargs='?', default=None,
                       help='LCI file stem (e.g., "grid" for data/inventory/grid.json)')
    parser.add_argument('--lci-file', type=str, default=None,
                       help='Full path to LCI JSON file (alternative to stem argument)')
    parser.add_argument('--methods', type=str, default='methods',
                       help='Methods file stem in data/methods/ (e.g., "ipcc", "midpoints", "iw_damages"). Default: "methods"')
    parser.add_argument('--param', action='append', default=[],
                       help='Parameter assignment override, e.g. --param n_units=10 (repeatable)')
    parser.add_argument('--params-json', type=str, default=None,
                       help='JSON object string with parameter overrides, e.g. {"n_units": 10}')
    parser.add_argument('--params-file', type=str, default=None,
                       help='Path to JSON file containing parameter overrides as an object/dict')
    args = parser.parse_args()

    try:
        parameter_values = resolve_parameter_values(args.param, args.params_json, args.params_file)
    except Exception as e:
        print(f"❌ Invalid parameter overrides: {e}")
        exit(1)
    
    # Resolve LCI file path
    inventory_dir = get_inventory_dir()
    methods_dir = get_methods_dir()

    if args.lci_file:
        # Use explicit --lci-file if provided
        lci_file = args.lci_file
    elif args.lci_stem:
        # Use positional stem argument
        lci_file = str(inventory_dir / f"{args.lci_stem}.json")
    else:
        # Default fallback
        lci_file = str(inventory_dir / "pipe.json")
    
    # Check if file exists
    if not Path(lci_file).exists():
        print(f"❌ Error: LCI file not found: {lci_file}")
        print(f"\nAvailable inventory files in {inventory_dir}:")
        try:
            if inventory_dir.exists():
                json_files = sorted(inventory_dir.glob("*.json"))
                for f in json_files:
                    print(f"  • {f.stem}")
        except Exception:
            pass
        exit(1)
    
    # Resolve methods file path
    methods_file = methods_dir / f"{args.methods}.json"
    if not methods_file.exists():
        print(f"⚠️  Methods file not found: {methods_file}")
        print(f"Available methods files in {methods_dir}:")
        try:
            if methods_dir.exists():
                json_files = sorted(methods_dir.glob("*.json"))
                for f in json_files:
                    print(f"  • {f.stem}")
        except Exception:
            pass
        fallback_method_file = methods_dir / "methods.json"
        if not fallback_method_file.exists():
            fallback_method_file = methods_dir / "ipcc.json"
        print(f"\nUsing default methods file: {fallback_method_file}")
        methods_file = fallback_method_file
    
    # Load LCIA methods from JSON file with enhanced format support
    try:
        lcia_methods, method_metadata = load_lcia_methods(str(methods_file))
        if lcia_methods:
            print_method_info(lcia_methods, method_metadata)
        else:
            print("⚠️ No methods loaded from methods file")
    except Exception as e:
        print(f"Error loading methods file: {e}")
        lcia_methods = []
        method_metadata = {}
    
    # Set default method if no methods specified
    if not lcia_methods:
        lcia_methods = ["IPCC 2021 climate change GWP100"]
        print("Using default LCIA method: IPCC 2021 climate change GWP100")
    
    # Placeholder functional unit
    functional_unit = {("LCA_DB", "process_1"): 1.0}

    # Use inventory-defined base energy as the default analysis basis.
    try:
        with open(lci_file, "r", encoding="utf-8") as f:
            preview = json.load(f)
        primary_input = preview.get("energy_metadata", {}).get("primary_input", {})
        base_value = float(primary_input.get("value", 1.0))
        base_unit = str(primary_input.get("unit", "MJ"))
        energy_amount_mj = _energy_to_mj(base_value, base_unit)
        print(
            "Energy basis: using inventory base input "
            f"{base_value} {base_unit} ({energy_amount_mj:.6g} MJ)"
        )
    except Exception as e:
        print(f"⚠️ Could not resolve inventory base energy ({e}); falling back to 1.0 MJ")
        energy_amount_mj = 1.0
    
    print("Starting LCA analysis...")

    if parameter_values:
        print(f"Parameter overrides: {parameter_values}")
    
    # Run LCA using inventory base energy by default.
    results = run_lca(
        lci_file,
        lcia_methods,
        parameter_values=parameter_values,
        functional_unit=functional_unit,
        energy_amount_mj=energy_amount_mj,
    )
    
    # Generate output filenames based on inventory and method
    inventory_name = Path(lci_file).stem  # e.g., "example", "grid"
    method_name = args.methods  # e.g., "ipcc", "midpoints"
    
    results_basename = f"{inventory_name}_{method_name}_result"
    results_json = f"results/{results_basename}.json"
    results_png = f"results/{results_basename}.png"
    results_csv = f"results/{results_basename}.csv"
    
    print("\n=== LCA RESULTS SUMMARY ===")
    
    # Print concise impact results
    if "impact_results" in results and results["impact_results"]:
        print("Impact Assessment Results:")
        for method, data in results["impact_results"].items():
            if isinstance(data, dict) and "total_score" in data:
                simplified_name = simplify_method_name(method)
                score = data["total_score"]
                unit = data.get("unit", "impact units")
                
                # Format the score appropriately
                if abs(score) >= 1:
                    formatted_score = f"{score:.3f}"
                elif abs(score) >= 0.001:
                    formatted_score = f"{score:.4f}"
                else:
                    formatted_score = f"{score:.2e}"
                
                print(f"  • {simplified_name}: {formatted_score} {unit}")
    
    # Print functional unit and system info
    print(f"\nSystem Information:")
    print(f"  • Functional unit: {results.get('functional_unit', 'Unknown')}")
    print(f"  • Main process: {results.get('main_process', 'Unknown')}")
    print(f"  • Database: {results.get('database', 'Unknown')}")
    
    # Print life cycle stage summary if available
    if "stage_breakdown" in results and results["stage_breakdown"]:
        print(f"\nLife Cycle Stages:")
        first_method = list(results["stage_breakdown"].keys())[0]
        stages = results["stage_breakdown"][first_method]
        
        for stage_name, stage_data in stages.items():
            if stage_data["score"] > 0:
                print(f"  • {stage_name}: Active")
            else:
                print(f"  • {stage_name}: No processes")
    
    print(f"  • Setup status: {results.get('setup', 'Unknown')}")
    
    # Save results to JSON
    try:
        with open(results_json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {results_json}")
    except Exception as e:
        print(f"Error saving JSON results: {e}")
    
    # Create visualizations and CSV if we have impact results
    if "impact_results" in results and results["impact_results"]:
        print("\nGenerating stacked bar chart and CSV...")
        create_visualization(results, results_png)
        save_results_csv(results, results_csv)
    
    print("LCA analysis complete!")
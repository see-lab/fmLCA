"""
LCIA Methods Manager for LCA-FMU

Centralized management of Life Cycle Impact Assessment (LCIA) methods including:
- Loading and validating method configurations from JSON files
- Extracting all methods from Brightway databases
- Importing new methods from bw2package files
- Inferring method categories and units
- Resolving method names to Brightway tuples

Author: LCA-FMU Team
"""

import json
import bw2data as bd
import bw2io as bi
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Union


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY AND UNIT INFERENCE
# ═══════════════════════════════════════════════════════════════════════════

def infer_category(method_tuple: Tuple) -> str:
    """
    Infer impact category from method name tuple.
    
    Args:
        method_tuple: Brightway method tuple (e.g., ('IPCC 2021', 'climate change', ...))
        
    Returns:
        str: Inferred category name (e.g., 'climate_change', 'human_health')
    """
    method_str = ' '.join(str(part).lower() for part in method_tuple)
    
    # Category mapping based on keywords
    categories = {
        'climate_change': ['climate', 'gwp', 'global warming'],
        'ecosystem_quality': ['ecosystem quality', 'species', 'biodiversity', 'pdf'],
        'human_health': ['human health', 'daly', 'mortality', 'morbidity', 'cancer'],
        'resources': ['resources', 'mineral', 'fossil', 'surplus'],
        'acidification': ['acidification', 'acid'],
        'eutrophication': ['eutrophication', 'nutrient'],
        'ecotoxicity': ['ecotoxic', 'aquatic', 'terrestrial toxic'],
        'human_toxicity': ['human tox', 'carcinogen'],
        'ozone_depletion': ['ozone', 'odp'],
        'photochemical_oxidation': ['photochemical', 'smog', 'pofp'],
        'land_use': ['land', 'occupation', 'transformation'],
        'water_use': ['water', 'deprivation', 'scarcity'],
        'ionising_radiation': ['radiation', 'ionizing', 'ionising'],
        'particulate_matter': ['particulate', 'respiratory'],
        'energy': ['energy', 'cumulative energy demand', 'ced']
    }
    
    for category, keywords in categories.items():
        if any(keyword in method_str for keyword in keywords):
            return category
    
    return 'other'


def infer_unit(method_tuple: Tuple) -> str:
    """
    Infer measurement unit from method name tuple.
    
    Args:
        method_tuple: Brightway method tuple
        
    Returns:
        str: Inferred unit (e.g., 'kg CO2-eq', 'DALY', 'points')
    """
    method_str = ' '.join(str(part).lower() for part in method_tuple)
    
    # Unit mapping based on keywords
    units = {
        'kg CO2-eq': ['gwp', 'climate change', 'co2'],
        'kg CFC-11-eq': ['ozone', 'odp'],
        'kg SO2-eq': ['acidification'],
        'kg PO4-eq': ['eutrophication'],
        'kg 1,4-DCB-eq': ['ecotoxic', 'human tox'],
        'kg NMVOC-eq': ['photochemical'],
        'CTUh': ['human tox', 'carcinogen', 'ctu'],
        'CTUe': ['ecotoxic', 'ctu'],
        'DALY': ['daly', 'human health'],
        'species.yr': ['species', 'biodiversity', 'ecosystem quality'],
        'USD': ['surplus', 'cost'],
        'points': ['points', 'pt'],
        'MJ': ['energy', 'ced', 'mj'],
        'm2*yr': ['land use', 'occupation'],
        'kg PM2.5-eq': ['particulate', 'pm2.5'],
        'kBq U235-eq': ['radiation', 'ionizing'],
        'm3': ['water', 'm3']
    }
    
    for unit, keywords in units.items():
        if any(keyword in method_str for keyword in keywords):
            return unit
    
    return ''


# ═══════════════════════════════════════════════════════════════════════════
# METHOD EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_all_methods(project_name: str = 'ecoinvent3.12') -> Dict:
    """
    Extract all LCIA methods from a Brightway database project.
    
    Args:
        project_name: Name of Brightway project to extract from
        
    Returns:
        dict: Comprehensive method data organized by families
        
    Example output:
        {
            "total_methods": 728,
            "extraction_date": "2026-07-23",
            "brightway_project": "ecoinvent3.12",
            "method_families": {
                "IPCC 2021": {
                    "count": 12,
                    "methods": [...]
                }
            }
        }
    """
    # Set the Brightway project
    bd.projects.set_current(project_name)
    
    # Get all available methods
    from bw2data.method import methods
    all_methods = sorted(list(methods))
    
    print(f"Found {len(all_methods)} LCIA methods in project '{project_name}'")
    
    # Organize methods by family (first element of tuple)
    method_families = defaultdict(list)
    
    for method in all_methods:
        family = method[0]
        
        # Create method object with metadata
        method_obj = {
            "name": ', '.join(str(part) for part in method),
            "family": family,
            "tuple": list(method),
            "category": infer_category(method),
            "unit": infer_unit(method)
        }
        
        method_families[family].append(method_obj)
    
    # Create output structure
    output = {
        "description": "Comprehensive reference of all LCIA methods available in Brightway",
        "note": "This file is for reference/browsing only. For simulations, use ipcc.json, midpoints.json, or endpoints.json",
        "total_methods": len(all_methods),
        "extraction_date": datetime.now().strftime("%Y-%m-%d"),
        "brightway_project": project_name,
        "method_families": {}
    }
    
    # Add family information
    for family, methods_list in sorted(method_families.items()):
        output["method_families"][family] = {
            "count": len(methods_list),
            "methods": methods_list
        }
    
    return output


def save_methods_reference(output_data: Dict, output_file: Path) -> None:
    """
    Save extracted methods data to JSON file.
    
    Args:
        output_data: Methods data dictionary from extract_all_methods()
        output_file: Path where JSON file should be saved
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n✓ Created reference file: {output_file}")
    print(f"  Total methods: {output_data['total_methods']}")
    print(f"  Method families: {len(output_data['method_families'])}")
    
    # Print top 10 families by count
    families = [(name, data['count']) for name, data in output_data['method_families'].items()]
    families.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n  Top method families:")
    for name, count in families[:10]:
        print(f"    • {name}: {count} methods")


# ═══════════════════════════════════════════════════════════════════════════
# METHOD IMPORT
# ═══════════════════════════════════════════════════════════════════════════

def import_method_from_package(
    package_path: Union[str, Path],
    project_name: str = 'ecoinvent3.12',
    force: bool = True
) -> int:
    """
    Import LCIA method from a bw2package file into a Brightway project.
    
    Args:
        package_path: Path to .bw2package file
        project_name: Target Brightway project name
        force: Whether to force import (skip backup)
        
    Returns:
        int: Number of objects imported
        
    Raises:
        FileNotFoundError: If package file doesn't exist
        ValueError: If project doesn't exist or lacks required databases
    """
    package_path = Path(package_path)
    
    # Verify package file exists
    if not package_path.exists():
        raise FileNotFoundError(f"Package file not found: {package_path}")
    
    print(f"📦 Found package: {package_path.name}\n")
    
    # Verify project exists
    available_projects = [p.name for p in bd.projects]
    if project_name not in available_projects:
        raise ValueError(
            f"Project '{project_name}' not found. "
            f"Available: {available_projects}"
        )
    
    # Set project
    bd.projects.set_current(project_name)
    print(f"✅ Current project: {bd.projects.current}")
    
    # Verify biosphere database exists
    databases = list(bd.databases)
    has_biosphere = any('biosphere' in db for db in databases)
    if not has_biosphere:
        raise ValueError(
            f"No biosphere database found in project '{project_name}'. "
            f"Available databases: {databases}"
        )
    
    # Import the method
    print(f"\nImporting method from package: {package_path.name}")
    print("⏳ This may take a few minutes...")
    
    try:
        # Try with force parameter first
        imported = bi.BW2Package.import_file(str(package_path), force=force)
        print(f"✅ Method imported successfully!")
        print(f"   Imported {len(imported)} object(s)")
        return len(imported)
    except TypeError:
        # Fallback for older bw2io versions
        print("   Trying without force parameter...")
        imported = bi.BW2Package.import_file(str(package_path))
        print(f"✅ Method imported successfully!")
        print(f"   Imported {len(imported)} object(s)")
        return len(imported)


def list_imported_methods(
    project_name: str,
    family_filter: Optional[str] = None,
    max_display: int = 20
) -> List[Tuple]:
    """
    List methods in a Brightway project, optionally filtered by family.
    
    Args:
        project_name: Brightway project name
        family_filter: Optional string to filter method families (e.g., 'IW+', 'IPCC')
        max_display: Maximum number of methods to display
        
    Returns:
        list: List of method tuples
    """
    bd.projects.set_current(project_name)
    
    all_methods = list(bd.methods)
    
    if family_filter:
        filtered = [m for m in all_methods if family_filter in str(m)]
        print(f"\n✅ Found {len(filtered)} methods matching '{family_filter}':")
    else:
        filtered = all_methods
        print(f"\n✅ Total methods in project: {len(filtered)}")
    
    for i, method in enumerate(sorted(filtered)[:max_display], 1):
        print(f"   {i}. {method}")
    
    if len(filtered) > max_display:
        print(f"   ... and {len(filtered) - max_display} more")
    
    return filtered


# ═══════════════════════════════════════════════════════════════════════════
# METHOD LOADING AND VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def load_lcia_methods(methods_file: Union[str, Path]) -> Tuple[List, Dict]:
    """
    Load LCIA methods from JSON file.
    
    Supports multiple formats:
    - Legacy: ["method1", "method2", ...]
    - Enhanced: [{"name": "method1", "description": "...", ...}, ...]
    - Brightway tuples: [{"name": "...", "brightway_tuple": ["tuple", "parts"], ...}, ...]
    
    Args:
        methods_file: Path to methods JSON file
        
    Returns:
        tuple: (method_names: list, method_metadata: dict)
        
    Example:
        method_names, metadata = load_lcia_methods("data/methods/ipcc.json")
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
                brightway_tuple = item.get("brightway_tuple")
                
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


def validate_method_format(method_data: Dict) -> Tuple[bool, List[str]]:
    """
    Validate method configuration data format.
    
    Args:
        method_data: Dictionary containing method configuration
        
    Returns:
        tuple: (is_valid: bool, errors: List[str])
    """
    errors = []
    
    # Check required fields
    if "lcia_methods" not in method_data:
        errors.append("Missing required field: 'lcia_methods'")
        return False, errors
    
    methods_list = method_data["lcia_methods"]
    if not isinstance(methods_list, list):
        errors.append("Field 'lcia_methods' must be a list")
        return False, errors
    
    # Validate each method
    for i, method in enumerate(methods_list):
        if isinstance(method, str):
            # Legacy format is valid
            continue
        elif isinstance(method, dict):
            # Check for required fields in enhanced format
            if "name" not in method:
                errors.append(f"Method {i}: missing required field 'name'")
            
            # Validate optional fields
            if "unit" in method and not isinstance(method["unit"], str):
                errors.append(f"Method {i}: 'unit' must be a string")
            
            if "brightway_tuple" in method:
                bt = method["brightway_tuple"]
                if not isinstance(bt, list):
                    errors.append(f"Method {i}: 'brightway_tuple' must be a list")
        else:
            errors.append(f"Method {i}: must be string or dict, got {type(method)}")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def resolve_lcia_methods(method_names: List[Union[str, Tuple]]) -> List[Tuple]:
    """
    Resolve method names to Brightway method tuples.
    
    Args:
        method_names: List of method names (strings) or tuples
        
    Returns:
        list: List of resolved method tuples that exist in Brightway
    """
    available_methods = list(bd.methods)
    resolved = []
    
    for method in method_names:
        if isinstance(method, tuple):
            # Already a tuple
            if method in available_methods:
                resolved.append(method)
            else:
                print(f"⚠️ Method not found: {method}")
        else:
            # String - search for matching method
            matches = [m for m in available_methods if method.lower() in str(m).lower()]
            if matches:
                resolved.append(matches[0])
                if len(matches) > 1:
                    print(f"⚠️ Multiple matches for '{method}', using: {matches[0]}")
            else:
                print(f"⚠️ No match found for method: {method}")
    
    return resolved


def get_default_climate_methods() -> List[Tuple]:
    """
    Get default climate change methods (IPCC 2021 GWP100).
    
    Returns:
        list: List of default method tuples
    """
    available_methods = list(bd.methods)
    
    # Try to find IPCC 2021 climate change methods
    ipcc_methods = [
        m for m in available_methods 
        if 'IPCC 2021' in str(m) and 'climate change' in str(m).lower()
    ]
    
    if ipcc_methods:
        return ipcc_methods[:1]  # Return first match
    
    # Fallback to any climate change method
    climate_methods = [
        m for m in available_methods 
        if 'climate' in str(m).lower() or 'gwp' in str(m).lower()
    ]
    
    return climate_methods[:1] if climate_methods else []


# ═══════════════════════════════════════════════════════════════════════════
# METHOD UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def get_method_unit(method_str: str) -> str:
    """
    Extract unit from method string.
    
    Args:
        method_str: Method name or string representation
        
    Returns:
        str: Unit string (e.g., 'kg CO2-eq')
    """
    method_lower = method_str.lower()
    
    # Common unit patterns
    if 'gwp' in method_lower or 'climate' in method_lower:
        return 'kg CO2-eq'
    elif 'odp' in method_lower or 'ozone' in method_lower:
        return 'kg CFC-11-eq'
    elif 'daly' in method_lower:
        return 'DALY'
    elif 'species' in method_lower or 'pdf' in method_lower:
        return 'species.yr'
    elif 'energy' in method_lower or 'ced' in method_lower:
        return 'MJ'
    elif 'points' in method_lower or ' pt' in method_lower:
        return 'points'
    else:
        return ''


def simplify_method_name(method_str: str) -> str:
    """
    Simplify method name for display.
    
    Args:
        method_str: Full method name
        
    Returns:
        str: Simplified name
    """
    # Remove common prefixes
    simplified = method_str.replace('IPCC 2021, ', '')
    simplified = simplified.replace('IMPACT World+, ', '')
    simplified = simplified.replace('ReCiPe 2016, ', '')
    
    # Truncate if too long
    if len(simplified) > 60:
        simplified = simplified[:57] + '...'
    
    return simplified


def print_method_info(method_names: List, method_metadata: Dict) -> None:
    """
    Print formatted information about loaded methods.
    
    Args:
        method_names: List of method names/tuples
        method_metadata: Dictionary of method metadata
    """
    print(f"\n📊 Loaded {len(method_names)} LCIA method(s):")
    for i, method in enumerate(method_names, 1):
        method_key = str(method)
        metadata = method_metadata.get(method_key, {})
        
        name = metadata.get("name", str(method))
        unit = metadata.get("unit", "")
        category = metadata.get("category", "")
        
        print(f"   {i}. {simplify_method_name(name)}")
        if unit:
            print(f"      Unit: {unit}")
        if category:
            print(f"      Category: {category}")

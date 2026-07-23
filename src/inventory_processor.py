#!/usr/bin/env python3
"""
inventory_processor.py - Inventory file loading and validation

Library module for inventory processing. Import this module, do not run directly.

Usage:
    from src.inventory_processor import load_inventory, validate_inventory_format

Centralized handling of LCI inventory files:
- Load inventory files from JSON
- Validate inventory format and structure
- Extract energy metadata
- Find energy-related exchanges
- Resolve amount references

Part of the LCA-FMU core library.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

# Handle both relative and absolute imports
try:
    from .lca_utils import get_inventory_dir, load_json_file
except ImportError:
    from lca_utils import get_inventory_dir, load_json_file


# ── Inventory Loading ────────────────────────────────────────────────────────

def get_inventory_path(stem: str, search_dirs: Optional[List[Path]] = None) -> Path:
    """
    Find an inventory file by stem name.
    
    Searches in:
    1. Provided search_dirs
    2. data/inventory/
    3. Current directory
    
    Args:
        stem: Inventory file stem (e.g., "grid" for "grid.json")
        search_dirs: Optional list of directories to search
        
    Returns:
        Path to inventory file
        
    Raises:
        FileNotFoundError: If inventory file not found
        
    Examples:
        >>> get_inventory_path("grid")
        Path('/path/to/data/inventory/grid.json')
    """
    # Normalize stem - remove .json if present
    if stem.endswith('.json'):
        stem = stem[:-5]
    
    # Build search paths
    if search_dirs is None:
        search_dirs = []
    
    search_dirs = [Path(d) for d in search_dirs]
    search_dirs.extend([
        get_inventory_dir(),
        Path.cwd(),
    ])
    
    # Search for file
    for directory in search_dirs:
        for extension in ['.json', '']:
            candidate = directory / f"{stem}{extension}"
            if candidate.exists() and candidate.is_file():
                return candidate
    
    # Not found
    searched = ", ".join(str(d) for d in search_dirs)
    raise FileNotFoundError(
        f"Inventory file '{stem}.json' not found. Searched: {searched}"
    )


def load_inventory(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load an inventory file from JSON.
    
    Args:
        file_path: Path to inventory JSON file (or stem name)
        
    Returns:
        Inventory data dictionary
        
    Raises:
        FileNotFoundError: If file not found
        json.JSONDecodeError: If invalid JSON
        ValueError: If inventory format is invalid
        
    Examples:
        >>> inv = load_inventory("grid.json")
        >>> inv['name']
        'Electricity Grid Production System'
    """
    # Try to resolve path if it's just a stem
    file_path = Path(file_path)
    if not file_path.exists():
        try:
            file_path = get_inventory_path(str(file_path))
        except FileNotFoundError:
            raise FileNotFoundError(f"Inventory file not found: {file_path}")
    
    # Load JSON
    inventory = load_json_file(file_path)
    
    # Basic validation
    if not validate_inventory_format(inventory):
        raise ValueError(f"Invalid inventory format in {file_path}")
    
    return inventory


# ── Inventory Validation ─────────────────────────────────────────────────────

def validate_inventory_format(data: Dict[str, Any]) -> bool:
    """
    Validate that an inventory has the required format.
    
    Checks for:
    - Required fields: name, unit, exchanges
    - Valid exchange structure
    - Valid types
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        True if valid, False otherwise
    """
    # Check required top-level fields
    required_fields = ['name', 'unit', 'exchanges']
    for field in required_fields:
        if field not in data:
            print(f"❌ Missing required field: {field}")
            return False
    
    # Check exchanges is a list
    if not isinstance(data['exchanges'], list):
        print(f"❌ 'exchanges' must be a list")
        return False
    
    # Check each exchange
    for i, exchange in enumerate(data['exchanges']):
        if not isinstance(exchange, dict):
            print(f"❌ Exchange {i} is not a dictionary")
            return False
        
        # Check required exchange fields
        if 'type' not in exchange:
            print(f"❌ Exchange {i} missing 'type' field")
            return False
        
        # Production exchange must have amount 1.0
        if exchange.get('type') == 'production':
            if 'amount' in exchange and exchange['amount'] != 1.0:
                print(f"⚠️  Production exchange should have amount=1.0, found {exchange['amount']}")
    
    return True


# ── Energy Metadata Extraction ──────────────────────────────────────────────

def extract_energy_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract energy metadata from inventory.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        Energy metadata dictionary (empty if none found)
        
    Examples:
        >>> metadata = extract_energy_metadata(inventory)
        >>> metadata['primary_input']['value']
        90.0
    """
    return data.get('energy_metadata', {})


def get_primary_energy_value(data: Dict[str, Any]) -> Optional[float]:
    """
    Get the primary energy input value from inventory.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        Energy value in MJ, or None if not found
    """
    metadata = extract_energy_metadata(data)
    primary = metadata.get('primary_input', {})
    return primary.get('value')


def get_primary_energy_unit(data: Dict[str, Any]) -> Optional[str]:
    """
    Get the primary energy input unit from inventory.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        Energy unit (e.g., "MJ", "kWh"), or None if not found
    """
    metadata = extract_energy_metadata(data)
    primary = metadata.get('primary_input', {})
    return primary.get('unit')


def has_energy_metadata(data: Dict[str, Any]) -> bool:
    """
    Check if inventory has energy metadata.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        True if energy metadata exists, False otherwise
    """
    metadata = extract_energy_metadata(data)
    return bool(metadata and metadata.get('primary_input'))


# ── Energy Exchange Identification ──────────────────────────────────────────

def find_energy_exchanges(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Find exchanges that reference energy metadata (use amount_ref).
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        List of energy-related exchanges
        
    Examples:
        >>> energy_ex = find_energy_exchanges(inventory)
        >>> [ex['name'] for ex in energy_ex]
        ['electricity, low voltage']
    """
    energy_exchanges = []
    
    for exchange in data.get('exchanges', []):
        # Check if exchange uses amount_ref to energy_metadata
        if 'amount_ref' in exchange:
            amount_ref = str(exchange.get('amount_ref', ''))
            if 'energy_metadata' in amount_ref:
                energy_exchanges.append(exchange)
    
    return energy_exchanges


def count_energy_processes(data: Dict[str, Any]) -> int:
    """
    Count the number of energy-related processes in inventory.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        Number of energy processes
    """
    # Check energy_metadata field
    metadata = extract_energy_metadata(data)
    if 'energy_processes' in metadata:
        return metadata['energy_processes']
    
    # Fallback: count exchanges with amount_ref
    return len(find_energy_exchanges(data))


# ── Amount Resolution ────────────────────────────────────────────────────────

def resolve_amount_refs(data: Dict[str, Any], 
                       energy_value: Optional[float] = None) -> Dict[str, Any]:
    """
    Resolve amount_ref fields to actual numeric amounts.
    
    Replaces amount_ref with computed amount values based on energy metadata.
    
    Args:
        data: Inventory data dictionary
        energy_value: Optional energy value to use (overrides metadata)
        
    Returns:
        New inventory dict with resolved amounts
        
    Examples:
        >>> resolved = resolve_amount_refs(inventory, energy_value=100.0)
        >>> # amount_ref -> actual numeric amount
    """
    import copy
    result = copy.deepcopy(data)
    
    # Get energy value
    if energy_value is None:
        energy_value = get_primary_energy_value(data)
    
    if energy_value is None:
        return result  # No energy value to resolve
    
    # Resolve each exchange
    for exchange in result.get('exchanges', []):
        if 'amount_ref' in exchange:
            amount_ref = exchange['amount_ref']
            
            # Parse amount_ref (e.g., "energy_metadata.primary_input.value")
            if isinstance(amount_ref, str) and amount_ref.startswith('energy_metadata.'):
                # For now, just use the energy value
                exchange['amount'] = energy_value
                # Keep amount_ref for reference
                exchange['amount_ref_original'] = amount_ref
    
    return result


# ── Life Cycle Stages ────────────────────────────────────────────────────────

def get_life_cycle_stages(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get life cycle stage definitions from inventory.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        Life cycle stages dictionary
        
    Examples:
        >>> stages = get_life_cycle_stages(inventory)
        >>> stages.keys()
        dict_keys(['Production', 'Transport', 'Use', 'EOL'])
    """
    return data.get('life_cycle_stages', {})


def get_exchanges_by_stage(data: Dict[str, Any], 
                           stage: str) -> List[Dict[str, Any]]:
    """
    Get all exchanges for a specific life cycle stage.
    
    Args:
        data: Inventory data dictionary
        stage: Life cycle stage name (e.g., "Production", "Use")
        
    Returns:
        List of exchanges in that stage
    """
    exchanges = []
    for exchange in data.get('exchanges', []):
        if exchange.get('life_cycle_stage') == stage:
            exchanges.append(exchange)
    return exchanges


# ── Inventory Summary ────────────────────────────────────────────────────────

def get_inventory_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a summary of inventory contents.
    
    Args:
        data: Inventory data dictionary
        
    Returns:
        Summary dictionary with counts and metadata
    """
    exchanges = data.get('exchanges', [])
    
    # Count by type
    type_counts = {}
    for exchange in exchanges:
        ex_type = exchange.get('type', 'unknown')
        type_counts[ex_type] = type_counts.get(ex_type, 0) + 1
    
    # Count by stage
    stage_counts = {}
    for exchange in exchanges:
        stage = exchange.get('life_cycle_stage', 'unassigned')
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    
    summary = {
        'name': data.get('name', 'Unknown'),
        'unit': data.get('unit', 'unit'),
        'location': data.get('location', 'GLO'),
        'total_exchanges': len(exchanges),
        'exchanges_by_type': type_counts,
        'exchanges_by_stage': stage_counts,
        'has_energy_metadata': has_energy_metadata(data),
        'energy_processes': count_energy_processes(data),
    }
    
    if has_energy_metadata(data):
        summary['primary_energy'] = {
            'value': get_primary_energy_value(data),
            'unit': get_primary_energy_unit(data),
        }
    
    return summary


def print_inventory_summary(data: Dict[str, Any]) -> None:
    """
    Print a formatted summary of inventory contents.
    
    Args:
        data: Inventory data dictionary
    """
    summary = get_inventory_summary(data)
    
    print(f"\n{'='*60}")
    print(f"Inventory: {summary['name']}")
    print(f"{'='*60}")
    print(f"Unit: {summary['unit']}")
    print(f"Location: {summary['location']}")
    print(f"Total exchanges: {summary['total_exchanges']}")
    
    print(f"\nBy type:")
    for ex_type, count in summary['exchanges_by_type'].items():
        print(f"  {ex_type}: {count}")
    
    print(f"\nBy life cycle stage:")
    for stage, count in summary['exchanges_by_stage'].items():
        print(f"  {stage}: {count}")
    
    if summary['has_energy_metadata']:
        print(f"\nEnergy metadata:")
        print(f"  Primary input: {summary['primary_energy']['value']} {summary['primary_energy']['unit']}")
        print(f"  Energy processes: {summary['energy_processes']}")
    else:
        print(f"\n⚠️  No energy metadata found")
    
    print(f"{'='*60}\n")

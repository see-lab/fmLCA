#!/usr/bin/env python3
"""
lca_utils.py - Shared utility functions for LCA-FMU

Provides common utilities used across multiple modules:
- Name sanitization (class names, file names)
- Path management (project root, data directories)
- Unit conversions (MJ ↔ kWh)
- File I/O helpers (JSON loading/saving)

Part of the LCA-FMU core library.
"""

import json
import os
import re
from pathlib import Path
from typing import Union, Dict, Any


# ── Name Sanitization ────────────────────────────────────────────────────────

def safe_classname(text: str) -> str:
    """
    Convert arbitrary text into a valid Python class identifier.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Valid Python class name (CamelCase, starts with uppercase)
        
    Examples:
        >>> safe_classname("IPCC 2021")
        'Ipcc2021'
        >>> safe_classname("my-module name")
        'MyModuleName'
    """
    # Remove special characters, replace with underscores
    s = re.sub(r"[^A-Za-z0-9]", "_", text).strip("_")
    
    # Convert to CamelCase
    parts = s.split("_")
    camel = "".join(part.capitalize() for part in parts if part)
    
    # Ensure starts with letter
    if not camel:
        return "LcaClass"
    if camel[0].isdigit():
        return "C" + camel
        
    return camel


def safe_filename(text: str, extension: str = "") -> str:
    """
    Convert arbitrary text into a valid filename.
    
    Args:
        text: Input text to sanitize
        extension: Optional file extension (with or without leading dot)
        
    Returns:
        Valid filename with lowercase, underscores, and extension
        
    Examples:
        >>> safe_filename("My FMU Model", ".fmu")
        'my_fmu_model.fmu'
        >>> safe_filename("IPCC 2021 Results")
        'ipcc_2021_results'
    """
    # Convert to lowercase, replace spaces and special chars with underscores
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", text.lower()).strip("_")
    
    # Remove duplicate underscores
    s = re.sub(r"_+", "_", s)
    
    # Add extension if provided
    if extension:
        if not extension.startswith("."):
            extension = "." + extension
        return s + extension
    
    return s


# ── Path Management ──────────────────────────────────────────────────────────

def get_project_root() -> Path:
    """
    Get the absolute path to the project root directory.
    
    Returns:
        Path to project root (contains src/, scripts/, data/)
    """
    # This file is in src/, so parent is project root
    return Path(__file__).parent.parent.resolve()


def get_src_dir() -> Path:
    """Get the src/ directory path."""
    return get_project_root() / "src"


def get_data_dir() -> Path:
    """Get the data directory path, preferring repo layout then bundled assets."""
    env_root = os.environ.get("LCA_FMU_ROOT")
    if env_root:
        env_data = Path(env_root).expanduser().resolve() / "data"
        if env_data.exists():
            return env_data

    repo_data = get_project_root() / "data"
    if repo_data.exists():
        return repo_data

    # Installed wheel fallback: ship minimal data under src/resources/data.
    bundled_data = Path(__file__).resolve().parent / "resources" / "data"
    return bundled_data


def get_inventory_dir() -> Path:
    """Get the data/inventory/ directory path."""
    return get_data_dir() / "inventory"


def get_methods_dir() -> Path:
    """Get the data/methods/ directory path."""
    return get_data_dir() / "methods"


def get_results_dir() -> Path:
    """Get the results/ directory path."""
    return get_project_root() / "results"


def get_fmu_dir() -> Path:
    """Get the fmu/ directory path."""
    return get_project_root() / "fmu"


def get_config_dir() -> Path:
    """Get the config directory path, preferring repo layout then bundled assets."""
    env_root = os.environ.get("LCA_FMU_ROOT")
    if env_root:
        env_config = Path(env_root).expanduser().resolve() / "config"
        if (env_config / "system_config.json").exists():
            return env_config

    repo_config = get_project_root() / "config"
    if (repo_config / "system_config.json").exists():
        return repo_config

    # Installed wheel fallback: ship minimal config under src/resources/config.
    bundled_config = Path(__file__).resolve().parent / "resources" / "config"
    return bundled_config


def ensure_dir_exists(path: Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path to check/create
        
    Returns:
        The same path (for chaining)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Unit Conversions ─────────────────────────────────────────────────────────

def mj_to_kwh(mj: float) -> float:
    """
    Convert megajoules to kilowatt-hours.
    
    Args:
        mj: Energy in MJ
        
    Returns:
        Energy in kWh
        
    Note:
        1 kWh = 3.6 MJ, so MJ → kWh = MJ / 3.6
    """
    return mj / 3.6


def kwh_to_mj(kwh: float) -> float:
    """
    Convert kilowatt-hours to megajoules.
    
    Args:
        kwh: Energy in kWh
        
    Returns:
        Energy in MJ
        
    Note:
        1 kWh = 3.6 MJ
    """
    return kwh * 3.6


def mj_to_mwh(mj: float) -> float:
    """
    Convert megajoules to megawatt-hours.
    
    Args:
        mj: Energy in MJ
        
    Returns:
        Energy in MWh
        
    Note:
        1 MWh = 3600 MJ
    """
    return mj / 3600.0


def mwh_to_mj(mwh: float) -> float:
    """
    Convert megawatt-hours to megajoules.
    
    Args:
        mwh: Energy in MWh
        
    Returns:
        Energy in MJ
        
    Note:
        1 MWh = 3600 MJ
    """
    return mwh * 3600.0


def convert_energy_units(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert energy between different units.
    
    Args:
        value: Energy value to convert
        from_unit: Source unit (MJ, kWh, MWh, GJ)
        to_unit: Target unit (MJ, kWh, MWh, GJ)
        
    Returns:
        Converted energy value
        
    Raises:
        ValueError: If unit is not recognized
        
    Examples:
        >>> convert_energy_units(100, "MJ", "kWh")
        27.777777777777777
        >>> convert_energy_units(1, "MWh", "MJ")
        3600.0
    """
    # Normalize to MJ first
    from_unit = from_unit.upper()
    to_unit = to_unit.upper()
    
    # Convert to MJ
    if from_unit == "MJ":
        value_mj = value
    elif from_unit == "KWH":
        value_mj = kwh_to_mj(value)
    elif from_unit == "MWH":
        value_mj = mwh_to_mj(value)
    elif from_unit == "GJ":
        value_mj = value * 1000.0
    else:
        raise ValueError(f"Unknown unit: {from_unit}")
    
    # Convert from MJ to target
    if to_unit == "MJ":
        return value_mj
    elif to_unit == "KWH":
        return mj_to_kwh(value_mj)
    elif to_unit == "MWH":
        return mj_to_mwh(value_mj)
    elif to_unit == "GJ":
        return value_mj / 1000.0
    else:
        raise ValueError(f"Unknown unit: {to_unit}")


# ── File I/O Helpers ─────────────────────────────────────────────────────────

def load_json_file(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load JSON data from a file.
    
    Args:
        path: Path to JSON file
        
    Returns:
        Parsed JSON data as dictionary
        
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    path = Path(path)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json_file(data: Dict[str, Any], path: Union[str, Path], 
                   indent: int = 2, sort_keys: bool = False) -> None:
    """
    Save data as JSON to a file.
    
    Args:
        data: Data to save (must be JSON-serializable)
        path: Path to output JSON file
        indent: Number of spaces for indentation (default: 2)
        sort_keys: Whether to sort dictionary keys (default: False)
        
    Raises:
        TypeError: If data is not JSON-serializable
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, sort_keys=sort_keys, ensure_ascii=False)


# ── Method String Parsing ────────────────────────────────────────────────────

def parse_method_tuple(method_str: str) -> tuple:
    """
    Parse a method string representation into a tuple.
    
    Args:
        method_str: String like "('IPCC 2021', 'climate change', 'GWP100')"
        
    Returns:
        Tuple of method components
        
    Examples:
        >>> parse_method_tuple("('IPCC 2021', 'climate change', 'GWP100')")
        ('IPCC 2021', 'climate change', 'GWP100')
    """
    # Remove outer parentheses and quotes
    method_str = method_str.strip()
    if method_str.startswith("(") and method_str.endswith(")"):
        method_str = method_str[1:-1]
    
    # Split by comma and strip quotes
    parts = []
    for part in method_str.split(","):
        part = part.strip().strip("'\"")
        parts.append(part)
    
    return tuple(parts)


def format_method_name(method_tuple: tuple) -> str:
    """
    Format a method tuple into a human-readable name.
    
    Args:
        method_tuple: Brightway method tuple
        
    Returns:
        Formatted string
        
    Examples:
        >>> format_method_name(('IPCC 2021', 'climate change', 'GWP100'))
        'IPCC 2021 climate change GWP100'
    """
    return " ".join(str(part) for part in method_tuple)


# ── String Formatting ────────────────────────────────────────────────────────

def truncate_string(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        text: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if truncated (default: "...")
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_number(value: float, precision: int = 2, 
                 use_scientific: bool = None) -> str:
    """
    Format a number for display.
    
    Args:
        value: Number to format
        precision: Number of decimal places
        use_scientific: Force scientific notation (auto if None)
        
    Returns:
        Formatted string
    """
    if use_scientific is None:
        # Auto-detect: use scientific for very large or very small numbers
        use_scientific = abs(value) > 1e6 or (abs(value) < 0.001 and value != 0)
    
    if use_scientific:
        return f"{value:.{precision}e}"
    else:
        return f"{value:.{precision}f}"


# ── Validation ───────────────────────────────────────────────────────────────

def is_valid_identifier(text: str) -> bool:
    """
    Check if a string is a valid Python identifier.
    
    Args:
        text: String to check
        
    Returns:
        True if valid identifier, False otherwise
    """
    return text.isidentifier()


def is_numeric(value: Any) -> bool:
    """
    Check if a value is numeric (int or float).
    
    Args:
        value: Value to check
        
    Returns:
        True if numeric, False otherwise
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


if __name__ == "__main__":
    # Simple tests
    print("Testing lca_utils.py...")
    print(f"Project root: {get_project_root()}")
    print(f"Data dir: {get_data_dir()}")
    print(f"100 MJ = {mj_to_kwh(100):.2f} kWh")
    print(f"1 MWh = {mwh_to_mj(1):.0f} MJ")
    print(f"safe_classname('IPCC 2021'): {safe_classname('IPCC 2021')}")
    print(f"safe_filename('My FMU Model', '.fmu'): {safe_filename('My FMU Model', '.fmu')}")
    print("✅ All imports working!")

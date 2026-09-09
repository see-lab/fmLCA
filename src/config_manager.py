#!/usr/bin/env python3
"""
Configuration Manager for fmLCA System

Library module for configuration management. Import this module, do not run directly.

Usage:
    from src.config_manager import get_config

Centralized configuration loading and management
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from .lca_utils import get_config_dir
except ImportError:
    from lca_utils import get_config_dir


class ConfigManager:
    """Centralized configuration management for LCA system"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = get_config_dir()
        
        self.config_dir = Path(config_dir)
        self.system_config = self.load_system_config()
        
    def load_system_config(self) -> Dict[str, Any]:
        """Load main system configuration"""
        config_file = self.config_dir / "system_config.json"
        
        if not config_file.exists():
            raise FileNotFoundError(f"System configuration not found: {config_file}")
            
        with open(config_file, 'r') as f:
            return json.load(f)
    
    def get_database_patterns(self) -> List[str]:
        """Get all supported database naming patterns"""
        patterns = []
        for db_config in self.system_config["system"]["supported_databases"]:
            for pattern in db_config["naming_patterns"]:
                for version in db_config["versions"]:
                    patterns.append(pattern.format(version=version))
        return patterns
    
    def get_project_search_names(self) -> List[str]:
        """Get project names to search for existing setups"""
        return self.system_config["system"]["project_search_names"]
    
    def get_energy_config(self) -> Dict[str, Any]:
        """Get energy application configuration"""
        return self.system_config["energy_applications"]
    
    def get_csv_field_mapping(self) -> Dict[str, List[str]]:
        """Get flexible CSV field mappings"""
        return self.system_config["data_formats"]["csv_mapping"]["field_aliases"]
    
    def get_lifecycle_stages(self) -> Dict[str, List[str]]:
        """Get lifecycle stage mappings"""
        stages_config = self.system_config["data_formats"]["lifecycle_stages"]
        return {
            "default": stages_config["default_stages"],
            "aliases": stages_config["stage_aliases"]
        }
    
    def get_method_categories(self) -> Dict[str, Any]:
        """Get LCIA method categorization"""
        return self.system_config["lcia_methods"]["categories"]
    
    def get_fmu_templates(self) -> Dict[str, Any]:
        """Get FMU generation templates"""
        return self.system_config["fmu_generation"]["templates"]
    
    def get_fmu_outputs(self) -> Dict[str, Any]:
        """Get available FMU output categories"""
        return self.system_config["fmu_generation"]["output_categories"]
    
    def resolve_csv_field(self, headers: List[str], field_type: str) -> Optional[str]:
        """Resolve CSV field name from headers using aliases"""
        aliases = self.get_csv_field_mapping()
        field_aliases = aliases.get(field_type, [field_type])
        
        # Add the field_type itself as primary option
        all_options = [field_type] + field_aliases
        
        for header in headers:
            for option in all_options:
                if header.lower().replace(' ', '_') == option.lower().replace(' ', '_'):
                    return header
                if option.lower() in header.lower():
                    return header
        
        return None
    
    def get_energy_scaling_factor(self, process_name: str) -> tuple[float, str]:
        """Get scaling factor for energy-based processes"""
        energy_config = self.get_energy_config()
        process_lower = process_name.lower()
        
        # Check scaling processes
        for scaling_process in energy_config["scaling_processes"]:
            if any(keyword in process_lower for keyword in scaling_process["keywords"]):
                return scaling_process["conversion_factor"], scaling_process["unit"]
        
        # Check fallback processes
        for fallback_process in energy_config["fallback_processes"]:
            if any(keyword in process_lower for keyword in fallback_process["keywords"]):
                return fallback_process["conversion_factor"], fallback_process["unit"]
        
        # Default: assume MJ energy input
        return 1.0, "MJ"
    
    def categorize_method(self, method_str: str) -> Optional[str]:
        """Categorize LCIA method based on keywords"""
        method_lower = method_str.lower()
        
        for category, config in self.get_method_categories().items():
            if any(keyword in method_lower for keyword in config["keywords"]):
                return category
        
        return None
    
    def get_method_unit(self, method_str: str) -> str:
        """Get appropriate unit for LCIA method"""
        category = self.categorize_method(method_str)
        
        if category:
            method_config = self.get_method_categories()[category]
            return method_config["units"][0]  # Return first (preferred) unit
        
        return "impact_units"  # Default fallback


# Global configuration instance
config_manager = ConfigManager()


def get_config() -> ConfigManager:
    """Get global configuration manager instance"""
    return config_manager

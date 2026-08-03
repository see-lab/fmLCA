"""
LCA Analysis System - Energy Applications

A comprehensive Life Cycle Assessment analysis system with support for:
- Energy-based input parameters (MJ)
- Flexible database detection and matching
- Configuration-driven CSV processing
- Template-based FMU generation for co-simulation
- Multi-database support (ecoinvent, IDEMAT, custom)
- Centralized LCIA methods management

Author: LCA Analysis System
Version: 2.0.0 - Energy Applications
"""

__version__ = "2.0.0"
__author__ = "LCA Analysis System"
__description__ = "Energy-Based Life Cycle Assessment Analysis with Flexible FMU Co-simulation Support"

# Note: Avoid importing from modules that have their own imports to prevent circular dependencies
# Individual modules can be imported directly when needed

# Available modules:
# - lca_engine: Core LCA calculation engine
# - config_manager: Configuration handling
# - database_manager: Brightway database management
# - lci_data_manager: Life cycle inventory data processing
# - lca_utils: Utility functions (paths, units, file I/O)
# - inventory_processor: Inventory loading and validation
# - fmu_generator: FMU generation core logic
# - methods_manager: LCIA methods management (NEW)

__all__ = []

"""Compatibility exports for legacy src imports.

A comprehensive Life Cycle Assessment analysis system with support for:
- Energy-based input parameters (MJ)
- Flexible database detection and matching
- Configuration-driven CSV processing
- Template-based FMU generation for co-simulation
- Multi-database support (ecoinvent, IDEMAT, custom)
- Centralized LCIA methods management

Author: LCA Analysis System
Version: 0.0.1 - Energy Applications
Canonical public package: fmlca.
"""

__version__ = "0.0.1"
__author__ = "LCA Analysis System"
__description__ = "Energy-Based Life Cycle Assessment Analysis with Flexible FMU Co-simulation Support"

from .fmu_api import (
	BlackboxComplianceError,
	BuildOptions,
	BuildResult,
	FmuBuildError,
	FmuPackagingError,
	FmuValidationError,
	LcaRunError,
	LciFileNotFoundError,
	MethodConfigError,
	ParameterLinearityError,
	build_lca_fmu,
	build_lca_fmu_internal,
	create_fmu,
)

# Note: Avoid importing from modules that have their own imports to prevent circular dependencies
# Individual modules can be imported directly when needed

# Available modules:
# - lca_engine: Core LCA calculation engine
# - config_manager: Configuration handling
# - database_manager: Brightway database management
# - lci_data_manager: Life cycle inventory data processing
# - lca_utils: Utility functions (paths, units, file I/O)
# - fmu_generator: FMU generation core logic

__all__ = [
	"build_lca_fmu",
	"build_lca_fmu_internal",
	"create_fmu",
	"BuildOptions",
	"BuildResult",
	"FmuBuildError",
	"LciFileNotFoundError",
	"MethodConfigError",
	"LcaRunError",
	"FmuPackagingError",
	"BlackboxComplianceError",
	"FmuValidationError",
	"ParameterLinearityError",
]

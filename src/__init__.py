"""Compatibility exports for legacy `src` imports.

This module re-exports the core FMU build API so older code paths that import
from `src` continue to work during the transition to the canonical `fmlca`
package namespace.

Current source layout (selected modules):
- `fmu_api`: typed FMU build API, options/results, and exceptions
- `fmu_generator`: FMU generation and packaging internals
- `lca_engine`: Brightway-backed LCA execution logic
- `lci_data_manager`: inventory data loading and transformations
- `database_manager`: Brightway database resolution helpers
- `config_manager`: system/project configuration management
- `lca_utils`: shared utility functions

Recommended usage:
- Public imports should use `fmlca` for API stability.
- This `src` package remains as a compatibility layer.

Maintainers:
- Kathryn Hinkelman
- SEE Lab, University of Vermont
"""

__version__ = "1.0.0"
__author__ = "SEE Lab (University of Vermont)"
__description__ = "Compatibility exports for fmLCA core FMU build API"

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

# Keep imports minimal in this compatibility layer to reduce circular import risk.

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

# fmlca Release Tracking

## Information

This document summarizes user-visible changes by release.

- Version 0.0.1 (September 8, 2026)

## Version 0.0.1

### Information

Version 0.0.1 is the first unofficial public release of fmlca.
This release establishes the project's core architecture, primary workflows, and
public interfaces for FMU-based life cycle assessment and dynamic co-simulation.

The following major features have been added:

- Introduced a full workflow for inventory-driven LCA execution and FMU
	generation from the same project codebase.
- Added a public Python API for build and packaging operations with typed result
	objects and explicit exception classes.
- Built a script-first CLI workflow for users who prefer command-line operations,
	with API and CLI designed to interoperate.

Key design choices in this release:

- API-first internals with CLI compatibility: the same core build path is
	available programmatically and from scripts.
- Explicit contract boundaries: options and results are represented with typed
	structures, and failure modes use dedicated exception types.
- Conservative compatibility: legacy import usage remains available through a
	lightweight alias rather than parallel implementations.
- Practical FMU distribution defaults: release-oriented naming and build options
	are provided without removing advanced controls.

Compatibility notes:

- Public import path: fmlca is the canonical package namespace.
- Legacy import path: fmLCA remains available as a lightweight compatibility alias.
- CLI workflows remain supported through existing scripts.

Scope notes:

- This first unofficial release prioritizes a stable baseline workflow over
	broad feature surface.
- Advanced optimization, high-volume scenario orchestration, and tool-specific
	integrations remain future expansion areas.

Validation notes:

- Primary build paths and dry-run checks were exercised for representative
	scenarios before release preparation.

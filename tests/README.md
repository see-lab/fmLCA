# Tests Directory

Pytest-based unit and integration tests for fmLCA.

## Structure

- `test_*.py`: Primarily pytest modules (some also provide optional standalone entrypoints).
- `reference_results/`: Text baselines used by regression/parity tests.
- `resources/`: Test data assets (not collected as tests).
- `archive/`: Historical scripts kept for reference (excluded from pytest collection).

## Running Tests

```bash
# Run the full suite locally
python -m pytest tests/

# Run a single pytest module
python -m pytest tests/test_cosimulation.py -q
```

Important:
- Most `test_*.py` files are pytest modules and should be run with `pytest`.
- Running a pytest module directly (for example `python tests/test_cosimulation.py`) may exit silently because there is no script-style entrypoint.

Standalone-capable files in this folder (safe to run with `python ...`):

```bash
python tests/generate_regression_report.py
python tests/renewable_sources_cosim_sequential.py
python tests/scaling_validation.py
python tests/storage_validation.py
python tests/storage_validation_recipe.py
python tests/test_parameter_lca.py
python tests/test_parameter_propegation.py
python tests/test_pv_bess_wecc_native_vs_fmu.py --mode smoke
python tests/test_renewable_sources.py --no-show
```

Storage validation scripts:

```bash
# IPCC staged-impact parity plot/table
python tests/storage_validation.py

# ReCiPe single-score (Pt) parity plot/table
python tests/storage_validation_recipe.py

# Or run both via Makefile
make validation-suite
```

Optional marker filters:

```bash
# Run integration tests only
python -m pytest tests/ -m integration

# Run ecoinvent-dependent tests (requires private Brightway/ecoinvent setup)
python -m pytest tests/ -m ecoinvent
```

CI note:
- GitHub Actions runs three required jobs:
	- unit tests: `python -m pytest tests/ -m "not integration and not ecoinvent"`
	- integration tests: `python -m pytest tests/ -m integration`
	- CLI smoke tests: install package, run CLI help for setup/build tools, and run `fmlca-validate`
- `ecoinvent` tests run only in optional manual/scheduled CI because they require private dataset credentials and Brightway project setup.

## Regression Summary Report

Generate a Modelica-style regression summary with color-coded status rows
(green/orange/red) and difference plots (simulated vs reference):

```bash
python tests/generate_regression_report.py
```

Outputs:
- `tests/reports/regression_summary.html`
- `tests/reports/plots/*.png`

## Reference Baselines

- Store expected values in plain text files under `tests/reference_results/`
- Use `key=value` pairs for easy parsing in tests

## Parameterization Tests

### `test_parameter_lca.py`
**Purpose:** 	Validate that LCA impacts scale proportionally with inventory parameters

**Usage:**
```bash
python tests/test_parameter_lca.py
# or via pytest marker
python -m pytest tests/test_parameter_lca.py -m ecoinvent
```

- Loads `example.json` with `n_units` parameter
- Runs LCA with `n_units = 1, 10`
- Validates impacts scale proportionally (10x)
- Verifies within `REL_TOL` (see `tests/test_parameter_lca.py`)

### `test_parameter_propegation.py`
**Purpose:** 	Test parameter extraction and multi-file combination.
				This essentially is a formatting check.

**Usage:**
```bash
python tests/test_parameter_propegation.py
# or as pytest tests
python -m pytest tests/test_parameter_propegation.py
```

**What it tests:**
- Single CSV parameter extraction
- Multiple CSV file combination  
- Parameter propagation to exchanges
- JSON output structure validation

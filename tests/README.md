# Tests Directory

Pytest-based unit and integration tests for LCA-FMU.

## Structure

- `test_*.py`: Collected pytest modules only.
- `reference_results/`: Text baselines used by regression/parity tests.
- `resources/`: Test data assets (not collected as tests).
- `archive/`: Historical scripts kept for reference (excluded from pytest collection).

## Running Tests

```bash
# Run the full suite locally
python -m pytest tests/
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
	- CLI smoke tests: install package, run CLI help for setup/build tools, and run `lca-fmu-validate`
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
```

**What it tests:**
- Loads `example.json` with `n_units` parameter
- Runs LCA with `n_units = 1, 5, 10`
- Validates impacts scale proportionally (5x and 10x)
- Verifies within 1% tolerance

### `test_parameter_propegation.py`
**Purpose:** 	Test parameter extraction and multi-file combination.
				This essentially is a formatting check.

**Usage:**
```bash
python tests/test_parameter_propegation.py
```

**What it tests:**
- Single CSV parameter extraction
- Multiple CSV file combination  
- Parameter propagation to exchanges
- JSON output structure validation

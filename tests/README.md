# Tests Directory

This directory will contain unit tests and integration tests for LCA-FMU.

## Planned Test Structure

- `test_{src-name}.py` - Tests for core module functionality
- `reference_results/` - Shared baseline files for regression and parity checks

## Running Tests

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests
make test

# Or directly with pytest
pytest tests/ -v
```

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

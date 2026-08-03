# Tests Directory

Pytest-based unit and integration tests for LCA-FMU.

## Structure

- `test_*.py`: Collected pytest modules only.
- `reference_results/`: Text baselines used by regression/parity tests.
- `resources/`: Test data assets (not collected as tests).
- `archive/`: Historical scripts kept for reference (excluded from pytest collection).

## Running Tests

```bash
# Run the full suite (same command used in CI)
python -m pytest tests/
```

Optional marker filters:

```bash
# Run integration tests only
python -m pytest tests/ -m integration
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

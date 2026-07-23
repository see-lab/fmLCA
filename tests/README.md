# Tests Directory

This directory will contain unit tests and integration tests for LCA-FMU.

## Planned Test Structure

- `test_{src-name}.py` - Tests for core module functionality

## Running Tests

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests
make test

# Or directly with pytest
pytest tests/ -v
```

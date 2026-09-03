# Makefile for LCA Analysis System

.PHONY: help install install-dev test clean lint format fmu docs run-example storage-validation storage-validation-recipe validation-suite

# Default Python interpreter
PYTHON ?= python3
PIP ?= pip3

# Virtual environment directory
VENV_DIR = venv

help: ## Show this help message
	@echo "LCA Analysis System - Available Commands:"
	@echo "========================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package and dependencies
	$(PIP) install -e .

install-dev: ## Install with development dependencies
	$(PIP) install -e ".[dev,fmu,notebooks]"

setup-venv: ## Create and setup virtual environment
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip setuptools wheel
	$(VENV_DIR)/bin/pip install -e ".[dev,fmu,notebooks]"

test: ## Run tests
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

storage-validation: ## Run storage IPCC staged-impact validation script
	$(PYTHON) tests/storage_validation.py

storage-validation-recipe: ## Run storage ReCiPe single-score (Pt) validation script
	$(PYTHON) tests/storage_validation_recipe.py

validation-suite: ## Run both storage validation scripts (IPCC + ReCiPe)
	$(PYTHON) tests/storage_validation.py
	$(PYTHON) tests/storage_validation_recipe.py

lint: ## Run linting checks
	flake8 src/ scripts/ tests/
	mypy src/ --ignore-missing-imports

format: ## Format code with black
	black src/ scripts/ tests/ examples/

clean: ## Clean temporary files and build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf results/*.png results/*.json results/*.csv
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run-basic: ## Run basic LCA analysis with default parameters
	cd src && $(PYTHON) runBW.py

run-high-water: ## Run LCA analysis with high water consumption
	cd src && $(PYTHON) runBW.py --water 150

run-sensitivity: ## Run sensitivity analysis with multiple water values
	cd src && $(PYTHON) runBW.py --water 10
	cd src && $(PYTHON) runBW.py --water 50  
	cd src && $(PYTHON) runBW.py --water 100
	cd src && $(PYTHON) runBW.py --water 200

fmu-create: ## Create FMU package
	cd scripts && $(PYTHON) create_lca_fmu.py

fmu-validate: ## Validate FMU structure
	$(PYTHON) scripts/validate_fmu.py

fmu-test: ## Test FMU with FMPy (requires FMPy installation)
	$(PYTHON) dist/fmu/test_lca_fmu.py

example: ## Run example script
	$(PYTHON) examples/simple_lca.py

docs: ## Generate documentation (placeholder)
	@echo "Documentation generation not yet implemented"
	@echo "README.md and reports are in docs/ directory"

jupyter: ## Start Jupyter notebook server
	jupyter notebook docs/notebooks/

check-structure: ## Display current project structure
	tree -I 'venv|__pycache__|*.pyc|.git' -L 3

package: ## Create distribution packages
	$(PYTHON) setup.py sdist bdist_wheel

upload-test: ## Upload to test PyPI (requires credentials)
	twine upload --repository testpypi dist/*

upload: ## Upload to PyPI (requires credentials)
	twine upload dist/*

# Development workflow commands
dev-setup: setup-venv ## Complete development environment setup
	@echo "Development environment ready!"
	@echo "Activate with: source $(VENV_DIR)/bin/activate"

dev-check: lint test ## Run all development checks
	@echo "All checks passed!"

# CI/CD related commands
ci-install: ## Install for CI environment
	$(PIP) install -e ".[dev,fmu]"

ci-test: ## Run tests for CI
	pytest tests/ -v --cov=src --cov-report=xml --cov-report=term

# Docker related (future implementation)
docker-build: ## Build Docker image (placeholder)
	@echo "Docker support not yet implemented"

docker-run: ## Run in Docker container (placeholder)
	@echo "Docker support not yet implemented"

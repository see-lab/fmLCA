"""
Setup script for LCA Analysis System

This script allows the LCA Analysis System to be installed as a package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8')

# Read requirements
requirements = []
requirements_file = this_directory / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="lca-fmu",
    version="1.0.0",
    author="Kathryn Hinkelman, Fitz Koch",
    author_email="kathryn.hinkelman@colorado.edu",
    description="Life Cycle Assessment with Functional Mock-up Units for energy systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/see-lab/lca-fmu",
    py_modules=[
        "config_manager",
        "database_manager",
        "fmu_generator",
        "lca_engine",
        "lca_utils",
        "lci_data_manager",
        "inventory_processor",
        "methods_manager",
    ],
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Environmental Science",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.9",
            "mypy>=0.910",
        ],
        "fmu": [
            "FMPy>=0.3.15",
        ],
        "notebooks": [
            "jupyter>=1.0.0",
            "ipykernel>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "lca-analysis=src.runBW:main",
            "create-lca-fmu=scripts.create_lca_fmu:main",
            "validate-fmu=scripts.validate_fmu:test_lca_fmu_simple",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["data/inventory/*.json", "data/inventory/*.csv", "data/methods/*.json", "config/secrets/*.json"],
    },
    project_urls={
        "Bug Reports": "https://github.com/yourusername/lca-analysis-system/issues",
        "Source": "https://github.com/yourusername/lca-analysis-system",
        "Documentation": "https://lca-analysis-system.readthedocs.io/",
    },
)

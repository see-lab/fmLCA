"""
Setup script for LCA Analysis System

This script allows the LCA Analysis System to be installed as a package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8')

def read_requirements(filename: str) -> list[str]:
    """Read requirements from a file, skipping comments and empty lines."""
    requirements_file = this_directory / filename
    if not requirements_file.exists():
        return []

    with open(requirements_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


# Keep runtime dependencies minimal for lean production installs.
runtime_requirements = read_requirements("requirements-runtime.txt")
if not runtime_requirements:
    runtime_requirements = read_requirements("requirements.txt")

setup(
    name="fmLCA",
    version="1.0.1",
    author="Kathryn Hinkelman, Fitz Koch",
    author_email="kathryn.hinkelman@colorado.edu",
    description="Life Cycle Assessment with Functional Mock-up Units for energy systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="BSD-3-Clause",
    url="https://github.com/see-lab/fmLCA",
    packages=find_packages(include=["src", "src.*", "scripts", "scripts.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Environmental Science",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.9",
    install_requires=runtime_requirements,
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
            "fmlca-create=scripts.create_fmu:main",
            "fmlca-csv2json=scripts.csv_to_json_translator:main",
            "fmlca-setup-brightway=scripts.setup_brightway:main",
            "fmlca-setup-ecoinvent=scripts.setup_brightway:main",
            "fmlca-setup-env=scripts.setup_environment:main",
            "fmlca-validate=scripts.validate_requirements:main",
        ],
    },
    include_package_data=True,
    package_data={
        "src": [
            "resources/config/system_config.json",
            "resources/data/inventory/default.json",
            "resources/data/inventory/example.json",
            "resources/data/inventory/wecc.json",
            "resources/data/inventory/pv_wecc_bess.json",
            "resources/data/inventory/pv.csv",
            "resources/data/inventory/bess.csv",
            "resources/data/methods/ipcc.json",
            "resources/data/methods/recipe_endpoint_ha.json",
            "resources/data/methods/brightway_methods_reference.json",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/see-lab/fmLCA/issues",
        "Source": "https://github.com/see-lab/fmLCA",
    },
)

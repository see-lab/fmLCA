# LCA-FMU

Life Cycle Assessment platform with Functional Mock-up Unit generation for energy systems modeling.

Built with Brightway 2.5 and ecoinvent integration.

[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![CI Tests](https://github.com/see-lab/lca-fmu/actions/workflows/ci.yml/badge.svg)](https://github.com/see-lab/lca-fmu/actions/workflows/ci.yml)

## Contributors

**Kathryn Hinkelman** & **Fitz Koch** - [SEE Lab](http://www.theseelab.org/), University of Vermont

## Features

- **Dynamic Energy Propagation** - Energy scaling throughout LCA calculations
- **Automatic Process Detection** - Zero-config CSV import with energy process recognition
- **FMU Generation** - Create functional mockup units for co-simulation
- **IPCC 2021 & IMPACT World+** - 728+ LCIA methods including climate change indicators
- **Cooling Systems Analysis** - Pre-configured power plant cooling technology inventories

## Quick Start

### Installation

```bash
git clone https://github.com/see-lab/lca-fmu.git
cd lca-fmu
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

**Requirements:**
- Python 3.9-3.13
- Ecoinvent 3.8+ database (see `scripts/setup_brightway.py`)


**Setting up Ecoinvent:**
If you don't have an ecoinvent database:
```bash
# Show current project status only
python scripts/setup_brightway.py --name LCA-FMU --ecoinvent 3.12 --check

# Import ecoinvent (LCI + LCIA)
python scripts/setup_brightway.py --name LCA-FMU --ecoinvent 3.12 --system-model cutoff
```

See [Ecoinvent Setup Guide](docs/ECOINVENT_SETUP.md) for detailed instructions.

### Brightway Setup Helper

```bash
python scripts/setup_brightway.py --name LCA-FMU --ecoinvent 3.12
```

### Convert CSV to JSON for LCI import


```bash
# Auto-detect energy processes and convert CSV
python scripts/csv_to_json_translator.py example.csv
```

### Run LCA Analysis

```bash
python src/lca_engine.py example --methods ipcc
```

### Generate FMU

```bash
# Create FMU for co-simulation
python scripts/create_fmu.py example --method ipcc

# Create FMU with bytecode-only resources and strict black-box enforcement
# This is for sharing LCA-FMUs with proprietary and confidential data (e.g., ecoinvent EULA)
python scripts/create_fmu.py example --method ipcc --export-mode bytecode --blackbox-policy enforce
```

Black-box compliance policy:
- By default, create_fmu enforces black-box auditing and fails export if readable source/data payloads are present in resources/.
- By default, create_fmu now uses bytecode export mode: implementation modules are compiled to .pyc and only a minimal loader stub remains as .py.
- For local debugging only, use --blackbox-policy warn or --blackbox-policy off.

### Simulate (& co-simulate) FMUs (FUTURE ADDITION, nomenclature TBD)
python scripts/co-simulate.py --fmu1 [name] --fmu2 [name]

## Project Structure

```
├── src/                    # Core library modules
├── scripts/                # CLI tools
├── data/                   # Inventories & LCIA methods
│   ├── inventory/         # JSON inventories (grid, cooling, storage)
│   └── methods/           # IPCC, IMPACT World+ methods
├── config/                # Configuration files
├── fmu/                   # Generated FMUs
├── results/               # Analysis outputs
└── tests/                 # Test suite
```

## Testing

```bash
# Test FMU logic
python tests/test_cumulative_fmu.py

# Run all tests
python -m pytest tests/
```

**Note:** FMU binaries require Linux/Windows.

## Documentation

- **[Release Tracking](docs/RELEASE_TRACKING.md)** - Update status and remaining tasks for alpha deployment
- More to come later...

## Contributing

Contributions welcome! Fork the repo, create a feature branch, test your changes, and submit a PR.

See development guidelines in `CONTRIBUTING.md`.

## License

MIT License - see [LICENSE](LICENSE) file.

## Citation

```
Will be listed here when available. 
```

## Links

- [GitHub Repository](https://github.com/see-lab/lca-fmu)
- [SEE Lab](http://www.theseelab.org/)
- [Brightway Documentation](https://docs.brightway.dev/)

---

**Maintained by the SEE Lab at University of Vermont**

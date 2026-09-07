# fmLCA

Create and simulate dynamic Life Cycle Assessment (LCA) models with the Functional Mockup Interface (FMI). As a functional Mock-up Unit (FMU), users can evaluate comprehensive environmental impacts as IP-protected black boxes through co-simulation with a variety of FMI-compatible tools. 

[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![CI Tests](https://github.com/see-lab/fmLCA/actions/workflows/ci.yml/badge.svg)](https://github.com/see-lab/fmLCA/actions/workflows/ci.yml)

## Contributors

**Kathryn Hinkelman**, **Fitzwilliam Keenan-Koch**, & **Anastasija Mensikova** - [SEE Lab](http://www.theseelab.org/), University of Vermont

## Features

- **Dynamic Energy Propagation** - Energy scaling throughout LCA calculations
- **Parameterized Subsystems** - Combine multiple CSV inventories with parameters (e.g., n_pv, n_bess)
- **Automatic Process Detection** - Zero-config CSV import with energy process recognition
- **FMU Generation** - Create functional mockup units for co-simulation using the [Functional Mockup Interface (FMI)](https://fmi-standard.org/) Standard
- **LCA Features** - Built with [Brightway 2.5](https://docs.brightway.dev/en/latest/) and [ecoinvent](https://ecoinvent.org/) integration. 
- **Modelica co-simulation** - Couple LCA models with Modelica system models via Dymola, Python, or FMI-compatible runtime [tools](https://fmi-standard.org/tools/)
- **Comprehensive impact assessment methods** - 728+ LCIA methods including climate change indicators

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
python scripts/setup_brightway.py --name fmLCA --ecoinvent 3.12 --check

# Import ecoinvent (LCI + LCIA)
python scripts/setup_brightway.py --name fmLCA --ecoinvent 3.12 --system-model cutoff
```

See [Ecoinvent Setup Guide](docs/ECOINVENT_SETUP.md) for detailed instructions.

### Brightway Setup Helper

```bash
python scripts/setup_brightway.py --name fmLCA --ecoinvent 3.12
```

### Convert CSV to JSON for LCI import

```bash
# Single file - auto-detect energy processes and convert CSV
# Parameterized single files are the same command. Parameter metadata is auto detected.
python scripts/csv_to_json_translator.py example.csv

# Combine multiple parameterized subsystems, with a declared output name
# Default output name is `example1_example2.json'
python scripts/csv_to_json_translator.py example1 example2 --output combined_system.json
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
# This is for sharing LCA models as FMUs with proprietary and confidential data (e.g., ecoinvent EULA)
python scripts/create_fmu.py example --method ipcc --export-mode bytecode --blackbox-policy enforce
```

### Simulate FMUs and run sequential co-simulation

Use `scripts/run_fmu.py` in either single-FMU mode or sequential co-simulation mode.

```bash
# Single FMU mode (default)
python scripts/run_fmu.py --mode single --fmu fmu/Example_Ipcc_v1.0.fmu --u0 100 --step-size 60

# Sequential co-simulation mode
# system output -> LCA input
python scripts/run_fmu.py \
	--mode cosim \
	--system-fmu fmu/PV_System_WECC.fmu \
	--lca-fmu fmu/PvWecc_Ipcc_v1.0.fmu \
	--system-output gri.P.real \
	--lca-input u \
	--lca-output y \
	--parameter-name n_pv \
	--parameter-value 2.0 \
	--output-interval 3600 \
	--solver CVode \
	--save-plot results/cosim.png
```

Supported co-simulation flags:
- `--system-fmu`, `--lca-fmu`
- `--system-output`, `--lca-input`, `--lca-output`
- `--parameter-name`, `--parameter-value`
- `--system-start-value key=value` (repeatable)
- `--lca-start-value key=value` (repeatable)
- `--output-interval`, `--solver`

Notebook import usage (no local function redefinition required):

```python
from pathlib import Path
from scripts.run_fmu import inspect_fmu, simulate_system_fmu, sequential_cosim

system_result, lca_result = sequential_cosim(
		system_fmu=Path("fmu/PV_System_WECC.fmu"),
		lca_fmu=Path("fmu/PvWecc_Ipcc_v1.0.fmu"),
		start_s=0.0,
		stop_s=365 * 24 * 3600.0,
		system_output="gri.P.real",
		lca_input="u",
		lca_output="y",
		parameter_name="n_pv",
		parameter_value=2.0,
		output_interval_s=3600.0,
)
```

Black-box compliance policy:
- By default, create_fmu enforces black-box auditing and fails export if readable source/data payloads are present in resources/.
- By default, create_fmu now uses bytecode export mode: implementation modules are compiled to .pyc and only a minimal loader stub remains as .py.
- For local debugging only, use --blackbox-policy warn or --blackbox-policy off.

### Dymola Export Preset (Short Guide)

Use the Dymola preset when importing FMUs into Dymola:

```bash
# Dymola-compatible defaults (source mode + runtime guidance)
python scripts/create_fmu.py grid --method ipcc --target-tool dymola --accept-ip-risk

# Preferred for external sharing / stronger IP protection
python scripts/create_fmu.py grid --method ipcc --target-tool dymola --export-mode bytecode --blackbox-policy enforce
```

Notes:
- `--target-tool dymola` sets compatibility-oriented defaults unless you override them.
- Source mode is not black-box compliant; the CLI prints a risk warning and requires explicit acknowledgment.
- For ecoinvent/IP-sensitive distribution, use bytecode + enforce and validate importer compatibility before sharing.

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

BSD 3-Clause License - see [LICENSE](LICENSE) file.

## Citation

```
Will be listed here when available. 
```

## Links

- [GitHub Repository](https://github.com/see-lab/fmLCA)
- [SEE Lab](http://www.theseelab.org/)
- [Brightway Documentation](https://docs.brightway.dev/)

---

**Maintained by the SEE Lab at University of Vermont**

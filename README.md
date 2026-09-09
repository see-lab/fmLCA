# fmlca

Create and simulate dynamic Life Cycle Assessment (LCA) models with the Functional Mockup Interface (FMI). fmlca supports CLI and Python API workflows for inventory conversion, LCA runs, FMU generation, and sequential co-simulation.

[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](https://github.com/see-lab/fmLCA/blob/main/LICENSE)
[![CI Tests](https://github.com/see-lab/fmLCA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/see-lab/fmLCA/actions/workflows/ci.yml)

## Contributors

**Kathryn Hinkelman**, **Fitzwilliam Keenan-Koch**, and **Anastasija Mensikova** - [SEE Lab](https://www.theseelab.org/), University of Vermont

## Features

- Dynamic energy propagation through LCA calculations
- Parameterized subsystem composition from CSV inventories
- FMU generation for FMI-compatible co-simulation
- Brightway + ecoinvent based impact assessment workflows
- CLI and Python API support for end-to-end pipelines

## Installation

```bash
git clone https://github.com/see-lab/fmLCA.git
cd fmLCA
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

Requirements:
- Python 3.9-3.13
- ecoinvent 3.8+ database

## Brightway And Ecoinvent Setup

```bash
# Check status
python scripts/setup_brightway.py --name fmlca --ecoinvent 3.12 --check

# Import ecoinvent (LCI + LCIA)
python scripts/setup_brightway.py --name fmlca --ecoinvent 3.12 --system-model cutoff
```

For complete setup options, run:
```bash
python scripts/setup_brightway.py -h
```

Detailed guidance: [Ecoinvent Setup Guide](https://github.com/see-lab/fmLCA/blob/main/docs/ECOINVENT_SETUP.md)

## Safe Project Selection

Set the target Brightway project explicitly in multi-project environments:

```powershell
$env:FMLCA_BW_PROJECT = "fmlca"
```

Optional non-interactive project switching:

```powershell
$env:FMLCA_AUTO_CONFIRM_PROJECT_SWITCH = "true"
```

## CLI Workflow (Primary Reference)

Get full options for each command with `-h`.

### 1) Convert CSV To Inventory JSON

```bash
python scripts/csv_to_json_translator.py example.csv
python scripts/csv_to_json_translator.py example1 example2 --output combined_system.json
python scripts/csv_to_json_translator.py -h
```

### 2) Run LCA

```bash
python src/lca_engine.py example --methods ipcc
python src/lca_engine.py -h
```

### 3) Build FMU

```bash
python scripts/create_fmu.py example --method ipcc
python scripts/create_fmu.py example --method ipcc --bw-project fmlca
python scripts/create_fmu.py -h
```

### 4) Run FMU / Sequential Co-simulation

```bash
python scripts/run_fmu.py --mode single --fmu fmu/Example_Ipcc_v0.0.1.fmu --u0 100 --step-size 60
python scripts/run_fmu.py --mode cosim --system-fmu fmu/PV_System_WECC.fmu --lca-fmu fmu/PvWecc_Ipcc_v0.0.1.fmu --system-output gri.P.real --lca-input u --lca-output y --parameter-name n_pv --parameter-value 2.0 --output-interval 3600 --solver CVode --save-plot results/cosim.png
python scripts/run_fmu.py -h
```

## Python API Workflow

Use lowercase package import:

```python
from fmlca import csv_to_json_translator, create_fmu, lca_engine, run_fmu
csv_to_json_translator("data/inventory/example.csv", "data/inventory/example.json")
fmu_path = create_fmu("data/inventory/example.json", "fmu", method="ipcc", version="0.0.1")
results = lca_engine("data/inventory/example.json", ["IPCC 2021 climate change total excl biogenic GWP100"])
sim = run_fmu(fmu_path, stop_time=3600.0, input_u=100.0)
```

Two-FMU co-simulation API:

```python
from pathlib import Path
from fmlca.run_fmu import sequential_cosim
system_result, lca_result = sequential_cosim(system_fmu=Path("fmu/PV_System_WECC.fmu"), lca_fmu=Path("fmu/PvWecc_Ipcc_v0.0.1.fmu"), start_s=0.0, stop_s=3600.0, system_output="gri.P.real", lca_input="u", lca_output="y")
```

## Advanced Options

- Dymola preset: `python scripts/create_fmu.py grid --method ipcc --target-tool dymola --accept-ip-risk`.
- Strict distribution mode: `python scripts/create_fmu.py grid --method ipcc --target-tool dymola --export-mode bytecode --blackbox-policy enforce`.
- Default safety posture: bytecode export + black-box enforce; run `python scripts/create_fmu.py -h` for all policy/export options.

## Project Structure

```
├── src/                    # Core library modules
├── scripts/                # CLI tools
├── data/                   # Inventories and LCIA methods
│   ├── inventory/
│   └── methods/
├── config/                 # Configuration files
├── fmu/                    # Generated FMUs
├── results/                # Analysis outputs
└── tests/                  # Test suite
```

## Testing

```bash
python tests/test_cumulative_fmu.py
python -m pytest tests/
```

## Documentation

- [Release Tracking](https://github.com/see-lab/fmLCA/blob/main/docs/RELEASE_TRACKING.md)

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](https://github.com/see-lab/fmLCA/blob/main/CONTRIBUTING.md).

## License

BSD 3-Clause License. See [LICENSE](https://github.com/see-lab/fmLCA/blob/main/LICENSE).

## Citation

Citation details will be added here.

## Links

- [GitHub Repository](https://github.com/see-lab/fmLCA)
- [SEE Lab](https://www.theseelab.org/)
- [Brightway Documentation](https://docs.brightway.dev/)

---

Maintained by the SEE Lab at University of Vermont

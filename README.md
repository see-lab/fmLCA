# LCA-FMU

Life Cycle Assessment platform with Functional Mock-up Unit generation for energy systems modeling.

Built with Brightway 2.5 and ecoinvent integration.

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
- Brightway 2.5
- Ecoinvent 3.8+ database
- 8GB+ RAM

### Run LCA Analysis

```bash
# Analyze cooling systems with IMPACT World+ methods
python src/lca_engine.py coolingtower --methods iw_damages
python src/lca_engine.py oncethroughcooling --methods iw_damages
```

### Generate FMU

```bash
# Create FMU for co-simulation
python scripts/create_fmu.py --inventory data/inventory/grid.json \
  --name "Grid_Cumulative" --method climate_change
```

### Convert CSV to LCA

```bash
# Auto-detect energy processes and convert CSV
python scripts/csv_to_json_translator.py input_inventory.csv
```

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
# Test FMU logic (macOS compatible)
python tests/test_cumulative_fmu_direct.py

# Run all tests
python -m pytest tests/
```

**Note:** FMU binaries require Linux/Windows. macOS users can test via direct Python execution.

## Documentation

- **[Release Tracking](docs/RELEASE_TRACKING.md)** - Update status and remaining tasks for alpha deployment
- More to come later...

## Contributing

Contributions welcome! Fork the repo, create a feature branch, test your changes, and submit a PR.

See development guidelines in `CONTRIBUTING.md`.

## License

MIT License - see [LICENSE](LICENSE) file.

## Citation

```bibtex
@software{lca_fmu_2026,
  title = {LCA-FMU: Life Cycle Assessment with Functional Mock-up Units},
  author = {Hinkelman, Kathryn and Koch, Fitz},
  year = {2026},
  url = {https://github.com/see-lab/lca-fmu},
  organization = {SEE Lab, University of Vermont}
}
```

## Links

- [GitHub Repository](https://github.com/see-lab/lca-fmu)
- [SEE Lab](http://www.theseelab.org/)
- [Brightway Documentation](https://docs.brightway.dev/)

---

**Maintained by the SEE Lab at University of Vermont**
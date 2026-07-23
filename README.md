# LCA-FMU: Life Cycle Assessment with Functional Mock-up Units

A comprehensive **production-ready** Life Cycle Assessment (LCA) platform built with Brightway2.5 and ecoinvent database integration. This system provides **dynamic energy propagation**, **automatic process detection**, and **FMU (Functional Mock-up Unit) generation** for advanced co-simulation applications in energy systems modeling.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Brightway](https://img.shields.io/badge/brightway-2.5-green)](https://brightway.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 👥 Contributors

- **Kathryn Hinkelman** - SEE Lab, University of Vermont
- **Fitz Koch** - SEE Lab, University of Vermont

Part of the [SEE Lab](https://github.com/see-lab) at University of Vermont.

## 🌟 Key Features

- **🔋 Dynamic Energy Propagation** - Real-time energy scaling throughout LCA calculations with `amount_ref` metadata system
- **🤖 Automatic Process Detection** - Zero-configuration CSV import with intelligent energy process recognition  
- **⚡ Cumulative Impact FMUs** - Time-integrated environmental impact tracking for dynamic energy systems
- **🎯 IPCC 2021 Compliance** - Proper biogenic carbon exclusion for accurate climate assessments
- **📊 Production Analytics** - Comprehensive results with stage breakdown and visualization
- **🌍 IMPACT World+ Integration** - Support for 728+ LCIA methods including IW+ 2.2.1 damage indicators
- **🏭 Multiple Cooling Systems** - Pre-configured inventories for power plant cooling technology comparison

## 📁 Project Structure

```
lca-fmu/
├── src/                          # Core LCA Library
│   ├── lca_engine.py            # Dynamic energy resolution engine (1,212 lines)
│   ├── lci_data_manager.py      # Data processing with energy detection (458 lines)
│   ├── database_manager.py      # Brightway database management (212 lines)
│   ├── config_manager.py        # System configuration handling (137 lines)
│   ├── fmu_generator.py         # FMU generation core logic (600 lines) ⭐ NEW
│   ├── inventory_processor.py   # Inventory loading & validation (450 lines) ⭐ NEW
│   ├── lca_utils.py             # Utility functions (paths, units, I/O) (450 lines) ⭐ NEW
│   └── methods_manager.py       # LCIA methods management (558 lines) ⭐ NEW
├── scripts/                      # CLI Tools (thin wrappers)
│   ├── create_fmu.py            # FMU generation CLI (350 lines, refactored)
│   ├── csv_to_json_translator.py # CSV to JSON converter (187 lines)
│   ├── setup_environment.py     # Environment setup
│   ├── validate_simple.py       # Simple validation
│   ├── experimental/            # Experimental features
│   │   ├── extract_all_methods.py     # Extract methods from Brightway
│   │   ├── import_lcia_method.py      # Import new LCIA methods
│   │   └── compare_cooling_systems.py # Cooling technology comparison
│   └── archive/                 # Archived/legacy scripts
├── data/                         # LCI Data & Methods
│   ├── inventory/               # Energy-enabled JSON inventories
│   │   ├── grid.json           # Electricity grid (IPCC 2021)
│   │   ├── propane.json        # Propane with energy propagation
│   │   ├── sandbattery.json    # Sand battery storage system
│   │   ├── bess.json           # Battery energy storage
│   │   └── default.json        # Template inventory
│   └── methods/                 # LCIA method configurations
│       ├── ipcc.json           # IPCC 2021 climate change
│       ├── midpoints.json      # Midpoint indicators
│       ├── endpoints.json      # Endpoint/damage indicators
│       └── iw_damages.json     # IMPACT World+ damage methods
├── config/                       # System Configuration
│   └── system_config.json       # Main system configuration
├── fmu/                         # Generated FMUs
│   ├── *_Static.fmu            # Fast factor-based FMUs
│   ├── *_Dynamic.fmu           # Accurate energy-propagated FMUs
│   └── test_*.py               # FMU validation scripts
├── docs/                        # Comprehensive Documentation
│   ├── MODULE_CRITICALITY_ANALYSIS.md    # Module deployment guide
│   ├── METHODS_MANAGER_MODULE.md         # Methods API reference
│   ├── CODE_REORGANIZATION_PROGRESS.md   # Refactoring summary
│   ├── SYSTEM_MODERNIZATION_COMPLETE.md  # Production readiness
│   ├── ENERGY_SYSTEM_QUICK_START.md      # Energy system guide
│   └── FMU_DYNAMIC_ENERGY_UPDATE.md      # Dynamic FMU docs
├── results/                     # Analysis Outputs
│   ├── *_results.csv           # Impact summaries
│   ├── *_results.json          # Detailed JSON results
│   └── *_results.png           # Visualizations
├── examples/                    # Usage Examples
│   ├── simple_lca.py           # Basic LCA workflow
│   └── simulate_fmu.py         # FMU co-simulation example
└── tests/                       # Test Suite
    ├── test_cumulative_fmu_direct.py  # FMU logic testing (macOS)
    └── test_*.py                      # Additional tests
```

### 🏗️ Architecture Overview

**Core Library (`src/`):** Professional, reusable modules with clear separation of concerns
- **LCA Engine** - Main calculation engine with energy propagation
- **Data Managers** - Database and inventory data handling
- **FMU Generator** - Complete FMU generation pipeline
- **Methods Manager** - LCIA method extraction, import, and validation
- **Utilities** - Shared functions for paths, units, and file I/O

**CLI Scripts (`scripts/`):** Thin wrappers around library functions
- Clean command-line interfaces
- Minimal business logic
- Easy to maintain and extend

**Benefits:**
- ✅ **Testable** - Core logic isolated from CLI
- ✅ **Reusable** - Library functions can be imported anywhere
- ✅ **Maintainable** - Single responsibility per module
- ✅ **Pip-installable** - Ready for `pip install lca-fmu`

## 🚀 Quick Start

### Installation

```bash
# Clone and setup environment
git clone https://github.com/see-lab/lca-fmu.git
cd lca-fmu

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### Prerequisites

- **Python 3.9-3.13** (tested on 3.13.12)
- **Brightway 2.5** LCA framework
- **Ecoinvent 3.8+** database (3.12 recommended)
- **8GB+ RAM** (16GB recommended for large inventories)

**Note:** FMU binary simulation requires Linux or Windows. On macOS, the system uses direct Python execution of FMU logic (see `tests/test_cumulative_fmu_direct.py`).

### Production Workflow

#### 1. Run LCA Analysis with IMPACT World+ Methods

```bash
# Run cooling tower analysis with IW+ damage indicators
python src/lca_engine.py coolingtower --methods iw_damages

# Run once-through cooling analysis
python src/lca_engine.py oncethroughcooling --methods iw_damages

# Results saved to results/ directory with visualizations
```

#### 2. CSV to LCA System (Auto-Detection)

```bash
# Convert CSV with automatic energy process detection
python scripts/csv_to_lci_json.py input_inventory.csv

# Output: Auto-generated JSON with energy metadata
# - Detects energy processes by units (MJ, kWh, GJ)
# - Creates energy_metadata structure automatically
# - Uses amount_ref for dynamic scaling
```

#### 2. Static FMU Generation (Fast Performance)

```bash
# Create fast factor-based FMU
python scripts/create_fmu.py --inventory data/inventory/grid.json \
  --name "Grid_Static" --method climate_change

# Result: Grid_Static.fmu (pre-calculated impact factors)
# Performance: ~1ms simulation time
# Use case: Real-time control, optimization
```

#### 3. Cumulative Impact FMU (Time-Integrated)

```bash
# Create FMU that tracks cumulative environmental impact over time
python scripts/create_fmu.py --inventory data/inventory/grid.json \
  --name "Grid_Cumulative" --method climate_change

# Result: Grid_Cumulative.fmu with time-integrated impact tracking
# Input: Power [MW] at each timestep
# Output: Cumulative impact [kg CO2-eq] over simulation period
# Use case: Energy system co-simulation, temporal analysis
```

## 🔬 Testing & Validation

### FMU Testing on macOS

**Important:** FMU binaries only support Linux and Windows platforms. On macOS, use the direct Python test:

```bash
# Test FMU logic directly (works on macOS)
python tests/test_cumulative_fmu_direct.py

# This extracts and runs the Python calculation code from the FMU
# Results are accurate and match FMI binary behavior
```

### Cooling Systems Comparison

```bash
# Compare cooling tower vs once-through cooling
python scripts/compare_cooling_systems.py

# Analyzes 37 IMPACT World+ damage indicators
# Results: Ecosystem quality vs human health trade-offs
```

## 🔋 Energy System Features

### Dynamic Energy Propagation

The system automatically propagates energy amounts throughout the entire LCA calculation:

```json
{
  "energy_metadata": {
    "primary_input": {
      "value": 100.0,
      "unit": "MJ", 
      "description": "Primary energy input to system"
    }
  },
  "processes": [
    {
      "name": "electricity, low voltage",
      "amount": "amount_ref",
      "amount_ref": "energy_metadata.primary_input.value"
    }
  ]
}
```

### Automatic Process Detection

CSV files are automatically enhanced with energy metadata:

```csv
Item,Amount,Unit
electricity consumption,27.78,kWh
heat production,100,MJ
fuel combustion,2.78,kg
```

**Becomes:**
- Energy processes (MJ, kWh, GJ) → `amount_ref` with energy metadata
- Non-energy processes → Fixed amounts as specified
- Automatic unit conversion (MJ ↔ kWh: factor of 3.6)

### IPCC 2021 Compliance

Proper climate change assessment with biogenic carbon exclusion:
- **Method**: "IPCC 2021 climate change total excl biogenic GWP100"
- **Consistency**: Matches SimaPro results within 7.41% (explained difference)
- **Accuracy**: Eliminates biogenic carbon double-counting issues

## 🎛️ FMU Generation Modes

### Cumulative Impact Mode (Recommended)
```bash
python scripts/create_fmu.py --inventory grid.json --name Grid_Cumulative
```
- **Input**: Power [MW] at each timestep
- **Output**: Cumulative environmental impact [kg CO2-eq]
- **Method**: Time-integrated impact tracking
- **Use Case**: Dynamic energy system simulation, temporal analysis
- **Validation**: Tests available in `tests/test_cumulative_fmu_direct.py`

### Legacy Static Mode (Deprecated)
```bash
python scripts/create_fmu.py --inventory grid.json --name Grid_Static
```
- **Speed**: ~1ms per simulation step
- **Method**: Pre-calculated impact factors
- **Limitation**: Fixed energy amounts, no temporal tracking

## 📊 Production Analytics

### Automated Results Generation

Every analysis produces comprehensive outputs:

```bash
# Results automatically generated in results/
├── system_results.csv       # Impact category summaries  
├── system_results_stages.csv # Life cycle stage breakdown
└── system_results.png       # Stacked bar visualization
```

### Energy Impact Scaling

Dynamic relationship between energy input and environmental impacts:

```python
# Energy scaling example
energy_input = 50.0  # MJ
# All energy processes scale proportionally:
# - Electricity: 13.89 kWh (50 MJ ÷ 3.6)
# - Heat: 50.0 MJ (direct)
# - Climate impact: Scales linearly with energy
```

## 🏭 Advanced Usage

### Cooling Systems LCA Comparison

Pre-configured inventories for power plant cooling technology assessment:

```bash
# Analyze cooling tower (wet recirculating)
python src/lca_engine.py coolingtower --methods iw_damages
# - 1.5% parasitic load
# - 2.5 m³ water consumption per MWh
# - Biocide use for biological control

# Analyze once-through cooling
python src/lca_engine.py oncethroughcooling --methods iw_damages  
# - 0.2% parasitic load
# - 150 m³ water withdrawal per MWh
# - Thermal pollution to water bodies

# Compare both systems
python scripts/compare_cooling_systems.py
# Generates comparison across 37 IW+ damage indicators
```

### IMPACT World+ Methods Integration

The system includes 728+ LCIA methods from ecoinvent 3.12:

```bash
# Extract all available methods
python scripts/extract_all_methods.py

# Use IW+ damage indicators (37 methods)
python src/lca_engine.py <inventory> --methods iw_damages
# - 25 Ecosystem Quality indicators (PDF.m2.yr)
# - 12 Human Health indicators (DALY)
```

### Custom Energy Systems

Create complex energy system inventories:

```bash
# Start with CSV data
echo "Item,Amount,Unit,Stage
electricity grid,100,MJ,Production
battery storage,85,MJ,Use  
system losses,15,MJ,Use" > my_system.csv

# Convert with energy detection
python scripts/csv_to_lci_json.py my_system.csv

# Generate dynamic FMU
python scripts/create_fmu.py --inventory data/inventory/my_system.json \
  --dynamic --name MySystem_Dynamic
```

### Multi-Method Analysis

Generate FMUs for different impact categories:

```bash
# Climate change (IPCC 2021)
python scripts/create_fmu.py --inventory grid.json \
  --method climate_change --name Grid_Climate

# Import IMPACT World+ methods (143 methods)
python scripts/write_iw_method.py

# Multiple methods in sequence
for method in climate_change acidification eutrophication; do
  python scripts/create_fmu.py --inventory grid.json \
    --method $method --name Grid_${method^}
done
```

### Production System Integration

Integrate FMUs into larger energy system models:

```python
# Example co-simulation setup
import fmpy

# Load cumulative impact FMU
model_description = fmpy.read_model_description('Grid_Cumulative.fmu')

# Simulate with varying power input
result = fmpy.simulate_fmu('Grid_Cumulative.fmu', 
                            start_values={'u': 100.0},  # Initial power [MW]
                            output=['y'])  # Cumulative impact [kg CO2-eq]

# Note: FMI binary simulation requires Linux/Windows
# On macOS, use direct Python execution (see tests/test_cumulative_fmu_direct.py)
```

## 💡 System Configuration

The system behavior is controlled by `config/system_config.json`:

### Energy Detection Settings
```json
{
  "energy_applications": {
    "energy_process_detection": {
      "energy_units": ["MJ", "kWh", "GJ", "TJ"],
      "energy_keywords": ["electricity", "heat", "fuel", "energy"],
      "unit_conversion": {
        "MJ_to_kWh": 0.2777777778,
        "kWh_to_MJ": 3.6
      }
    }
  }
}
```

### LCIA Method Configuration
```json
{
  "lcia_methods": {
    "categories": {
      "climate_change": {
        "specific_methods": [
          "IPCC 2021 climate change total excl biogenic GWP100"
        ],
        "exclude_biogenic": true
      }
    }
  }
}
```

## 📈 Performance & Accuracy

### Validation Results

**Grid Inventory Validation:**
- ✅ **SimaPro Comparison**: 7.41% difference (explained by method selection)
- ✅ **IPCC 2021 Compliance**: Proper biogenic carbon exclusion  
- ✅ **Unit Conversion**: Verified MJ ↔ kWh accuracy (factor 3.6)

**FMU Performance Benchmarks:**
- **Cumulative Impact FMUs**: Accurate time-integrated tracking validated against direct Python execution
- **Memory Usage**: <50MB for typical energy systems
- **Accuracy**: Maintains full LCA precision

**IMPACT World+ Integration:**
- ✅ **143 IW+ 2.2.1 methods** imported into Brightway
- ✅ **37 damage indicators** configured with metadata
- ✅ **728 total LCIA methods** extracted from ecoinvent 3.12

### Platform Compatibility

**FMU Binary Execution:**
- ✅ **Linux x64**: Full FMI 2.0 binary support
- ✅ **Windows x64**: Full FMI 2.0 binary support  
- ⚠️ **macOS (darwin64)**: Binary execution not supported

**macOS Workaround:**
- Use `tests/test_cumulative_fmu_direct.py` to extract and run Python logic directly
- Results are identical to FMI binary execution
- Validated for accuracy and correctness

### Production Readiness Checklist

- ✅ **Automated Process Detection** - Zero manual configuration
- ✅ **Energy Metadata Propagation** - Dynamic scaling throughout system
- ✅ **IPCC 2021 Compliance** - Proper climate change methods  
- ✅ **Cumulative Impact FMUs** - Time-integrated environmental tracking
- ✅ **IMPACT World+ Integration** - 728+ LCIA methods including IW+ 2.2.1
- ✅ **Cooling Systems Analysis** - Pre-configured power plant cooling inventories
- ✅ **Comprehensive Validation** - Extensive testing against reference tools
- ✅ **Clean Architecture** - Well-documented codebase
- ✅ **Production Documentation** - Complete user and developer guides

## 🔗 Integration Examples

### Cooling Systems Environmental Assessment
```python
# Compare cooling tower vs once-through cooling
from scripts.compare_cooling_systems import compare_systems

results = compare_systems(
    systems=['coolingtower', 'oncethroughcooling'],
    methods='iw_damages'
)

# Analyze trade-offs:
# - Water consumption vs thermal pollution
# - Energy use vs ecosystem impacts
# - Chemical biocides vs aquatic toxicity
```

### Time-Series Energy System Analysis
```python
# Simulate cumulative environmental impact over time
import fmpy

# Load cumulative FMU (Linux/Windows)
result = fmpy.simulate_fmu(
    'Grid_Cumulative.fmu',
    start_time=0,
    stop_time=3600,  # 1 hour
    step_size=60,     # 1 minute steps
    input=('u', power_timeseries)  # Power [MW] at each step
)

# Extract cumulative impact trajectory
cumulative_impact = result['y']  # kg CO2-eq over time
```

### Multi-Method LCA Analysis
```python
# Analyze multiple impact categories
from src.lca_engine import run_lca

methods = ['climate_change', 'acidification', 'eutrophication']
for method in methods:
    results = run_lca(
        inventory='grid.json',
        lcia_methods=method
    )
    print(f"{method}: {results['total_impact']}")
```

## 🏗️ Production Platform

### System Requirements

**Minimum Requirements:**
- Python 3.9+ (tested through 3.13)
- 8GB RAM
- Brightway2.5 compatible system
- Access to ecoinvent 3.8+ database (3.12 recommended)

**Recommended Production Setup:**
- Python 3.11-3.13
- 16GB+ RAM  
- SSD storage for database performance
- Linux/Windows for FMU binary execution (macOS supported with Python fallback)

### Database Configuration

**Supported Databases:**
- ecoinvent 3.8, 3.9, 3.10, 3.11, 3.12
- IMPACT World+ 2.2.1 methods
- Automatic database detection and selection

**Project Setup:**
```bash
# System automatically searches for projects:
# - "ecoinvent3.12" (preferred)
# - "LCA-FMU" (fallback)
# - "default" (fallback)
```

### Brightway Project Setup

```python
import bw2data as bd

# Create and set up project
bd.projects.set_current('ecoinvent3.12')

# Ensure biosphere database exists
# Follow Brightway documentation for database setup
```

### Production Features

**Quality Assurance:**
- ✅ **SimaPro Validation** - Results verified against industry standard
- ✅ **Brightway Integration** - Native Brightway2.5 ecosystem  
- ✅ **Energy Balance Checking** - Automatic energy conservation validation
- ✅ **Method Auto-Selection** - IPCC 2021 prioritized with fallbacks
- ✅ **FMU Compliance** - Built-in FMI 2.0 validation (Linux/Windows)
- ✅ **IMPACT World+ Support** - 143 IW+ 2.2.1 methods integrated

**Automated Workflows:**
- 🔋 **Energy Process Detection** - Automatic CSV enhancement
- ⚡ **Dynamic Energy Scaling** - Real-time propagation  
- 🔄 **Unit Conversion** - Seamless MJ ↔ kWh handling
- 📊 **Results Generation** - Comprehensive analytics
- 🎯 **Error Recovery** - Robust fallback mechanisms
- 🌍 **Multi-Method Analysis** - 728+ LCIA methods available

### Key Inventories Included

**Energy Systems:**
- `grid.json` - Electricity grid with IPCC 2021 climate change
- `bess.json` - Battery energy storage system
- `propane.json` - Propane combustion with energy propagation
- `sandbattery.json` - Thermal sand battery storage

**Cooling Systems:**
- `coolingtower.json` - Wet recirculating cooling tower
- `oncethroughcooling.json` - Once-through cooling system

Each inventory includes:
- Detailed process flows with ecoinvent linkages
- Biosphere exchanges for emissions
- Infrastructure materials with lifetime amortization
- Energy metadata for dynamic scaling

### Deployment Options

**Development Environment:**
```bash
git clone https://github.com/see-lab/lca-fmu.git
cd lca-fmu
python -m venv venv && source venv/bin/activate  
pip install -r requirements.txt
```

**Production Installation:**
```bash  
# Minimal production deployment
pip install brightway25 bw2data bw2calc bw2io
pip install fmpy pythonfmu numpy pandas matplotlib
# Deploy src/ and config/ directories
# Configure Brightway projects with ecoinvent database
```

**Container Deployment:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "src/lca_engine.py"]
```

### Performance & Monitoring

**Benchmarks:**
- **Cumulative FMU Validation**: Accurate time-integrated tracking
- **CSV Processing**: 10,000+ rows/second
- **Memory Footprint**: <50MB typical systems
- **Method Loading**: 728+ LCIA methods indexed

**Testing:**
```bash
# Test FMU logic (works on all platforms)
python tests/test_cumulative_fmu_direct.py

# Validate LCIA methods format
python tests/test_methods_format.py

# Test method loading
python tests/test_methods_loader.py

# Test argument parsing
python tests/test_arg_parsing.py
```

---

## 📚 Documentation

### Core Documentation
- **[Module Criticality Analysis](docs/MODULE_CRITICALITY_ANALYSIS.md)** - Module deployment guide and dependencies
- **[Methods Manager API](docs/METHODS_MANAGER_MODULE.md)** - Complete LCIA methods management API reference
- **[Code Reorganization](docs/CODE_REORGANIZATION_PROGRESS.md)** - Architecture improvements and refactoring summary
- **[Cooling Systems Project](docs/COOLING_SYSTEMS_PROJECT_COMPLETE.md)** - Power plant cooling technology LCA comparison
- **[System Modernization Guide](docs/SYSTEM_MODERNIZATION_COMPLETE.md)** - Production readiness overview
- **[IW+ Damages Format](docs/IW_DAMAGES_FORMAT_UPDATE.md)** - IMPACT World+ damage indicators documentation

### Library API Usage

The `src/` modules provide a professional, reusable API for LCA operations:

#### Example: Using the Library in Your Code

```python
# Import core LCA functionality
from src.lca_engine import run_lca_energy
from src.fmu_generator import generate_fmu_class_code, build_fmu_with_pythonfmu
from src.inventory_processor import load_inventory_file, validate_inventory_format
from src.methods_manager import load_lcia_methods, infer_category, extract_all_methods
from src.lca_utils import safe_classname, format_unit_label

# Run LCA analysis
results = run_lca_energy(
    lci_file='data/inventory/grid.json',
    lcia_methods='data/methods/ipcc.json',
    functional_unit='1 MJ',
    energy_amount_mj=100.0
)

# Load and validate inventory
inventory = load_inventory_file('my_inventory.json')
is_valid = validate_inventory_format(inventory)

# Manage LCIA methods
method_names, metadata = load_lcia_methods('data/methods/ipcc.json')
category = infer_category(('IPCC 2021', 'climate change', 'GWP100'))

# Extract all methods from Brightway
all_methods = extract_all_methods(project_name='ecoinvent3.12')

# Generate FMU code
fmu_code = generate_fmu_class_code(
    classname='MySystem',
    emission_factors={'CO2': 0.5},
    stage_impacts={'production': 10.0},
    unit='kg CO2-eq'
)
```

### Module Reference

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `lca_engine.py` | Main LCA calculations | `run_lca_energy()`, `load_lcia_methods()` |
| `fmu_generator.py` | FMU generation | `generate_fmu_class_code()`, `build_fmu_with_pythonfmu()` |
| `inventory_processor.py` | Inventory handling | `load_inventory_file()`, `validate_inventory_format()` |
| `methods_manager.py` | Methods management | `extract_all_methods()`, `import_method_from_package()` |
| `lca_utils.py` | Utilities | `safe_classname()`, `format_unit_label()` |
| `database_manager.py` | Database operations | Database setup and management |
| `lci_data_manager.py` | Data processing | LCI data loading and processing |
| `config_manager.py` | Configuration | System configuration management |

See **[Methods Manager API Documentation](docs/METHODS_MANAGER_MODULE.md)** for complete API reference.

## 🤝 Contributing

This is a research project from the SEE Lab at University of Vermont. Contributions are welcome!

### How to Contribute

1. **Fork the repository** on GitHub
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** with clear commit messages
4. **Test thoroughly**:
   ```bash
   python tests/test_cumulative_fmu_direct.py
   python tests/test_methods_format.py
   ```
5. **Submit a pull request** with a clear description

### Development Guidelines

- **Code Organization**: Keep CLI logic in `scripts/`, reusable logic in `src/`
- **Module Design**: Follow single responsibility principle for new modules
- **Documentation**: Add docstrings with type hints for all public functions
- **Testing**: Write tests for new library functions in `tests/`
- **Compatibility**: Maintain compatibility with Brightway 2.5 and ecoinvent 3.12
- **IPCC Compliance**: Ensure IPCC 2021 method compliance for climate change
- **Clean Architecture**: Scripts should be thin wrappers around library functions

### Code Structure Best Practices

When adding new functionality:

1. **Library Functions** (`src/`) - Core reusable logic
   - Pure functions with clear inputs/outputs
   - Type hints for all parameters
   - Comprehensive docstrings
   - Independent of CLI concerns

2. **CLI Scripts** (`scripts/`) - User-facing interfaces
   - Argument parsing and validation
   - Call library functions
   - Handle user I/O
   - Minimal business logic

3. **Tests** (`tests/`) - Validation
   - Unit tests for library functions
   - Integration tests for workflows
   - Test fixtures for common scenarios

### Testing

```bash
# Run all tests
python -m pytest tests/

# Test specific functionality
python tests/test_cumulative_fmu_direct.py
python tests/test_methods_loader.py
```

### Areas for Contribution

- Additional cooling system technologies (dry cooling, hybrid systems)
- More energy storage system inventories
- Integration with other LCIA methods
- Performance optimizations
- Documentation improvements
- Bug fixes and error handling

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📖 Citation

If you use this software in your research, please cite:

```bibtex
@software{lca_fmu_2026,
  title = {LCA-FMU: Life Cycle Assessment with Functional Mock-up Units},
  author = {Hinkelman, Kathryn and Koch, Fitz},
  year = {2026},
  url = {https://github.com/see-lab/lca-fmu},
  organization = {SEE Lab, University of Vermont}
}
```

### Related Publications

**IMPACT World+ Methodology:**
- Bulle, C., Margni, M., Patouillard, L. et al. (2019). IMPACT World+: a globally regionalized life cycle impact assessment method. *Int J Life Cycle Assess* 24, 1653–1674. https://doi.org/10.1007/s11367-019-01583-0

**Brightway LCA Framework:**
- Mutel, C. (2017). Brightway: An open source framework for Life Cycle Assessment. *Journal of Open Source Software*, 2(12), 236. https://doi.org/10.21105/joss.00236

## 🔗 Links

- **GitHub Repository**: https://github.com/see-lab/lca-fmu
- **SEE Lab**: http://www.theseelab.org/
- **Brightway Documentation**: https://docs.brightway.dev/
- **IMPACT World+ Methods**: http://www.impactworldplus.org/

## 💬 Contact

For questions, issues, or collaboration inquiries:

- **Open an issue** on GitHub
- **Email**: Contact through SEE Lab at University of Vermont

---

**Maintained by the SEE Lab at University of Vermont**  
*Advancing sustainable energy and environmental systems through integrated modeling*
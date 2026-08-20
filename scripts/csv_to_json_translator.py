#!/usr/bin/env python3
"""
CSV to JSON Translator for Life Cycle Inventory (LCI) Data
Converts CSV inventory data to JSON format,
with energy propagation for dynamic consumption rates.

Features:
  • Automatic energy process detection (by unit: MJ, kWh, GJ, etc.)
  • Energy processes use amount_ref instead of hardcoded amounts
    • Energy metadata retains original inventory base value and unit (no normalization)
  • Modern energy_metadata format with "value" field
    • Conversion to required analysis units is handled by lca_engine before impacts
  • Combines multiple CSV files into a single system with parameter support

Usage:
    python scripts/csv_to_json_translator.py input # Creates input.json
    python scripts/csv_to_json_translator.py example1 example2  # Creates example1_example2_combined.json

Energy Process Conversion:
  • CSV: "Water pump, 540, MJ" → JSON: "amount_ref": "energy_metadata.primary_input.value"
    • CSV: "Electricity, 25, kWh" → Metadata: "value": 25, "unit": "kWh"
  • All non-energy processes keep direct amounts

Supports flexible CSV formats through configuration-driven field mapping.
Lines beginning with '#' are treated as metadata/comments.
Parameterization is pulled from '#' metadata lines, structured as follows:
    # Parameter: parameter_name
    # Parameter_Description: description text
    # Parameter_Default: default_value
"""

import csv
import json
import argparse
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def convert_csv_to_lci_json_flexible(csv_files, output_file=None):
    """
    Convert CSV inventory data to LCI JSON format using flexible configuration
    
    Args:
        csv_files: Path to input CSV file, or list of CSV files for multi-subsystem combination
                   (or stem names to search in data/inventory/)
        output_file: Path to output JSON file (optional, defaults to same name with .json)
    
    Returns:
        dict: The generated LCI data structure
    """
    
    # Normalize input to list
    if isinstance(csv_files, str):
        csv_files = [csv_files]
    
    # Resolve all CSV file paths
    csv_paths = []
    for csv_file in csv_files:
        csv_path = Path(csv_file)
        
        # If file doesn't exist, try searching in data/inventory/
        if not csv_path.exists():
            # Try as stem name (without .csv)
            stem = csv_file.replace('.csv', '')
            inventory_dir = project_root / 'data' / 'inventory'
            
            # Search for file with .csv extension
            candidate = inventory_dir / f"{stem}.csv"
            if candidate.exists():
                csv_path = candidate
            else:
                raise FileNotFoundError(
                    f"CSV file not found: {csv_file}\n"
                    f"   Tried: {csv_file}\n"
                    f"   Tried: {candidate}"
                )
        
        csv_paths.append(csv_path)
    
    # Determine output file name
    if output_file is None:
        if len(csv_paths) == 1:
            output_file = csv_paths[0].with_suffix('.json')
        else:
            # For multiple files, create combined name
            combined_name = "_".join([p.stem for p in csv_paths])
            output_file = csv_paths[0].parent / f"{combined_name}_combined.json"
    
    print(f"🔄 Converting CSV to LCI JSON using flexible configuration...")
    print(f"   📁 Input: {', '.join(str(p) for p in csv_paths)}")
    print(f"   📁 Output: {output_file}")
    
    # Initialize managers
    from src.config_manager import get_config
    from src.lci_data_manager import LCIDataManager

    config = get_config()
    lci_manager = LCIDataManager()
    
    try:
        # Import CSV data using flexible manager
        if len(csv_paths) == 1:
            # Single file import
            lci_data = lci_manager.import_data(str(csv_paths[0]), format_type="csv")
        else:
            # Multi-file import with parameter support
            lci_data = lci_manager.import_multiple_csv(csv_paths)
        
        if not lci_data:
            raise Exception("Failed to import CSV data")
        
        print(f"✅ Successfully converted CSV data")
        print(f"   📋 Process: {lci_data.get('name', 'Unknown')}")
        print(f"   🔄 Exchanges: {len(lci_data.get('exchanges', []))}")
        if 'parameters' in lci_data:
            print(f"   📊 Parameters: {list(lci_data['parameters'].keys())}")
        
        # Export to JSON
        lci_manager.export_to_json(lci_data, str(output_file))
        
        print(f"✅ JSON file created: {output_file}")
        return lci_data
        
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        return None


def test_with_lca_analysis(json_file, product_name):
    """Test the generated JSON with the LCA system"""
    try:
        # Import LCA system components
        from src.lca_engine import run_lca_energy
        
        # Test with default methods
        methods = ["IPCC 2021 climate change total excl biogenic GWP100"]
        functional_unit = {}
        
        print(f"   🔄 Testing with {json_file}")
        results = run_lca_energy(str(json_file), methods, functional_unit, 180.0)
        
        if "error" in results:
            print(f"   ⚠️ LCA test had issues: {results['error']}")
            return False
        else:
            print("   ✅ LCA test completed successfully")
            return True
            
    except Exception as e:
        print(f"   ⚠️ LCA test failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert CSV inventory data to LCI JSON format (supports multi-file combination)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file (using short name - searches in data/inventory/)
  python scripts/csv_to_json_translator.py example
  python scripts/csv_to_json_translator.py example.csv
  
  # Single file (using full path)
  python scripts/csv_to_json_translator.py data/inventory/example.csv
  python scripts/csv_to_json_translator.py my_product.csv my_product.json
  
  # Multiple files with parameters (combined into single system)
  python scripts/csv_to_json_translator.py pv bess
  
  # With validation
  python scripts/csv_to_json_translator.py example --validate

Metadata/comments:
    Lines starting with '#' in CSV files are ignored by the translator, except parameterization:
    Parameter metadata format:
      # Parameter: parameter_name
      # Parameter_Description: description text
      # Parameter_Default: default_value
        """
    )
    
    parser.add_argument("csv_files", nargs='+', help="Input CSV file(s) - stem names or full paths. Multiple files will be combined.")
    parser.add_argument("--output", "-o", dest="json_file", help="Output JSON file path (optional)")
    parser.add_argument("--validate", action="store_true", help="Validate the generated JSON")
    parser.add_argument("--test", action="store_true", help="Test with LCA analysis system")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    
    args = parser.parse_args()
    
    if args.quiet:
        # Redirect stdout to suppress prints
        import os
        devnull = open(os.devnull, 'w')
        sys.stdout = devnull
    
    try:
        # Use flexible conversion mode (supports single or multiple files)
        print("🔄 Using flexible conversion mode")
        lci_data = convert_csv_to_lci_json_flexible(args.csv_files, args.json_file)
        
        if lci_data is None:
            print("❌ Conversion failed")
            sys.exit(1)
        
        # Determine output file for validation/testing
        if args.json_file:
            output_file = args.json_file
        elif len(args.csv_files) == 1:
            output_file = Path(args.csv_files[0]).with_suffix('.json')
        else:
            combined_name = "_".join([Path(f).stem for f in args.csv_files])
            output_file = f"{combined_name}_combined.json"
        
        product_name = Path(args.csv_files[0]).stem
        
        # Restore stdout for final messages
        if args.quiet:
            sys.stdout = sys.__stdout__
            devnull.close()
        
        # Validation
        if args.validate:
            from src.lci_data_manager import validate_inventory_format

            print("   🔍 Validating JSON structure...")
            is_valid = validate_inventory_format(lci_data)
            if not is_valid:
                print(f"⚠️  Validation found issues - please review")
        
        # Testing
        if args.test:
            test_success = test_with_lca_analysis(output_file, product_name)
            if not test_success:
                print(f"⚠️  LCA analysis test had issues")
        
        print(f"\n🎉 CSV to LCI JSON conversion completed!")
        print(f"   📁 Output file: {output_file}")
        print(f"   🚀 Ready for FMU generation with:")
        print(f"      python scripts/quick_fmu_creator.py {product_name}")
        
    except Exception as e:
        if args.quiet:
            sys.stdout = sys.__stdout__
            devnull.close()
        print(f"❌ Conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

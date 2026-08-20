#!/usr/bin/env python3
"""
Test script for parameterized LCA-FMU systems

Demonstrates:
1. Single CSV with parameters
2. Multiple CSV files combined with different parameters
3. Parameter extraction and propagation to amounts
4. Verification of parameter formulas in output JSON
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lci_data_manager import LCIDataManager


def test_single_parameterized_csv():
    """Test single CSV with parameter metadata"""
    print("\n" + "="*80)
    print("TEST 1: Single Parameterized CSV (PV System)")
    print("="*80)
    
    lci_manager = LCIDataManager()
    
    # Import single parameterized CSV
    csv_file = project_root / 'data' / 'inventory' / 'pv.csv'
    lci_data = lci_manager.import_data(str(csv_file), format_type='csv')
    
    # Verify parameters were extracted
    assert 'parameters' in lci_data, "Parameters not found in LCI data"
    assert 'n_pv' in lci_data['parameters'], "Parameter 'n_pv' not found"
    
    param = lci_data['parameters']['n_pv']
    assert param['name'] == 'n_pv'
    assert param['description'] == 'Number of PV panels in the system'
    assert param['default'] == 1.0
    
    print(f"✅ Parameter extracted: {param['name']}")
    print(f"   Description: {param['description']}")
    print(f"   Default: {param['default']}")
    
    # Verify exchanges
    print(f"\n📦 Exchanges: {len(lci_data['exchanges'])}")
    for exchange in lci_data['exchanges']:
        if exchange.get('type') != 'production':
            print(f"   - {exchange['name']}: {exchange.get('amount')} {exchange.get('unit')}")
    
    return True


def test_multiple_parameterized_csv():
    """Test combining multiple CSV files with different parameters"""
    print("\n" + "="*80)
    print("TEST 2: Multiple Parameterized CSVs (PV + BESS Combined)")
    print("="*80)
    
    lci_manager = LCIDataManager()
    
    # Import multiple parameterized CSVs
    csv_files = [
        project_root / 'data' / 'inventory' / 'pv.csv',
        project_root / 'data' / 'inventory' / 'bess.csv'
    ]
    
    lci_data = lci_manager.import_multiple_csv(csv_files)
    
    # Verify parameters from both files
    assert 'parameters' in lci_data, "Parameters not found in combined data"
    assert 'n_pv' in lci_data['parameters'], "Parameter 'n_pv' not found"
    assert 'n_bess' in lci_data['parameters'], "Parameter 'n_bess' not found"
    
    print(f"✅ Parameters extracted:")
    for param_name, param_info in lci_data['parameters'].items():
        print(f"   - {param_name}: {param_info['description']} (default={param_info['default']})")
        print(f"     Subsystem: {param_info.get('subsystem', 'N/A')}")
    
    # Verify subsystems
    assert 'subsystems' in lci_data
    assert len(lci_data['subsystems']) == 2
    print(f"\n📦 Subsystems: {lci_data['subsystems']}")
    
    # Verify parameter formulas in exchanges
    print(f"\n🔄 Exchanges with parameter formulas:")
    for exchange in lci_data['exchanges']:
        if 'amount_formula' in exchange:
            print(f"   - {exchange['name']} ({exchange.get('subsystem', 'N/A')})")
            print(f"     Formula: {exchange['amount_formula']}")
            print(f"     Base amount: {exchange.get('amount_base', exchange.get('amount'))}")
    
    return True


def test_parameter_propagation():
    """Test that parameters correctly propagate to all amounts"""
    print("\n" + "="*80)
    print("TEST 3: Parameter Propagation Verification")
    print("="*80)
    
    lci_manager = LCIDataManager()
    
    csv_files = [
        project_root / 'data' / 'inventory' / 'pv.csv',
        project_root / 'data' / 'inventory' / 'bess.csv'
    ]
    
    lci_data = lci_manager.import_multiple_csv(csv_files)
    
    # Count exchanges by parameter
    param_counts = {}
    for exchange in lci_data['exchanges']:
        if 'parameter' in exchange:
            param = exchange['parameter']
            param_counts[param] = param_counts.get(param, 0) + 1
    
    print(f"✅ Parameter usage in exchanges:")
    for param, count in param_counts.items():
        print(f"   - {param}: {count} exchanges")
    
    # Verify all PV exchanges have n_pv parameter
    pv_exchanges = [ex for ex in lci_data['exchanges'] if ex.get('subsystem') == 'Pv']
    for ex in pv_exchanges:
        assert ex.get('parameter') == 'n_pv', f"PV exchange {ex['name']} missing n_pv parameter"
    
    # Verify all BESS exchanges have n_bess parameter
    bess_exchanges = [ex for ex in lci_data['exchanges'] if ex.get('subsystem') == 'Bess']
    for ex in bess_exchanges:
        assert ex.get('parameter') == 'n_bess', f"BESS exchange {ex['name']} missing n_bess parameter"
    
    print(f"✅ All subsystem exchanges correctly linked to parameters")
    
    return True


def test_json_output_structure():
    """Verify the JSON output structure is correct for FMU generation"""
    print("\n" + "="*80)
    print("TEST 4: JSON Output Structure for FMU Generation")
    print("="*80)
    
    # Load the combined JSON file
    json_file = project_root / 'data' / 'inventory' / 'pv_bess_combined.json'
    
    if not json_file.exists():
        print(f"⚠️  Combined JSON not found, generating...")
        lci_manager = LCIDataManager()
        csv_files = [
            project_root / 'data' / 'inventory' / 'pv.csv',
            project_root / 'data' / 'inventory' / 'bess.csv'
        ]
        lci_data = lci_manager.import_multiple_csv(csv_files)
        lci_manager.export_to_json(lci_data, str(json_file))
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Verify required fields for FMU generation
    required_fields = ['name', 'unit', 'exchanges', 'parameters']
    for field in required_fields:
        assert field in data, f"Required field '{field}' missing from JSON"
        print(f"✅ Field '{field}' present")
    
    # Verify parameter structure
    for param_name, param_info in data['parameters'].items():
        assert 'name' in param_info
        assert 'description' in param_info
        assert 'default' in param_info
        print(f"✅ Parameter '{param_name}' has complete metadata")
    
    # Verify exchange formulas
    formula_count = sum(1 for ex in data['exchanges'] if 'amount_formula' in ex)
    print(f"✅ {formula_count} exchanges have parameter formulas")
    
    return True


def main():
    """Run all parameterization tests"""
    print("\n" + "="*80)
    print("PARAMETERIZATION TEST SUITE")
    print("="*80)
    
    tests = [
        ("Single Parameterized CSV", test_single_parameterized_csv),
        ("Multiple Parameterized CSVs", test_multiple_parameterized_csv),
        ("Parameter Propagation", test_parameter_propagation),
        ("JSON Output Structure", test_json_output_structure)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if error:
            print(f"       Error: {error}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All parameterization tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())

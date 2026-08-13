#!/usr/bin/env python3
"""
LCI Data Manager for Flexible Data Import and Processing

Library module for LCI data processing. Import this module, do not run directly.

Usage:
    from src.lci_data_manager import load_lci_data, process_csv_to_json

Supports CSV, JSON, and other formats with configurable mappings
"""

import csv
import io
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


def validate_inventory_format(data: Dict[str, Any]) -> bool:
    """Validate core inventory structure for downstream LCA processing."""
    required_fields = ["name", "unit", "exchanges"]
    for field in required_fields:
        if field not in data:
            print(f"❌ Missing required field: {field}")
            return False

    if not isinstance(data["exchanges"], list):
        print("❌ 'exchanges' must be a list")
        return False

    for i, exchange in enumerate(data["exchanges"]):
        if not isinstance(exchange, dict):
            print(f"❌ Exchange {i} is not a dictionary")
            return False

        if "type" not in exchange:
            print(f"❌ Exchange {i} missing 'type' field")
            return False

        if exchange.get("type") == "production":
            amount = exchange.get("amount")
            if amount is not None and amount != 1.0:
                print(f"⚠️  Production exchange should have amount=1.0, found {amount}")

    return True

# Handle both relative and absolute imports
try:
    from .config_manager import get_config
except ImportError:
    import sys
    from pathlib import Path
    
    # Add src directory to path if not already there
    src_dir = Path(__file__).parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    
    from config_manager import get_config


class LCIDataManager:
    """Manages LCI data import and processing with flexible formats"""
    
    def __init__(self):
        self.config = get_config()
    
    def import_data(self, file_path: str, format_type: str = "auto") -> Dict[str, Any]:
        """Import LCI data from various formats"""
        path_obj = Path(file_path)
        
        if not path_obj.exists():
            raise FileNotFoundError(f"LCI data file not found: {file_path}")
        
        if format_type == "auto":
            format_type = self.detect_format(path_obj)
        
        print(f"🔄 Importing LCI data...")
        print(f"   📁 File: {file_path}")
        print(f"   📋 Format: {format_type}")
        
        if format_type == "csv":
            return self.import_from_csv(path_obj)
        elif format_type == "json":
            return self.import_from_json(path_obj)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def detect_format(self, file_path: Path) -> str:
        """Detect file format based on extension"""
        suffix = file_path.suffix.lower()
        
        format_map = {
            '.csv': 'csv',
            '.json': 'json',
            '.txt': 'csv',  # Assume tab-separated
            '.tsv': 'csv'
        }
        
        return format_map.get(suffix, 'unknown')
    
    def import_from_csv(self, csv_file: Path) -> Dict[str, Any]:
        """Import from CSV with flexible column mapping"""
        with open(csv_file, 'r', encoding='utf-8') as f:
            raw_lines = f.readlines()

        # Skip metadata/comment lines (starting with '#') and blank lines.
        data_lines = [
            line for line in raw_lines
            if line.strip() and not line.lstrip().startswith('#')
        ]

        if not data_lines:
            raise ValueError(f"No CSV data lines found in file: {csv_file}")

        # Detect delimiter from non-comment content.
        sample = ''.join(data_lines[:20])
        delimiter = ',' if ',' in sample else '\t' if '\t' in sample else ';'

        reader = csv.DictReader(io.StringIO(''.join(data_lines)), delimiter=delimiter)
        rows = [row for row in reader if any((v or '').strip() for v in row.values())]
        
        if not rows:
            raise ValueError(f"No data found in CSV file: {csv_file}")
        
        # Analyze headers and create field mapping
        headers = list(rows[0].keys())
        field_mapping = self.create_field_mapping(headers)
        
        print(f"   📊 Found {len(rows)} rows with {len(headers)} columns")
        print(f"   🔗 Field mapping: {field_mapping}")
        
        # Extract product name from filename
        product_name = csv_file.stem.replace('_', ' ').title()
        
        # Process data
        lci_data = self.process_csv_data(rows, field_mapping, product_name)
        
        return lci_data
    
    def import_from_json(self, json_file: Path) -> Dict[str, Any]:
        """Import from existing JSON file"""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate and normalize JSON structure
        return self.normalize_json_structure(data)
    
    def create_field_mapping(self, headers: List[str]) -> Dict[str, Optional[str]]:
        """Create flexible field mapping from CSV headers"""
        mapping = {}
        
        required_fields = ['name', 'amount', 'unit']
        optional_fields = ['stage', 'location', 'database', 'code', 'process_match',
                           'brightway_code', 'brightway_database', 'brightway_location',
                           'brightway_ref_product']
        
        for field_type in required_fields + optional_fields:
            mapped_field = self.config.resolve_csv_field(headers, field_type)
            mapping[field_type] = mapped_field
            
            if field_type in required_fields and mapped_field is None:
                print(f"   ⚠️  Required field '{field_type}' not found in headers")
        
        return mapping
    
    def process_csv_data(self, rows: List[Dict], field_mapping: Dict[str, Optional[str]], product_name: str) -> Dict[str, Any]:
        """Process CSV data into LCI structure"""
        
        # Initialize LCI structure
        lci_data = {
            "name": f"{product_name} Production System",
            "unit": "unit", 
            "location": "GLO",
            "categories": ["technosphere", f"{product_name.lower()} production"],
            "type": "process",
            "exchanges": []
        }
        
        # Group by lifecycle stages
        stages = {}
        all_exchanges = []
        energy_processes = []
        unlinked_exchanges = []   # rows skipped during CSV import

        for i, row in enumerate(rows):
            # Skip empty rows
            if not any(row.values()):
                continue

            # Extract data using field mapping
            process_data = self.extract_process_data(row, field_mapping)

            if not process_data:
                # Determine why we're skipping and record it
                item_name = row.get('Item', row.get('Name', f'Row {i+1}'))
                amount_raw = row.get('Amount', '').strip()
                bw_code = row.get('Brightway Match Code', '').strip()
                note = row.get('Notes', '').strip()
                try:
                    amt = float(amount_raw) if amount_raw else None
                except ValueError:
                    amt = None

                if amt is None or amt <= 0:
                    reason = f"Amount is {amount_raw!r}" + (f" — {note}" if note else "")
                elif not bw_code:
                    reason = "No Brightway Match Code"
                else:
                    reason = "Insufficient data"

                print(f"   ⚠️  Row {i+1}: Skipping '{item_name}' — {reason}")
                unlinked_exchanges.append({
                    "row": i + 1,
                    "name": item_name,
                    "stage": row.get('Stage', ''),
                    "amount": amount_raw,
                    "unit": row.get('Unit', ''),
                    "reason": reason,
                    "notes": note,
                    "inventory_selection": row.get('Inventory Selection', ''),
                })
                continue
            
            # Determine lifecycle stage
            stage = self.determine_lifecycle_stage(process_data.get('stage', 'Production'))
            
            # Create exchange
            exchange = self.create_exchange(process_data, stage)
            
            if exchange:
                all_exchanges.append(exchange)
                
                # Group by stage
                if stage not in stages:
                    stages[stage] = []
                stages[stage].append(exchange['name'])
                
                # Track energy-related processes (check name AND unit)
                if self.is_energy_process(exchange['name'], exchange.get('unit', '')):
                    # Store the original process data for energy metadata calculation
                    energy_process_with_data = exchange.copy()
                    energy_process_with_data['original_amount'] = process_data['amount']
                    energy_process_with_data['original_unit'] = process_data.get('unit', 'MJ')
                    energy_processes.append(energy_process_with_data)
        
        print(f"   ✅ Processed {len(all_exchanges)} valid exchanges")
        if unlinked_exchanges:
            print(f"   🔗 Unlinked/skipped: {len(unlinked_exchanges)} row(s) (see unlinked_exchanges in output)")
        print(f"   📊 Lifecycle stages: {list(stages.keys())}")
        print(f"   ⚡ Energy processes: {len(energy_processes)}")
        
        # Add production exchange
        production_exchange = {
            "name": f"{product_name} Production System",
            "amount": 1.0,
            "unit": "unit",
            "type": "production",
            "input": [f"{product_name}_System_DB", f"{product_name}_1unit"]
        }
        
        lci_data["exchanges"] = [production_exchange] + all_exchanges
        
        # Add lifecycle stages metadata
        lci_data["life_cycle_stages"] = {}
        for stage_name, exchange_names in stages.items():
            lci_data["life_cycle_stages"][stage_name] = {
                "description": f"{stage_name} stage processes",
                "exchanges": exchange_names
            }
        
        # Add energy metadata with new format
        energy_value = self.determine_energy_value(energy_processes)
        energy_unit = self.determine_energy_unit(energy_processes)
        
        lci_data["energy_metadata"] = {
            "energy_processes": len(energy_processes),
            "primary_input": {
                "name": "energy_input",
                "unit": energy_unit,
                "description": "Energy input to the system",
                "value": energy_value
            }
        }

        # Record exchanges that could not be linked
        lci_data["unlinked_exchanges"] = unlinked_exchanges
        
        return lci_data
    
    def extract_process_data(self, row: Dict[str, str], field_mapping: Dict[str, Optional[str]]) -> Optional[Dict[str, Any]]:
        """Extract process data from CSV row using field mapping"""
        data = {}
        
        for field_type, column_name in field_mapping.items():
            if column_name and column_name in row:
                value = row[column_name].strip() if row[column_name] else None
                
                if field_type == 'amount' and value:
                    try:
                        data[field_type] = float(value)
                    except ValueError:
                        print(f"   ⚠️  Invalid amount: {value}")
                        return None
                else:
                    data[field_type] = value
        
        # Validate required fields
        if not data.get('name') or not data.get('amount') or data.get('amount', 0) <= 0:
            return None
        
        return data
    
    def determine_lifecycle_stage(self, stage_input: str) -> str:
        """Determine lifecycle stage using aliases"""
        if not stage_input:
            return "Production"
        
        stage_input_lower = stage_input.lower().strip()
        stage_config = self.config.get_lifecycle_stages()
        
        # Direct match with default stages
        for default_stage in stage_config.get("default", []):
            if stage_input_lower == default_stage.lower():
                return default_stage
        
        # Match using aliases
        stage_aliases = stage_config.get("aliases", {})
        if isinstance(stage_aliases, dict):
            for default_stage, aliases in stage_aliases.items():
                if stage_input_lower in [alias.lower() for alias in aliases]:
                    return default_stage
        
        # Fallback to input (capitalized)
        return stage_input.title()
    
    def create_exchange(self, process_data: Dict[str, Any], stage: str) -> Optional[Dict[str, Any]]:
        """Create exchange from process data with new energy metadata format"""
        exchange = {
            "name": process_data["name"],
            "unit": process_data.get("unit", "unit"),
            "type": "technosphere",
            "life_cycle_stage": stage
        }
        
        # Check if this is an energy process
        is_energy = self.is_energy_process(process_data["name"], process_data.get("unit", ""))
        
        if is_energy:
            # For energy processes, use energy metadata reference instead of hardcoded amount
            exchange["amount_ref"] = "energy_metadata.primary_input.value"
            print(f"   ⚡ Energy process: {process_data['name']} → using energy_metadata reference")
        else:
            # For non-energy processes, use direct amount
            exchange["amount"] = process_data["amount"]
        
        # Add optional fields
        if process_data.get("location"):
            exchange["location"] = process_data["location"]
        
        # Prefer Brightway Match Code (md5 hash) over Inventory UID (ecoinvent UUID)
        bw_code = process_data.get("brightway_code")
        bw_db = process_data.get("brightway_database")
        fallback_code = process_data.get("code")
        fallback_db = process_data.get("database")
        
        code = bw_code or fallback_code
        db = bw_db or fallback_db
        
        if db and code:
            exchange["input"] = [db, code]
        
        # Use Brightway Match Location over CSV location if available
        if process_data.get("brightway_location"):
            exchange["location"] = process_data["brightway_location"]
        
        if process_data.get("process_match"):
            exchange["process_match"] = process_data["process_match"]
        
        return exchange
    
    def is_energy_process(self, process_name: str, unit: str = '') -> bool:
        """
        Check if process is a true energy-consumption item.

        Rules (in priority order):
        1. Unit is an energy unit (MJ, kWh, GJ, …) → always an energy process.
        2. Name matches a non-fuel keyword (electricity, heat, steam, …) AND unit is
           an energy unit → redundant but consistent.
        3. Name-only keyword matches (e.g. "propane" in kg) are NOT counted because
           that represents a material input, not an energy flow.
        """
        energy_units = {'mj', 'kwh', 'gj', 'wh', 'tj', 'megajoule', 'kilowatt hour', 'gigajoule'}
        unit_is_energy = unit.lower().strip() in energy_units

        # Primary signal: the exchange is quantified in energy units
        return unit_is_energy
    
    def determine_energy_value(self, energy_processes: List[Dict[str, Any]]) -> float:
        """Determine energy metadata value while preserving inventory base quantity."""
        if not energy_processes:
            return 100.0  # Default energy value if no energy processes found
        
        # Use the first detected energy process as the inventory baseline.
        first_energy = energy_processes[0]
        original_amount = first_energy.get("original_amount", first_energy.get("amount", 100.0))
        original_unit = first_energy.get("original_unit", first_energy.get("unit", "MJ"))

        print(
            "   ⚡ Energy metadata retained from inventory base: "
            f"{original_amount} {original_unit}"
        )
        return float(original_amount)
    
    def determine_energy_unit(self, energy_processes: List[Dict[str, Any]]) -> str:
        """Determine energy metadata unit while preserving inventory base unit."""
        if not energy_processes:
            return "MJ"

        first_energy = energy_processes[0]
        original_unit = first_energy.get("original_unit", first_energy.get("unit", "MJ"))
        return str(original_unit).strip() or "MJ"
    
    def normalize_json_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize JSON structure for consistency"""
        # Ensure required fields exist
        normalized = {
            "name": data.get("name", "Unknown Process"),
            "unit": data.get("unit", "unit"),
            "location": data.get("location", "GLO"),
            "categories": data.get("categories", ["technosphere"]),
            "type": data.get("type", "process"),
            "exchanges": data.get("exchanges", [])
        }
        
        # Preserve additional fields
        for key, value in data.items():
            if key not in normalized:
                normalized[key] = value
        
        return normalized
    
    def export_to_json(self, lci_data: Dict[str, Any], output_file: str) -> None:
        """Export LCI data to JSON file"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(lci_data, f, indent=2, ensure_ascii=False)
        
        print(f"   💾 Exported to: {output_path}")
    
    def validate_lci_data(self, lci_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate LCI data structure"""
        issues = []
        
        # Check required fields
        required_fields = ["name", "exchanges"]
        for field in required_fields:
            if field not in lci_data:
                issues.append(f"Missing required field: {field}")
        
        # Check exchanges
        exchanges = lci_data.get("exchanges", [])
        if not exchanges:
            issues.append("No exchanges found")
        
        # Check for production exchange
        has_production = any(ex.get("type") == "production" for ex in exchanges)
        if not has_production:
            issues.append("No production exchange found")
        
        # Count technosphere exchanges
        technosphere_count = sum(1 for ex in exchanges if ex.get("type") == "technosphere")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "statistics": {
                "total_exchanges": len(exchanges),
                "technosphere_exchanges": technosphere_count,
                "has_production": has_production,
                "lifecycle_stages": len(lci_data.get("life_cycle_stages", {}))
            }
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of LCI data management capabilities"""
        return {
            "supported_formats": ["csv", "json"],
            "energy_config": self.config.get_energy_config(),
            "lifecycle_stages": self.config.get_lifecycle_stages()
        }

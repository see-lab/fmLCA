#!/usr/bin/env python3
"""
Ecoinvent Database Setup Script for LCA-FMU

Downloads and imports ecoinvent databases into Brightway when they don't exist.
Reads credentials from config/secrets/passwords.json

Usage:
    python scripts/setup_ecoinvent.py --version 3.12 --system-model cutoff
    python scripts/setup_ecoinvent.py --version 3.10 --system-model apos
    python scripts/setup_ecoinvent.py --list-available
    python scripts/setup_ecoinvent.py --check

Options:
    --version         Ecoinvent version (e.g., 3.8, 3.9, 3.10, 3.11, 3.12)
    --system-model    System model: cutoff, apos, consequential
    --list-available  Show what's available to download
    --check           Check current databases and credentials
    --project         Brightway project name (default: auto-create)
"""

import sys
import json
import argparse
from pathlib import Path
import getpass
import textwrap


def configure_console_encoding() -> None:
    """Configure console streams to avoid UnicodeEncodeError on Windows."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        # Python 3.7+ text streams support reconfigure.
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                # Keep default stream configuration if reconfigure fails.
                pass


configure_console_encoding()

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import bw2data as bd
import bw2io as bi


class EcoinventSetup:
    """Handle ecoinvent database download and setup"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.secrets_file = self.project_root / "config" / "secrets" / "passwords.json"
        self.credentials = None
        
    def load_credentials(self):
        """Load ecoinvent credentials from secrets file"""
        if not self.secrets_file.exists():
            print(f"❌ Secrets file not found: {self.secrets_file}")
            print("   Creating template...")
            self.create_secrets_template()
            return False
        
        try:
            with open(self.secrets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            username = data.get('ecoinvent_username')
            password = data.get('ecoinvent_password')
            
            if not username or not password:
                print("❌ Missing credentials in secrets file")
                print(f"   Please add 'ecoinvent_username' and 'ecoinvent_password' to {self.secrets_file}")
                return False
            
            self.credentials = {
                'username': username,
                'password': password
            }
            
            print(f"✅ Loaded credentials for: {username}")
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in secrets file: {e}")
            return False
        except Exception as e:
            print(f"❌ Error loading credentials: {e}")
            return False
    
    def create_secrets_template(self):
        """Create a template secrets file"""
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        
        template = {
            "ecoinvent_username": "your_email@example.com",
            "ecoinvent_password": "your_password_here"
        }
        
        with open(self.secrets_file, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=4)
        
        print(f"📝 Created template: {self.secrets_file}")
        print("   Please edit this file with your ecoinvent credentials")
        print("   Get credentials from: https://ecoinvent.org/")
    
    def prompt_for_credentials(self):
        """Prompt user for credentials if not in file"""
        print("\n🔐 Ecoinvent Credentials Required")
        print("=" * 60)
        
        username = input("Ecoinvent username (email): ").strip()
        password = getpass.getpass("Ecoinvent password: ").strip()
        
        save = input("Save credentials to config/secrets/passwords.json? (y/n): ").strip().lower()
        
        if save == 'y':
            self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing data if file exists
            existing_data = {}
            if self.secrets_file.exists():
                try:
                    with open(self.secrets_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except:
                    pass
            
            # Update with ecoinvent credentials
            existing_data['ecoinvent_username'] = username
            existing_data['ecoinvent_password'] = password
            
            with open(self.secrets_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=4)
            
            print(f"✅ Credentials saved to {self.secrets_file}")
        
        self.credentials = {
            'username': username,
            'password': password
        }
        
        return True
    
    def check_existing_databases(self):
        """Check what ecoinvent databases already exist"""
        print("\n📊 Checking Existing Databases")
        print("=" * 60)
        
        current_project = bd.projects.current
        print(f"Current project: {current_project}")
        
        available_dbs = list(bd.databases)
        ecoinvent_dbs = [db for db in available_dbs if 'ecoinvent' in db.lower()]
        
        if ecoinvent_dbs:
            print(f"\n✅ Found {len(ecoinvent_dbs)} ecoinvent database(s):")
            for db_name in ecoinvent_dbs:
                db = bd.Database(db_name)
                print(f"   • {db_name} ({len(db)} activities)")
        else:
            print("⚠️  No ecoinvent databases found")
        
        return ecoinvent_dbs
    
    def list_available_versions(self):
        """List available ecoinvent versions for download"""
        print("\n📦 Available Ecoinvent Versions")
        print("=" * 60)
        print("""
Supported versions:
  • 3.8   - cutoff, apos, consequential
  • 3.9   - cutoff, apos, consequential  
  • 3.10  - cutoff, apos, consequential
  • 3.11  - cutoff, apos, consequential (recommended)
  • 3.12  - cutoff, apos, consequential (latest, recommended)

System models:
  • cutoff        - Cutoff by classification (most common)
  • apos          - Allocation at point of substitution
  • consequential - Consequential modeling

Recommended: ecoinvent 3.12 cutoff
        """)
    
    def download_and_import(self, version: str, system_model: str, project_name: str = None):
        """Download and import ecoinvent database"""
        
        # Validate inputs
        valid_versions = ['3.8', '3.9', '3.10', '3.11', '3.12']
        valid_models = ['cutoff', 'apos', 'consequential']
        
        if version not in valid_versions:
            print(f"❌ Invalid version: {version}")
            print(f"   Valid versions: {', '.join(valid_versions)}")
            return False
        
        if system_model not in valid_models:
            print(f"❌ Invalid system model: {system_model}")
            print(f"   Valid models: {', '.join(valid_models)}")
            return False
        
        # Load credentials
        if not self.credentials:
            if not self.load_credentials():
                if not self.prompt_for_credentials():
                    return False
        
        # Set up project
        if project_name is None:
            project_name = f"ecoinvent{version}"
        
        print(f"\n🚀 Setting up ecoinvent {version} ({system_model})")
        print("=" * 60)
        print(f"Project: {project_name}")
        
        # Create/switch to project
        bd.projects.set_current(project_name)
        print(f"✅ Using project: {project_name}")
        
        # Check if already exists
        db_name = f"ecoinvent-{version}-{system_model}"
        if db_name in bd.databases:
            print(f"⚠️  Database '{db_name}' already exists")
            overwrite = input("Overwrite? (y/n): ").strip().lower()
            if overwrite != 'y':
                print("❌ Aborted")
                return False
        
        try:
            # Import biosphere if needed
            if 'biosphere3' not in bd.databases:
                print("\n📦 Installing biosphere database...")
                bi.bw2setup()
                print("✅ Biosphere installed")
            
            # Download and import ecoinvent
            print(f"\n⬇️  Downloading ecoinvent {version} {system_model}...")
            print("   This may take several minutes...")
            
            # Use bw2io to import ecoinvent from web
            ei = bi.SingleOutputEcospold2Importer(
                f"ecoinvent {version} {system_model}",
                f"ecoinvent-{version}-{system_model}",
                use_mp=False  # Disable multiprocessing for stability
            )
            
            # Note: Actual download requires ecoinvent credentials
            # The user needs to manually download the database files
            print("\n⚠️  MANUAL DOWNLOAD REQUIRED")
            print("=" * 60)
            print("Brightway cannot automatically download ecoinvent databases.")
            print("\nPlease follow these steps:")
            print(f"1. Go to https://ecoinvent.org/")
            print(f"2. Log in with: {self.credentials['username']}")
            print(f"3. Download: ecoinvent {version} {system_model} (ecospold2)")
            print(f"4. Extract the .7z file")
            print(f"5. Import using:")
            print(f"\n   Python code:")
            print(f"   >>> import bw2io as bi")
            print(f"   >>> import bw2data as bd")
            print(f"   >>> bd.projects.set_current('{project_name}')")
            print(f"   >>> ei = bi.SingleOutputEcospold2Importer('/path/to/datasets', '{db_name}')")
            print(f"   >>> ei.apply_strategies()")
            print(f"   >>> ei.statistics()")
            print(f"   >>> ei.write_database()")
            print("\n" + "=" * 60)
            
            return False  # Not actually downloaded
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def provide_manual_import_guide(self, version: str, system_model: str):
        """Provide detailed manual import instructions"""
        project_name = f"ecoinvent{version}"
        db_name = f"ecoinvent-{version}-{system_model}"
        
        print("\n📚 MANUAL IMPORT GUIDE")
        print("=" * 60)
        
        guide = f"""
STEP 1: Add Ecoinvent Credentials
----------------------------------
Create or update:

config/secrets/passwords.json

With keys:

{{
  "ecoinvent_username": "your_email@example.com",
  "ecoinvent_password": "your_password"
}}

STEP 2: Import into Brightway (recommended)
--------------------------------------------
Run this Python code:

```python
import json
from pathlib import Path
import bw2io as bi
import bw2data as bd

# Set project
bd.projects.set_current('{project_name}')

# Load ecoinvent credentials
root = Path.cwd()
with open(root / 'config' / 'secrets' / 'passwords.json', 'r', encoding='utf-8') as f:
    secrets = json.load(f)

# IMPORTANT: Do not run bi.bw2setup() before this call.
# import_ecoinvent_release handles biosphere setup/migrations correctly.
bi.import_ecoinvent_release(
    version='{version}',
    system_model='{system_model}',
    username=secrets['ecoinvent_username'],
    password=secrets['ecoinvent_password'],
    lci=True,
    lcia=False,
    use_mp=False,
)

print("✅ Import complete!")
```

STEP 3: Verify Import
----------------------
```python
import bw2data as bd
bd.projects.set_current('{project_name}')
print(list(bd.databases))
# Should include: '{db_name}'
```

Save this script as: scripts/import_ecoinvent_{version}_{system_model}.py
        """
        
        print(guide)
        
        # Save to file
        script_file = self.project_root / "scripts" / f"import_ecoinvent_{version}_{system_model}.py"
        
        script_content = textwrap.dedent(f'''\
#!/usr/bin/env python3
"""
Import ecoinvent {version} {system_model} into Brightway

Auto-generated import script
"""

import json
from pathlib import Path

import bw2io as bi
import bw2data as bd

print("🚀 Importing ecoinvent {version} {system_model}")

# Set project
bd.projects.set_current('{project_name}')
print(f"✅ Using project: {project_name}")

# Load credentials from project config
project_root = Path(__file__).parent.parent
secrets_file = project_root / "config" / "secrets" / "passwords.json"

with open(secrets_file, 'r', encoding='utf-8') as f:
    secrets = json.load(f)

username = secrets.get('ecoinvent_username', '').strip()
password = secrets.get('ecoinvent_password', '').strip()
if not username or not password:
    raise ValueError(
        f"Missing credentials in {{secrets_file}}. "
        "Set ecoinvent_username and ecoinvent_password."
    )

print(f"✅ Loaded credentials for: {{username}}")
print("⬇️  Running import_ecoinvent_release (this can take a while)...")

# IMPORTANT: Do not run bi.bw2setup() before this call.
bi.import_ecoinvent_release(
    version='{version}',
    system_model='{system_model}',
    username=username,
    password=password,
    lci=True,
    lcia=False,
    use_mp=False,
)

if '{db_name}' in bd.databases:
    print("✅ Import complete!")
    print(f"   Database: {db_name}")
    print(f"   Activities: {{len(bd.Database('{db_name}'))}}")
else:
    print("⚠️  Import finished but database was not found. Check logs above.")
''')
        
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        script_file.chmod(0o755)  # Make executable
        
        print(f"\n💾 Import script saved to: {script_file}")
        print(f"   Run with: python {script_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Setup ecoinvent databases for LCA-FMU',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check current setup
  python scripts/setup_ecoinvent.py --check
  
  # List available versions
  python scripts/setup_ecoinvent.py --list-available
  
  # Get import guide for specific version
  python scripts/setup_ecoinvent.py --version 3.12 --system-model cutoff
  
  # Use custom project name
  python scripts/setup_ecoinvent.py --version 3.12 --system-model cutoff --project "my_lca_project"
        """
    )
    
    parser.add_argument('--version', type=str, help='Ecoinvent version (3.8, 3.9, 3.10, 3.11, 3.12)')
    parser.add_argument('--system-model', type=str, choices=['cutoff', 'apos', 'consequential'],
                       help='System model')
    parser.add_argument('--project', type=str, help='Brightway project name')
    parser.add_argument('--check', action='store_true', help='Check existing databases')
    parser.add_argument('--list-available', action='store_true', help='List available versions')
    
    args = parser.parse_args()
    
    setup = EcoinventSetup()
    
    print("🌍 Ecoinvent Database Setup for LCA-FMU")
    print("=" * 60)
    
    # Check mode
    if args.check:
        setup.load_credentials()
        setup.check_existing_databases()
        return
    
    # List mode
    if args.list_available:
        setup.list_available_versions()
        return
    
    # Setup mode
    if args.version and args.system_model:
        setup.provide_manual_import_guide(args.version, args.system_model)
    else:
        # Interactive mode
        print("\n📋 Interactive Setup")
        print("=" * 60)
        
        # Check existing
        setup.check_existing_databases()
        
        # Ask if user wants to add database
        add = input("\nSet up a new ecoinvent database? (y/n): ").strip().lower()
        if add != 'y':
            print("👋 Exiting")
            return
        
        # List options
        setup.list_available_versions()
        
        # Get user input
        version = input("\nEnter version (e.g., 3.12): ").strip()
        system_model = input("Enter system model (cutoff/apos/consequential): ").strip().lower()
        
        if version and system_model:
            setup.provide_manual_import_guide(version, system_model)
        else:
            print("❌ Invalid input")


if __name__ == "__main__":
    main()

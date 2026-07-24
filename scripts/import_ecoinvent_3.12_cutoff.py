#!/usr/bin/env python3
"""
Import ecoinvent 3.12 cutoff into Brightway

Auto-generated import script
"""

import json
from pathlib import Path

import bw2io as bi
import bw2data as bd

print("🚀 Importing ecoinvent 3.12 cutoff")

# Set project
bd.projects.set_current('ecoinvent3.12')
print(f"✅ Using project: ecoinvent3.12")

# Load credentials from project config
project_root = Path(__file__).parent.parent
secrets_file = project_root / "config" / "secrets" / "passwords.json"

with open(secrets_file, 'r', encoding='utf-8') as f:
    secrets = json.load(f)

username = secrets.get('ecoinvent_username', '').strip()
password = secrets.get('ecoinvent_password', '').strip()
if not username or not password:
    raise ValueError(
        f"Missing credentials in {secrets_file}. "
        "Set ecoinvent_username and ecoinvent_password."
    )

print(f"✅ Loaded credentials for: {username}")
print("⬇️  Running import_ecoinvent_release (this can take a while)...")

# IMPORTANT: Do not run bi.bw2setup() before this call.
bi.import_ecoinvent_release(
    version='3.12',
    system_model='cutoff',
    username=username,
    password=password,
    lci=True,
    lcia=False,
    use_mp=False,
)

if 'ecoinvent-3.12-cutoff' in bd.databases:
    print("✅ Import complete!")
    print(f"   Database: ecoinvent-3.12-cutoff")
    print(f"   Activities: {len(bd.Database('ecoinvent-3.12-cutoff'))}")
else:
    print("⚠️  Import finished but database was not found. Check logs above.")

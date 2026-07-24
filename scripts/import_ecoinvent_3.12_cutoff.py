#!/usr/bin/env python3
"""
Import ecoinvent 3.12 cutoff into Brightway

Auto-generated import script
"""

import bw2io as bi
import bw2data as bd

print("🚀 Importing ecoinvent 3.12 cutoff")

# Set project
bd.projects.set_current('ecoinvent3.12')
print(f"✅ Using project: ecoinvent3.12")

# Import biosphere if needed
if 'biosphere3' not in bd.databases:
    print("📦 Installing biosphere...")
    bi.bw2setup()

# Import ecoinvent
datasets_path = input("Path to ecoinvent datasets folder: ").strip()

print(f"⬇️  Importing from: {datasets_path}")
ei = bi.SingleOutputEcospold2Importer(datasets_path, 'ecoinvent-3.12-cutoff')

print("🔄 Applying strategies...")
ei.apply_strategies()

print("📊 Statistics:")
print(ei.statistics())

confirm = input("\nProceed with import? This takes 10-30 minutes (y/n): ").strip().lower()
if confirm == 'y':
    print("💾 Writing database... (this will take a while)")
    ei.write_database()
    print("✅ Import complete!")
    print(f"   Database: ecoinvent-3.12-cutoff")
    print(f"   Activities: {len(bd.Database('ecoinvent-3.12-cutoff'))}")
else:
    print("❌ Import cancelled")

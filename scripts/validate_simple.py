#!/usr/bin/env python3
"""
Simple Requirements Validation for LCA-FMU Production Platform

Quick validation of critical dependencies without complex imports.
"""

import sys
import subprocess
import importlib

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    print(f"🐍 Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3:
        print("❌ Requires Python 3.x")
        return False
    
    if version.minor < 8:
        print("❌ Requires Python 3.8 or higher")
        return False
        
    if version.minor >= 13:
        print("⚠️  Python 3.13+ may have compatibility issues with some packages")
    
    print("✅ Python version compatible")
    return True

def check_package(name):
    """Simple package existence check"""
    try:
        pkg = importlib.import_module(name)
        version = getattr(pkg, '__version__', 'unknown')
        print(f"✅ {name} - {version}")
        return True
    except ImportError:
        print(f"❌ {name} - Not installed")
        return False

def main():
    print("🔍 LCA-FMU Requirements Validation")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return False
    
    print("\n📦 Critical packages:")
    critical_packages = [
        'numpy', 'pandas', 'matplotlib',
        'brightway25', 'bw2data', 'bw2calc', 'bw2io',
        'pythonfmu', 'fmpy'
    ]
    
    missing_critical = []
    for pkg in critical_packages:
        if not check_package(pkg):
            missing_critical.append(pkg)
    
    print(f"\n📦 Optional packages:")
    optional_packages = ['lxml', 'pytest', 'jupyter', 'pydantic']
    
    missing_optional = []
    for pkg in optional_packages:
        if not check_package(pkg):
            missing_optional.append(pkg)
    
    # Summary
    print("\n📊 Summary:")
    print("─" * 20)
    
    if missing_critical:
        print(f"❌ Missing critical: {', '.join(missing_critical)}")
        print("💡 Install with: pip install -r requirements.txt")
        return False
    else:
        print("✅ All critical packages installed")
    
    if missing_optional:
        print(f"ℹ️  Missing optional: {', '.join(missing_optional)}")
    
    # Test basic imports
    print("\n🔬 Testing core functionality:")
    
    try:
        from bw2data import projects
        print("✅ Brightway2.5 imports successful")
    except Exception as e:
        print(f"❌ Brightway2.5 import failed: {e}")
        return False
    
    try:
        from pythonfmu import Fmi2Slave
        print("✅ PythonFMU imports successful")
    except Exception as e:
        print(f"❌ PythonFMU import failed: {e}")
        return False
    
    print("\n🚀 System validation successful!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

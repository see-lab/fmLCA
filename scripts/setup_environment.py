#!/usr/bin/env python3
"""
Environment Setup and Troubleshooting Script for LCA-FMU Platform
Helps diagnose and fix common installation issues, especially on macOS.

Usage:
    python scripts/setup_environment.py [--fix-numpy] [--install-all] [--conda]
"""

import sys
import subprocess
import platform
import os
import argparse
from pathlib import Path

def detect_environment():
    """Detect the current Python environment and platform"""
    info = {
        'platform': platform.system(),
        'arch': platform.machine(), 
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'python_path': sys.executable,
        'is_conda': 'conda' in sys.executable or 'CONDA_DEFAULT_ENV' in os.environ,
        'is_venv': hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix),
        'is_apple_silicon': platform.system() == 'Darwin' and platform.machine() == 'arm64'
    }
    
    return info

def print_environment_info():
    """Print detailed environment information"""
    info = detect_environment()
    
    print("🔍 Environment Detection")
    print("=" * 40)
    print(f"Platform: {info['platform']} ({info['arch']})")
    print(f"Python: {info['python_version']}")  
    print(f"Python Path: {info['python_path']}")
    print(f"Conda Environment: {'Yes' if info['is_conda'] else 'No'}")
    print(f"Virtual Environment: {'Yes' if info['is_venv'] else 'No'}")
    print(f"Apple Silicon Mac: {'Yes' if info['is_apple_silicon'] else 'No'}")
    
    return info

def fix_numpy_macos():
    """Fix NumPy BLAS issues on macOS"""
    print("\n🔧 Fixing NumPy BLAS issues on macOS...")
    
    info = detect_environment()
    
    if info['platform'] != 'Darwin':
        print("ℹ️  This fix is only for macOS systems")
        return False
    
    try:
        # Uninstall problematic NumPy
        print("Uninstalling current NumPy...")
        subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "numpy"])
        
        # Install compatible NumPy version
        if info['is_apple_silicon']:
            print("Installing NumPy optimized for Apple Silicon...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "numpy>=1.21.0,<1.25.0", "--no-cache-dir"
            ])
        else:
            print("Installing NumPy for Intel Mac...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "numpy>=1.21.0,<1.25.0"
            ])
        
        # Test NumPy import
        subprocess.check_call([sys.executable, "-c", "import numpy; print(f'NumPy {numpy.__version__} imported successfully')"])
        
        print("✅ NumPy fix completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ NumPy fix failed: {e}")
        return False

def install_brightway():
    """Install Brightway2.5 with proper dependencies"""
    print("\n📦 Installing Brightway2.5...")
    
    try:
        # Install core dependencies first
        print("Installing scientific computing stack...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "numpy>=1.21.0,<1.25.0",
            "scipy>=1.7.0,<1.12.0", 
            "pandas>=1.5.0,<2.1.0",
            "matplotlib>=3.5.0,<3.8.0"
        ])
        
        # Install Brightway components
        print("Installing Brightway2.5 components...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "brightway25>=1.1.1",
            "bw2data>=4.6.0",
            "bw2calc>=2.4.0",
            "bw2io>=0.9.14",
            "bw2analyzer>=0.11.8",
            "bw2parameters>=1.1.0",
            "bw_processing>=1.0.0",
            "bw-migrations>=0.2.0"
        ])
        
        print("✅ Brightway2.5 installation completed")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Brightway2.5 installation failed: {e}")
        return False

def install_fmu_tools():
    """Install FMU development tools"""
    print("\n🔧 Installing FMU tools...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "pythonfmu>=0.7.4",
            "fmpy>=0.4.1"
        ])
        
        print("✅ FMU tools installation completed")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ FMU tools installation failed: {e}")
        return False

def install_all_requirements():
    """Install all requirements from requirements.txt"""
    print("\n📦 Installing all requirements...")
    
    requirements_file = Path(__file__).parent.parent / "requirements.txt"
    
    if not requirements_file.exists():
        print(f"❌ Requirements file not found: {requirements_file}")
        return False
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ])
        
        print("✅ All requirements installed")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Requirements installation failed: {e}")
        return False

def setup_conda_environment():
    """Set up conda environment for LCA-FMU"""
    print("\n🐍 Setting up conda environment...")
    
    info = detect_environment()
    
    if not info['is_conda']:
        print("ℹ️  Not in a conda environment. Please activate conda first.")
        print("    conda create -n lca-fmu python=3.11")
        print("    conda activate lca-fmu")
        return False
    
    try:
        # Install conda-forge packages for better compatibility
        print("Installing conda-forge packages...")
        subprocess.check_call([
            "conda", "install", "-c", "conda-forge", "-y",
            "numpy<1.25",
            "scipy<1.12", 
            "pandas<2.1",
            "matplotlib<3.8",
            "openblas"  # Ensures proper BLAS libraries
        ])
        
        # Install pip packages
        print("Installing pip packages...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "brightway25>=1.1.1",
            "pythonfmu>=0.7.4",
            "fmpy>=0.4.1"
        ])
        
        print("✅ Conda environment setup completed")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Conda environment setup failed: {e}")
        return False

def validate_installation():
    """Validate that key packages are working"""
    print("\n✅ Validating installation...")
    
    tests = [
        ("NumPy", "import numpy; print(f'NumPy {numpy.__version__}')"),
        ("Pandas", "import pandas; print(f'Pandas {pandas.__version__}')"),
        ("Matplotlib", "import matplotlib; print(f'Matplotlib {matplotlib.__version__}')"),
        ("Brightway25", "import brightway25; print('Brightway2.5 OK')"),
        ("BW2Data", "from bw2data import projects; print('BW2Data OK')"),
        ("PythonFMU", "import pythonfmu; print(f'PythonFMU {pythonfmu.__version__}')"),
        ("FMPy", "import fmpy; print('FMPy OK')"),
    ]
    
    success_count = 0
    
    for name, test_code in tests:
        try:
            result = subprocess.check_output([
                sys.executable, "-c", test_code
            ], stderr=subprocess.STDOUT, text=True)
            print(f"✅ {name}: {result.strip()}")
            success_count += 1
        except subprocess.CalledProcessError as e:
            print(f"❌ {name}: Failed")
    
    print(f"\n📊 Validation Results: {success_count}/{len(tests)} packages working")
    return success_count == len(tests)

def main():
    parser = argparse.ArgumentParser(description="Setup LCA-FMU environment")
    parser.add_argument("--fix-numpy", action="store_true", help="Fix NumPy BLAS issues")
    parser.add_argument("--install-all", action="store_true", help="Install all requirements")
    parser.add_argument("--conda", action="store_true", help="Setup conda environment")
    parser.add_argument("--validate", action="store_true", help="Only validate installation")
    
    args = parser.parse_args()
    
    print("🚀 LCA-FMU Environment Setup")
    print("=" * 50)
    
    # Print environment info
    info = print_environment_info()
    
    # Handle specific actions
    if args.validate:
        validate_installation()
        return
    
    if args.fix_numpy:
        fix_numpy_macos()
        return
    
    if args.conda:
        setup_conda_environment()
        validate_installation()
        return
    
    if args.install_all:
        install_all_requirements()
        validate_installation()
        return
    
    # Interactive setup
    print("\n🛠️  Recommended Setup Steps:")
    print("=" * 30)
    
    if info['is_apple_silicon']:
        print("1. 🍎 Apple Silicon Mac detected")
        print("   Recommendation: Use conda for best compatibility")
        print("   conda create -n lca-fmu python=3.11")
        print("   conda activate lca-fmu")
        print("   python scripts/setup_environment.py --conda")
        
    elif info['platform'] == 'Darwin':
        print("1. 🍎 Intel Mac detected") 
        print("   Fix NumPy issues first:")
        print("   python scripts/setup_environment.py --fix-numpy")
        
    else:
        print("1. 🐧 Linux/Windows detected")
        print("   Standard installation should work:")
        print("   python scripts/setup_environment.py --install-all")
    
    print(f"\n2. Current environment: {'Conda' if info['is_conda'] else 'venv' if info['is_venv'] else 'system'}")
    print(f"3. Python version: {info['python_version']} ({'✅ Compatible' if 3.9 <= float(info['python_version'][:3]) <= 3.12 else '⚠️ May have issues'})")
    
    print("\n💡 Quick commands:")
    print("  --fix-numpy     Fix NumPy BLAS issues (macOS)")
    print("  --conda         Setup conda environment") 
    print("  --install-all   Install all requirements")
    print("  --validate      Test current installation")

if __name__ == "__main__":
    main()

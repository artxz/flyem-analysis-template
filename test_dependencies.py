#!/usr/bin/env python
"""
Test each dependency individually to identify which ones are installed
and which ones cause problems.
"""

import sys
import importlib

# List of dependencies to test: {import_name: package_name}
dependencies = {
    # Core scientific
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "matplotlib": "matplotlib",
    "sklearn": "scikit-learn",

    # Network & visualization
    "networkx": "networkx",
    "plotly": "plotly",

    # Data
    "h5py": "h5py",
    "tqdm": "tqdm",

    # Jupyter
    "jupyter": "jupyter",
    "ipykernel": "ipykernel",
    "jupytext": "jupytext",

    # Environment
    "dotenv": "python-dotenv",
}

print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}\n")
print("=" * 60)

results = {"success": [], "failed": []}

for module_name, package_name in dependencies.items():
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "unknown")
        print(f"  {package_name:25s} (version: {version})")
        results["success"].append(package_name)
    except ImportError:
        print(f"  {package_name:25s} - NOT INSTALLED")
        results["failed"].append(package_name)
    except Exception as e:
        print(f"  {package_name:25s} - ERROR: {e}")
        results["failed"].append(package_name)

print("=" * 60)
print(f"\nSummary:")
print(f"  Installed: {len(results['success'])}/{len(dependencies)}")
print(f"  Missing:   {len(results['failed'])}/{len(dependencies)}")

if results["failed"]:
    print(f"\nMissing packages: {', '.join(results['failed'])}")

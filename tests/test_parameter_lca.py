#!/usr/bin/env python3
"""
Test LCA parameter scaling with a single parameterized LCI file: data/inventory/example.json

This test validates that LCA impacts scale proportionally with the parameter n_pv
by running the same inventory with different parameter values and comparing results.

Test cases:
1. Run LCA with n_pv = 1 (baseline)
2. Run LCA with n_pv = 5 (should be ~5x impacts)
3. Run LCA with n_pv = 10 (should be ~10x impacts)

Expected behavior:
- All impact categories should scale linearly with n_pv
- Relative error should be < 1% (accounting for numerical precision)
"""

# Import dependencies
import json
import sys
import copy
from pathlib import Path



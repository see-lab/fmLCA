#!/usr/bin/env python3
"""Run LCA with an inventory parameter and verify linear scaling."""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fmlca.lca_engine import run_lca

LCI_FILE = project_root / "data" / "inventory" / "example.json"
METHODS = ["IPCC 2021 climate change total excl biogenic GWP100"]
CASES = [
    {"n_units": 1.0},
    {"n_units": 10.0},
]
REL_TOL = 1e-6  # relative tolerance for linear scaling check

def _score(result):
	impact_results = result.get("impact_results", {})
	first = next(iter(impact_results.values()), {})
	return float(first.get("total_score", 0.0))


def main() -> int:
	runs = []
	for params in CASES:
		result = run_lca(str(LCI_FILE), METHODS, parameter_values=params, functional_unit={}, energy_amount_mj=180.0)
		if "error" in result:
			print(f"FAIL: run_lca error for {params}: {result['error']}")
			return 1
		runs.append((params["n_units"], _score(result), result))

	baseline_units, baseline_score, _ = runs[0]
	print("\nParameter scaling report")
	print("units\tscore\texpected_ratio\tactual_ratio\trel_error")
	print(f"{baseline_units:g}\t{baseline_score:.6e}\t1.000000\t1.000000\t0.000000")

	for units, score, _ in runs[1:]:
		expected = units / baseline_units
		actual = score / baseline_score if baseline_score else 0.0
		rel_error = abs(actual - expected) / expected if expected else 0.0
		print(f"{units:g}\t{score:.6e}\t{expected:.6f}\t{actual:.6f}\t{rel_error:.6f}")
		if rel_error > REL_TOL:
			print(f"FAIL: linear scaling check exceeded tolerance ({REL_TOL:.2%})")
			return 1

	print("PASS: linear scaling verified")
	return 0


@pytest.mark.ecoinvent
def test_parameter_linear_scaling():
	assert main() == 0


if __name__ == "__main__":
	raise SystemExit(main())



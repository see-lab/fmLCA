#!/usr/bin/env python3
"""Backward-compatible CLI entry point for ecoinvent setup.

This wrapper preserves the historical `lca-fmu-setup-ecoinvent` command while
reusing the maintained Brightway setup implementation.
"""

from __future__ import annotations

from scripts.setup_brightway import main


if __name__ == "__main__":
    raise SystemExit(main())

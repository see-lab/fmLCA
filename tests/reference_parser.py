"""Helpers to read regression reference files in plain-text format."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def parse_reference_file(path: Path) -> dict[str, Any]:
    """Parse a key=value text file with scalar or list values.

    Supported forms:
    - key=value
    - key=[1.0, 2.0, 3.0]
    - key={"json": "object"}
    """
    if not path.exists():
        raise FileNotFoundError(f"Reference file not found: {path}")

    parsed: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid reference line (missing '='): {raw_line}")

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Keep a Modelica-like metadata line readable as plain string.
        if key == "last-generated":
            parsed[key] = value
            continue

        # Try Python literal parsing first for arrays and dict-like values.
        try:
            parsed[key] = ast.literal_eval(value)
            continue
        except Exception:
            pass

        # Try float fallback.
        try:
            parsed[key] = float(value)
            continue
        except ValueError:
            parsed[key] = value

    return parsed
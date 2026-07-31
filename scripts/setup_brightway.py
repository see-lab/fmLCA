#!/usr/bin/env python3
"""
Set up a Brightway project with ecoinvent data and LCIA methods.

This script creates or switches to a Brightway project and imports an
ecoinvent release using Brightway's standard import workflow.

Usage:
    python scripts/setup_brightway.py --name LCA-FMU --ecoinvent 3.12

Notes:
    - Credentials are read from config/secrets/passwords.json
    - Uses bw2io.import_ecoinvent_release (recommended Brightway workflow)
    - Imports LCIA methods by default to avoid missing-method errors
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import bw2data as bd
import bw2io as bi


VALID_VERSIONS = ("3.8", "3.9", "3.10", "3.11", "3.12")
VALID_SYSTEM_MODELS = ("cutoff", "apos", "consequential")


def configure_console_encoding() -> None:
    """Configure UTF-8 streams when available (helps on Windows terminals)."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def load_ecoinvent_credentials(project_root: Path) -> Tuple[str, str]:
    """Load ecoinvent credentials from config/secrets/passwords.json."""
    secrets_file = project_root / "config" / "secrets" / "passwords.json"
    if not secrets_file.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {secrets_file}. "
            "Create it with keys 'ecoinvent_username' and 'ecoinvent_password'."
        )

    with open(secrets_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    username = str(data.get("ecoinvent_username", "")).strip()
    password = str(data.get("ecoinvent_password", "")).strip()
    if not username or not password:
        raise ValueError(
            f"Missing credentials in {secrets_file}. "
            "Set both 'ecoinvent_username' and 'ecoinvent_password'."
        )

    return username, password


def summarize_project() -> Dict[str, object]:
    """Return a compact summary of current Brightway project state."""
    db_names = sorted(list(bd.databases))
    methods = sorted(list(bd.methods))

    family_counts: Dict[str, int] = {}
    for method in methods:
        family = str(method[0]) if method else "unknown"
        family_counts[family] = family_counts.get(family, 0) + 1

    top_families = sorted(family_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "project": bd.projects.current,
        "database_count": len(db_names),
        "databases": db_names,
        "method_count": len(methods),
        "top_families": top_families,
    }


def print_summary(summary: Dict[str, object]) -> None:
    """Print a human-readable project summary."""
    print("\nBrightway project summary")
    print("=" * 80)
    print(f"Project: {summary['project']}")
    print(f"Databases: {summary['database_count']}")
    for db_name in summary["databases"]:
        print(f"  - {db_name}")

    print(f"Methods: {summary['method_count']}")
    print("Top method families:")
    if summary["top_families"]:
        for family, count in summary["top_families"]:
            print(f"  - {family}: {count}")
    else:
        print("  - none")


def setup_brightway_project(
    project_name: str,
    version: str,
    system_model: str,
    username: str,
    password: str,
    include_lci: bool,
    include_lcia: bool,
    use_mp: bool,
) -> None:
    """Create/switch project and run Brightway standard ecoinvent import."""
    if not include_lci and not include_lcia:
        raise ValueError("At least one of include_lci/include_lcia must be True.")

    target_db = f"ecoinvent-{version}-{system_model}"

    bd.projects.set_current(project_name)
    print(f"Using Brightway project: {project_name}")

    has_db = target_db in bd.databases
    method_count_before = len(list(bd.methods))

    print("\nPre-import state")
    print("-" * 80)
    print(f"Target database '{target_db}' present: {has_db}")
    print(f"Existing methods: {method_count_before}")

    effective_lci = include_lci and not has_db
    if include_lci and has_db:
        print("Skipping LCI import because target database already exists.")

    # Brightway standard importer handles migrations and setup internally.
    bi.import_ecoinvent_release(
        version=version,
        system_model=system_model,
        username=username,
        password=password,
        lci=effective_lci,
        lcia=include_lcia,
        use_mp=use_mp,
    )

    method_count_after = len(list(bd.methods))
    print("\nImport complete")
    print("-" * 80)
    print(f"LCI imported: {effective_lci}")
    print(f"LCIA imported: {include_lcia}")
    print(f"Methods before: {method_count_before}")
    print(f"Methods after:  {method_count_after}")


def build_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Set up a Brightway project with ecoinvent and LCIA methods.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Brightway project name to create/use.",
    )
    parser.add_argument(
        "--ecoinvent",
        required=True,
        choices=VALID_VERSIONS,
        help="Ecoinvent release version.",
    )
    parser.add_argument(
        "--system-model",
        default="cutoff",
        choices=VALID_SYSTEM_MODELS,
        help="Ecoinvent system model.",
    )
    parser.add_argument(
        "--lci-only",
        action="store_true",
        help="Import only LCI database data (skip LCIA methods).",
    )
    parser.add_argument(
        "--lcia-only",
        action="store_true",
        help="Import only LCIA methods (skip LCI import).",
    )
    parser.add_argument(
        "--use-mp",
        action="store_true",
        help="Enable multiprocessing in import_ecoinvent_release.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only print project summary after switching/creating project.",
    )
    return parser


def main() -> int:
    configure_console_encoding()

    parser = build_parser()
    args = parser.parse_args()

    if args.lci_only and args.lcia_only:
        parser.error("--lci-only and --lcia-only are mutually exclusive")

    include_lci = not args.lcia_only
    include_lcia = not args.lci_only

    project_root = Path(__file__).resolve().parent.parent

    print("Brightway setup")
    print("=" * 80)
    print(f"Project: {args.name}")
    print(f"Ecoinvent: {args.ecoinvent} ({args.system_model})")
    print(f"Import LCI: {include_lci}")
    print(f"Import LCIA methods: {include_lcia}")

    try:
        bd.projects.set_current(args.name)

        if args.check:
            print_summary(summarize_project())
            return 0

        try:
            username, password = load_ecoinvent_credentials(project_root)
        except Exception as exc:
            print(f"Error loading credentials: {exc}")
            return 1

        setup_brightway_project(
            project_name=args.name,
            version=args.ecoinvent,
            system_model=args.system_model,
            username=username,
            password=password,
            include_lci=include_lci,
            include_lcia=include_lcia,
            use_mp=args.use_mp,
        )
        print_summary(summarize_project())
        return 0
    except Exception as exc:
        print(f"Setup failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
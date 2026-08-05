#!/usr/bin/env python3
"""Populate Brightway Match Code with real ecoinvent activity codes for an inventory CSV.

This script resolves each unique inventory item to an activity in the selected
ecoinvent database and writes the resolved activity code into the
"Brightway Match Code" column.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bw2data import Database, projects

try:
    from src.config_manager import get_config
except ImportError:
    from config_manager import get_config


BAD_KEYWORDS = {
    "waste",
    "treatment",
    "disposal",
    "landfill",
    "incineration",
    "sludge",
    "residue",
    "residues",
    "used",
    "scrap",
    "demolition",
    "deconstruction",
}


def _tokenize(text):
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2]


def score_candidate(activity, item_name, material_group, tally_group):
    name = (activity.get("name") or "").lower()
    ref_product = (activity.get("reference product") or "").lower()
    full_text = f"{name} {ref_product}"

    score = 0

    item_tokens = _tokenize(item_name)
    group_tokens = _tokenize(material_group) + _tokenize(tally_group)

    phrase = item_name.lower().strip()
    if phrase and phrase in full_text:
        score += 40

    matched_item_tokens = 0
    for tok in item_tokens:
        if tok in full_text:
            score += 5
            matched_item_tokens += 1

    if item_tokens and matched_item_tokens == len(item_tokens):
        score += 15

    for tok in group_tokens:
        if tok in full_text:
            score += 2

    if name.startswith("market for "):
        score += 3
    if "production" in name:
        score += 3

    if "steel" in phrase and "steel" in full_text:
        score += 8
    if "aluminum" in phrase and "aluminium" in full_text:
        score += 8
    if "gypsum" in phrase and "gypsum" in full_text:
        score += 8
    if "glass" in phrase and "glass" in full_text:
        score += 6
    if "concrete" in phrase and "concrete" in full_text:
        score += 8
    if "wood" in phrase and "wood" in full_text:
        score += 8
    if "insulation" in phrase and "insulation" in full_text:
        score += 6

    if any(k in full_text for k in BAD_KEYWORDS):
        score -= 30

    location = (activity.get("location") or "")
    if location in {"US", "RoW", "RER", "GLO", "CH", "CA-QC"}:
        score += 2

    return score


def resolve_code(db, item_name, material_group, tally_group, location):
    queries = [item_name]
    if material_group and material_group.lower() not in item_name.lower():
        queries.append(f"{item_name} {material_group}")
    if tally_group and tally_group.lower() not in item_name.lower():
        queries.append(f"{item_name} {tally_group}")

    # Fallback-only queries for coarse categories.
    for fallback in (material_group, tally_group):
        if fallback:
            queries.append(fallback)

    item_tokens = _tokenize(item_name)
    if item_tokens:
        queries.extend(item_tokens[:3])

    candidates = {}
    for query in queries:
        try:
            for activity in db.search(query, limit=80):
                code = activity.get("code")
                if code:
                    candidates[code] = activity
        except Exception:
            continue

    best = None
    best_score = -10**9

    for activity in candidates.values():
        s = score_candidate(activity, item_name, material_group, tally_group)
        if s > best_score:
            best = activity
            best_score = s

    if not best:
        return None, None, None

    return best.get("code"), best.get("name"), best.get("location")


def ensure_project(config):
    target = config.system_config.get("system", {}).get("default_project", "LCA-FMU")
    all_projects = [str(p).replace("Project: ", "") for p in projects]
    if target in all_projects:
        projects.set_current(target)


def populate_codes(csv_path):
    config = get_config()
    ensure_project(config)

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    if "Brightway Match Code" not in fieldnames:
        try:
            insert_idx = fieldnames.index("UUID") + 1
            fieldnames.insert(insert_idx, "Brightway Match Code")
        except ValueError:
            fieldnames.append("Brightway Match Code")

    unique_key_to_code = {}
    unresolved_keys = []

    for row in rows:
        db_name = (row.get("Database") or "").strip() or "ecoinvent-3.12-cutoff"
        item_name = (row.get("Brightway Match Name") or row.get("Item") or "").strip()
        material_group = (row.get("Material Group") or "").strip()
        tally_group = (row.get("Tally Material Group") or "").strip()
        location = (row.get("Location") or "").strip()

        key = (db_name, item_name, material_group, tally_group)
        if key in unique_key_to_code:
            continue

        if not item_name:
            unique_key_to_code[key] = ""
            continue

        db = Database(db_name)
        code, match_name, match_loc = resolve_code(db, item_name, material_group, tally_group, location)
        if code:
            unique_key_to_code[key] = code
        else:
            unique_key_to_code[key] = ""
            unresolved_keys.append(key)

    filled_rows = 0
    for row in rows:
        db_name = (row.get("Database") or "").strip() or "ecoinvent-3.12-cutoff"
        item_name = (row.get("Brightway Match Name") or row.get("Item") or "").strip()
        material_group = (row.get("Material Group") or "").strip()
        tally_group = (row.get("Tally Material Group") or "").strip()

        code = unique_key_to_code.get((db_name, item_name, material_group, tally_group), "")
        row["Brightway Match Code"] = code
        if code:
            filled_rows += 1

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"rows={len(rows)}")
    print(f"rows_with_code={filled_rows}")
    print(f"unresolved_unique_keys={len(unresolved_keys)}")
    if unresolved_keys:
        for key in unresolved_keys:
            print(f"unresolved_item={key[1]}|material_group={key[2]}|tally={key[3]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate Brightway Match Code from ecoinvent search")
    parser.add_argument("csv_path", nargs="?", default="data/inventory/building59.csv")
    args = parser.parse_args()

    populate_codes(Path(args.csv_path))

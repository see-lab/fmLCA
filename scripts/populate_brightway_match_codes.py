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


def _candidate_queries(item_name, material_group, tally_group):
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

    # Preserve order while removing duplicates.
    seen = set()
    unique = []
    for q in queries:
        qn = q.strip()
        if qn and qn not in seen:
            seen.add(qn)
            unique.append(qn)
    return unique


def find_ranked_candidates(db, item_name, material_group, tally_group, limit=3):
    """Return ranked candidate activity tuples: (score, activity, query_hits)."""
    candidates = {}
    query_hits = {}

    for query in _candidate_queries(item_name, material_group, tally_group):
        try:
            for activity in db.search(query, limit=80):
                code = activity.get("code")
                if not code:
                    continue
                candidates[code] = activity
                query_hits.setdefault(code, set()).add(query)
        except Exception:
            continue

    ranked = []
    for code, activity in candidates.items():
        score = score_candidate(activity, item_name, material_group, tally_group)
        ranked.append((score, activity, sorted(query_hits.get(code, set()))))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[:limit]


def resolve_code(db, item_name, material_group, tally_group, location):
    ranked = find_ranked_candidates(db, item_name, material_group, tally_group, limit=1)
    best = ranked[0][1] if ranked else None

    if not best:
        return None, None, None

    return best.get("code"), best.get("name"), best.get("location")


def ensure_project(config):
    target = config.system_config.get("system", {}).get("default_project", "LCA-FMU")
    all_projects = [str(p).replace("Project: ", "") for p in projects]
    if target in all_projects:
        projects.set_current(target)


def resolve_csv_input(csv_arg):
    """Resolve CSV argument as path or inventory stem."""
    candidate = Path(csv_arg)
    if candidate.exists():
        return candidate

    stem = csv_arg[:-4] if csv_arg.lower().endswith(".csv") else csv_arg
    inventory_path = PROJECT_ROOT / "data" / "inventory" / f"{stem}.csv"
    if inventory_path.exists():
        return inventory_path

    raise FileNotFoundError(
        f"CSV not found: {csv_arg}. Tried '{candidate}' and '{inventory_path}'."
    )


def default_populated_output_path(csv_path):
    return PROJECT_ROOT / "data" / "inventory" / f"{csv_path.stem}-populated.csv"


def default_review_output_path(csv_path):
    return PROJECT_ROOT / "results" / f"{csv_path.stem}_match_review.csv"


def populate_codes(csv_path, output_csv_path):
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

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"input_csv={csv_path}")
    print(f"output_csv={output_csv_path}")
    print(f"rows={len(rows)}")
    print(f"rows_with_code={filled_rows}")
    print(f"unresolved_unique_keys={len(unresolved_keys)}")
    if unresolved_keys:
        for key in unresolved_keys:
            print(f"unresolved_item={key[1]}|material_group={key[2]}|tally={key[3]}")


def export_review_report(csv_path, output_path, top_n=3):
    """Export top-N ranked candidates per unique inventory item for manual QA."""
    config = get_config()
    ensure_project(config)

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    unique_items = {}
    for row in rows:
        db_name = (row.get("Database") or "").strip() or "ecoinvent-3.12-cutoff"
        item_name = (row.get("Brightway Match Name") or row.get("Item") or "").strip()
        material_group = (row.get("Material Group") or "").strip()
        tally_group = (row.get("Tally Material Group") or "").strip()
        location = (row.get("Location") or "").strip()
        stage = (row.get("Life Cycle Stage") or row.get("Stage") or "").strip()

        key = (db_name, item_name, material_group, tally_group)
        if key not in unique_items:
            unique_items[key] = {
                "db_name": db_name,
                "item_name": item_name,
                "material_group": material_group,
                "tally_group": tally_group,
                "location": location,
                "example_stage": stage,
            }

    report_rows = []
    for _, info in sorted(unique_items.items(), key=lambda kv: kv[1]["item_name"].lower()):
        item_name = info["item_name"]
        if not item_name:
            continue

        db = Database(info["db_name"])
        ranked = find_ranked_candidates(
            db,
            item_name,
            info["material_group"],
            info["tally_group"],
            limit=top_n,
        )

        if not ranked:
            report_rows.append({
                "Database": info["db_name"],
                "Item": item_name,
                "Material Group": info["material_group"],
                "Tally Material Group": info["tally_group"],
                "Location": info["location"],
                "Example Stage": info["example_stage"],
                "Rank": 1,
                "Score": "",
                "Candidate Code": "",
                "Candidate Name": "",
                "Candidate Location": "",
                "Candidate Reference Product": "",
                "Matched Queries": "",
            })
            continue

        for rank, (score, activity, query_hits) in enumerate(ranked, start=1):
            report_rows.append({
                "Database": info["db_name"],
                "Item": item_name,
                "Material Group": info["material_group"],
                "Tally Material Group": info["tally_group"],
                "Location": info["location"],
                "Example Stage": info["example_stage"],
                "Rank": rank,
                "Score": score,
                "Candidate Code": activity.get("code", ""),
                "Candidate Name": activity.get("name", ""),
                "Candidate Location": activity.get("location", ""),
                "Candidate Reference Product": activity.get("reference product", ""),
                "Matched Queries": " | ".join(query_hits),
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Database",
        "Item",
        "Material Group",
        "Tally Material Group",
        "Location",
        "Example Stage",
        "Rank",
        "Score",
        "Candidate Code",
        "Candidate Name",
        "Candidate Location",
        "Candidate Reference Product",
        "Matched Queries",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    unique_count = len(unique_items)
    unresolved_count = sum(1 for r in report_rows if r["Rank"] == 1 and not r["Candidate Code"])
    print(f"review_report={output_path}")
    print(f"unique_items={unique_count}")
    print(f"report_rows={len(report_rows)}")
    print(f"unresolved_items={unresolved_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Populate Brightway Match Code from ecoinvent search",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="example",
        help="Input CSV path or inventory stem",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Output path for populated CSV",
    )
    parser.add_argument("--review-report", action="store_true",
                        help="Export a review CSV with top candidate activities per unique item")
    parser.add_argument("--report-path", default=None,
                        help="Output path for review report CSV")
    parser.add_argument("--top-n", type=int, default=3,
                        help="Top N candidates to include per item in review report")
    args = parser.parse_args()

    csv_path = resolve_csv_input(args.csv_path)
    output_csv_path = Path(args.output_csv) if args.output_csv else default_populated_output_path(csv_path)
    report_path = Path(args.report_path) if args.report_path else default_review_output_path(csv_path)

    if args.review_report:
        export_review_report(csv_path, report_path, top_n=max(1, args.top_n))
    else:
        populate_codes(csv_path, output_csv_path)

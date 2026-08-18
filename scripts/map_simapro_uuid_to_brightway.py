#!/usr/bin/env python3
"""
Map SimaPro UUID-based inventory rows to Brightway activities and populate
Brightway match columns in inventory CSV files.

Matching strategy intentionally stays close to explicit SimaPro names:
- Primary query: Inventory Selection activity name (middle token in SimaPro pipe format)
- Minimal fallback query: process name without location braces

Metadata lines starting with '#' are preserved when reading/writing CSV.
"""

import argparse
import csv
import io
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bw2data as bd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config_manager import get_config


def resolve_csv_input(csv_arg: str) -> Path:
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


def default_output_path(csv_path: Path) -> Path:
    return PROJECT_ROOT / "data" / "inventory" / f"{csv_path.stem}-populated.csv"


def is_metadata_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") or s.startswith('"#') or s.startswith("'#")


def read_inventory_csv(path: Path) -> Tuple[List[str], List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        raw_lines = f.readlines()

    metadata_lines = [line for line in raw_lines if is_metadata_line(line)]
    data_lines = [line for line in raw_lines if line.strip() and not is_metadata_line(line)]

    if not data_lines:
        raise ValueError(f"No CSV data rows found in: {path}")

    sample = "".join(data_lines[:20])
    delimiter = "," if "," in sample else "\t" if "\t" in sample else ";"

    reader = csv.DictReader(io.StringIO("".join(data_lines)), delimiter=delimiter)
    rows = [row for row in reader]
    if not reader.fieldnames:
        raise ValueError(f"CSV header not found in: {path}")

    return metadata_lines, list(reader.fieldnames), rows


def write_inventory_csv(path: Path, metadata_lines: List[str], fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        for line in metadata_lines:
            f.write(line if line.endswith("\n") else line + "\n")

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ensure_project_for_db(target_db: str) -> None:
    config = get_config()
    target_project = config.system_config.get("system", {}).get("default_project", "LCA-FMU")

    all_projects = [str(p).replace("Project: ", "") for p in bd.projects]
    if target_project in all_projects:
        bd.projects.set_current(target_project)

    if target_db in bd.databases:
        return

    for project in all_projects:
        try:
            bd.projects.set_current(project)
            if target_db in bd.databases:
                return
        except Exception:
            continue

    raise RuntimeError(
        f"Database '{target_db}' not found in available Brightway projects: {all_projects}"
    )


def parse_simapro_inventory_selection(text: str) -> Dict[str, str]:
    raw = (text or "").strip()
    parts = [p.strip() for p in raw.split("|")]

    process_with_loc = parts[0] if len(parts) > 0 else raw
    activity_name = parts[1] if len(parts) > 1 else process_with_loc

    loc_match = re.search(r"\{([^}]+)\}", process_with_loc)
    location_hint = loc_match.group(1).strip() if loc_match else ""

    process_name = re.sub(r"\{[^}]+\}", "", process_with_loc).strip()
    process_name = re.sub(r"\s+", " ", process_name)

    return {
        "raw": raw,
        "activity_name": activity_name,
        "process_name": process_name,
        "location_hint": location_hint,
    }


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def significant_tokens(s: str) -> List[str]:
    generic = {
        "production", "market", "treatment", "process", "for", "of", "and", "the",
        "cut", "off", "unit",
    }
    out = []
    for tok in normalize(s).split():
        if tok in generic:
            continue
        if tok.isdigit():
            continue
        if len(tok) < 3:
            continue
        out.append(tok)
    return out


def build_queries(parsed: Dict[str, str]) -> List[str]:
    activity_name = (parsed.get("activity_name") or "").strip()
    process_name = (parsed.get("process_name") or "").strip()
    compact_activity = re.sub(r"[,;:]+", " ", activity_name)
    compact_process = re.sub(r"[,;:]+", " ", process_name)
    token_query = " ".join(significant_tokens(activity_name or process_name)[:7])
    joined_token_query = " ".join(significant_tokens(f"{process_name} {activity_name}")[:10])

    queries = [
        activity_name,
        process_name,
        compact_activity,
        compact_process,
        token_query,
        joined_token_query,
        normalize(activity_name),
    ]
    seen = set()
    unique = []
    for q in queries:
        qq = q.strip()
        if qq and qq not in seen:
            seen.add(qq)
            unique.append(qq)
    return unique


def score_candidate(activity: Dict, parsed: Dict[str, str]) -> int:
    score = 0
    cand_name = normalize(activity.get("name", ""))
    target_name = normalize(parsed["activity_name"])
    process_name = normalize(parsed["process_name"])
    cand_loc = (activity.get("location") or "").strip()
    target_loc = parsed["location_hint"].strip()

    if cand_name == target_name:
        score += 100
    elif target_name and target_name in cand_name:
        score += 70
    elif cand_name and cand_name in target_name:
        score += 50

    if target_name and cand_name:
        score += int(80 * SequenceMatcher(None, target_name, cand_name).ratio())

    if process_name and process_name in cand_name:
        score += 25

    target_tokens = set(significant_tokens(parsed["activity_name"]))
    cand_tokens = set(significant_tokens(activity.get("name", "")))
    if target_tokens and cand_tokens:
        overlap = len(target_tokens & cand_tokens)
        score += 10 * overlap
        if overlap == len(target_tokens):
            score += 25

    # Penalize semantic drift when target intent is explicit.
    if " production " in f" {target_name} " and " production " not in f" {cand_name} ":
        score -= 25
    if " treatment " in f" {cand_name} " and " treatment " not in f" {target_name} ":
        score -= 20
    if " market for " in f" {cand_name} " and " market for " not in f" {target_name} ":
        score -= 10

    if target_loc:
        if cand_loc == target_loc:
            score += 25
        elif target_loc == "RoW" and cand_loc == "GLO":
            score += 10

    return score


def is_acceptable_match(activity: Dict, parsed: Dict[str, str], min_similarity: float = 0.72) -> bool:
    cand_name_raw = (activity.get("name") or "").strip()
    target_name_raw = (parsed.get("activity_name") or "").strip()
    process_name_raw = (parsed.get("process_name") or "").strip()
    cand_name = normalize(cand_name_raw)
    target_name = normalize(target_name_raw)
    process_name = normalize(process_name_raw)

    if not cand_name or not target_name:
        return False

    similarity = SequenceMatcher(None, target_name, cand_name).ratio()
    process_similarity = SequenceMatcher(None, process_name, cand_name).ratio() if process_name else 0.0
    if max(similarity, process_similarity) < min_similarity:
        return False

    target_tokens = set(significant_tokens(target_name_raw))
    process_tokens = set(significant_tokens(process_name_raw))
    candidate_tokens = set(significant_tokens(cand_name_raw))
    token_bases = [target_tokens]
    if process_tokens:
        token_bases.append(target_tokens | process_tokens)

    if any(token_bases):
        overlap_ratio = 0.0
        for base in token_bases:
            if not base:
                continue
            overlap = len(base & candidate_tokens)
            overlap_ratio = max(overlap_ratio, overlap / max(len(base), 1))
        if overlap_ratio < 0.60:
            return False

    # If SimaPro explicitly says "production", do not accept non-production activities.
    if " production " in f" {target_name} " and " production " not in f" {cand_name} ":
        return False

    # Preserve location explicitness when present.
    target_loc = (parsed.get("location_hint") or "").strip()
    cand_loc = (activity.get("location") or "").strip()
    if target_loc and target_loc != "RoW" and cand_loc and cand_loc != target_loc:
        return False

    return True


def find_best_activity(db: bd.Database, parsed: Dict[str, str], limit_per_query: int = 30) -> Optional[Dict]:
    candidates = {}

    for query in build_queries(parsed):
        try:
            for act in db.search(query, limit=limit_per_query):
                code = act.get("code")
                if code:
                    candidates[code] = act
        except Exception:
            continue

    if not candidates:
        return None

    ranked = sorted(candidates.values(), key=lambda a: score_candidate(a, parsed), reverse=True)
    best = ranked[0]
    if not is_acceptable_match(best, parsed):
        return None
    return best


def populate_brightway_fields(csv_path: Path, output_path: Path, dry_run: bool = False) -> None:
    metadata_lines, fieldnames, rows = read_inventory_csv(csv_path)

    needed_columns = [
        "Brightway Match Code",
        "Brightway Match Key",
        "Brightway Match Name",
        "Brightway Match Database",
        "Brightway Match Location",
        "Brightway Match Ref Product",
    ]
    for col in needed_columns:
        if col not in fieldnames:
            fieldnames.append(col)

    resolved = 0
    unresolved = 0

    cache: Dict[Tuple[str, str], Optional[Dict]] = {}

    for row in rows:
        db_name = (row.get("Database") or "").strip() or "ecoinvent-3.10-cutoff"
        inventory_selection = (row.get("Inventory Selection") or "").strip()

        if not inventory_selection:
            unresolved += 1
            continue

        ensure_project_for_db(db_name)
        db = bd.Database(db_name)

        cache_key = (db_name, inventory_selection)
        if cache_key in cache:
            match = cache[cache_key]
        else:
            parsed = parse_simapro_inventory_selection(inventory_selection)
            match = find_best_activity(db, parsed)
            cache[cache_key] = match

        if not match:
            unresolved += 1
            continue

        code = match.get("code", "")
        row["Brightway Match Code"] = code
        row["Brightway Match Key"] = str((db_name, code)) if code else ""
        row["Brightway Match Name"] = match.get("name", "")
        row["Brightway Match Database"] = db_name
        row["Brightway Match Location"] = match.get("location", "")
        row["Brightway Match Ref Product"] = match.get("reference product", "")
        resolved += 1

    if not dry_run:
        write_inventory_csv(output_path, metadata_lines, fieldnames, rows)

    print(f"input_csv={csv_path}")
    print(f"output_csv={output_path}")
    print(f"rows={len(rows)}")
    print(f"resolved_rows={resolved}")
    print(f"unresolved_rows={unresolved}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map SimaPro UUID inventory rows to Brightway activities using Inventory Selection names",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("csv_path", nargs="?", default="example", help="Input CSV path or inventory stem")
    parser.add_argument("--output-csv", default=None, help="Output CSV path")
    parser.add_argument("--in-place", action="store_true", help="Write results back to input CSV")
    parser.add_argument("--dry-run", action="store_true", help="Run matching but do not write output")
    args = parser.parse_args()

    csv_path = resolve_csv_input(args.csv_path)
    output_path = csv_path if args.in_place else Path(args.output_csv) if args.output_csv else default_output_path(csv_path)

    populate_brightway_fields(csv_path, output_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

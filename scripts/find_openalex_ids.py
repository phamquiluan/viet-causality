"""For each researcher in _data/researchers.yml that lacks an OpenAlex ID,
search OpenAlex for the best matching author and write the OpenAlex URL back
into the appropriate raw stage file.

Usage: python3 scripts/find_openalex_ids.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"
RAW = ROOT / "scripts" / "raw"
UA = "viet-causality-oa-lookup/1.0 (mailto:phamquiluan@gmail.com)"

CAUSALITY_CONCEPTS = ["C158600405", "C11671645", "C163504300", "C115086926"]


def curl_json(url: str) -> dict[str, Any] | None:
    try:
        res = subprocess.run(
            ["curl", "-sSL", "--fail", "-A", UA, "-H", "Accept: application/json", url],
            check=False, capture_output=True, timeout=30,
        )
        if res.returncode != 0:
            return None
        return json.loads(res.stdout.decode("utf-8"))
    except Exception:
        return None


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def name_to_search_query(name: str) -> str:
    """Convert 'Family, Given' to a Scholar-style 'Given Family' string for search."""
    raw = strip_diacritics(name).strip()
    if "," in raw:
        family, given = [s.strip() for s in raw.split(",", 1)]
        return f"{given} {family}".strip()
    return raw


def get_inst_keywords(entry: dict[str, Any]) -> set[str]:
    inst = (entry.get("affiliation") or {}).get("institution", "") or ""
    inst = strip_diacritics(inst).lower()
    inst = re.sub(r"[\W_]+", " ", inst)
    generic = {
        "university", "research", "institute", "center", "centre", "school",
        "department", "college", "faculty", "the", "of",
    }
    return {t for t in inst.split() if len(t) > 3 and t not in generic}


def search_author(query: str, aff_keywords: set[str]) -> str | None:
    """Search OpenAlex for an author matching the query. Returns the OpenAlex ID
    of the best affiliation-matched candidate, or None if ambiguous."""
    q = urllib.parse.quote_plus(query)
    url = (
        f"https://api.openalex.org/authors?search={q}&per-page=10"
        f"&select=id,display_name,display_name_alternatives,last_known_institutions,works_count,summary_stats"
    )
    data = curl_json(url)
    if not data:
        return None
    candidates = data.get("results", [])
    if not candidates:
        return None

    # Score each candidate by affiliation overlap.
    best: tuple[int, str] | None = None
    for c in candidates:
        oa_id = (c.get("id") or "").rsplit("/", 1)[-1]
        if not oa_id:
            continue
        # Affiliation match score
        score = 0
        for inst in c.get("last_known_institutions") or []:
            inst_str = strip_diacritics(inst.get("display_name", "")).lower()
            score += sum(1 for kw in aff_keywords if kw in inst_str)
        # Tie-breaker: works_count (real researchers have more works)
        score = score * 1000 + min(c.get("works_count", 0), 999)
        if best is None or score > best[0]:
            best = (score, oa_id)
    # Require at least 1 affiliation keyword match unless there's only 1 candidate.
    if best is None:
        return None
    score, oa_id = best
    if len(candidates) > 1 and score < 1000:
        return None  # ambiguous, no clear affiliation winner
    return oa_id


def count_causality_works(oa_id: str) -> int:
    """Total works under narrow causality concepts."""
    total = 0
    for cid in CAUSALITY_CONCEPTS:
        url = f"https://api.openalex.org/works?filter=author.id:{oa_id},concepts.id:{cid}&per-page=1"
        data = curl_json(url)
        total += (data or {}).get("meta", {}).get("count", 0) if data else 0
        time.sleep(0.25)
    return total


def save_yaml(path: Path, entries: list[dict[str, Any]]) -> None:
    old = path.read_text(encoding="utf-8")
    header = ""
    for line in old.split("\n"):
        if line.startswith("#") or line.strip() == "":
            header += line + "\n"
        else:
            break
    body = yaml.dump(entries, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    path.write_text(header + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    existing = yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    pending = [e for e in existing if not (e.get("links") or {}).get("openalex")]
    print(f"Researchers missing OpenAlex IDs: {len(pending)}/{len(existing)}")
    if args.limit:
        pending = pending[: args.limit]

    # Map: entry-id -> (raw_file_path, raw_index)
    raw_index: dict[str, tuple[Path, int]] = {}
    raw_data: dict[Path, list[dict[str, Any]]] = {}
    for path in sorted(RAW.glob("*.yml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        raw_data[path] = entries
        for i, e in enumerate(entries):
            raw_index[e["id"]] = (path, i)

    found = 0
    no_match = 0
    no_causal = 0
    pending_files: set[Path] = set()

    for i, entry in enumerate(pending, 1):
        query = name_to_search_query(entry["name"])
        kws = get_inst_keywords(entry)
        print(f"[{i:3d}/{len(pending)}] {entry['id']:42s} query='{query}'", end="  ", flush=True)
        oa_id = search_author(query, kws)
        time.sleep(0.3)
        if not oa_id:
            print("no match")
            no_match += 1
            continue
        n_causal = count_causality_works(oa_id)
        if n_causal == 0:
            print(f"{oa_id} but 0 causal works -- skip")
            no_causal += 1
            continue
        print(f"-> {oa_id} (causal={n_causal})")
        # Write back into raw file
        loc = raw_index.get(entry["id"])
        if not loc:
            print(f"    warning: {entry['id']} not found in any raw file")
            continue
        path, idx = loc
        raw_entry = raw_data[path][idx]
        raw_entry.setdefault("links", {})
        raw_entry["links"]["openalex"] = f"https://openalex.org/{oa_id}"
        pending_files.add(path)
        found += 1

    if not args.dry_run:
        for path in pending_files:
            save_yaml(path, raw_data[path])
            print(f"  updated {path.name}")

    print(f"\n  Found OpenAlex IDs:  {found}")
    print(f"  No match:            {no_match}")
    print(f"  Match but 0 causal:  {no_causal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Fetch up to N recent causality papers per researcher from OpenAlex.

Strategy:
  For each entry with an OpenAlex author ID, query /works filtered by author and
  by the 4 narrow causality concepts (OR-joined). Sort by publication_year desc.
  Take up to N papers. Store as `recent_works` list back into the entry's raw file.

URL preference per work: DOI > OpenAlex work URL.

Usage:
    python3 scripts/fetch_recent_works.py                 # all raw files
    python3 scripts/fetch_recent_works.py --limit 4       # N=4 papers each
    python3 scripts/fetch_recent_works.py --only id1,id2  # subset of ids
    python3 scripts/fetch_recent_works.py --refresh       # overwrite existing
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "scripts" / "raw"

# 4 narrow causality concepts; works tagged with any one of these counts.
NARROW_CONCEPTS = ["C158600405", "C11671645", "C163504300", "C115086926"]

UA = "viet-causality/1.0 (mailto:phamquiluan@gmail.com)"


def http_json(url: str) -> dict[str, Any] | None:
    try:
        res = subprocess.run(
            ["curl", "-sSL", "--fail", "-A", UA, "-H", "Accept: application/json", url],
            check=False, capture_output=True, timeout=30,
        )
        if res.returncode != 0:
            return None
        return json.loads(res.stdout.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def extract_oa_id(url: str) -> str | None:
    m = re.search(r"openalex\.org/(A\w+)", url or "")
    return m.group(1) if m else None


def best_url(work: dict[str, Any]) -> str:
    """Prefer DOI URL, then OpenAlex work URL."""
    doi = work.get("doi")
    if doi:
        # OpenAlex returns DOI as a full URL like https://doi.org/10.xxx
        return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    wid = work.get("id") or ""
    if wid:
        return wid  # full url like https://openalex.org/Wxxx
    return ""


def fetch_recent(author_id: str, n: int) -> list[dict[str, Any]]:
    """Up to n most-recent works by author tagged with any narrow causality concept."""
    concepts = "|".join(NARROW_CONCEPTS)
    url = (
        f"https://api.openalex.org/works"
        f"?filter=author.id:{author_id},concepts.id:{concepts}"
        f"&sort=publication_year:desc"
        f"&per-page={n}"
        f"&select=id,doi,title,publication_year,primary_location"
    )
    data = http_json(url)
    if not data:
        return []
    works = []
    for w in data.get("results", []):
        title = (w.get("title") or "").strip()
        if not title:
            continue
        venue = ""
        prim = w.get("primary_location") or {}
        src = (prim or {}).get("source") or {}
        venue = (src.get("display_name") or "").strip()
        works.append({
            "title": title,
            "year": w.get("publication_year"),
            "venue": venue or None,
            "url": best_url(w),
        })
    # Drop None venue keys (yaml prefers absent over null)
    for w in works:
        if w.get("venue") is None:
            w.pop("venue", None)
    return works


def load(path: Path) -> tuple[list[dict[str, Any]], str]:
    text = path.read_text(encoding="utf-8")
    header_lines = []
    for line in text.split("\n"):
        if line.startswith("#") or line.strip() == "":
            header_lines.append(line)
        else:
            break
    header = "\n".join(header_lines)
    if header and not header.endswith("\n"):
        header += "\n"
    if header:
        header += "\n" if not text.startswith(header + "\n") else ""
    data = yaml.safe_load(text) or []
    return data, header


def save(path: Path, entries: list[dict[str, Any]], header: str) -> None:
    body = yaml.dump(entries, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    path.write_text(header + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=4, help="Max works per researcher")
    parser.add_argument("--only", type=str, default="", help="Comma-separated list of entry ids to process")
    parser.add_argument("--refresh", action="store_true", help="Overwrite existing recent_works")
    parser.add_argument("--sleep", type=float, default=0.3, help="Seconds between API calls")
    args = parser.parse_args()

    only_ids = set(s.strip() for s in args.only.split(",") if s.strip()) if args.only else None

    files = sorted(RAW.glob("*.yml"))
    grand_added = 0
    grand_skipped = 0
    grand_nohit = 0

    for path in files:
        entries, header = load(path)
        changed = False
        oa_entries = [
            (i, e) for i, e in enumerate(entries)
            if extract_oa_id((e.get("links") or {}).get("openalex", ""))
        ]
        if not oa_entries:
            continue
        if only_ids:
            oa_entries = [(i, e) for i, e in oa_entries if e.get("id") in only_ids]
        if not oa_entries:
            continue
        print(f"\n=== {path.name}: {len(oa_entries)} OpenAlex entries ===")

        for k, (i, e) in enumerate(oa_entries, 1):
            eid = e["id"]
            if e.get("recent_works") and not args.refresh:
                print(f"  [{k:2d}/{len(oa_entries)}] {eid:42s} -- already has recent_works, skip")
                grand_skipped += 1
                continue
            oa = extract_oa_id((e.get("links") or {}).get("openalex", ""))
            print(f"  [{k:2d}/{len(oa_entries)}] {eid:42s} ", end="", flush=True)
            works = fetch_recent(oa, args.limit)  # type: ignore[arg-type]
            if not works:
                print("no causal works found")
                grand_nohit += 1
            else:
                e["recent_works"] = works
                print(f"{len(works)} works")
                changed = True
                grand_added += 1
            time.sleep(args.sleep)

        if changed:
            save(path, entries, header)
            print(f"  -> saved {path.name}")

    print(f"\nAdded: {grand_added}  Skipped (had data): {grand_skipped}  No OpenAlex hits: {grand_nohit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

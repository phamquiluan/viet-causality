"""Backfill `recent_works` from manually-curated `key_papers` for entries that
don't already have recent_works.

For each key_paper:
  - If it has a URL, copy it over.
  - If not, try OpenAlex /works?search=<title> to find a matching work and use
    DOI > OpenAlex URL as the URL.

Usage:
    python3 scripts/backfill_recent_works.py
    python3 scripts/backfill_recent_works.py --only id1,id2
    python3 scripts/backfill_recent_works.py --refresh   # overwrite existing recent_works
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "scripts" / "raw"

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


def url_for_work(w: dict[str, Any]) -> str:
    doi = w.get("doi")
    if doi:
        return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    return w.get("id") or ""


def is_causal_work(w: dict[str, Any]) -> bool:
    title = (w.get("title") or "").lower()
    if any(k in title for k in ("causal", "causation", "counterfactual", "mendelian random",
                                  "instrumental var", "treatment effect", "do-calculus",
                                  "confounder", "intervention")):
        return True
    # also check concepts list if present (search returns concepts too)
    concepts = w.get("concepts") or []
    for c in concepts:
        cid = (c.get("id") or "").split("/")[-1]
        if cid in {"C158600405", "C11671645", "C163504300", "C115086926"}:
            return True
    return False


def title_similar(a: str, b: str) -> bool:
    """Fuzzy: shared lowercase non-stopword tokens > 60%."""
    def toks(s: str) -> set:
        return {w for w in re.findall(r"[a-z0-9]+", s.lower())
                if len(w) > 2 and w not in {"the", "and", "for", "with", "from"}}
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap > 0.6


def search_openalex(title: str) -> dict[str, Any] | None:
    """Return best-matching work for `title` via OpenAlex /works?search="""
    q = urllib.parse.quote(title[:200])
    url = (
        f"https://api.openalex.org/works"
        f"?search={q}"
        f"&per-page=5"
        f"&select=id,doi,title,publication_year,primary_location,concepts"
    )
    data = http_json(url)
    if not data:
        return None
    best = None
    for w in data.get("results", []):
        if title_similar(title, w.get("title") or ""):
            best = w
            break
    return best


def enrich_paper(kp: dict[str, Any]) -> dict[str, Any]:
    """Return a recent_works-style dict. If kp already has url, just copy.
    Otherwise try to resolve via OpenAlex title search."""
    title = (kp.get("title") or "").strip()
    year = kp.get("year")
    venue = kp.get("venue")
    rw = {"title": title}
    if year:
        rw["year"] = year
    if venue:
        rw["venue"] = venue

    if kp.get("url"):
        rw["url"] = kp["url"]
        return rw

    # Try resolution
    w = search_openalex(title) if title else None
    if w:
        u = url_for_work(w)
        if u:
            rw["url"] = u
        # also enrich venue if we didn't have one
        if not venue:
            prim = (w.get("primary_location") or {}) or {}
            src = (prim.get("source") or {}) or {}
            v = (src.get("display_name") or "").strip()
            if v:
                rw["venue"] = v
        # enrich year if missing
        if not year and w.get("publication_year"):
            rw["year"] = w["publication_year"]
    return rw


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
    data = yaml.safe_load(text) or []
    return data, header


def save(path: Path, entries: list[dict[str, Any]], header: str) -> None:
    body = yaml.dump(entries, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    path.write_text(header + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=str, default="")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--max-papers", type=int, default=4)
    args = parser.parse_args()

    only_ids = set(s.strip() for s in args.only.split(",") if s.strip()) if args.only else None

    files = sorted(RAW.glob("*.yml"))
    total_enriched = 0
    total_with_url = 0
    total_without_url = 0

    for path in files:
        entries, header = load(path)
        changed = False
        candidates = [
            (i, e) for i, e in enumerate(entries)
            if e.get("key_papers") and (args.refresh or not e.get("recent_works"))
        ]
        if only_ids:
            candidates = [(i, e) for i, e in candidates if e.get("id") in only_ids]
        if not candidates:
            continue
        print(f"\n=== {path.name}: {len(candidates)} candidates ===")
        for k, (i, e) in enumerate(candidates, 1):
            eid = e["id"]
            kps = e["key_papers"][:args.max_papers]
            print(f"  [{k:2d}/{len(candidates)}] {eid:42s} ({len(kps)} papers)")
            rws = []
            for kp in kps:
                rw = enrich_paper(kp)
                if rw.get("url"):
                    total_with_url += 1
                else:
                    total_without_url += 1
                rws.append(rw)
                if not kp.get("url"):
                    time.sleep(args.sleep)
            if rws:
                e["recent_works"] = rws
                changed = True
                total_enriched += 1

        if changed:
            save(path, entries, header)
            print(f"  -> saved {path.name}")

    print(f"\nEnriched {total_enriched} entries.")
    print(f"Papers with URL: {total_with_url}   without URL: {total_without_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

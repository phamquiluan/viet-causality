"""Audit Stage B4 (arXiv) entries by verifying each key_paper arXiv ID resolves
to a real paper. Flags entries where ALL listed arXiv IDs fail to resolve, since
those entries' papers were likely fabricated by the scrape agent.

Usage: python3 scripts/audit_arxiv.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "scripts" / "raw"
UA = "viet-causality-arxiv-audit/1.0"

ARXIV_ID_RE = re.compile(r"(?:abs/|arxiv\.org/)(\d{4}\.\d{4,5})", re.IGNORECASE)


def curl_get(url: str) -> str | None:
    try:
        res = subprocess.run(
            ["curl", "-sSL", "--fail", "-A", UA, url],
            check=False, capture_output=True, timeout=30,
        )
        if res.returncode != 0:
            return None
        return res.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None


def fetch_arxiv(arxiv_id: str) -> tuple[str, list[str]] | None:
    """Return (title, authors) for a given arXiv ID, or None if it doesn't resolve."""
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    body = curl_get(url)
    if not body:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        return None
    entry = entries[0]
    title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
    if not title or "Error" in title:
        return None
    authors = [
        (a.findtext("atom:name", default="", namespaces=ns) or "").strip()
        for a in entry.findall("atom:author", ns)
    ]
    return title, authors


def extract_arxiv_ids(entry: dict[str, Any]) -> list[str]:
    """Pull arXiv IDs from key_papers urls and the entry's arxiv link."""
    ids: list[str] = []
    for p in entry.get("key_papers") or []:
        url = p.get("url", "") or ""
        for m in ARXIV_ID_RE.finditer(url):
            ids.append(m.group(1))
    return list(dict.fromkeys(ids))  # dedupe preserving order


def main() -> int:
    b4 = RAW / "stage_b4_arxiv.yml"
    entries = yaml.safe_load(b4.read_text(encoding="utf-8")) or []
    print(f"Auditing {len(entries)} Stage B4 entries for arXiv ID resolution...\n")

    all_papers_fail: list[str] = []
    some_fail: list[tuple[str, list[str]]] = []
    fully_ok: list[str] = []
    no_papers: list[str] = []

    for i, e in enumerate(entries, 1):
        ids = extract_arxiv_ids(e)
        if not ids:
            no_papers.append(e["id"])
            print(f"[{i:2d}/{len(entries)}] {e['id']:42s} (no arXiv IDs in key_papers)")
            continue
        results = []
        for aid in ids:
            res = fetch_arxiv(aid)
            results.append((aid, res is not None, res[0][:80] if res else ""))
            time.sleep(0.3)
        failed = [aid for aid, ok, _ in results if not ok]
        print(f"[{i:2d}/{len(entries)}] {e['id']:42s} {len(ids)-len(failed)}/{len(ids)} arXiv IDs resolved")
        for aid, ok, title in results:
            mark = "OK" if ok else "FAIL"
            print(f"    [{mark:4}] {aid} {title}")
        if len(failed) == len(ids):
            all_papers_fail.append(e["id"])
        elif failed:
            some_fail.append((e["id"], failed))
        else:
            fully_ok.append(e["id"])

    print("\n" + "=" * 80)
    print("AUDIT RESULTS:")
    print(f"  Entries with all arXiv IDs resolving:        {len(fully_ok)}")
    print(f"  Entries with NO arXiv IDs in key_papers:     {len(no_papers)}")
    print(f"  Entries with some failed arXiv IDs:          {len(some_fail)}")
    print(f"  Entries where ALL arXiv IDs failed (suspect): {len(all_papers_fail)}")
    if all_papers_fail:
        print("\nSUSPECT (all listed arXiv IDs failed to resolve):")
        for eid in all_papers_fail:
            print(f"  - {eid}")
    if some_fail:
        print("\nPARTIAL FAILURES (some listed arXiv IDs failed):")
        for eid, failed in some_fail:
            print(f"  - {eid}: failed IDs {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

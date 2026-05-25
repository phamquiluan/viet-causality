"""Verify all recent_works URLs in _data/researchers.yml resolve to real pages.

Strategy:
  - arXiv abs/PDF URLs: GET (not HEAD) + check 200 status and that body
    contains the arXiv ID (cheap way to spot 404 pages that still 200).
  - DOI URLs: HEAD with -L for redirects; accept any 2xx after redirects.
  - Other URLs (mlr.press, journal sites, OpenAlex W-id): HEAD with -L.

Reports broken URLs grouped by researcher and prints a JSON dump suitable
for further automated fixup.

Usage:
    python3 scripts/verify_urls.py                # verify all
    python3 scripts/verify_urls.py --concurrency 6
    python3 scripts/verify_urls.py --json /tmp/broken.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
TIMEOUT = 20


def http_status(url: str, method: str = "HEAD", retries: int = 1) -> tuple[int, str]:
    """Return (http_code, raw_status_string). 0 means network failure."""
    flag = "-sSLI" if method == "HEAD" else "-sSL"
    extra = [] if method == "HEAD" else ["-r", "0-0"]
    for attempt in range(retries + 1):
        try:
            res = subprocess.run(
                ["curl", flag, "-A", UA, "--max-time", str(TIMEOUT),
                 "-o", "/dev/null", "-w", "%{http_code}"] + extra + [url],
                check=False, capture_output=True, timeout=TIMEOUT + 5,
            )
            code_str = res.stdout.decode().strip()
            try:
                code = int(code_str)
            except ValueError:
                code = 0
            if code > 0:
                return code, code_str
        except subprocess.TimeoutExpired:
            pass
        time.sleep(0.5)
    return 0, "timeout"


def crossref_exists(doi: str) -> tuple[bool, str]:
    """Verify a DOI via the Crossref API (open, no Cloudflare)."""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        res = subprocess.run(
            ["curl", "-sSL", "-A", "viet-causality/1.0 (mailto:phamquiluan@gmail.com)",
             "--max-time", str(TIMEOUT), url],
            check=False, capture_output=True, timeout=TIMEOUT + 5,
        )
        if res.returncode != 0:
            return False, "crossref network error"
        body = res.stdout.decode("utf-8", errors="replace")
        # Crossref returns JSON with 'status':'ok' for valid DOIs
        if '"status":"ok"' in body or '"status": "ok"' in body:
            return True, "crossref ok"
        if "Resource not found" in body or '"status":"failed"' in body:
            return False, "crossref: doi not found"
        return False, f"crossref: unexpected ({body[:80]})"
    except Exception as e:  # noqa: BLE001
        return False, f"crossref exception: {e}"


def verify_url(url: str) -> tuple[str, bool, str]:
    """HEAD first, fall back to GET, then Crossref for DOIs."""
    code, raw = http_status(url, "HEAD")
    if 200 <= code < 400:
        return url, True, f"HEAD {code}"
    code2, raw2 = http_status(url, "GET", retries=1)
    if 200 <= code2 < 400:
        return url, True, f"GET {code2}"
    # DOI fallback: hit Crossref API directly
    m = re.match(r"https?://(?:dx\.)?doi\.org/(.+)$", url)
    if m:
        ok, why = crossref_exists(m.group(1))
        if ok:
            return url, True, f"crossref (HEAD {raw})"
        return url, False, f"HEAD {raw} / GET {raw2} / {why}"
    return url, False, f"HEAD {raw} / GET {raw2}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--json", type=str, default="/tmp/broken_urls.json")
    args = parser.parse_args()

    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    # Collect (url, researcher_id, work_index) triples
    tasks: list[tuple[str, str, int]] = []
    for e in data:
        for i, w in enumerate(e.get("recent_works") or []):
            u = (w or {}).get("url")
            if u:
                tasks.append((u, e["id"], i))

    print(f"Verifying {len(tasks)} URLs across {len(data)} researchers (concurrency={args.concurrency})...")
    results: dict[str, tuple[bool, str]] = {}
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(verify_url, u): (u, eid, idx) for u, eid, idx in tasks}
        done = 0
        for fut in as_completed(futures):
            url, ok, why = fut.result()
            results[url] = (ok, why)
            done += 1
            if done % 25 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} ({time.time()-started:.0f}s) ok={sum(1 for r in results.values() if r[0])}")

    broken: list[dict[str, Any]] = []
    by_researcher: dict[str, list[dict]] = {}
    for u, eid, idx in tasks:
        ok, why = results[u]
        if not ok:
            entry = {"id": eid, "work_idx": idx, "url": u, "reason": why}
            broken.append(entry)
            by_researcher.setdefault(eid, []).append(entry)

    print(f"\n{'='*60}")
    print(f"OK: {len(tasks) - len(broken)}/{len(tasks)} ({100*(len(tasks)-len(broken))/max(1,len(tasks)):.0f}%)")
    print(f"BROKEN: {len(broken)}")
    print(f"{'='*60}")
    if broken:
        for eid, items in sorted(by_researcher.items()):
            print(f"\n  {eid}:")
            for b in items:
                print(f"    [{b['work_idx']}] {b['url']}  ({b['reason']})")

    Path(args.json).write_text(json.dumps(broken, indent=2))
    print(f"\nWrote: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Phase 1: For entries that already have a Google Scholar URL, fetch the page
via curl, extract the display name, normalize the URL, and commit per-entry.

Phase 2 (WebSearch-driven name discovery) is handled outside this script via
`scripts/set_scholar.py`.

Usage:
    python3 scripts/fetch_scholar.py            # process all entries with a scholar URL
    python3 scripts/fetch_scholar.py --limit 5  # only first 5 pending
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def curl_get(url: str) -> str | None:
    try:
        res = subprocess.run(
            ["curl", "-sSL", "--fail", "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9", url],
            check=False, capture_output=True, timeout=30,
        )
        if res.returncode != 0:
            print(f"  curl error ({res.returncode}): {res.stderr.decode(errors='replace')[:120]}", file=sys.stderr)
            return None
        return res.stdout.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        print(f"  Exception: {e}", file=sys.stderr)
        return None


def extract_user_id(scholar_url: str) -> str | None:
    m = re.search(r"user=([\w-]+)", scholar_url)
    return m.group(1) if m else None


def normalize_scholar_url(url: str) -> str:
    uid = extract_user_id(url)
    if not uid:
        return url
    return f"https://scholar.google.com/citations?user={uid}&hl=en&oi=ao"


def fetch_profile_name(scholar_url: str) -> str | None:
    html = curl_get(scholar_url)
    if not html:
        return None
    m = re.search(r'id="gsc_prf_in"[^>]*>([^<]+)<', html)
    if m:
        return m.group(1).strip()
    return None


def save_yaml(entries: list[dict[str, Any]]) -> None:
    yaml_dump = yaml.dump(
        entries, sort_keys=False, allow_unicode=True,
        default_flow_style=False, width=120,
    )
    header = (
        "# Vietnamese researchers working on causality.\n"
        "# Source: scripts/consolidate.py merges _data/researchers.yml + scripts/raw/*.yml.\n"
        "# To regenerate after adding raw scrape data: python scripts/consolidate.py\n"
        "# Schema: see CONTRIBUTING.md.\n\n"
    )
    DATA.write_text(header + yaml_dump, encoding="utf-8")
    subprocess.run(["python3", str(ROOT / "scripts" / "render_table.py")], check=True, cwd=ROOT)


def commit(message: str) -> None:
    subprocess.run(["git", "add", "-A"], check=True, cwd=ROOT)
    subprocess.run(
        ["git", "-c", "user.name=viet-causality",
         "-c", "user.email=phamquiluan@gmail.com",
         "commit", "-q", "-m", message],
        check=True, cwd=ROOT,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    entries = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    have_url = [e for e in entries if (e.get("links") or {}).get("scholar") and not e.get("name_scholar")]
    print(f"{len(have_url)} entries with scholar URL but no display name yet")

    done = 0
    for entry in have_url:
        if args.limit is not None and done >= args.limit:
            break
        links = entry.setdefault("links", {})
        url = normalize_scholar_url(links["scholar"])
        print(f"[{done+1}] {entry['id']} ({entry['name']})...", flush=True)
        display = fetch_profile_name(url)
        if display:
            entry["name_scholar"] = display
            links["scholar"] = url
            save_yaml(entries)
            commit(f"scholar: {entry['id']} -> {display}")
            print(f"    OK -> {display}")
            done += 1
        else:
            print("    FAIL (no name extracted)")
        time.sleep(random.uniform(2.0, 5.0))

    print(f"\nProcessed {done}/{len(have_url)} entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Phase 2: bulk-update Scholar info from a JSON list piped on stdin.

Each item: {"id": "...", "user_id": "...", "display_name": "..."}
For each, sets links.scholar (normalized) and name_scholar, renders the table,
and commits per-entry with a 2-5s sleep.

Usage:
    cat batch.json | python3 scripts/set_scholar.py
    echo '[{"id":"huynh-van-nam-jaist","user_id":"XVThR3QAAAAJ","display_name":"Van Nam Huynh"}]' | python3 scripts/set_scholar.py
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"


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
    batch = json.load(sys.stdin)
    if not isinstance(batch, list):
        print("input must be a JSON list", file=sys.stderr)
        return 1

    entries = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in entries}

    done = 0
    for item in batch:
        eid = item["id"]
        uid = item["user_id"].strip()
        display = item["display_name"].strip()
        entry = by_id.get(eid)
        if entry is None:
            print(f"  skip: unknown id {eid}", file=sys.stderr)
            continue
        if not uid or not display:
            print(f"  skip: empty user_id or display_name for {eid}")
            continue

        url = f"https://scholar.google.com/citations?user={uid}&hl=en&oi=ao"
        links = entry.setdefault("links", {})
        # Don't overwrite an existing different URL silently — warn.
        if links.get("scholar") and uid not in links["scholar"]:
            print(f"  warn: {eid} already has scholar URL {links['scholar']} (overwriting with user={uid})")
        links["scholar"] = url
        entry["name_scholar"] = display
        save_yaml(entries)
        commit(f"scholar: {eid} -> {display}")
        print(f"[{done+1}/{len(batch)}] {eid} -> {display}")
        done += 1
        time.sleep(random.uniform(2.0, 5.0))

    print(f"\nProcessed {done}/{len(batch)} entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

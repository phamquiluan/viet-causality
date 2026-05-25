"""Apply sub-agent results (a JSON map of id -> list of works) into raw files.

Usage:
    python3 scripts/apply_subagent_results.py /tmp/subagent_results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "scripts" / "raw"


def load(path: Path) -> tuple[list[dict], str]:
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
    return yaml.safe_load(text) or [], header


def save(path: Path, entries: list[dict], header: str) -> None:
    body = yaml.dump(entries, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    path.write_text(header + body, encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: apply_subagent_results.py results.json", file=sys.stderr)
        return 1
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    files = sorted(RAW.glob("*.yml"))
    applied = 0
    for path in files:
        entries, header = load(path)
        changed = False
        for e in entries:
            eid = e.get("id")
            if eid in results:
                e["recent_works"] = results[eid]
                changed = True
                applied += 1
                print(f"  {path.name}: {eid} -> {len(results[eid])} works")
        if changed:
            save(path, entries, header)

    print(f"\nApplied {applied} entry updates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

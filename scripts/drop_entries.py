"""Drop entries by id from all raw files. Used after audit confirms 0 causality
works for borderline researchers.

Usage:
    python3 scripts/drop_entries.py id1 id2 id3 ...
"""
from __future__ import annotations

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
    drops = set(sys.argv[1:])
    if not drops:
        print("usage: drop_entries.py id1 id2 ...", file=sys.stderr)
        return 1
    total = 0
    for path in sorted(RAW.glob("*.yml")):
        entries, header = load(path)
        kept = [e for e in entries if e.get("id") not in drops]
        removed = len(entries) - len(kept)
        if removed:
            save(path, kept, header)
            print(f"  {path.name}: dropped {removed} entries")
            total += removed
    print(f"Total dropped: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

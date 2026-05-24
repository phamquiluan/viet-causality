"""Render _data/researchers.yml into the Markdown table in README.md.

Usage: python scripts/render_table.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("pyyaml is required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"
README = ROOT / "README.md"
START_TAG = "<!-- TABLE_START -->"
END_TAG = "<!-- TABLE_END -->"


def fmt_link(label: str, url: str) -> str:
    if not url:
        return ""
    return f"[{label}]({url})"


def fmt_links(links: dict[str, str]) -> str:
    parts = []
    for label, key in [("home", "homepage"), ("scholar", "scholar"), ("dblp", "dblp"), ("orcid", "orcid")]:
        v = (links or {}).get(key)
        if v:
            parts.append(fmt_link(label, v))
    return " · ".join(parts)


def fmt_areas(areas: list[str]) -> str:
    return ", ".join(f"`{a}`" for a in (areas or []))


def render_rows(entries: list[dict[str, Any]]) -> str:
    by_country: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        country = (e.get("affiliation") or {}).get("country", "Unknown")
        by_country.setdefault(country, []).append(e)

    out: list[str] = []
    out.append(f"_Last updated: see commit log. **{len(entries)} researchers** across {len(by_country)} countries._\n")
    out.append("| Name | Position | Affiliation | Sub-areas | Links | Confidence |")
    out.append("|---|---|---|---|---|---|")
    for country in sorted(by_country):
        out.append(f"| **{country}** | | | | | |")
        rows = sorted(by_country[country], key=lambda e: e["name"])
        for e in rows:
            aff = e.get("affiliation") or {}
            row = [
                e["name"],
                aff.get("position", ""),
                aff.get("institution", ""),
                fmt_areas(e.get("sub_areas", [])),
                fmt_links(e.get("links", {})),
                e.get("confidence", ""),
            ]
            out.append("| " + " | ".join(row) + " |")
    return "\n".join(out) + "\n"


def main() -> int:
    if not DATA.exists():
        print(f"missing data file: {DATA}", file=sys.stderr)
        return 1
    entries = yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    if not isinstance(entries, list):
        print("researchers.yml must be a YAML list", file=sys.stderr)
        return 1

    table = render_rows(entries)

    readme = README.read_text(encoding="utf-8")
    if START_TAG not in readme or END_TAG not in readme:
        print(f"README is missing {START_TAG} / {END_TAG} markers", file=sys.stderr)
        return 1
    pre = readme.split(START_TAG)[0] + START_TAG + "\n"
    post = "\n" + END_TAG + readme.split(END_TAG)[1]
    README.write_text(pre + table + post, encoding="utf-8")
    print(f"rendered {len(entries)} entries to README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

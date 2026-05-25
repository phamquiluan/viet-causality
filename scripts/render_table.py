"""Render _data/researchers.yml into the Markdown table in README.md.

Usage: python scripts/render_table.py
"""
from __future__ import annotations

import re
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


def fmt_areas(areas: list[str]) -> str:
    return ", ".join(f"`{a}`" for a in (areas or []))


def fmt_recent_works(works: list[dict]) -> str:
    """Render up to 4 works as [1][2][3][4] hyperlinks; items lacking URL appear as plain [N]."""
    if not works:
        return ""
    parts = []
    for i, w in enumerate(works[:4], 1):
        url = (w or {}).get("url") or ""
        if url:
            parts.append(f"[\\[{i}\\]]({url})")
        else:
            parts.append(f"\\[{i}\\]")
    return "".join(parts)


# Academic seniority ladder. Match by substring (lowercased) against the
# position field; first match wins, so longer/more-specific titles go first.
ACADEMIC_RANK: list[tuple[str, str]] = [
    ("full professor", "Full Professor"),
    ("emeritus professor", "Emeritus Professor"),
    ("associate research professor", "Associate Research Professor"),
    ("associate professor", "Associate Professor"),
    ("junior professor", "Assistant Professor"),
    ("assistant professor", "Assistant Professor"),
    ("senior lecturer", "Senior Lecturer"),
    ("lecturer", "Lecturer"),
    ("senior research scientist", "Senior Research Scientist"),
    ("senior research fellow", "Senior Research Fellow"),
    ("research scientist", "Research Scientist"),
    ("research fellow", "Research Fellow"),
    ("postdoctoral researcher", "Postdoc"),
    ("postdoc", "Postdoc"),
    ("senior researcher", "Senior Researcher"),
    ("researcher", "Researcher"),
    ("faculty", "Faculty"),
]

# Institutions that should always be categorized as Industry (lowercased substrings).
INDUSTRY_HINTS = {
    "google", "deepmind", "amazon", "microsoft", "apple", "meta", "facebook",
    "adobe", "ibm", "salesforce", "openai", "anthropic", "nvidia",
    "qualcomm", "intel", "huawei", "tencent", "alibaba", "bytedance", "samsung",
    "bosch", "pfizer", "amgen", "abbvie", "roche", "novartis", "sanofi",
    "vinai", "fpt software", "vnpt", "diabetes australia",
    # Adobe, Yandex etc covered above
}


def categorize(entry: dict[str, Any]) -> str:
    aff = entry.get("affiliation") or {}
    pos = (aff.get("position") or "").lower()
    inst = (aff.get("institution") or "").lower()
    if "phd student" in pos or "phd graduate" in pos or pos.strip() == "student":
        return "PhD Students"
    if "industry researcher" in pos or "applied scientist" in pos:
        return "Industry"
    if any(re.search(rf"\b{re.escape(h)}\b", inst) for h in INDUSTRY_HINTS) \
            and "university" not in inst and "institute" not in inst:
        return "Industry"
    return "Academic"


def academic_rank(entry: dict[str, Any]) -> tuple[int, str, str]:
    pos = ((entry.get("affiliation") or {}).get("position") or "").lower()
    for i, (needle, _label) in enumerate(ACADEMIC_RANK):
        if needle in pos:
            return (i, _label, entry.get("name", ""))
    return (len(ACADEMIC_RANK), "Other", entry.get("name", ""))


def works_count(entry: dict[str, Any]) -> int:
    return len(entry.get("recent_works") or [])


def sort_key_by_works(entry: dict[str, Any]) -> tuple[int, str]:
    """Sort by recent_works count desc, then name asc (stable tiebreaker)."""
    return (-works_count(entry), entry.get("name", ""))


def position_label(entry: dict[str, Any]) -> str:
    """Normalize the position field into a display label (or empty)."""
    pos = ((entry.get("affiliation") or {}).get("position") or "")
    if not pos or "unknown" in pos.lower():
        return ""
    return pos


def render_section(name: str, items: list[dict[str, Any]], group_by_rank: bool = False) -> list[str]:
    out: list[str] = []
    if not items:
        return out
    out.append(f"\n### {name} ({len(items)})\n")
    out.append("| Name | Position | Affiliation | Country | Sub-areas | Recent works |")
    out.append("|---|---|---|---|---|---|")

    if group_by_rank:
        # Group rows under a rank sub-heading; within a rank, sort by
        # recent_works count desc.
        by_rank: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for entry in items:
            i, rank, _ = academic_rank(entry)
            by_rank.setdefault((i, rank), []).append(entry)
        for (i, rank) in sorted(by_rank.keys()):
            out.append(f"| **{rank}** | | | | | |")
            for entry in sorted(by_rank[(i, rank)], key=sort_key_by_works):
                out.append(row_for(entry))
    else:
        for entry in sorted(items, key=sort_key_by_works):
            out.append(row_for(entry))
    return out


def name_cell(entry: dict[str, Any]) -> str:
    """First-column name. Prefer Google-Scholar display name + link when present."""
    scholar_name = entry.get("name_scholar")
    scholar_url = (entry.get("links") or {}).get("scholar")
    if scholar_name and scholar_url:
        return f"[{scholar_name}]({scholar_url})"
    return entry["name"]


def row_for(entry: dict[str, Any]) -> str:
    aff = entry.get("affiliation") or {}
    return "| " + " | ".join([
        name_cell(entry),
        position_label(entry),
        aff.get("institution", "") or "",
        aff.get("country", "") or "",
        fmt_areas(entry.get("sub_areas", [])),
        fmt_recent_works(entry.get("recent_works") or []),
    ]) + " |"


def render_rows(entries: list[dict[str, Any]]) -> str:
    from collections import Counter
    countries = Counter((e.get("affiliation") or {}).get("country", "Unknown") for e in entries)
    sub_count: Counter = Counter()
    for e in entries:
        for s in e.get("sub_areas") or []:
            sub_count[s] += 1

    bucketed: dict[str, list[dict[str, Any]]] = {"Academic": [], "Industry": [], "PhD Students": []}
    for e in entries:
        bucketed[categorize(e)].append(e)

    out: list[str] = []
    out.append(
        f"_**{len(entries)} researchers** across {len(countries)} countries._"
    )
    out.append(
        f"\n**By category:** Academic ({len(bucketed['Academic'])}), "
        f"Industry ({len(bucketed['Industry'])}), "
        f"PhD Students ({len(bucketed['PhD Students'])})."
    )
    country_summary = ", ".join(f"{c} ({n})" for c, n in countries.most_common(8))
    out.append(f"\n**By country (top 8):** {country_summary}.")
    sub_summary = ", ".join(f"`{s}` ({n})" for s, n in sub_count.most_common(8))
    out.append(f"\n**By sub-area (top 8):** {sub_summary}.")

    out.extend(render_section("Academic", bucketed["Academic"], group_by_rank=True))
    out.extend(render_section("Industry", bucketed["Industry"]))
    out.extend(render_section("PhD Students", bucketed["PhD Students"]))
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

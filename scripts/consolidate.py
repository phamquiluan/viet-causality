"""Consolidate seed + Stage A/B raw staging YAML files into _data/researchers.yml.

Strategy:
1. Load seed researchers.yml + all scripts/raw/*.yml.
2. Normalize each entry into a merge_key.
3. Group entries by merge_key.
4. For each group, merge into a single canonical entry, preserving the best
   affiliation/links/papers/notes and combining sub_areas across sources.
5. Output sorted by country then family name.

Usage: python scripts/consolidate.py
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("pyyaml required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"
RAW = ROOT / "scripts" / "raw"
OUT = ROOT / "_data" / "researchers.yml"

# Source priority — higher value = trust this entry's affiliation/position more.
SOURCE_PRIORITY = {
    "manual_seed": 100,
    "self_submitted": 90,
    "community_pr": 80,
    "scrape_dblp": 70,        # DBLP author records are typically well-curated
    "scrape_dynaroars": 65,
    "scrape_viet_wics": 65,
    "scrape_vis_uki": 65,
    "scrape_openalex": 50,
    "scrape_semantic_scholar": 40,
    "scrape_arxiv": 30,
    "referral": 20,
}

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}

# Manual duplicate aliases: map (alt_merge_key) -> canonical_merge_key.
# Used to force-merge entries whose names differ slightly across sources.
MANUAL_ALIASES: dict[str, str] = {
    # Le, Minh (OpenAlex A5016537664) is the same person as Le, Minh Khoa at Deakin A2I2
    # (both authored "Learning Structural Causal Models from Ordering").
    "le minh": "khoa le minh",
}


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_TOKEN_RE = re.compile(r"[A-Za-z]+")


def name_tokens(name: str) -> list[str]:
    ascii_name = strip_diacritics(name).lower()
    return _TOKEN_RE.findall(ascii_name)


# Vietnamese title/honorific words to drop from the merge key.
_STOPWORDS = {"dr", "mr", "ms", "prof", "professor", "the"}


def merge_key(entry: dict[str, Any]) -> str:
    name = entry.get("name", "")
    tokens = [t for t in name_tokens(name) if t not in _STOPWORDS]
    return " ".join(sorted(tokens))


def load_yaml_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a YAML list")
    return data


def best_value(a: Any, b: Any) -> Any:
    """Pick the better of two values (prefer non-empty / non-Unknown)."""
    def is_filled(x: Any) -> bool:
        if x is None or x == "":
            return False
        if isinstance(x, str) and "Unknown" in x:
            return False
        return True
    if is_filled(a) and not is_filled(b):
        return a
    if is_filled(b) and not is_filled(a):
        return b
    return a if a else b


def merge_links(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if v and not out.get(k):
            out[k] = v
    return out


def merge_papers(a: list, b: list) -> list:
    seen = set()
    out: list = []
    for paper in list(a or []) + list(b or []):
        if not paper:
            continue
        title = (paper.get("title") or "").strip().lower()
        if title in seen:
            continue
        seen.add(title)
        out.append(paper)
    return out


def merge_sub_areas(a: list, b: list) -> list:
    seen = set()
    out: list = []
    # Normalize: lowercase, replace _ with -.
    for area in list(a or []) + list(b or []):
        if not area:
            continue
        norm = str(area).lower().replace("_", "-")
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def merge_two(canon: dict, other: dict) -> dict:
    """Merge `other` into `canon`. `canon` is the higher-priority source."""
    canon_aff = canon.get("affiliation") or {}
    other_aff = other.get("affiliation") or {}

    merged_aff = {
        "institution": best_value(canon_aff.get("institution"), other_aff.get("institution")),
        "country": best_value(canon_aff.get("country"), other_aff.get("country")),
        "position": best_value(canon_aff.get("position"), other_aff.get("position")),
    }

    return {
        "id": canon.get("id") or other.get("id"),
        "name": canon.get("name") or other.get("name"),
        "name_vi": canon.get("name_vi") or other.get("name_vi"),
        "affiliation": merged_aff,
        "links": merge_links(canon.get("links") or {}, other.get("links") or {}),
        "sub_areas": merge_sub_areas(canon.get("sub_areas"), other.get("sub_areas")),
        "key_papers": merge_papers(canon.get("key_papers"), other.get("key_papers")),
        "alumnus_of": (canon.get("alumnus_of") or other.get("alumnus_of")),
        # Combine notes (deduplicated)
        "notes": " | ".join(
            sorted({n for n in [canon.get("notes"), other.get("notes")] if n})
        ) or None,
        # Take highest confidence
        "confidence": max(
            [canon.get("confidence", ""), other.get("confidence", "")],
            key=lambda c: CONFIDENCE_RANK.get(c, 0),
        ),
        # Track all sources
        "source": canon.get("source"),
        "sources_all": sorted(set(
            (canon.get("sources_all") or [canon.get("source")]) +
            (other.get("sources_all") or [other.get("source")])
        )) if canon.get("source") != other.get("source") else None,
        "last_verified": max(
            [canon.get("last_verified", ""), other.get("last_verified", "")]
        ),
    }


def main() -> int:
    files = sorted(RAW.glob("*.yml"))
    all_entries: list[dict[str, Any]] = []
    for f in files:
        entries = load_yaml_list(f)
        for e in entries:
            e.setdefault("source", "unknown")
            all_entries.append(e)
    print(f"loaded {len(all_entries)} raw entries from {len(files)} files")

    # Group by merge_key
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in all_entries:
        k = merge_key(entry)
        k = MANUAL_ALIASES.get(k, k)
        groups[k].append(entry)

    # Merge each group, picking the highest-priority entry as canonical
    merged: list[dict[str, Any]] = []
    for k, entries in groups.items():
        entries.sort(
            key=lambda e: (
                SOURCE_PRIORITY.get(e.get("source", ""), 0),
                CONFIDENCE_RANK.get(e.get("confidence", ""), 0),
            ),
            reverse=True,
        )
        canon = entries[0]
        for other in entries[1:]:
            canon = merge_two(canon, other)
        # Strip None-valued keys
        canon = {kk: vv for kk, vv in canon.items() if vv is not None and vv != ""}
        merged.append(canon)

    print(f"merged into {len(merged)} unique researchers")

    # Sort by country, then by name
    def sort_key(e: dict[str, Any]) -> tuple[str, str]:
        country = (e.get("affiliation") or {}).get("country", "ZZZ") or "ZZZ"
        return (country, e.get("name", ""))

    merged.sort(key=sort_key)

    # Write
    yaml_dump = yaml.dump(
        merged,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=120,
    )
    header = (
        "# Vietnamese researchers working on causality.\n"
        "# Source: scripts/consolidate.py merges _data/researchers.yml + scripts/raw/*.yml.\n"
        "# To regenerate after adding raw scrape data: python scripts/consolidate.py\n"
        "# Schema: see CONTRIBUTING.md.\n\n"
    )
    OUT.write_text(header + yaml_dump, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

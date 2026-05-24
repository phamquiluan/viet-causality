"""Stage D snowball: from confirmed researchers (with OpenAlex IDs), walk the
co-author graph on causality-concept papers and surface new Vietnamese-named
co-authors who also have causality work.

Writes candidates to scripts/raw/stage_d_snowball.yml. Run scripts/consolidate.py
afterwards to merge.

Usage: python3 scripts/snowball.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_data" / "researchers.yml"
RAW = ROOT / "scripts" / "raw"
OUT = RAW / "stage_d_snowball.yml"

# Narrow causality concepts (same as audit script).
CAUSALITY_CONCEPTS = ["C158600405", "C11671645", "C163504300", "C115086926"]

# Distinctive Vietnamese surnames (HIGH-confidence tier).
VN_SURNAMES_HIGH = {
    "nguyen", "tran", "pham", "truong", "ngo", "huynh", "phan", "dang",
    "bui", "doan", "trinh",
}
# Lower-confidence Vietnamese surnames (need second signal).
VN_SURNAMES_LOW = {
    "le", "vu", "vo", "lam", "cao", "ho", "ly", "lieu", "do", "hoang",
    "duong", "dinh", "luong", "chu", "dao", "tang", "ta", "quach",
    "trieu", "ton", "diep",
}
# Vietnamese given-name tokens (used as second signal for LOW surnames).
VN_GIVEN_TOKENS = {
    "quoc", "hung", "dung", "anh", "linh", "hoa", "mai", "tuan", "thanh",
    "hai", "minh", "nam", "long", "phong", "tien", "duc", "phuc", "trung",
    "cuong", "khanh", "hieu", "bao", "son", "khoa", "vinh", "chi", "trang",
    "huong", "lan", "thu", "ngoc", "hanh", "huy", "quang", "manh", "dat",
    "toan", "khang", "van", "thi", "nhi", "vy", "ha", "kim", "thao", "lan",
    "kien", "dien", "nhan",
}

UA = "viet-causality-snowball/1.0 (mailto:phamquiluan@gmail.com)"


def curl_json(url: str) -> dict[str, Any] | None:
    try:
        res = subprocess.run(
            ["curl", "-sSL", "--fail", "-A", UA, "-H", "Accept: application/json", url],
            check=False, capture_output=True, timeout=30,
        )
        if res.returncode != 0:
            return None
        return json.loads(res.stdout.decode("utf-8"))
    except Exception:
        return None


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def is_vietnamese_name(name: str) -> bool:
    """Heuristic: distinctive Vietnamese surname, OR ambiguous surname + VN given token."""
    ascii_name = strip_diacritics(name).lower()
    tokens = re.findall(r"[a-z]+", ascii_name)
    if not tokens:
        return False
    # Try each token as potential surname (the convention varies: "Family, Given"
    # may appear as "Family Given" or "Given Family" after OpenAlex normalization).
    has_high = any(t in VN_SURNAMES_HIGH for t in tokens)
    has_low = any(t in VN_SURNAMES_LOW for t in tokens)
    has_given_signal = any(t in VN_GIVEN_TOKENS for t in tokens)
    if has_high:
        return True
    if has_low and has_given_signal:
        return True
    return False


def extract_oa_id(url: str) -> str | None:
    m = re.search(r"openalex\.org/(A\w+)", url or "")
    return m.group(1) if m else None


def normalize_name_key(name: str) -> str:
    """Same as consolidate.py merge_key, for dedup against existing list."""
    ascii_name = strip_diacritics(name).lower()
    tokens = re.findall(r"[a-z]+", ascii_name)
    return " ".join(sorted(tokens))


def pull_coauthors(seed_oa_id: str) -> dict[str, dict[str, Any]]:
    """For a seed author, fetch their causality-tagged works and return all coauthors."""
    coauthors: dict[str, dict[str, Any]] = {}
    concept_filter = "|".join(CAUSALITY_CONCEPTS)
    url = (
        f"https://api.openalex.org/works"
        f"?filter=author.id:{seed_oa_id},concepts.id:{concept_filter}"
        f"&per-page=200"
        f"&select=id,title,publication_year,authorships"
    )
    data = curl_json(url)
    if not data:
        return coauthors
    for work in data.get("results", []):
        for au in work.get("authorships", []):
            a = au.get("author") or {}
            aid = (a.get("id") or "").rsplit("/", 1)[-1]
            name = a.get("display_name") or ""
            if not aid or aid == seed_oa_id:
                continue
            if aid not in coauthors:
                coauthors[aid] = {
                    "id": aid,
                    "name": name,
                    "shared_works": [],
                    "institutions": set(),
                }
            coauthors[aid]["shared_works"].append({
                "title": work.get("title", ""),
                "year": work.get("publication_year"),
            })
            for inst in au.get("institutions", []) or []:
                if inst.get("display_name"):
                    coauthors[aid]["institutions"].add(inst["display_name"])
    return coauthors


def count_causality_works(oa_id: str) -> int:
    """Total works under narrow causality concepts."""
    total = 0
    for cid in CAUSALITY_CONCEPTS:
        url = f"https://api.openalex.org/works?filter=author.id:{oa_id},concepts.id:{cid}&per-page=1"
        data = curl_json(url)
        total += (data or {}).get("meta", {}).get("count", 0) if data else 0
        time.sleep(0.3)
    return total


def fetch_author_detail(oa_id: str) -> dict[str, Any] | None:
    return curl_json(f"https://api.openalex.org/authors/{oa_id}")


def main() -> int:
    # Load existing researchers and build dedup set.
    existing = yaml.safe_load(DATA.read_text(encoding="utf-8")) or []
    existing_keys = {normalize_name_key(e["name"]) for e in existing}
    existing_oa_ids = set()
    seeds: list[tuple[str, str]] = []  # (entry_id, oa_id)
    for e in existing:
        oa_url = (e.get("links") or {}).get("openalex", "")
        oa_id = extract_oa_id(oa_url)
        if oa_id:
            existing_oa_ids.add(oa_id)
            seeds.append((e["id"], oa_id))

    print(f"Existing list: {len(existing)} researchers; {len(existing_keys)} unique name keys; {len(seeds)} OpenAlex seeds.\n")

    # Phase 1: collect co-authors from each seed.
    print("Phase 1: walking co-author graph from each seed...")
    all_candidates: dict[str, dict[str, Any]] = {}  # aid -> {name, shared_works, institutions, seeds[]}
    for i, (eid, oa_id) in enumerate(seeds, 1):
        print(f"  [{i:2d}/{len(seeds)}] {eid} ({oa_id})...", flush=True)
        coauthors = pull_coauthors(oa_id)
        time.sleep(0.5)
        for aid, info in coauthors.items():
            if aid in existing_oa_ids:
                continue
            if aid not in all_candidates:
                all_candidates[aid] = {
                    "id": aid,
                    "name": info["name"],
                    "shared_works": info["shared_works"],
                    "institutions": info["institutions"],
                    "seeds": [eid],
                }
            else:
                all_candidates[aid]["shared_works"].extend(info["shared_works"])
                all_candidates[aid]["institutions"].update(info["institutions"])
                all_candidates[aid]["seeds"].append(eid)

    print(f"\nTotal unique co-authors found: {len(all_candidates)}")

    # Phase 2: filter by Vietnamese name heuristic.
    vn_candidates = {
        aid: c for aid, c in all_candidates.items()
        if is_vietnamese_name(c["name"]) and normalize_name_key(c["name"]) not in existing_keys
    }
    print(f"After Vietnamese-name filter + dedup: {len(vn_candidates)}")

    # Phase 3: verify each candidate has causality publications.
    print("\nPhase 3: verifying causality publications for each candidate...")
    confirmed: list[dict[str, Any]] = []
    for i, (aid, c) in enumerate(sorted(vn_candidates.items(), key=lambda x: -len(x[1]["shared_works"])), 1):
        print(f"  [{i:3d}/{len(vn_candidates)}] {c['name']:35s}", end="  ", flush=True)
        n_causal = count_causality_works(aid)
        print(f"causal_works={n_causal}  shared_with={len(set(c['seeds']))}")
        if n_causal >= 1:
            confirmed.append({**c, "n_causal_works": n_causal})

    print(f"\nConfirmed (>=1 causal work): {len(confirmed)}")

    # Phase 4: produce YAML output.
    out_entries = []
    for c in confirmed:
        # Slug from name
        name = c["name"]
        ascii_name = strip_diacritics(name).lower()
        tokens = re.findall(r"[a-z]+", ascii_name)
        slug = "-".join(tokens) + "-snowball"
        # Try to infer institution
        institutions = list(c["institutions"])
        inst = institutions[0] if institutions else "Unknown - please verify"
        country = "Unknown"
        out_entries.append({
            "id": slug,
            "name": name,
            "affiliation": {
                "institution": inst,
                "country": country,
                "position": "Unknown - please verify",
            },
            "links": {
                "openalex": f"https://openalex.org/{c['id']}",
            },
            "sub_areas": ["causal-ml"],
            "notes": (
                f"OpenAlex {c['n_causal_works']} causal-concept works. "
                f"Surfaced via co-authorship with {len(set(c['seeds']))} seed(s): "
                f"{', '.join(sorted(set(c['seeds']))[:3])}{'...' if len(set(c['seeds']))>3 else ''}"
            ),
            "source": "scrape_snowball",
            "confidence": "high" if c["n_causal_works"] >= 3 else "medium",
            "last_verified": "2026-05-24",
        })

    header = (
        "# Stage D snowball: co-author graph walk from confirmed researchers\n"
        "# Each entry has at least 1 work tagged under a narrow causality concept\n"
        "# AND was a co-author with a confirmed researcher on a causality paper.\n"
        "# See scripts/snowball.py for the logic.\n\n"
    )
    body = yaml.dump(out_entries, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    OUT.write_text(header + body, encoding="utf-8")
    print(f"\nWrote {len(out_entries)} candidates to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

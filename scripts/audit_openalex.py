"""Audit Stage B1 (OpenAlex) entries: for each entry with an OpenAlex author URL,
re-query OpenAlex and count works tagged under the four CAUSALITY-SPECIFIC concepts
(not the broader Topic T11303 "Bayesian Modeling and Causal Inference" that mixes
pure Bayesian methods with causal inference).

Reports any entry with zero works under all four narrow causality concepts as a
likely false positive.

Usage:
    python3 scripts/audit_openalex.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "scripts" / "raw"

# Four narrow causality concepts from OpenAlex.
CONCEPTS = {
    "C158600405": "causal inference",
    "C11671645":  "causal model",
    "C163504300": "causal structure",
    "C115086926": "causal reasoning",
}

UA = "viet-causality-audit/1.0 (mailto:phamquiluan@gmail.com)"


def http_json(url: str) -> dict[str, Any] | None:
    try:
        res = subprocess.run(
            ["curl", "-sSL", "--fail", "-A", UA, "-H", "Accept: application/json", url],
            check=False, capture_output=True, timeout=30,
        )
        if res.returncode != 0:
            print(f"  curl error ({res.returncode})", file=sys.stderr)
            return None
        return json.loads(res.stdout.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  error: {e}", file=sys.stderr)
        return None


def extract_oa_id(url: str) -> str | None:
    m = re.search(r"openalex\.org/(A\w+)", url or "")
    return m.group(1) if m else None


def count_causality_works(author_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cid, _name in CONCEPTS.items():
        url = (
            f"https://api.openalex.org/works"
            f"?filter=author.id:{author_id},concepts.id:{cid}&per-page=1"
        )
        data = http_json(url)
        counts[cid] = (data or {}).get("meta", {}).get("count", 0) if data else -1
        time.sleep(0.4)
    return counts


def main() -> int:
    stage_b1 = RAW / "stage_b1_openalex.yml"
    if not stage_b1.exists():
        print("stage_b1_openalex.yml not found", file=sys.stderr)
        return 1
    entries = yaml.safe_load(stage_b1.read_text(encoding="utf-8")) or []
    print(f"Auditing {len(entries)} Stage B1 entries against narrow causality concepts...\n")

    false_positives: list[tuple[str, dict[str, int]]] = []
    confirmed: list[tuple[str, dict[str, int]]] = []
    skipped: list[str] = []

    for i, e in enumerate(entries, 1):
        links = e.get("links") or {}
        oa_url = links.get("openalex", "")
        oa_id = extract_oa_id(oa_url)
        if not oa_id:
            skipped.append(e["id"])
            continue
        print(f"[{i:2d}/{len(entries)}] {e['id']:42s} {e['name']:30s}", end="  ", flush=True)
        counts = count_causality_works(oa_id)
        total = sum(c for c in counts.values() if c >= 0)
        summary = " ".join(f"{cid[1:]}={c}" for cid, c in counts.items())
        print(f"  total={total}  ({summary})")
        if total == 0:
            false_positives.append((e["id"], counts))
        else:
            confirmed.append((e["id"], counts))

    print("\n" + "=" * 80)
    print(f"AUDIT RESULTS:")
    print(f"  Confirmed (>=1 work under narrow causality concept): {len(confirmed)}")
    print(f"  Likely false positives (zero across all concepts):   {len(false_positives)}")
    print(f"  Skipped (no OpenAlex URL):                           {len(skipped)}")
    print()
    if false_positives:
        print("FALSE POSITIVES (consider removing):")
        for eid, counts in false_positives:
            print(f"  - {eid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

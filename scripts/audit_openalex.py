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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", default=[],
                        help="Raw YAML files to audit (default: all scripts/raw/*.yml)")
    args = parser.parse_args()

    files = [Path(f) for f in args.files] if args.files else sorted(RAW.glob("*.yml"))

    false_positives: list[tuple[str, str, dict[str, int]]] = []
    confirmed: list[tuple[str, str, int]] = []
    skipped_count = 0
    total_seen = 0

    for path in files:
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        oa_entries = [e for e in entries if extract_oa_id((e.get("links") or {}).get("openalex", ""))]
        if not oa_entries:
            continue
        print(f"\n=== {path.name}: {len(oa_entries)} entries with OpenAlex URL ===")
        for i, e in enumerate(oa_entries, 1):
            total_seen += 1
            oa_id = extract_oa_id((e.get("links") or {}).get("openalex", ""))
            print(f"  [{i:2d}/{len(oa_entries)}] {e['id']:42s} {e['name']:32s}", end="  ", flush=True)
            counts = count_causality_works(oa_id)  # type: ignore[arg-type]
            total = sum(c for c in counts.values() if c >= 0)
            print(f"total={total}")
            if total == 0:
                false_positives.append((path.name, e["id"], counts))
            else:
                confirmed.append((path.name, e["id"], total))

    print("\n" + "=" * 80)
    print("AUDIT RESULTS:")
    print(f"  Files scanned: {len(files)}")
    print(f"  Entries with OpenAlex URL audited: {total_seen}")
    print(f"  Confirmed (>=1 narrow-causality-concept work): {len(confirmed)}")
    print(f"  False positives (zero across all 4 concepts): {len(false_positives)}")
    if false_positives:
        print("\nFALSE POSITIVES by source file:")
        by_file: dict[str, list[str]] = {}
        for src, eid, _ in false_positives:
            by_file.setdefault(src, []).append(eid)
        for src in sorted(by_file):
            print(f"  {src}:")
            for eid in by_file[src]:
                print(f"    - {eid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

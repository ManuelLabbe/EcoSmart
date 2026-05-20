"""Build a side-by-side comparison Markdown table from two or more eval runs.

Usage:
  python compare_results.py evals/base_run evals/finetuned_run [evals/another_run ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FIELDS_ORDER = [
    "valid_json",
    "fields_present",
    "fire_present",
    "thermal_hotspot_intensity",
    "fire_size",
    "smoke_visible",
    "image_quality_limited",
]


def main():
    if len(sys.argv) < 3:
        print("usage: compare_results.py <eval_dir1> <eval_dir2> [...]")
        sys.exit(1)
    metas = []
    for d in sys.argv[1:]:
        p = Path(d) / "meta.json"
        meta = json.loads(p.read_text())
        meta["_path"] = d
        metas.append(meta)

    # header
    header = ["field"] + [f"{m['model']}" for m in metas]
    rows = [header, ["---"] * len(header)]
    for f in FIELDS_ORDER:
        row = [f]
        for m in metas:
            row.append(f"{m['per_field'].get(f, 0.0):.2f}")
        rows.append(row)
    rows.append(["**overall**"] + [f"**{m['overall']:.2f}**" for m in metas])
    rows.append(["**avg latency (s)**"] + [f"**{m['avg_latency_s']:.2f}**" for m in metas])
    rows.append(["**n samples**"] + [str(m["n"]) for m in metas])

    print("\n".join("| " + " | ".join(r) + " |" for r in rows))


if __name__ == "__main__":
    main()

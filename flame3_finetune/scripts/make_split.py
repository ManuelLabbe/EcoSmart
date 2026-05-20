"""Stratified 80/20 split on the Fire / No Fire category.

Output: data/split.csv (same columns as labels.csv + 'split' in {train,test}).
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "data" / "labels.csv"
OUT = ROOT / "data" / "split.csv"
SEED = 42
TEST_RATIO = 0.2


def main():
    rows = list(csv.DictReader(LABELS.open()))
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    rng = random.Random(SEED)
    for cat, items in by_cat.items():
        rng.shuffle(items)

    out_rows = []
    for cat, items in by_cat.items():
        n_test = round(len(items) * TEST_RATIO)
        for i, r in enumerate(items):
            r = dict(r)
            r["split"] = "test" if i < n_test else "train"
            out_rows.append(r)

    fieldnames = list(out_rows[0].keys())
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # report
    from collections import Counter
    counts = Counter((r["split"], r["category"]) for r in out_rows)
    print(f"Wrote {OUT}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    n_train = sum(1 for r in out_rows if r["split"] == "train")
    n_test = sum(1 for r in out_rows if r["split"] == "test")
    print(f"train={n_train} test={n_test} total={len(out_rows)}")


if __name__ == "__main__":
    main()

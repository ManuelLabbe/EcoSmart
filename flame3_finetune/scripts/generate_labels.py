"""Generate enriched JSON labels for every scene in FLAME 3 Sycan Marsh.

Output: data/labels.csv with columns
  scene_id, category (Fire/No Fire), rgb_path, thermal_path, label_json
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = ROOT / "dataset" / "FLAME 3 CV Dataset (Sycan Marsh)"
OUT_CSV = ROOT / "flame3_finetune" / "data" / "labels.csv"


def bin_intensity(max_temp: float) -> str:
    if max_temp <= 60:
        return "none"
    if max_temp <= 200:
        return "low"
    if max_temp <= 400:
        return "medium"
    return "high"


def bin_size(pct_hot: float) -> str:
    if pct_hot == 0:
        return "none"
    if pct_hot <= 1:
        return "small"
    if pct_hot <= 5:
        return "medium"
    return "large"


def smoke_heuristic(rgb: np.ndarray) -> bool:
    """Detect gray/whitish low-saturation bright pixels typical of smoke."""
    r, g, b = rgb[..., 0].astype(np.float32), rgb[..., 1].astype(np.float32), rgb[..., 2].astype(np.float32)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx == 0, 0, (mx - mn) / np.maximum(mx, 1e-6))
    val = mx / 255.0
    smoke_mask = (sat < 0.18) & (val > 0.55)
    return float(smoke_mask.mean()) > 0.05


def quality_limited(rgb: np.ndarray) -> bool:
    gray = rgb.mean(axis=2)
    m, s = float(gray.mean()), float(gray.std())
    return m < 30 or m > 220 or s < 15


def build_label(thermal_celsius: np.ndarray, rgb: np.ndarray) -> dict:
    max_t = float(thermal_celsius.max())
    pct_hot = float((thermal_celsius > 100).sum() / thermal_celsius.size * 100)
    fire = max_t > 60
    return {
        "fire_present": fire,
        "thermal_hotspot_intensity": bin_intensity(max_t),
        "fire_size": bin_size(pct_hot) if fire else "none",
        "smoke_visible": bool(smoke_heuristic(rgb)) if fire else False,
        "image_quality_limited": bool(quality_limited(rgb)),
    }


def iter_scenes():
    for cat in ["Fire", "No Fire"]:
        rgb_dir = DATASET / cat / "RGB" / "Corrected FOV"
        thr_jpg_dir = DATASET / cat / "Thermal" / "Raw JPG"
        thr_tif_dir = DATASET / cat / "Thermal" / "Celsius TIFF"
        for tif in sorted(thr_tif_dir.glob("*.TIFF")):
            stem = tif.stem
            rgb = rgb_dir / f"{stem}.JPG"
            thr = thr_jpg_dir / f"{stem}.JPG"
            if rgb.exists() and thr.exists():
                yield cat, stem, rgb, thr, tif


def main():
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    n_total = n_skipped = 0
    for cat, stem, rgb_path, thr_path, tif_path in iter_scenes():
        n_total += 1
        try:
            rgb = np.array(Image.open(rgb_path).convert("RGB"))
            tiff = np.array(Image.open(tif_path))
        except Exception as e:
            print(f"skip {cat}/{stem}: {e}")
            n_skipped += 1
            continue
        label = build_label(tiff, rgb)
        if (cat == "Fire") != label["fire_present"]:
            print(f"WARNING: category/label mismatch on {cat}/{stem}: max_temp={tiff.max():.1f}")
        rows.append({
            "scene_id": f"{cat.replace(' ', '_').lower()}_{stem}",
            "category": cat,
            "rgb_path": str(rgb_path.relative_to(ROOT)),
            "thermal_path": str(thr_path.relative_to(ROOT)),
            "thermal_tiff_path": str(tif_path.relative_to(ROOT)),
            "label_json": json.dumps(label),
        })
        if n_total % 100 == 0:
            print(f"processed {n_total}")

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"\nWrote {OUT_CSV} | total={n_total} skipped={n_skipped} kept={len(rows)}")

    # quick distribution
    from collections import Counter
    by_cat = Counter(r["category"] for r in rows)
    print(f"by category: {dict(by_cat)}")
    intens = Counter(json.loads(r["label_json"])["thermal_hotspot_intensity"] for r in rows)
    size = Counter(json.loads(r["label_json"])["fire_size"] for r in rows)
    smoke = Counter(json.loads(r["label_json"])["smoke_visible"] for r in rows)
    qual = Counter(json.loads(r["label_json"])["image_quality_limited"] for r in rows)
    print(f"intensity: {dict(intens)}")
    print(f"fire_size: {dict(size)}")
    print(f"smoke_visible: {dict(smoke)}")
    print(f"image_quality_limited: {dict(qual)}")


if __name__ == "__main__":
    main()

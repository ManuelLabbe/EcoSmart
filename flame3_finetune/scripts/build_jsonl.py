"""Build leap-finetune VLM SFT JSONL files from split.csv.

Stages all images into data/images/ with unique flat filenames and emits
  data/train.jsonl
  data/test.jsonl
using the shared SYSTEM_PROMPT / USER_TEXT from prompts.py.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from prompts import SYSTEM_PROMPT, USER_TEXT  # noqa: E402

REPO_ROOT = ROOT.parent
SPLIT = ROOT / "data" / "split.csv"
IMAGES_DIR = ROOT / "data" / "images"


def stage_image(src: Path, dst_name: str) -> str:
    dst = IMAGES_DIR / dst_name
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst_name


def make_row(rgb_name: str, thermal_name: str, label_json: str) -> dict:
    return {
        "messages": [
            {
                "role": "system",
                "content": [{"type": "text", "text": SYSTEM_PROMPT.strip()}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": rgb_name},
                    {"type": "image", "image": thermal_name},
                    {"type": "text", "text": USER_TEXT},
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": label_json}],
            },
        ]
    }


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(SPLIT.open()))
    train, test = [], []

    for r in rows:
        scene = r["scene_id"]  # e.g. fire_00001
        rgb_src = REPO_ROOT / r["rgb_path"]
        thr_src = REPO_ROOT / r["thermal_path"]
        rgb_name = f"{scene}_rgb.jpg"
        thr_name = f"{scene}_thermal.jpg"
        stage_image(rgb_src, rgb_name)
        stage_image(thr_src, thr_name)

        # The assistant response is a deterministic compact JSON of the label
        label_obj = json.loads(r["label_json"])
        label_text = json.dumps(label_obj)
        row = make_row(rgb_name, thr_name, label_text)
        (train if r["split"] == "train" else test).append(row)

    train_path = ROOT / "data" / "train.jsonl"
    test_path = ROOT / "data" / "test.jsonl"
    train_path.write_text("\n".join(json.dumps(r) for r in train) + "\n")
    test_path.write_text("\n".join(json.dumps(r) for r in test) + "\n")
    print(f"Wrote {train_path} ({len(train)} rows)")
    print(f"Wrote {test_path}  ({len(test)} rows)")
    print(f"Staged images in {IMAGES_DIR} ({len(list(IMAGES_DIR.iterdir()))} files)")


if __name__ == "__main__":
    main()

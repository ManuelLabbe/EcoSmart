"""Evaluate a VLM on the FLAME 3 test split.

Runs every test sample through the model, parses the JSON output, and computes
accuracy per field, overall accuracy, and average latency.

Backends:
  - local-gguf: uses llama-server (llama.cpp) via OpenAI-compatible API.
    Start it like:
        llama-server -m <backbone.gguf> --mmproj <mmproj.gguf> --host 0.0.0.0 --port 8080
  - hf:        uses transformers to load a HF checkpoint directly. Requires GPU.

Outputs:
  evals/<run-name>/report.md
  evals/<run-name>/results.json
  evals/<run-name>/meta.json
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from prompts import FIELDS, SYSTEM_PROMPT, USER_TEXT  # noqa: E402

DATA = ROOT / "data"
IMAGES = DATA / "images"
EVALS = ROOT / "evals"


def parse_json(text: str) -> dict | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    # extract first {...} block
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def encode_b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


def call_local_gguf(rgb_path: Path, thr_path: Path, base_url: str, model: str) -> tuple[str, float]:
    """Call llama-server's OpenAI-compatible API."""
    import requests

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_b64(rgb_path)}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_b64(thr_path)}"}},
                    {"type": "text", "text": USER_TEXT},
                ],
            },
        ],
        "max_tokens": 256,
        "temperature": 0.0,
    }
    t0 = time.time()
    r = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=120)
    r.raise_for_status()
    dt = time.time() - t0
    return r.json()["choices"][0]["message"]["content"], dt


def call_hf(rgb_path: Path, thr_path: Path, hf_state: dict) -> tuple[str, float]:
    """Call a transformers VLM checkpoint loaded in hf_state."""
    from PIL import Image

    processor = hf_state["processor"]
    model = hf_state["model"]
    rgb = Image.open(rgb_path).convert("RGB")
    thr = Image.open(thr_path).convert("RGB")

    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT.strip()}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": rgb},
                {"type": "image", "image": thr},
                {"type": "text", "text": USER_TEXT},
            ],
        },
    ]
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
        tokenize=True,
    ).to(model.device)
    in_len = inputs["input_ids"].shape[1]

    t0 = time.time()
    out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
    dt = time.time() - t0
    text = processor.batch_decode(out[:, in_len:], skip_special_tokens=True)[0]
    return text, dt


def load_hf(model_id: str) -> dict:
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_id, dtype="bfloat16", device_map="auto", trust_remote_code=True
    )
    model.eval()
    return {"processor": processor, "model": model}


def score(pred: dict | None, truth: dict) -> dict:
    per = {}
    valid_json = pred is not None
    fields_present = bool(pred) and all(k in pred for k in FIELDS)
    per["valid_json"] = int(valid_json)
    per["fields_present"] = int(fields_present)
    for f in FIELDS:
        if pred and f in pred:
            per[f] = int(pred[f] == truth[f])
        else:
            per[f] = 0
    return per


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["local-gguf", "hf"], required=True)
    p.add_argument("--model", required=True, help="HF repo id or llama-server model name tag")
    p.add_argument("--base-url", default="http://localhost:8080", help="llama-server URL")
    p.add_argument("--split", default="test", choices=["train", "test"])
    p.add_argument("--limit", type=int, default=0, help="0 = all")
    p.add_argument("--name", default=None, help="run name (default: timestamp)")
    args = p.parse_args()

    jsonl = DATA / f"{args.split}.jsonl"
    rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"Evaluating {len(rows)} samples on {args.split} split with {args.backend}:{args.model}")

    hf_state = load_hf(args.model) if args.backend == "hf" else None

    results = []
    sum_per = Counter()
    n = 0
    total_dt = 0.0
    for i, row in enumerate(rows, 1):
        user_content = row["messages"][1]["content"]
        rgb_name = user_content[0]["image"]
        thr_name = user_content[1]["image"]
        truth = json.loads(row["messages"][2]["content"][0]["text"])
        rgb_path = IMAGES / rgb_name
        thr_path = IMAGES / thr_name
        try:
            if args.backend == "local-gguf":
                text, dt = call_local_gguf(rgb_path, thr_path, args.base_url, args.model)
            else:
                text, dt = call_hf(rgb_path, thr_path, hf_state)
        except Exception as e:
            print(f"[{i}/{len(rows)}] ERROR: {e}")
            text, dt = "", 0.0
        pred = parse_json(text)
        s = score(pred, truth)
        for k, v in s.items():
            sum_per[k] += v
        n += 1
        total_dt += dt
        results.append(
            {
                "scene": rgb_name.rsplit("_rgb.jpg", 1)[0],
                "truth": truth,
                "pred": pred,
                "raw": text,
                "per_field": s,
                "latency_s": dt,
            }
        )
        if i % 10 == 0 or i == len(rows):
            running_overall = sum(sum_per[f] for f in FIELDS) / (n * len(FIELDS))
            print(f"[{i}/{len(rows)}] overall={running_overall:.3f}  avg_latency={total_dt/n:.2f}s")

    overall = sum(sum_per[f] for f in FIELDS) / (n * len(FIELDS)) if n else 0.0
    name = args.name or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = EVALS / name
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "backend": args.backend,
        "model": args.model,
        "split": args.split,
        "n": n,
        "avg_latency_s": total_dt / max(n, 1),
        "overall": overall,
        "per_field": {k: sum_per[k] / n for k in ["valid_json", "fields_present", *FIELDS]},
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))

    md = []
    md.append(f"# Eval report — {name}\n")
    md.append(f"- backend: `{args.backend}`")
    md.append(f"- model: `{args.model}`")
    md.append(f"- split: `{args.split}` ({n} samples)")
    md.append(f"- timestamp: {meta['timestamp']}\n")
    md.append("| field | accuracy |")
    md.append("|---|---|")
    for k in ["valid_json", "fields_present", *FIELDS]:
        md.append(f"| {k} | {sum_per[k]/n:.2f} |")
    md.append(f"| **overall** | **{overall:.2f}** |")
    md.append(f"| **avg latency (s)** | **{total_dt/n:.2f}** |")
    (out_dir / "report.md").write_text("\n".join(md) + "\n")
    print(f"\nWrote {out_dir}/report.md")
    print(f"Overall: {overall:.3f}  Avg latency: {total_dt/n:.2f}s")


if __name__ == "__main__":
    main()

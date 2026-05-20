# FLAME 3 — Fine-tuning LFM2.5-VL-450M on UAV wildfire imagery

Adaptation of the [Liquid4All wildfire-prevention cookbook](https://github.com/Liquid4All/cookbook/tree/main/examples/wildfire-prevention) to the [FLAME 3 Sycan Marsh dataset](https://www.kaggle.com/datasets/brycehopkins/flame-3-computer-vision-subset-sycan-marsh).

We take a compact Vision-Language Model (LFM2.5-VL-450M) and teach it to read **RGB + Thermal** image pairs captured from a UAV and emit a structured JSON risk report. We then compare the base model vs. the fine-tuned model on a held-out 20% test split.

## Pipeline overview

```
dataset/                                           (Kaggle download — 738 scenes)
   └── FLAME 3 CV Dataset (Sycan Marsh)/
        ├── Fire/    (622 scenes)
        └── No Fire/ (116 scenes)

flame3_finetune/
   ├── scripts/
   │   ├── generate_labels.py   → data/labels.csv      (enriched JSON per scene)
   │   ├── make_split.py        → data/split.csv      (stratified 80/20)
   │   ├── build_jsonl.py       → data/train.jsonl + test.jsonl + images/
   │   ├── prompts.py           (shared SYSTEM_PROMPT + schema)
   │   ├── evaluate.py          (run a model, write evals/<run>/report.md)
   │   └── compare_results.py   (build base vs fine-tuned table)
   ├── configs/
   │   ├── flame3_finetune.yaml       (full FT — H100 80GB)
   │   └── flame3_finetune_lora.yaml  (LoRA — 24GB cards)
   ├── data/                    (generated artifacts)
   └── evals/                   (eval run outputs)
```

## Output schema

The VLM is trained to emit:

```json
{
  "fire_present": true,
  "thermal_hotspot_intensity": "high",   // none | low | medium | high
  "fire_size": "small",                  // none | small | medium | large
  "smoke_visible": true,
  "image_quality_limited": false
}
```

Ground truth labels are derived algorithmically from the **Celsius TIFF** thermal channel (max temperature, hot-pixel area) and from RGB heuristics (saturation/brightness for smoke and quality), giving high-confidence training labels at zero API cost. See `scripts/generate_labels.py` for thresholds.

## Dataset stats (already generated)

```
total: 738 scenes
  Fire:    622
  No Fire: 116

split (stratified, seed=42):
  train: 591 (498 Fire / 93 No Fire)
  test:  147 (124 Fire / 23 No Fire)

label distribution:
  thermal_hotspot_intensity: high=482, medium=56, low=84, none=116
  fire_size:                 small=294, medium=273, large=55, none=116
  smoke_visible:             true=613, false=125
  image_quality_limited:     true=21, false=717
```

---

## Step 0 — Reproduce the data prep locally (already done)

```bash
cd /home/manuel-labbe/Desktop/comasa_hackaton
python3 flame3_finetune/scripts/generate_labels.py
python3 flame3_finetune/scripts/make_split.py
python3 flame3_finetune/scripts/build_jsonl.py
```

After this you have:
- `flame3_finetune/data/train.jsonl` and `test.jsonl` in leap-finetune VLM SFT format
- `flame3_finetune/data/images/` with 1476 staged images (`{scene_id}_rgb.jpg`, `{scene_id}_thermal.jpg`)

---

## Step 1 — Ship the data to the H100 box

From your laptop:

```bash
# package the things the H100 needs
cd /home/manuel-labbe/Desktop/comasa_hackaton/flame3_finetune
tar -czf flame3_data.tar.gz data/train.jsonl data/test.jsonl data/images/

# upload (replace user@host)
scp flame3_data.tar.gz user@h100-host:/workspace/
scp configs/flame3_finetune.yaml user@h100-host:/workspace/
scp scripts/evaluate.py scripts/prompts.py scripts/compare_results.py user@h100-host:/workspace/
```

On the H100:

```bash
ssh user@h100-host
cd /workspace
mkdir -p flame3 && tar -xzf flame3_data.tar.gz -C flame3 --strip-components=1
# Now /workspace/flame3/{train.jsonl, test.jsonl, images/}
```

The paths in `configs/flame3_finetune.yaml` already point to `/workspace/flame3/...`.

---

## Step 2 — Install leap-finetune on the H100

```bash
cd /workspace
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env  # or restart shell
git clone https://github.com/Liquid4All/leap-finetune.git
cd leap-finetune && uv sync
uv run huggingface-cli login   # required for model download
```

---

## Step 3 — Baseline evaluation (LFM2.5-VL-450M before fine-tuning)

You need a `llama-server` running the GGUF version of the base model.

```bash
# install llama.cpp (one-time)
git clone https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp
cd /opt/llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build -j

# download base GGUF (Q8_0)
mkdir -p /workspace/models/base && cd /workspace/models/base
huggingface-cli download LiquidAI/LFM2.5-VL-450M-GGUF --include "LFM2.5-VL-450M-Q8_0.gguf" --local-dir .
huggingface-cli download LiquidAI/LFM2.5-VL-450M-GGUF --include "mmproj-LFM2.5-VL-450M-F16.gguf" --local-dir .

# start the server (keep this terminal open or use tmux/screen)
/opt/llama.cpp/build/bin/llama-server \
  -m /workspace/models/base/LFM2.5-VL-450M-Q8_0.gguf \
  --mmproj /workspace/models/base/mmproj-LFM2.5-VL-450M-F16.gguf \
  --host 0.0.0.0 --port 8080 -c 4096 --gpu-layers 999
```

In a second terminal, run the eval:

```bash
cd /workspace
pip install requests pillow
python3 evaluate.py \
  --backend local-gguf \
  --model lfm2.5-vl-450m \
  --base-url http://localhost:8080 \
  --split test \
  --name base
```

Output lands in `/workspace/evals/base/{report.md, results.json, meta.json}`.

---

## Step 4 — Fine-tune

Stop the llama-server (frees GPU memory), then:

```bash
cd /workspace/leap-finetune
uv run leap-finetune /workspace/flame3_finetune.yaml
```

The run writes a checkpoint per epoch to `outputs/flame3-wildfire/<run-name>/`. With 591 training samples, batch=2, grad accum=8 (effective batch 16), 3 epochs, this is ~110 optimizer steps. Expect ~30-50 min on a single H100.

---

## Step 5 — Quantize the fine-tuned checkpoint

The cookbook ships `quantize.py` to produce the GGUF pair. Easiest route:

```bash
git clone https://github.com/Liquid4All/cookbook.git /opt/cookbook
cd /opt/cookbook/examples/wildfire-prevention
uv sync
uv run scripts/quantize.py \
  --checkpoint /workspace/leap-finetune/outputs/flame3-wildfire/<run-name>/<checkpoint> \
  --output /workspace/models/flame3/lfm2.5-vl-flame3-Q8_0.gguf
```

This produces:
- `/workspace/models/flame3/lfm2.5-vl-flame3-Q8_0.gguf`
- `/workspace/models/flame3/mmproj-lfm2.5-vl-flame3-Q8_0.gguf`

---

## Step 6 — Fine-tuned evaluation

Same as Step 3, but pointing llama-server at the fine-tuned GGUF:

```bash
# stop the previous llama-server, then:
/opt/llama.cpp/build/bin/llama-server \
  -m /workspace/models/flame3/lfm2.5-vl-flame3-Q8_0.gguf \
  --mmproj /workspace/models/flame3/mmproj-lfm2.5-vl-flame3-Q8_0.gguf \
  --host 0.0.0.0 --port 8080 -c 4096 --gpu-layers 999
```

In a second terminal:

```bash
cd /workspace
python3 evaluate.py \
  --backend local-gguf \
  --model lfm2.5-vl-450m-flame3 \
  --base-url http://localhost:8080 \
  --split test \
  --name finetuned
```

---

## Step 7 — Comparison table

```bash
cd /workspace
python3 compare_results.py evals/base evals/finetuned
```

You'll get something like:

```
| field                       | lfm2.5-vl-450m | lfm2.5-vl-450m-flame3 |
| ---                         | ---            | ---                   |
| valid_json                  | 1.00           | 1.00                  |
| fields_present              | 1.00           | 1.00                  |
| fire_present                | 0.85           | 0.99                  |
| thermal_hotspot_intensity   | 0.12           | 0.81                  |
| fire_size                   | 0.18           | 0.78                  |
| smoke_visible               | 0.71           | 0.92                  |
| image_quality_limited       | 0.30           | 0.93                  |
| **overall**                 | **0.43**       | **0.89**              |
| **avg latency (s)**         | **0.65**       | **0.55**              |
| **n samples**               | 147            | 147                   |
```

(Exact numbers will depend on the run — the cookbook reports overall 0.38 → 0.84 on the analogous task.)

---

## Notes / tweaks

- **Test set size**: 147 samples (124 Fire / 23 No Fire). Imbalanced toward Fire (~84%), so `fire_present` accuracy of a naive "always Fire" predictor would be 0.84 — keep that in mind when reading the table.
- **Why full FT, not LoRA**: UAV thermal/RGB imagery is severely underrepresented in pretraining data. The multimodal projector benefits more from full updates than from LoRA adapters on top of frozen weights. At 450M params this fits a single H100.
- **Seed**: split and training both pinned to `seed=42` for reproducibility.
- **Labels are derived, not human-annotated**: we use thermal max-temp thresholds and RGB heuristics to label each scene. This is the right move for `fire_present`/`thermal_hotspot_intensity`/`fire_size` because the Celsius TIFF is ground truth. `smoke_visible` and `image_quality_limited` are noisier — a future improvement is to pass these through Claude Opus for a labeling sanity pass.

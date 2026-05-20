# Runbook — H100 (camino corto)

Vamos por la vía mínima: **transformers directo, sin GGUF, sin llama.cpp, sin cuantizar**.
Total estimado en la H100: **~50-70 min**.

## Antes de conectar a la H100 (en el laptop)

Ya está hecho. Solo queda empaquetar el bundle:

```bash
cd /home/manuel-labbe/Desktop/comasa_hackaton/flame3_finetune

tar -czf /tmp/flame3_bundle.tar.gz \
  data/train.jsonl data/test.jsonl data/images/ \
  scripts/evaluate.py scripts/prompts.py scripts/compare_results.py \
  configs/flame3_finetune.yaml
```

(~80MB. Tamaño exacto: depende de la compresión JPG.)

## En la H100

Asumo `/workspace` como home de la sesión.

### 1. Subir y desempaquetar

Desde tu laptop:
```bash
scp /tmp/flame3_bundle.tar.gz USER@HOST:/workspace/
```

En la H100:
```bash
cd /workspace
tar -xzf flame3_bundle.tar.gz
mkdir -p flame3 && mv data/train.jsonl data/test.jsonl data/images flame3/
mv scripts/* . && mv configs/flame3_finetune.yaml .
rmdir scripts configs data
```

Ahora tienes:
```
/workspace/
├── flame3/{train.jsonl, test.jsonl, images/}
├── evaluate.py, prompts.py, compare_results.py
└── flame3_finetune.yaml
```

### 2. Setup (una sola vez)

```bash
# uv + leap-finetune
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env  # o el path donde uv quedó
git clone https://github.com/Liquid4All/leap-finetune.git
cd leap-finetune && uv sync && cd ..

# deps mínimas para evaluate.py
pip install transformers torch pillow huggingface_hub accelerate

# HF login (para descargar el modelo base)
huggingface-cli login
```

### 3. Eval base (modelo sin fine-tunear)

```bash
cd /workspace
python3 evaluate.py \
  --backend hf \
  --model LiquidAI/LFM2.5-VL-450M \
  --split test \
  --name base
```

Tarda ~5-10 min. Genera `/workspace/evals/base/{report.md, results.json, meta.json}`.

### 4. Fine-tune

```bash
cd /workspace/leap-finetune
uv run leap-finetune /workspace/flame3_finetune.yaml
```

~30-50 min. El checkpoint queda en `/workspace/leap-finetune/outputs/flame3-wildfire/<run-name>/checkpoint-*/`.

Apunta a la última checkpoint (la del último epoch):
```bash
ls /workspace/leap-finetune/outputs/flame3-wildfire/*/checkpoint-* -d | tail -1
```

### 5. Eval fine-tuned (sin cuantizar — directo desde el checkpoint HF)

```bash
cd /workspace
python3 evaluate.py \
  --backend hf \
  --model /workspace/leap-finetune/outputs/flame3-wildfire/<run-name>/checkpoint-XXX \
  --split test \
  --name finetuned
```

### 6. Tabla comparativa

```bash
python3 compare_results.py evals/base evals/finetuned
```

Eso es todo. Copia la tabla al README final.

---

## Qué saltamos vs. el cookbook original

| Paso del cookbook | Nuestro recorte |
|---|---|
| Compilar `llama.cpp` | Skipped — usamos `transformers` |
| Descargar GGUF base + mmproj | Skipped — descarga HF auto |
| Levantar `llama-server` para eval base | Skipped |
| Cuantizar el checkpoint FT a GGUF | Skipped — `evaluate.py` carga el checkpoint HF directo |
| Levantar `llama-server` con FT GGUF | Skipped |

Resultado: una sesión de SSH lineal, sin saltar entre terminales para llama-server.

## Si algo falla

- **OOM en fine-tune**: bajar `per_device_train_batch_size: 1` y subir `gradient_accumulation_steps: 16` en `flame3_finetune.yaml`.
- **OOM en eval HF**: el modelo es 450M en bf16 (~1GB), no debería ser problema en H100.
- **Path del checkpoint**: leap-finetune nombra el directorio así: `outputs/<project_name>/<run_name>/checkpoint-<step>/`. Usa la última checkpoint guardada (la del epoch 3).

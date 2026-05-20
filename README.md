# EcoSmart — COMASA Hackathon 2026

Prototipo de plataforma de inteligencia artificial para plantas termoeléctricas a biomasa. Combina **detección visual de incendios** (VLM fine-tuneado) y **mantenimiento predictivo** (Transformer multi-label sobre sensores industriales).

---

## Componentes

### 1. Detección de incendios con VLM (`flame3_finetune/`)
Fine-tuning del modelo **LFM2.5-VL-450M** (Liquid AI) sobre el dataset FLAME3 Computer Vision Subset — Sycan Marsh. El modelo recibe pares de imágenes RGB + térmica de dron UAV y retorna un JSON estructurado con evaluación de riesgo de incendio.

**Resultado:** accuracy overall 0.21 (base) → **0.86 (fine-tuned)** sobre 147 muestras de test.

### 2. Mantenimiento predictivo con Transformer (`predictive_maintenance/`)
**SensorTransformer** — Transformer encoder entrenado sobre el dataset público AI4I 2020 (UCI/Kaggle) para clasificación multi-label de modos de falla industrial en tiempo real.

**Resultado:** AUC > 0.92 en 3 de 5 modos de falla (TWF, HDF, OSF). Incluye visualización de attention weights para interpretabilidad.

---

## Estructura del proyecto

```
comasa_hackaton/
│
├── README.md
├── requirements.txt              # Dependencias Python del entorno
├── ai4i2020.csv                  # Dataset AI4I 2020 (10k muestras, sensores industriales)
│
├── pdm_analysis.ipynb            # Notebook principal: PdM — tutorial, resultados, inferencia
├── flame3_analysis.ipynb         # Notebook principal: FLAME3 — fine-tuning, comparación
│
├── predictive_maintenance/       # Módulo de mantenimiento predictivo
│   ├── preprocess.py             # Carga y feature engineering del dataset
│   ├── dataset.py                # SensorDataset con ventana deslizante (W=20)
│   ├── model.py                  # SensorTransformer (152k params, 3 layers, 4 heads)
│   ├── train_transformer.py      # Loop de entrenamiento (AdamW + Cosine LR + early stopping)
│   ├── evaluate_transformer.py   # Evaluación: AUC por modo, threshold óptimo
│   ├── attention_viz.py          # Visualización de attention weights
│   ├── plots_transformer.py      # Gráficos ROC, PR, AUC por modo
│   ├── models/
│   │   ├── transformer_best.pt   # Pesos del modelo entrenado (620 KB)
│   │   ├── transformer_config.json
│   │   └── transformer_stats.pkl # Stats de normalización (mean/std)
│   └── outputs/
│       ├── transformer_eval_final.json
│       └── plots/                # 11 gráficos PNG generados
│
└── flame3_finetune/              # Módulo de detección de incendios VLM
    ├── scripts/
    │   ├── generate_labels.py    # Deriva etiquetas JSON desde TIFFs de temperatura
    │   ├── prompts.py            # System prompt + schema JSON para el VLM
    │   ├── evaluate.py           # Inferencia y métricas base vs fine-tuned
    │   └── compare_results.py    # Tabla comparativa
    ├── configs/
    │   └── flame3_finetune.yaml  # Config de leap-finetune (Liquid AI)
    └── evals/                    # Resultados de evaluación (ignorados en git — ver nota)
```

> **Nota datasets:** `dataset/` (imágenes FLAME3, 7 GB) está excluido por tamaño. Los pesos del modelo fine-tuneado están en HuggingFace:
> ```bash
> hf download ManuelLabbe/ecosmart-flame3-finetune --local-dir flame3_finetune/model_finetuned/
> ```

---

## Setup del entorno

### Requisitos
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) o Anaconda
- Python 3.14
- CUDA 12+ (opcional, para entrenamiento en GPU)

### Crear entorno `ecosmart`

```bash
conda create -n ecosmart python=3.14 -y
conda activate ecosmart
pip install -r requirements.txt
pip install scikit-learn
```

### Registrar kernel en Jupyter

```bash
conda activate ecosmart
python -m ipykernel install --user --name ecosmart --display-name "ecosmart"
jupyter lab
```

---

## Entrenamiento del Transformer (PdM)

```bash
cd predictive_maintenance
conda run -n ecosmart python train_transformer.py
conda run -n ecosmart python evaluate_transformer.py
conda run -n ecosmart python attention_viz.py
conda run -n ecosmart python plots_transformer.py
```

---

## Fine-tuning del VLM (FLAME3)

El fine-tuning se ejecutó en Lightning AI (H100 80GB). Ver `flame3_finetune/RUNBOOK_H100.md` para instrucciones completas.

```bash
# Generar etiquetas desde TIFFs de temperatura
cd flame3_finetune
conda run -n ecosmart python scripts/generate_labels.py
```

---

## Tecnologías clave

| Componente | Tecnología |
|---|---|
| VLM fine-tuning | LFM2.5-VL-450M (Liquid AI) + leap-finetune |
| PdM Transformer | PyTorch 2.x, 152k params, int8-deployable |
| Edge deployment | ESP32-S3 via ESP-DL (ops: MatMul, Softmax, LayerNorm) |
| Análisis | Jupyter Lab, Matplotlib, scikit-learn |
| Dataset PdM | AI4I 2020 — UCI / Kaggle |
| Dataset VLM | FLAME3 Computer Vision Subset — Sycan Marsh |

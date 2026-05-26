# EcoSmart — COMASA Hackathon 2026

Plataforma de inteligencia artificial para plantas termoeléctricas a biomasa. Combina **detección visual de incendios** (VLM fine-tuneado), **mantenimiento predictivo** (Transformer multi-label sobre sensores industriales), **monitoreo IoT en tiempo real** (ESP32 + AWS) y **agentes de IA conversacionales** (Claude MCP + Skills).

---

## Arquitectura general

```
┌─────────────────────────────────────────────────────────────────┐
│                        PLANTA COMASA                            │
│  LoRa Nodes (sensores) ──► ESP32 Gateway ──► AWS IoT Core       │
└────────────────────────────────┬────────────────────────────────┘
                                 │ MQTT
                    ┌────────────▼────────────┐
                    │   AWS (SAM / Lambda)     │
                    │  S3 → Glue → Athena      │
                    │  MCP Lambda (ecosmart-mcp)│
                    └────┬──────────┬──────────┘
                         │          │
              ┌──────────▼──┐  ┌────▼──────────────┐
              │  Metabase    │  │   Claude Code      │
              │  Dashboard   │  │   (MCP + Skills)   │
              └─────────────┘  └────────────────────┘
```

---

## Componentes

### 1. Detección de incendios con VLM (`flame3_finetune/`)

Fine-tuning del modelo **LFM2.5-VL-450M** (Liquid AI) sobre el dataset FLAME3 Computer Vision Subset — Sycan Marsh. El modelo recibe pares de imágenes RGB + térmica de dron UAV y retorna un JSON estructurado con evaluación de riesgo de incendio.

**Resultado:** accuracy overall 0.21 (base) → **0.86 (fine-tuned)** sobre 147 muestras de test.

### 2. Mantenimiento predictivo con Transformer (`predictive_maintenance/`)

**SensorTransformer** — Transformer encoder entrenado sobre el dataset público AI4I 2020 (UCI/Kaggle) para clasificación multi-label de modos de falla industrial en tiempo real.

**Resultado:** AUC > 0.92 en 3 de 5 modos de falla (TWF, HDF, OSF). Incluye visualización de attention weights para interpretabilidad.

El modelo fue exportado a C (`transformer_weights.h`) para despliegue en edge vía ESP-DL.

### 3. Firmware ESP32 (`esp32_firmware/`)

Gateway IoT en C/C++ sobre ESP-IDF que:
- Recibe lecturas de nodos LoRa (temperatura, vibración, presión, corriente)
- Corre inferencia local del SensorTransformer cuantizado (int8) vía ESP-DL
- Publica lecturas + predicciones a AWS IoT Core vía MQTT con TLS
- Emite alertas automáticas cuando la inferencia detecta falla inminente

### 4. Infraestructura AWS (`infrastructure/`)

Stack SAM completo desplegado en AWS:

| Servicio | Rol |
|---|---|
| AWS IoT Core | Recibe mensajes MQTT del ESP32 |
| S3 | Almacena lecturas y alertas como JSON |
| AWS Glue | Cataloga las tablas para consultas SQL |
| Amazon Athena | Motor de consultas serverless sobre S3 |
| EC2 (Metabase) | Dashboard de visualización operacional |
| Lambda (MCP) | Servidor MCP HTTP para agentes de IA |

### 5. Servidor MCP (`infrastructure/mcp_lambda/`)

Lambda que expone **8 herramientas MCP** sobre el lago de datos Athena, consumibles por Claude Code u otros agentes LLM:

| Herramienta | Descripción |
|---|---|
| `query_sensor_readings` | Lecturas históricas de sensores por nodo/equipo |
| `query_alerts` | Alertas filtradas por severidad y nodo |
| `get_equipment_summary` | Estado global de todos los equipos |
| `list_nodes` | Nodos LoRa registrados con metadatos |
| `get_node_trend` | Serie temporal de un nodo (últimas N lecturas) |
| `get_top_risk_equipment` | Ranking de equipos con mayor riesgo de falla |
| `get_failure_mode_heatmap` | Heatmap de modos de falla activos por equipo |
| `run_diagnostic` | Diagnóstico completo de un nodo o equipo |

### 6. Skills de Claude Code (`skills/`)

Tres skills especializados para operadores de planta, listos para subir a la plataforma Claude:

| Skill | Función |
|---|---|
| `ecosmart-informe-ejecutivo` | Genera informe ejecutivo HTML del estado de la planta con KPIs, equipos críticos y tendencias |
| `ecosmart-orden-trabajo` | Crea órdenes de trabajo predictivas priorizadas según riesgo y modo de falla detectado |
| `ecosmart-investigacion-anomalia` | Investiga anomalías con RCA estructurado: hipótesis, evidencia, acción correctiva |

---

## Estructura del proyecto

```
comasa_hackaton/
│
├── README.md
├── requirements.txt
├── ai4i2020.csv                      # Dataset AI4I 2020 (10k muestras)
│
├── pdm_analysis.ipynb                # Notebook PdM: tutorial, resultados, inferencia
├── flame3_analysis.ipynb             # Notebook VLM: fine-tuning, comparación
│
├── predictive_maintenance/           # Módulo de mantenimiento predictivo
│   ├── model.py                      # SensorTransformer (152k params, 3 layers, 4 heads)
│   ├── train_transformer.py
│   ├── evaluate_transformer.py
│   ├── attention_viz.py
│   ├── models/
│   │   ├── transformer_best.pt       # Pesos del modelo (620 KB)
│   │   └── transformer_config.json
│   └── outputs/plots/                # Gráficos ROC, PR, AUC
│
├── flame3_finetune/                  # Módulo de detección de incendios VLM
│   ├── scripts/
│   │   ├── generate_labels.py
│   │   ├── prompts.py
│   │   └── evaluate.py
│   └── configs/flame3_finetune.yaml
│
├── esp32_firmware/                   # Firmware gateway IoT
│   ├── main/
│   │   ├── app_main.c               # Loop principal: LoRa → inferencia → MQTT
│   │   ├── sensor_transformer.c     # Inferencia int8 en C (ESP-DL)
│   │   └── transformer_weights.h    # Pesos cuantizados (2 MB)
│   └── CMakeLists.txt
│
├── infrastructure/                   # Stack AWS SAM
│   ├── template.yaml                 # Definición completa del stack
│   ├── mcp_lambda/handler.py         # Servidor MCP (8 herramientas Athena)
│   ├── tables/                       # DDL Athena
│   └── scripts/                      # Scripts de aprovisionamiento
│
└── skills/                           # Skills Claude Code para operadores
    ├── ecosmart-informe-ejecutivo/
    ├── ecosmart-investigacion-anomalia/
    └── ecosmart-orden-trabajo/
```

> **Nota datasets:** `dataset/` (imágenes FLAME3, 7 GB) está excluido por tamaño. Los pesos del modelo fine-tuneado están en HuggingFace:
> ```bash
> hf download ManuelLabbe/ecosmart-flame3-finetune --local-dir flame3_finetune/model_finetuned/
> ```

---

## Setup del entorno

```bash
conda create -n ecosmart python=3.14 -y
conda activate ecosmart
pip install -r requirements.txt
pip install scikit-learn
python -m ipykernel install --user --name ecosmart --display-name "ecosmart"
jupyter lab
```

---

## Entrenamiento del Transformer (PdM)

```bash
cd predictive_maintenance
conda run -n ecosmart python train_transformer.py
conda run -n ecosmart python evaluate_transformer.py
conda run -n ecosmart python plots_transformer.py
```

---

## Fine-tuning del VLM (FLAME3)

El fine-tuning se ejecutó en Lightning AI (H100 80GB). Ver `flame3_finetune/RUNBOOK_H100.md` para instrucciones completas.

```bash
cd flame3_finetune
conda run -n ecosmart python scripts/generate_labels.py
```

---

## Despliegue AWS

```bash
cd infrastructure
make deploy   # sam build + sam deploy --profile labbelopez.manuel@gmail.com
```

---

## Tecnologías clave

| Componente | Tecnología |
|---|---|
| VLM fine-tuning | LFM2.5-VL-450M (Liquid AI) + leap-finetune |
| PdM Transformer | PyTorch 2.x, 152k params, int8-deployable |
| Edge deployment | ESP32-S3 + ESP-DL (MatMul, Softmax, LayerNorm) |
| Conectividad IoT | LoRa + AWS IoT Core (MQTT/TLS) |
| Data lake | S3 + Glue + Athena (serverless) |
| Dashboard | Metabase v0.61 sobre EC2 |
| Agentes IA | Claude Code + MCP (HTTP Lambda) |
| Skills LLM | 3 Claude Skills para operadores de planta |
| Dataset PdM | AI4I 2020 — UCI / Kaggle |
| Dataset VLM | FLAME3 Computer Vision Subset — Sycan Marsh |

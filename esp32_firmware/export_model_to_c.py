"""
export_model_to_c.py — exporta los pesos del SensorTransformer como arrays C (float32).
Genera main/transformer_weights.h listo para compilar en ESP-IDF.

Uso: python export_model_to_c.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import torch
import pickle
import numpy as np

MODEL_PATH = "../predictive_maintenance/models/transformer_best.pt"
STATS_PATH = "../predictive_maintenance/models/transformer_stats.pkl"
OUT_PATH   = "main/transformer_weights.h"

# ── Cargar checkpoint ───────────────────────────────────────────────────────────
ck = torch.load(MODEL_PATH, map_location="cpu")
sd = ck["model_state_dict"] if "model_state_dict" in ck else ck

# ── Cargar stats de normalización ──────────────────────────────────────────────
with open(STATS_PATH, "rb") as f:
    stats = pickle.load(f)
mean = np.array(stats["mean"], dtype=np.float32)
std  = np.array(stats["std"],  dtype=np.float32)

# ── Helpers ─────────────────────────────────────────────────────────────────────
def c_array(name: str, arr: np.ndarray, comment: str = "") -> str:
    arr = arr.astype(np.float32).flatten()
    vals = ", ".join(f"{v:.8f}f" for v in arr)
    cmt = f"  // {comment}" if comment else ""
    return f"static const float {name}[{len(arr)}] = {{{vals}}};{cmt}\n"

lines = [
    "#pragma once\n",
    "/* Auto-generado por export_model_to_c.py — NO editar manualmente */\n\n",
    "#include <stdint.h>\n\n",
    "/* Arquitectura: d_model=64, n_heads=4, n_layers=3, dim_ff=256, window=20, n_feat=6 */\n",
    "#define ST_D_MODEL        64\n",
    "#define ST_N_HEADS         4\n",
    "#define ST_N_LAYERS        3\n",
    "#define ST_DIM_FF        256\n",
    "#define ST_WINDOW         20\n",
    "#define ST_N_FEATURES      6\n",
    "#define ST_N_LABELS        5\n",
    "#define ST_HEAD_DIM       16   /* D_MODEL / N_HEADS */\n\n",
    "/* Normalización de entrada */\n",
    c_array("ST_NORM_MEAN", mean, "mean por feature"),
    c_array("ST_NORM_STD",  std,  "std por feature"),
    "\n/* Input projection (64, 6) */\n",
    c_array("ST_INPUT_PROJ_W", sd["input_proj.weight"].numpy()),
    c_array("ST_INPUT_PROJ_B", sd["input_proj.bias"].numpy()),
    "\n/* Positional encoding (21, 64) */\n",
    c_array("ST_POS_ENC", sd["pos_enc.pe"].numpy().squeeze(0)),
]

for i in range(3):
    p = f"transformer.layers.{i}"
    lines += [
        f"\n/* === Encoder Layer {i} === */\n",
        f"/* Self-attention QKV in_proj (192, 64) */\n",
        c_array(f"ST_L{i}_QKV_W",   sd[f"{p}.self_attn.in_proj_weight"].numpy()),
        c_array(f"ST_L{i}_QKV_B",   sd[f"{p}.self_attn.in_proj_bias"].numpy()),
        c_array(f"ST_L{i}_OUTPROJ_W", sd[f"{p}.self_attn.out_proj.weight"].numpy()),
        c_array(f"ST_L{i}_OUTPROJ_B", sd[f"{p}.self_attn.out_proj.bias"].numpy()),
        f"/* FFN linear1 (256, 64) + linear2 (64, 256) */\n",
        c_array(f"ST_L{i}_FF1_W", sd[f"{p}.linear1.weight"].numpy()),
        c_array(f"ST_L{i}_FF1_B", sd[f"{p}.linear1.bias"].numpy()),
        c_array(f"ST_L{i}_FF2_W", sd[f"{p}.linear2.weight"].numpy()),
        c_array(f"ST_L{i}_FF2_B", sd[f"{p}.linear2.bias"].numpy()),
        f"/* LayerNorm 1 + 2 */\n",
        c_array(f"ST_L{i}_NORM1_W", sd[f"{p}.norm1.weight"].numpy()),
        c_array(f"ST_L{i}_NORM1_B", sd[f"{p}.norm1.bias"].numpy()),
        c_array(f"ST_L{i}_NORM2_W", sd[f"{p}.norm2.weight"].numpy()),
        c_array(f"ST_L{i}_NORM2_B", sd[f"{p}.norm2.bias"].numpy()),
    ]

lines += [
    "\n/* Final LayerNorm */\n",
    c_array("ST_NORM_W", sd["norm.weight"].numpy()),
    c_array("ST_NORM_B", sd["norm.bias"].numpy()),
    "\n/* Classifier: Linear(64→32) + GELU + Linear(32→5) */\n",
    c_array("ST_CLS0_W", sd["classifier.0.weight"].numpy()),
    c_array("ST_CLS0_B", sd["classifier.0.bias"].numpy()),
    c_array("ST_CLS3_W", sd["classifier.3.weight"].numpy()),
    c_array("ST_CLS3_B", sd["classifier.3.bias"].numpy()),
]

with open(OUT_PATH, "w") as f:
    f.writelines(lines)

total_floats = sum(
    np.array(v).size for v in sd.values()
) + len(mean) + len(std)
print(f"Exportado: {OUT_PATH}")
print(f"Total floats: {total_floats:,}  ({total_floats*4/1024:.0f} KB)")

"""
validate_c_vs_pytorch.py
Compara la salida del SensorTransformer en PyTorch contra
una reimplementación NumPy que replica exactamente el código C del ESP32.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import torch
import pickle

# ── Cargar modelo PyTorch ───────────────────────────────────────────────────
from predictive_maintenance.model import SensorTransformer
ck = torch.load("../predictive_maintenance/models/transformer_best.pt", map_location="cpu")
sd = ck["model_state_dict"] if "model_state_dict" in ck else ck

model = SensorTransformer(n_features=6)
model.load_state_dict(sd)
model.eval()

with open("../predictive_maintenance/models/transformer_stats.pkl", "rb") as f:
    stats = pickle.load(f)
mean = np.array(stats["mean"], dtype=np.float32)
std  = np.array(stats["std"],  dtype=np.float32)

# ── Reimplementación NumPy del código C ─────────────────────────────────────
def layer_norm_np(x, gamma, beta, eps=1e-5):
    m = x.mean(-1, keepdims=True)
    v = x.var(-1, keepdims=True)
    return (x - m) / np.sqrt(v + eps) * gamma + beta

def softmax_np(x):
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)

def gelu_np(x):
    return x * 0.5 * (1 + np.vectorize(lambda v: float(__import__('math').erf(v * 0.7071067811865476)))(x))

def sigmoid_np(x):
    return 1 / (1 + np.exp(-x))

def mha_np(x, qkv_w, qkv_b, out_w, out_b, n_heads=4):
    T, D = x.shape
    Hd = D // n_heads
    scale = 1.0 / np.sqrt(Hd)
    Q = x @ qkv_w[:D].T + qkv_b[:D]
    K = x @ qkv_w[D:2*D].T + qkv_b[D:2*D]
    V = x @ qkv_w[2*D:].T + qkv_b[2*D:]
    out = np.zeros_like(x)
    for h in range(n_heads):
        sl = slice(h*Hd, (h+1)*Hd)
        scores = softmax_np(Q[:, sl] @ K[:, sl].T * scale)
        out[:, sl] = scores @ V[:, sl]
    return out @ out_w.T + out_b

def encoder_layer_np(x, l):
    D = x.shape[1]
    # Pre-LN + attention
    xn = layer_norm_np(x, l['n1_w'], l['n1_b'])
    x = x + mha_np(xn, l['qkv_w'], l['qkv_b'], l['out_w'], l['out_b'])
    # Pre-LN + FFN
    xn = layer_norm_np(x, l['n2_w'], l['n2_b'])
    ff = gelu_np(xn @ l['ff1_w'].T + l['ff1_b'])
    x = x + ff @ l['ff2_w'].T + l['ff2_b']
    return x

def forward_np(raw_input):
    """raw_input: (20, 6) sin normalizar"""
    x = (raw_input - mean) / std
    x = x @ sd['input_proj.weight'].numpy().T + sd['input_proj.bias'].numpy()
    x = x + sd['pos_enc.pe'].numpy().squeeze(0)[:20]

    for i in range(3):
        p = f'transformer.layers.{i}'
        layer = {
            'qkv_w': sd[f'{p}.self_attn.in_proj_weight'].numpy(),
            'qkv_b': sd[f'{p}.self_attn.in_proj_bias'].numpy(),
            'out_w': sd[f'{p}.self_attn.out_proj.weight'].numpy(),
            'out_b': sd[f'{p}.self_attn.out_proj.bias'].numpy(),
            'ff1_w': sd[f'{p}.linear1.weight'].numpy(),
            'ff1_b': sd[f'{p}.linear1.bias'].numpy(),
            'ff2_w': sd[f'{p}.linear2.weight'].numpy(),
            'ff2_b': sd[f'{p}.linear2.bias'].numpy(),
            'n1_w':  sd[f'{p}.norm1.weight'].numpy(),
            'n1_b':  sd[f'{p}.norm1.bias'].numpy(),
            'n2_w':  sd[f'{p}.norm2.weight'].numpy(),
            'n2_b':  sd[f'{p}.norm2.bias'].numpy(),
        }
        x = encoder_layer_np(x, layer)

    x = layer_norm_np(x, sd['norm.weight'].numpy(), sd['norm.bias'].numpy())
    pooled = x.mean(0)
    mid = gelu_np(pooled @ sd['classifier.0.weight'].numpy().T + sd['classifier.0.bias'].numpy())
    logits = mid @ sd['classifier.3.weight'].numpy().T + sd['classifier.3.bias'].numpy()
    return sigmoid_np(logits)

# ── Test con 10 ventanas del dataset real ───────────────────────────────────
import pandas as pd
from predictive_maintenance.preprocess import FEATURE_COLS, FAILURE_COLS

df = pd.read_csv("../ai4i2020.csv")
df["Type_enc"] = df["Type"].map({"L": 0, "M": 1, "H": 2})
feats = df[FEATURE_COLS + ["Type_enc"]].values.astype(np.float32)

WINDOW = 20
labels = df[FAILURE_COLS].values

print(f"{'Sample':>6}  {'Mode':>6}  {'PyTorch':>20}  {'NumPy-C':>20}  {'Max diff':>10}  {'Match?':>8}")
print("-" * 80)

errors = []
for i in range(0, 200, 20):
    window = feats[i:i+WINDOW]
    if len(window) < WINDOW:
        break

    # PyTorch
    with torch.no_grad():
        x_norm = torch.tensor((window - mean) / std).unsqueeze(0)
        pt_logits = model(x_norm).squeeze(0)
        pt_probs = torch.sigmoid(pt_logits).numpy()

    # NumPy (replica exacta del C)
    np_probs = forward_np(window)

    diff = np.abs(pt_probs - np_probs).max()
    errors.append(diff)
    match = "✓" if diff < 1e-4 else "⚠" if diff < 1e-2 else "✗"
    print(f"{i:>6}  {'TWF,HDF,PWF,OSF,RNF':>6}  "
          f"{str(np.round(pt_probs,3)):>20}  "
          f"{str(np.round(np_probs,3)):>20}  "
          f"{diff:>10.2e}  {match:>8}")

print()
print(f"Max error across all samples: {max(errors):.2e}")
print(f"Mean error: {np.mean(errors):.2e}")
if max(errors) < 1e-3:
    print("✓ Implementación C es numéricamente equivalente a PyTorch")
else:
    print("⚠ Hay diferencias — revisar implementación C")

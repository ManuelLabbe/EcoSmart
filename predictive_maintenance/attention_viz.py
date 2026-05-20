"""Visualiza attention weights del Transformer para explicabilidad."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import torch
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

from preprocess import load_data, FAILURE_COLS
from dataset import build_windows, FEATURE_COLS_EXT
from model import SensorTransformer

MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
PLOTS_DIR = OUTPUTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_model_and_stats():
    with open(MODELS_DIR / "transformer_config.json") as f:
        cfg = json.load(f)
    with open(MODELS_DIR / "transformer_stats.pkl", "rb") as f:
        stats = pickle.load(f)
    model = SensorTransformer(
        n_features=len(stats["features"]),
        n_labels=len(FAILURE_COLS),
        d_model=cfg["d_model"],
        n_heads=cfg["n_heads"],
        n_layers=cfg["n_layers"],
        dim_feedforward=cfg["dim_feedforward"],
        dropout=0.0,
        window_size=cfg["window_size"],
    )
    model.load_state_dict(torch.load(MODELS_DIR / "transformer_best.pt", map_location="cpu"))
    model.eval()
    return model, stats, cfg


def plot_attention_heatmap(model, stats, cfg, sample_idx: int = None):
    """
    Muestra el mapa de atención para una muestra con falla real.
    Filas = timestep que "atiende", columnas = timestep "atendido".
    """
    df = load_data()
    (_, _, _), (X_test, y_test_multi, y_test_bin), _ = build_windows(df, cfg["window_size"])

    # Buscar sample con falla real si no se especifica
    failure_indices = np.where(y_test_bin == 1)[0]
    if sample_idx is None:
        sample_idx = failure_indices[0]

    x = torch.from_numpy(X_test[sample_idx:sample_idx+1])  # (1, T, F)
    attn = model.get_attention_for_sample(x)                # (T, T)
    attn_np = attn.numpy()

    active_labels = [FAILURE_COLS[i] for i in range(len(FAILURE_COLS)) if y_test_multi[sample_idx, i] == 1]
    label_str = ", ".join(active_labels) if active_labels else "normal"

    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(attn_np, cmap="Blues", aspect="auto", vmin=0)
    plt.colorbar(im, ax=ax, label="Peso de atención")
    ax.set_xlabel("Timestep atendido (pasado →)", fontsize=11)
    ax.set_ylabel("Timestep que atiende", fontsize=11)
    ax.set_title(f"Attention map — muestra con falla: [{label_str}]\n(cada tick = 1 lectura de sensor)",
                 fontsize=12)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(5))
    ax.set_xlim(-0.5, attn_np.shape[1] - 0.5)
    ax.set_ylim(attn_np.shape[0] - 0.5, -0.5)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "06_attention_heatmap.png", dpi=140)
    plt.close(fig)
    print("  06_attention_heatmap.png")


def plot_mean_attention_by_timestep(model, stats, cfg, n_samples: int = 50):
    """
    Atención promedio recibida por cada timestep en muestras con falla.
    Responde: ¿qué tan atrás mira el modelo antes de detectar la falla?
    """
    df = load_data()
    (_, _, _), (X_test, y_test_multi, y_test_bin), _ = build_windows(df, cfg["window_size"])

    failure_indices = np.where(y_test_bin == 1)[0][:n_samples]
    all_attn = []
    for idx in failure_indices:
        x = torch.from_numpy(X_test[idx:idx+1])
        attn = model.get_attention_for_sample(x).numpy()  # (T, T)
        all_attn.append(attn.mean(axis=0))                # promedio por timestep recibido

    mean_attn = np.stack(all_attn).mean(axis=0)           # (T,)
    timesteps = np.arange(cfg["window_size"])
    labels = [f"t-{cfg['window_size']-i-1}" if i < cfg["window_size"]-1 else "t (falla)" for i in timesteps]

    fig, ax = plt.subplots(figsize=(11, 4.5))
    bars = ax.bar(timesteps, mean_attn, color="#4a90d9", edgecolor="white")
    bars[-1].set_color("#e74c3c")  # último timestep (momento de falla) en rojo
    ax.set_xticks(timesteps[::2])
    ax.set_xticklabels(labels[::2], rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Atención promedio recibida", fontsize=11)
    ax.set_title(f"¿En qué momento del pasado se fija el modelo? (n={len(failure_indices)} muestras con falla)",
                 fontsize=12)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "07_attention_by_timestep.png", dpi=140)
    plt.close(fig)
    print("  07_attention_by_timestep.png")


def plot_training_curves():
    with open(OUTPUTS_DIR / "transformer_history.json") as f:
        history = json.load(f)

    epochs = [h["epoch"] for h in history]
    losses = [h["train_loss"] for h in history]
    f1s = [h["f1_macro"] for h in history]
    aucs = [h["roc_auc"] for h in history]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    ax1.plot(epochs, losses, color="#e74c3c", lw=2)
    ax1.set_xlabel("Época")
    ax1.set_ylabel("Train loss (BCEWithLogitsLoss)")
    ax1.set_title("Curva de pérdida — Transformer")
    ax1.grid(True, alpha=0.3)

    ax2.plot(epochs, f1s, color="#2ecc71", lw=2, label="F1 macro")
    ax2.plot(epochs, aucs, color="#4a90d9", lw=2, label="ROC-AUC macro")
    ax2.set_xlabel("Época")
    ax2.set_ylabel("Métrica (test)")
    ax2.set_title("F1 macro y ROC-AUC en test — Transformer")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig.suptitle("Evolución del entrenamiento — SensorTransformer multi-label", fontsize=13)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "08_training_curves.png", dpi=140)
    plt.close(fig)
    print("  08_training_curves.png")


def main():
    model, stats, cfg = load_model_and_stats()
    print(f"Generando visualizaciones en {PLOTS_DIR}/")
    plot_training_curves()
    plot_attention_heatmap(model, stats, cfg)
    plot_mean_attention_by_timestep(model, stats, cfg)
    print("\nListo.")


if __name__ == "__main__":
    main()

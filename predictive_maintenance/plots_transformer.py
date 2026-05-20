"""Gráficos de evaluación del Transformer — AUC por modo + curvas PR."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, precision_recall_curve, auc

OUTPUTS_DIR = Path(__file__).parent / "outputs"
PLOTS_DIR = OUTPUTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

COLORS = {"TWF": "#e74c3c", "HDF": "#3498db", "PWF": "#95a5a6",
          "OSF": "#2ecc71", "RNF": "#95a5a6"}
VALID = {"TWF", "HDF", "OSF"}  # modos con AUC > 0.85


def plot_auc_bars():
    with open(OUTPUTS_DIR / "transformer_eval_final.json") as f:
        results = json.load(f)
    per = results["per_label"]
    labels = list(per.keys())
    aucs = [per[l]["auc"] if per[l]["auc"] else 0.0 for l in labels]
    colors = [("#2ecc71" if l in VALID else "#e74c3c") for l in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, aucs, color=colors, edgecolor="white", linewidth=1.5)
    ax.axhline(0.5, color="gray", linestyle="--", lw=1.2, label="Baseline aleatorio (0.5)")
    ax.axhline(0.85, color="#27ae60", linestyle=":", lw=1.2, alpha=0.7, label="Umbral 'bueno' (0.85)")
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("ROC-AUC", fontsize=12)
    ax.set_title("AUC por modo de falla — SensorTransformer\n(verde = señal aprendida, rojo = datos insuficientes)", fontsize=12)
    ax.legend(fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    for bar, val, lbl in zip(bars, aucs, labels):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.02,
                f"{val:.3f}", ha="center", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "09_auc_per_mode.png", dpi=140)
    plt.close(fig)
    print("  09_auc_per_mode.png")


def plot_pr_curves(probs: np.ndarray, labels_multi: np.ndarray, failure_cols: list):
    valid_modes = [(i, col) for i, col in enumerate(failure_cols) if col in VALID]
    fig, axes = plt.subplots(1, len(valid_modes), figsize=(5 * len(valid_modes), 4.5))
    if len(valid_modes) == 1:
        axes = [axes]

    for ax, (i, col) in zip(axes, valid_modes):
        p, r, _ = precision_recall_curve(labels_multi[:, i], probs[:, i])
        pr_auc = auc(r, p)
        baseline = labels_multi[:, i].mean()
        ax.plot(r, p, color=COLORS.get(col, "#333"), lw=2, label=f"AUC-PR = {pr_auc:.3f}")
        ax.axhline(baseline, color="gray", linestyle="--", lw=1.2,
                   label=f"Baseline ({baseline:.3f})")
        ax.set_xlabel("Recall", fontsize=11)
        ax.set_ylabel("Precision", fontsize=11)
        ax.set_title(f"{col}", fontsize=13, fontweight="bold")
        ax.legend(fontsize=9)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Curvas Precision-Recall — modos con señal aprendida (AUC>0.85)", fontsize=12)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "10_pr_curves.png", dpi=140)
    plt.close(fig)
    print("  10_pr_curves.png")


def plot_roc_curves(probs: np.ndarray, labels_multi: np.ndarray, failure_cols: list):
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5, label="Aleatorio")
    for i, col in enumerate(failure_cols):
        if col not in VALID:
            continue
        fpr, tpr, _ = roc_curve(labels_multi[:, i], probs[:, i])
        roc_auc = auc(fpr, tpr)
        ax.plot(fpr, tpr, lw=2.5, color=COLORS.get(col), label=f"{col} (AUC={roc_auc:.3f})")

    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("True Positive Rate", fontsize=12)
    ax.set_title("Curvas ROC — SensorTransformer\n(modos con señal aprendida)", fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "11_roc_curves.png", dpi=140)
    plt.close(fig)
    print("  11_roc_curves.png")


def main():
    import pickle, torch, sys
    sys.path.insert(0, str(Path(__file__).parent))
    from preprocess import load_data, FAILURE_COLS
    from dataset import build_windows, SensorDataset
    from model import SensorTransformer
    from torch.utils.data import DataLoader

    with open(Path("models") / "transformer_config.json") as f:
        cfg = json.load(f)
    with open(Path("models") / "transformer_stats.pkl", "rb") as f:
        stats = pickle.load(f)

    model = SensorTransformer(
        n_features=len(stats["features"]), n_labels=len(FAILURE_COLS),
        d_model=cfg["d_model"], n_heads=cfg["n_heads"], n_layers=cfg["n_layers"],
        dim_feedforward=cfg["dim_feedforward"], dropout=0.0, window_size=cfg["window_size"])
    model.load_state_dict(torch.load(Path("models") / "transformer_best.pt", map_location="cpu"))
    model.eval()

    df = load_data()
    _, (X_test, y_test_multi, y_test_bin), _ = build_windows(df, cfg["window_size"])
    from dataset import SensorDataset
    loader = DataLoader(SensorDataset(X_test, y_test_multi, y_test_bin), batch_size=256)
    all_logits, all_labels = [], []
    with torch.no_grad():
        for X, y_multi, _ in loader:
            all_logits.append(model(X)); all_labels.append(y_multi)
    probs = torch.sigmoid(torch.cat(all_logits)).numpy()
    labels_multi = torch.cat(all_labels).numpy()

    print(f"Generando plots en {PLOTS_DIR}/")
    plot_auc_bars()
    plot_pr_curves(probs, labels_multi, FAILURE_COLS)
    plot_roc_curves(probs, labels_multi, FAILURE_COLS)
    print("\nListo.")


if __name__ == "__main__":
    main()

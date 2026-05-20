"""Genera gráficos de análisis del modelo de detección de anomalías."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.metrics import roc_curve, precision_recall_curve

from preprocess import load_data, get_features, TARGET_COL, FAILURE_COLS, FEATURE_COLS

MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
PLOTS_DIR = OUTPUTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = {"normal": "#4a90d9", "failure": "#e74c3c", "detected": "#2ecc71"}


def _load_predictions() -> pd.DataFrame:
    return pd.read_csv(OUTPUTS_DIR / "predictions.csv")


def _load_model():
    with open(MODELS_DIR / "isolation_forest.pkl", "rb") as f:
        clf = pickle.load(f)
    with open(MODELS_DIR / "scaler.pkl", "rb") as f:
        scaler = pickle.load(f)
    return clf, scaler


# ── 1. Distribución de anomaly score ──────────────────────────────────────────
def plot_score_distribution():
    df_pred = _load_predictions()
    df_full = load_data()
    df_full["anomaly_score"] = df_pred["anomaly_score"]

    fig, ax = plt.subplots(figsize=(10, 5))
    normal = df_full.loc[df_full[TARGET_COL] == 0, "anomaly_score"]
    failed = df_full.loc[df_full[TARGET_COL] == 1, "anomaly_score"]

    ax.hist(normal, bins=80, alpha=0.65, color=PALETTE["normal"], label=f"Normal (n={len(normal):,})", density=True)
    ax.hist(failed, bins=40, alpha=0.75, color=PALETTE["failure"], label=f"Falla real (n={len(failed):,})", density=True)
    ax.set_xlabel("Anomaly score (↑ más anómalo)", fontsize=12)
    ax.set_ylabel("Densidad", fontsize=12)
    ax.set_title("Distribución de Anomaly Score — Isolation Forest sobre AI4I 2020", fontsize=13)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "01_score_distribution.png", dpi=140)
    plt.close(fig)
    print("  01_score_distribution.png")


# ── 2. ROC + Precision-Recall ──────────────────────────────────────────────────
def plot_roc_pr():
    df_pred = _load_predictions()
    df_full = load_data()
    y_true = df_full[TARGET_COL].values
    y_score = df_pred["anomaly_score"].values

    fpr, tpr, _ = roc_curve(y_true, y_score)
    prec, rec, _ = precision_recall_curve(y_true, y_score)

    with open(OUTPUTS_DIR / "eval_results.json") as f:
        results = json.load(f)
    roc_auc = results["roc_auc"]
    avg_prec = results["avg_precision"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.plot(fpr, tpr, color=PALETTE["failure"], lw=2, label=f"ROC AUC = {roc_auc:.3f}")
    ax1.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5)
    ax1.set_xlabel("False Positive Rate")
    ax1.set_ylabel("True Positive Rate")
    ax1.set_title("Curva ROC")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(rec, prec, color=PALETTE["normal"], lw=2, label=f"Avg Precision = {avg_prec:.3f}")
    baseline = y_true.mean()
    ax2.axhline(y=baseline, color="k", linestyle="--", lw=1, alpha=0.5, label=f"Baseline ({baseline:.3f})")
    ax2.set_xlabel("Recall")
    ax2.set_ylabel("Precision")
    ax2.set_title("Curva Precision-Recall")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig.suptitle("Métricas de detección — Isolation Forest", fontsize=13)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "02_roc_pr.png", dpi=140)
    plt.close(fig)
    print("  02_roc_pr.png")


# ── 3. Detección por modo de falla ─────────────────────────────────────────────
def plot_failure_detection():
    with open(OUTPUTS_DIR / "eval_results.json") as f:
        results = json.load(f)
    det = results["failure_detection_by_type"]

    labels = list(det.keys())
    rates = [det[k]["rate"] for k in labels]
    totals = [det[k]["total"] for k in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, rates, color=PALETTE["normal"], edgecolor="white", linewidth=1.5)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Tasa de detección", fontsize=12)
    ax.set_title("Detección por modo de falla — Isolation Forest", fontsize=13)
    ax.grid(True, axis="y", alpha=0.3)
    for bar, rate, total in zip(bars, rates, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, rate + 0.03,
                f"{rate*100:.0f}%\n(n={total})", ha="center", fontsize=10, fontweight="bold")
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "03_failure_detection.png", dpi=140)
    plt.close(fig)
    print("  03_failure_detection.png")


# ── 4. Feature importance aproximada (mean score shift) ───────────────────────
def plot_feature_importance():
    clf, scaler = _load_model()
    df = load_data()
    X = get_features(df)
    X_scaled = scaler.transform(X)
    baseline_score = clf.decision_function(X_scaled)

    importances = []
    for i, feat in enumerate(FEATURE_COLS + ["Type_enc"]):
        X_perm = X_scaled.copy()
        np.random.default_rng(42).shuffle(X_perm[:, i])
        perm_score = clf.decision_function(X_perm)
        importance = np.mean(np.abs(baseline_score - perm_score))
        importances.append((feat, importance))

    importances.sort(key=lambda x: x[1], reverse=True)
    feats, vals = zip(*importances)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(list(reversed(feats)), list(reversed(vals)), color=PALETTE["normal"])
    ax.set_xlabel("Importancia (cambio medio en score por permutación)", fontsize=11)
    ax.set_title("Feature importance aproximada — Isolation Forest", fontsize=13)
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "04_feature_importance.png", dpi=140)
    plt.close(fig)
    print("  04_feature_importance.png")


# ── 5. Scatter: torque vs rotational speed coloreado por score ─────────────────
def plot_sensor_scatter():
    df = load_data()
    df_pred = _load_predictions()
    df["anomaly_score"] = df_pred["anomaly_score"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel izq: coloreado por anomaly score
    sc = axes[0].scatter(
        df["Rotational speed [rpm]"], df["Torque [Nm]"],
        c=df["anomaly_score"], cmap="RdYlGn_r", alpha=0.4, s=8
    )
    plt.colorbar(sc, ax=axes[0], label="Anomaly score")
    axes[0].set_xlabel("Rotational speed [rpm]")
    axes[0].set_ylabel("Torque [Nm]")
    axes[0].set_title("Anomaly score en espacio RPM-Torque")

    # Panel der: fallas reales marcadas
    normal_mask = df[TARGET_COL] == 0
    axes[1].scatter(df.loc[normal_mask, "Rotational speed [rpm]"],
                    df.loc[normal_mask, "Torque [Nm]"],
                    c=PALETTE["normal"], alpha=0.3, s=8, label="Normal")
    axes[1].scatter(df.loc[~normal_mask, "Rotational speed [rpm]"],
                    df.loc[~normal_mask, "Torque [Nm]"],
                    c=PALETTE["failure"], alpha=0.9, s=20, label="Falla real", zorder=5)
    axes[1].set_xlabel("Rotational speed [rpm]")
    axes[1].set_ylabel("Torque [Nm]")
    axes[1].set_title("Fallas reales en espacio RPM-Torque")
    axes[1].legend()

    fig.suptitle("Espacio de sensores — AI4I 2020", fontsize=13)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "05_sensor_scatter.png", dpi=140)
    plt.close(fig)
    print("  05_sensor_scatter.png")


def main():
    print(f"Generando plots en {PLOTS_DIR}/")
    plot_score_distribution()
    plot_roc_pr()
    plot_failure_detection()
    plot_feature_importance()
    plot_sensor_scatter()
    print(f"\nListo. {len(list(PLOTS_DIR.glob('*.png')))} plots generados.")


if __name__ == "__main__":
    main()

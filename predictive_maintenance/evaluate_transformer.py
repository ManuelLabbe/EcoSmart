"""Evaluación final del SensorTransformer — AUC como métrica principal."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_recall_curve,
    classification_report, confusion_matrix,
)

from preprocess import load_data, FAILURE_COLS, TARGET_COL
from dataset import build_windows, SensorDataset
from model import SensorTransformer

MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)


def load_artifacts():
    with open(MODELS_DIR / "transformer_config.json") as f:
        cfg = json.load(f)
    with open(MODELS_DIR / "transformer_stats.pkl", "rb") as f:
        stats = pickle.load(f)
    model = SensorTransformer(
        n_features=len(stats["features"]),
        n_labels=len(FAILURE_COLS),
        d_model=cfg["d_model"], n_heads=cfg["n_heads"],
        n_layers=cfg["n_layers"], dim_feedforward=cfg["dim_feedforward"],
        dropout=0.0, window_size=cfg["window_size"],
    )
    model.load_state_dict(torch.load(MODELS_DIR / "transformer_best.pt", map_location="cpu"))
    model.eval()
    return model, cfg, stats


def get_predictions(model, cfg):
    df = load_data()
    _, (X_test, y_test_multi, y_test_bin), _ = build_windows(df, cfg["window_size"])
    test_ds = SensorDataset(X_test, y_test_multi, y_test_bin)
    loader = DataLoader(test_ds, batch_size=256, shuffle=False)

    all_logits, all_y_multi, all_y_bin = [], [], []
    with torch.no_grad():
        for X, y_multi, y_bin in loader:
            all_logits.append(model(X))
            all_y_multi.append(y_multi)
            all_y_bin.append(y_bin)

    probs = torch.sigmoid(torch.cat(all_logits)).numpy()
    labels_multi = torch.cat(all_y_multi).numpy()
    labels_bin = torch.cat(all_y_bin).numpy()
    return probs, labels_multi, labels_bin


def find_optimal_threshold(y_true, y_prob):
    """Threshold que maximiza F1 en la curva Precision-Recall."""
    p, r, thresholds = precision_recall_curve(y_true, y_prob)
    f1s = 2 * p * r / (p + r + 1e-8)
    best_idx = f1s[:-1].argmax()
    return float(thresholds[best_idx]), float(f1s[best_idx])


def evaluate():
    model, cfg, stats = load_artifacts()
    probs, labels_multi, labels_bin = get_predictions(model, cfg)

    print("=" * 60)
    print("EVALUACIÓN — SensorTransformer Multi-Label (AI4I 2020)")
    print("=" * 60)

    per_label = {}
    print(f"\n{'Modo':<8} {'AUC':>7} {'Best_Thr':>10} {'Best_F1':>9} {'N_pos_test':>12}")
    print("-" * 52)
    for i, col in enumerate(FAILURE_COLS):
        n_pos = int(labels_multi[:, i].sum())
        if n_pos < 2:
            auc = float("nan")
            best_thr, best_f1 = 0.5, 0.0
        else:
            auc = roc_auc_score(labels_multi[:, i], probs[:, i])
            best_thr, best_f1 = find_optimal_threshold(labels_multi[:, i], probs[:, i])
        tag = "✅" if (auc > 0.85 and not np.isnan(auc)) else ("⚠️" if (auc > 0.5 and not np.isnan(auc)) else "❌")
        print(f"{col:<8} {auc:>6.3f}  {best_thr:>10.3f} {best_f1:>9.3f} {n_pos:>10}  {tag}")
        per_label[col] = {"auc": round(auc, 4) if not np.isnan(auc) else None,
                          "best_threshold": round(best_thr, 3),
                          "best_f1": round(best_f1, 3),
                          "n_pos_test": n_pos}

    # AUC macro solo sobre etiquetas con ≥2 positivos
    valid_aucs = [v["auc"] for v in per_label.values() if v["auc"] is not None]
    auc_macro = float(np.mean(valid_aucs))
    print(f"\nAUC macro (etiquetas válidas): {auc_macro:.4f}")

    # Machine failure binario con threshold óptimo
    probs_any = probs.max(axis=1)
    bin_auc = roc_auc_score(labels_bin, probs_any)
    bin_thr, bin_f1 = find_optimal_threshold(labels_bin, probs_any)
    preds_bin = (probs_any >= bin_thr).astype(int)
    cm = confusion_matrix(labels_bin, preds_bin)
    print(f"\nMachine failure (OR de modos, thr={bin_thr:.2f}):")
    print(f"  AUC  = {bin_auc:.4f}")
    print(f"  F1   = {bin_f1:.4f}")
    print(f"  Matriz de confusión:")
    print(f"    TN={cm[0,0]}  FP={cm[0,1]}")
    print(f"    FN={cm[1,0]}  TP={cm[1,1]}")
    recall = cm[1,1] / (cm[1,1] + cm[1,0]) if (cm[1,1] + cm[1,0]) > 0 else 0
    precision = cm[1,1] / (cm[1,1] + cm[0,1]) if (cm[1,1] + cm[0,1]) > 0 else 0
    print(f"  Recall (fallas detectadas): {recall:.1%}")
    print(f"  Precision: {precision:.1%}")

    results = {
        "auc_macro_valid_labels": round(auc_macro, 4),
        "machine_failure_auc": round(bin_auc, 4),
        "machine_failure_f1_optimal": round(bin_f1, 4),
        "machine_failure_recall": round(recall, 4),
        "per_label": per_label,
        "note_pwf_rnf": "PWF y RNF tienen señal insuficiente — requieren más datos históricos",
    }
    (OUTPUTS_DIR / "transformer_eval_final.json").write_text(json.dumps(results, indent=2))
    print(f"\nResultados guardados en {OUTPUTS_DIR}/transformer_eval_final.json")
    return results, probs, labels_multi, labels_bin


if __name__ == "__main__":
    evaluate()

"""Evalúa el Isolation Forest sobre todo el dataset AI4I 2020."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)

from preprocess import load_data, get_features, TARGET_COL, FAILURE_COLS

MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)


def load_model():
    with open(MODELS_DIR / "isolation_forest.pkl", "rb") as f:
        clf = pickle.load(f)
    with open(MODELS_DIR / "scaler.pkl", "rb") as f:
        scaler = pickle.load(f)
    return clf, scaler


def evaluate() -> dict:
    clf, scaler = load_model()
    df = load_data()
    X = get_features(df)
    X_scaled = scaler.transform(X)

    # Isolation Forest: -1 = anomalía, 1 = normal → convertir a 0/1
    df["anomaly_score"] = -clf.decision_function(X_scaled)  # más alto = más anómalo
    df["predicted_failure"] = (clf.predict(X_scaled) == -1).astype(int)

    y_true = df[TARGET_COL].values
    y_pred = df["predicted_failure"].values
    y_score = df["anomaly_score"].values

    # Métricas globales
    roc_auc = roc_auc_score(y_true, y_score)
    avg_prec = average_precision_score(y_true, y_score)
    cm = confusion_matrix(y_true, y_pred)
    report = classification_report(y_true, y_pred, target_names=["normal", "falla"], output_dict=True)

    print("=" * 55)
    print("EVALUACIÓN — Isolation Forest sobre AI4I 2020")
    print("=" * 55)
    print(f"\nROC-AUC  : {roc_auc:.4f}")
    print(f"Avg Prec : {avg_prec:.4f}")
    print(f"\nMatriz de confusión:")
    print(f"  TN={cm[0,0]}  FP={cm[0,1]}")
    print(f"  FN={cm[1,0]}  TP={cm[1,1]}")
    print(f"\nReporte de clasificación:")
    print(classification_report(y_true, y_pred, target_names=["normal", "falla"]))

    # Detección por modo de falla
    print("Tasa de detección por modo de falla:")
    failure_detection = {}
    for col in FAILURE_COLS:
        mask = df[col] == 1
        if mask.sum() > 0:
            detected = df.loc[mask, "predicted_failure"].sum()
            rate = detected / mask.sum()
            failure_detection[col] = {"total": int(mask.sum()), "detected": int(detected), "rate": round(rate, 3)}
            print(f"  {col}: {detected}/{mask.sum()} detectadas ({rate*100:.1f}%)")

    results = {
        "roc_auc": round(roc_auc, 4),
        "avg_precision": round(avg_prec, 4),
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
        "failure_detection_by_type": failure_detection,
    }

    # Guardar resultados
    (OUTPUTS_DIR / "eval_results.json").write_text(json.dumps(results, indent=2))

    # Guardar predicciones completas
    df[["UDI", "Product ID", "Type", TARGET_COL] + FAILURE_COLS + ["anomaly_score", "predicted_failure"]].to_csv(
        OUTPUTS_DIR / "predictions.csv", index=False
    )
    print(f"\nResultados guardados en {OUTPUTS_DIR}/")
    return results


if __name__ == "__main__":
    evaluate()

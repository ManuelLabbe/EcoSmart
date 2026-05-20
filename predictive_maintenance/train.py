"""Entrena Isolation Forest sobre datos normales de AI4I 2020."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from preprocess import load_data, get_normal_data, get_features, FEATURE_COLS

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)


def train(
    contamination: float = 0.01,
    n_estimators: int = 200,
    random_state: int = 42,
) -> tuple[IsolationForest, StandardScaler]:
    df = load_data()
    df_normal = get_normal_data(df)

    X_normal = get_features(df_normal)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_normal)

    clf = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    clf.fit(X_scaled)

    # Guardar modelos
    with open(MODELS_DIR / "isolation_forest.pkl", "wb") as f:
        pickle.dump(clf, f)
    with open(MODELS_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    meta = {
        "n_train": len(df_normal),
        "contamination": contamination,
        "n_estimators": n_estimators,
        "features": FEATURE_COLS + ["Type_enc"],
        "random_state": random_state,
    }
    (MODELS_DIR / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"Modelo entrenado sobre {len(df_normal):,} muestras normales.")
    print(f"Guardado en {MODELS_DIR}/")
    return clf, scaler


if __name__ == "__main__":
    train()

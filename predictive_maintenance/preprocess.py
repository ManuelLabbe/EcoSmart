"""Preprocesamiento del dataset AI4I 2020 para detección de anomalías."""
from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
FEATURE_COLS = [
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]
FAILURE_COLS = ["TWF", "HDF", "PWF", "OSF", "RNF"]
TARGET_COL = "Machine failure"


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "ai4i2020.csv")
    df["Type_enc"] = df["Type"].map({"L": 0, "M": 1, "H": 2})
    return df


def get_normal_data(df: pd.DataFrame) -> pd.DataFrame:
    """Registros sin ningún tipo de falla — usados para entrenar."""
    return df[df[TARGET_COL] == 0].reset_index(drop=True)


def get_features(df: pd.DataFrame, include_type: bool = True) -> np.ndarray:
    cols = FEATURE_COLS + (["Type_enc"] if include_type else [])
    return df[cols].values


def summary(df: pd.DataFrame) -> None:
    total = len(df)
    failed = df[TARGET_COL].sum()
    print(f"Total muestras   : {total:,}")
    print(f"Muestras normales: {total - failed:,} ({(total-failed)/total*100:.1f}%)")
    print(f"Fallas totales   : {failed:,} ({failed/total*100:.1f}%)")
    print("\nDesglose por modo de falla:")
    for col in FAILURE_COLS:
        n = df[col].sum()
        print(f"  {col}: {n:3d} ({n/total*100:.2f}%)")
    print("\nDistribución por tipo:")
    print(df["Type"].value_counts().to_string())

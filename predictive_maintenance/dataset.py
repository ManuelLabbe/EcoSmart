"""Dataset con ventana deslizante sobre AI4I 2020 para clasificación temporal."""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from sklearn.model_selection import train_test_split

from preprocess import load_data, FEATURE_COLS, FAILURE_COLS, TARGET_COL

WINDOW_SIZE = 20
FEATURE_COLS_EXT = FEATURE_COLS + ["Type_enc"]


def build_windows(df: pd.DataFrame, window_size: int = WINDOW_SIZE, test_size: float = 0.2, seed: int = 42):
    """
    Crea ventanas deslizantes y hace split estratificado por Machine failure.
    Estratificado garantiza que todos los modos de falla aparecen en train y test.
    """
    df = df.sort_values("UDI").reset_index(drop=True)

    X_raw = df[FEATURE_COLS_EXT].values.astype(np.float32)
    y_multi = df[FAILURE_COLS].values.astype(np.float32)
    y_binary = df[TARGET_COL].values.astype(np.float32)

    windows_X, windows_y_multi, windows_y_bin = [], [], []
    for i in range(window_size, len(df)):
        windows_X.append(X_raw[i - window_size:i])
        windows_y_multi.append(y_multi[i])
        windows_y_bin.append(y_binary[i])

    X_arr = np.stack(windows_X)
    y_multi_arr = np.stack(windows_y_multi)
    y_bin_arr = np.array(windows_y_bin)

    # Split estratificado por Machine failure
    idx = np.arange(len(X_arr))
    idx_train, idx_test = train_test_split(
        idx, test_size=test_size, random_state=seed, stratify=y_bin_arr
    )

    # Normalizar solo con estadísticas de train
    mean = X_arr[idx_train].mean(axis=(0, 1))
    std = X_arr[idx_train].std(axis=(0, 1)) + 1e-8
    X_norm = (X_arr - mean) / std

    train = (X_norm[idx_train], y_multi_arr[idx_train], y_bin_arr[idx_train])
    test = (X_norm[idx_test], y_multi_arr[idx_test], y_bin_arr[idx_test])

    stats = {"mean": mean.tolist(), "std": std.tolist(), "features": FEATURE_COLS_EXT}
    return train, test, stats


class SensorDataset(Dataset):
    def __init__(self, X: np.ndarray, y_multi: np.ndarray, y_bin: np.ndarray):
        self.X = torch.from_numpy(X)
        self.y_multi = torch.from_numpy(y_multi)
        self.y_bin = torch.from_numpy(y_bin)

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y_multi[idx], self.y_bin[idx]

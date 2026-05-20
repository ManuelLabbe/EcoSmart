"""Entrena el SensorTransformer sobre AI4I 2020 con clasificación multi-label."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import f1_score, roc_auc_score

from preprocess import load_data, FAILURE_COLS
from dataset import build_windows, SensorDataset
from model import SensorTransformer

MODELS_DIR = Path(__file__).parent / "models"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
MODELS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# ── Hiperparámetros ────────────────────────────────────────────────────────────
CONFIG = {
    "window_size": 20,
    "d_model": 64,
    "n_heads": 4,
    "n_layers": 3,
    "dim_feedforward": 256,
    "dropout": 0.15,
    "lr": 3e-4,
    "weight_decay": 1e-4,
    "epochs": 60,
    "batch_size": 128,
    "patience": 12,         # early stopping
    "seed": 42,
}


def compute_pos_weight(y_multi: np.ndarray) -> torch.Tensor:
    """Peso para cada etiqueta para compensar desbalanceo."""
    n = len(y_multi)
    pos = y_multi.sum(axis=0).clip(min=1)
    neg = n - pos
    return torch.tensor(neg / pos, dtype=torch.float32)


def evaluate_model(model, loader, device, threshold=0.5):
    model.eval()
    all_logits, all_labels = [], []
    with torch.no_grad():
        for X, y_multi, _ in loader:
            logits = model(X.to(device))
            all_logits.append(logits.cpu())
            all_labels.append(y_multi)
    logits = torch.cat(all_logits)
    labels = torch.cat(all_labels).numpy()
    probs = torch.sigmoid(logits).numpy()
    preds = (probs >= threshold).astype(int)

    f1_per = f1_score(labels, preds, average=None, zero_division=0)
    f1_macro = f1_score(labels, preds, average="macro", zero_division=0)
    try:
        auc = roc_auc_score(labels, probs, average="macro")
    except Exception:
        auc = 0.0
    return {"f1_per_label": f1_per.tolist(), "f1_macro": f1_macro, "roc_auc": auc,
            "probs": probs, "preds": preds, "labels": labels}


def train():
    torch.manual_seed(CONFIG["seed"])
    np.random.seed(CONFIG["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ── Datos ──────────────────────────────────────────────────────────────────
    df = load_data()
    (X_train, y_train_multi, y_train_bin), (X_test, y_test_multi, y_test_bin), stats = \
        build_windows(df, CONFIG["window_size"])

    print(f"Train: {len(X_train):,} ventanas | Test: {len(X_test):,} ventanas")
    print(f"Train failures: {y_train_bin.sum():.0f} ({y_train_bin.mean()*100:.1f}%)")
    print(f"Test  failures: {y_test_bin.sum():.0f} ({y_test_bin.mean()*100:.1f}%)")

    train_ds = SensorDataset(X_train, y_train_multi, y_train_bin)
    test_ds = SensorDataset(X_test, y_test_multi, y_test_bin)
    train_loader = DataLoader(train_ds, batch_size=CONFIG["batch_size"], shuffle=True, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=256, shuffle=False, num_workers=0)

    # ── Modelo ─────────────────────────────────────────────────────────────────
    model = SensorTransformer(
        n_features=len(stats["features"]),
        n_labels=len(FAILURE_COLS),
        d_model=CONFIG["d_model"],
        n_heads=CONFIG["n_heads"],
        n_layers=CONFIG["n_layers"],
        dim_feedforward=CONFIG["dim_feedforward"],
        dropout=CONFIG["dropout"],
        window_size=CONFIG["window_size"],
    ).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Parámetros: {n_params:,}")

    pos_weight = compute_pos_weight(y_train_multi).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG["lr"], weight_decay=CONFIG["weight_decay"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=CONFIG["epochs"])

    # ── Training loop ──────────────────────────────────────────────────────────
    history = []
    best_f1 = 0.0
    patience_counter = 0

    for epoch in range(1, CONFIG["epochs"] + 1):
        model.train()
        total_loss = 0.0
        for X, y_multi, _ in train_loader:
            X, y_multi = X.to(device), y_multi.to(device)
            optimizer.zero_grad()
            logits = model(X)
            loss = criterion(logits, y_multi)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item() * len(X)
        scheduler.step()

        avg_loss = total_loss / len(train_ds)
        metrics = evaluate_model(model, test_loader, device)
        history.append({
            "epoch": epoch,
            "train_loss": round(avg_loss, 4),
            "f1_macro": round(metrics["f1_macro"], 4),
            "roc_auc": round(metrics["roc_auc"], 4),
            "lr": scheduler.get_last_lr()[0],
        })

        if epoch % 5 == 0 or epoch == 1:
            print(f"Epoch {epoch:3d} | loss={avg_loss:.4f} | F1={metrics['f1_macro']:.4f} | AUC={metrics['roc_auc']:.4f}")

        # Early stopping + checkpoint
        if metrics["f1_macro"] > best_f1:
            best_f1 = metrics["f1_macro"]
            patience_counter = 0
            torch.save(model.state_dict(), MODELS_DIR / "transformer_best.pt")
        else:
            patience_counter += 1
            if patience_counter >= CONFIG["patience"]:
                print(f"Early stopping en epoch {epoch} (mejor F1={best_f1:.4f})")
                break

    # ── Evaluación final ───────────────────────────────────────────────────────
    model.load_state_dict(torch.load(MODELS_DIR / "transformer_best.pt", map_location=device))
    final = evaluate_model(model, test_loader, device)

    print("\n" + "=" * 55)
    print("EVALUACIÓN FINAL — Transformer multi-label")
    print("=" * 55)
    print(f"ROC-AUC macro : {final['roc_auc']:.4f}")
    print(f"F1 macro      : {final['f1_macro']:.4f}")
    print("\nF1 por modo de falla:")
    for label, f1 in zip(FAILURE_COLS, final["f1_per_label"]):
        print(f"  {label}: {f1:.4f}")

    # Guardar artefactos
    (OUTPUTS_DIR / "transformer_history.json").write_text(json.dumps(history, indent=2))
    (OUTPUTS_DIR / "transformer_eval.json").write_text(json.dumps({
        "roc_auc": final["roc_auc"],
        "f1_macro": final["f1_macro"],
        "f1_per_label": dict(zip(FAILURE_COLS, final["f1_per_label"])),
    }, indent=2))
    with open(MODELS_DIR / "transformer_stats.pkl", "wb") as f:
        pickle.dump(stats, f)
    (MODELS_DIR / "transformer_config.json").write_text(json.dumps(CONFIG, indent=2))

    print(f"\nModelo guardado en {MODELS_DIR}/transformer_best.pt")
    return model, stats, history


if __name__ == "__main__":
    train()

"""Generate training-evolution plots from trainer_state.json + eval metas."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
OUT = EVALS / "plots"
OUT.mkdir(parents=True, exist_ok=True)


def load_history():
    data = json.loads((EVALS / "trainer_state.json").read_text())
    train, evalh = [], []
    for e in data["log_history"]:
        if "loss" in e:
            train.append(e)
        if "eval_loss" in e:
            evalh.append(e)
    return train, evalh


def plot_loss(train, evalh):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot([e["step"] for e in train], [e["loss"] for e in train],
            marker="o", ms=4, lw=1.5, color="#1f77b4", label="train loss")
    ax.plot([e["step"] for e in evalh], [e["eval_loss"] for e in evalh],
            marker="s", ms=8, lw=2, color="#d62728", label="eval loss (per epoch)")
    ax.set_xlabel("step")
    ax.set_ylabel("loss")
    ax.set_title("Curva de pérdida — FLAME 3 fine-tuning LFM2.5-VL-450M")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    ax.legend()
    for i, e in enumerate(evalh):
        ax.annotate(f"epoch {i}\n{e['eval_loss']:.3f}", xy=(e["step"], e["eval_loss"]),
                    xytext=(8, 8), textcoords="offset points", fontsize=8,
                    color="#d62728")
    fig.tight_layout()
    fig.savefig(OUT / "01_loss_curve.png", dpi=140)
    plt.close(fig)


def plot_lr(train):
    fig, ax = plt.subplots(figsize=(9, 5))
    steps = [e["step"] for e in train]
    ax.plot(steps, [e["lr/language_model"] for e in train], lw=2, label="language_model")
    ax.plot(steps, [e["lr/multi_modal_projector"] for e in train], lw=2, label="multi_modal_projector")
    ax.plot(steps, [e["lr/vision_tower"] for e in train], lw=2, label="vision_tower (0.1x)")
    ax.set_xlabel("step")
    ax.set_ylabel("learning rate")
    ax.set_title("Learning rate schedule (cosine + warmup, full FT)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "02_lr_schedule.png", dpi=140)
    plt.close(fig)


def plot_grad_norm(train):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot([e["step"] for e in train], [e["grad_norm"] for e in train],
            marker="o", ms=4, lw=1.5, color="#2ca02c")
    ax.set_xlabel("step")
    ax.set_ylabel("grad_norm")
    ax.set_title("Gradient norm a lo largo del entrenamiento")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "03_grad_norm.png", dpi=140)
    plt.close(fig)


def plot_field_accuracy():
    base = json.loads((EVALS / "base" / "meta.json").read_text())
    ft = json.loads((EVALS / "finetuned" / "meta.json").read_text())
    fields = ["valid_json", "fields_present", "fire_present",
              "thermal_hotspot_intensity", "fire_size",
              "smoke_visible", "image_quality_limited"]
    base_vals = [base["per_field"][f] for f in fields]
    ft_vals = [ft["per_field"][f] for f in fields]

    import numpy as np
    x = np.arange(len(fields))
    w = 0.4
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(x - w/2, base_vals, w, label=f"base ({base['overall']:.2f} overall)", color="#9aa6b2")
    ax.bar(x + w/2, ft_vals, w, label=f"fine-tuned ({ft['overall']:.2f} overall)", color="#1f77b4")
    ax.set_xticks(x)
    ax.set_xticklabels(fields, rotation=20, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("accuracy")
    ax.set_title(f"Per-field accuracy — test split (n={base['n']})")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    for xi, b, f in zip(x, base_vals, ft_vals):
        ax.text(xi - w/2, b + 0.015, f"{b:.2f}", ha="center", fontsize=8)
        ax.text(xi + w/2, f + 0.015, f"{f:.2f}", ha="center", fontsize=8, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "04_field_accuracy.png", dpi=140)
    plt.close(fig)


def plot_summary():
    base = json.loads((EVALS / "base" / "meta.json").read_text())
    ft = json.loads((EVALS / "finetuned" / "meta.json").read_text())
    fig, ax = plt.subplots(figsize=(6, 4.5))
    bars = ax.bar(["base", "fine-tuned"], [base["overall"], ft["overall"]],
                  color=["#9aa6b2", "#1f77b4"], width=0.5)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("overall accuracy")
    ax.set_title("Overall accuracy: base vs fine-tuned")
    for b, v in zip(bars, [base["overall"], ft["overall"]]):
        ax.text(b.get_x() + b.get_width()/2, v + 0.02, f"{v:.2f}",
                ha="center", fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "05_overall.png", dpi=140)
    plt.close(fig)


def main():
    train, evalh = load_history()
    plot_loss(train, evalh)
    plot_lr(train)
    plot_grad_norm(train)
    plot_field_accuracy()
    plot_summary()
    print(f"Wrote 5 plots to {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}")


if __name__ == "__main__":
    main()

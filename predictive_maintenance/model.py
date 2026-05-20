"""Transformer encoder para clasificación multi-label de fallas industriales."""
from __future__ import annotations

import math
import torch
import torch.nn as nn


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 100, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(max_len).unsqueeze(1).float()
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, d_model)
        return self.dropout(x + self.pe[:, : x.size(1)])


class SensorTransformer(nn.Module):
    """
    Transformer encoder para clasificación multi-label de modos de falla.

    Arquitectura:
        Input (B, T, n_features)
        → Linear projection → d_model
        → Positional Encoding
        → N × TransformerEncoderLayer (con self-attention)
        → Mean pooling sobre T
        → Linear head → n_labels logits
    """

    def __init__(
        self,
        n_features: int = 6,
        n_labels: int = 5,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 3,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        window_size: int = 20,
    ):
        super().__init__()
        self.input_proj = nn.Linear(n_features, d_model)
        self.pos_enc = PositionalEncoding(d_model, max_len=window_size + 1, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            norm_first=True,  # Pre-LN: más estable para datasets pequeños
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.norm = nn.LayerNorm(d_model)
        self.classifier = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, n_labels),
        )
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor, return_attention: bool = False):
        # x: (B, T, n_features)
        x = self.input_proj(x)           # (B, T, d_model)
        x = self.pos_enc(x)
        x = self.transformer(x)          # (B, T, d_model)
        x = self.norm(x)
        pooled = x.mean(dim=1)           # (B, d_model) — mean pooling
        logits = self.classifier(pooled) # (B, n_labels)

        if return_attention:
            # Extraer attention weights de la última capa para visualización
            attn_weights = self._get_attention_weights(x)
            return logits, attn_weights
        return logits

    def _get_attention_weights(self, x: torch.Tensor) -> torch.Tensor:
        """Pasa x por la última capa y retorna los attention weights."""
        last_layer = self.transformer.layers[-1]
        # Self-attention sin mask
        with torch.no_grad():
            _, attn = last_layer.self_attn(x, x, x, need_weights=True, average_attn_weights=True)
        return attn  # (B, T, T)

    def get_attention_for_sample(self, x: torch.Tensor) -> torch.Tensor:
        """
        Dado un sample (1, T, n_features), retorna attention weights (T, T).
        Útil para visualización de qué timesteps importaron.
        """
        self.eval()
        with torch.no_grad():
            h = self.input_proj(x)
            h = self.pos_enc(h)
            # Pasar por todas las capas menos la última para tener h correcto
            for layer in self.transformer.layers[:-1]:
                h = layer(h)
            last = self.transformer.layers[-1]
            _, attn = last.self_attn(h, h, h, need_weights=True, average_attn_weights=True)
        return attn[0]  # (T, T)

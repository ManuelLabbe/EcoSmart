#!/usr/bin/env python3
"""
UG Simulator — simula lecturas del ciclo agua-vapor de COMASA
Lee los valores nominales del xlsx y publica cada TAG a AWS IoT Core via MQTT.

Uso:
    pip install paho-mqtt pandas openpyxl
    python ug_simulator.py [--anomaly-rate 0.05] [--cycle-secs 120] [--interval 10]
"""
import argparse
import json
import os
import random
import signal
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import paho.mqtt.client as mqtt

# ── Rutas ─────────────────────────────────────────────────────────────────────

ROOT  = Path(__file__).parent.parent.parent   # comasa_hackaton/
XLSX  = ROOT / "dataset" / "Agua, Vapor y Condensado Planta COMASA.xlsx"
CERTS = ROOT / "esp32_firmware" / "main" / "certs"

IOT_ENDPOINT = "a1on3yakrzxggo-ats.iot.us-east-1.amazonaws.com"
IOT_PORT     = 8883
TOPIC        = "ecosmart/process/readings"

SHEET_MAP = {
    "UG_1_MT":  ("esp32-ug1-001", "MT"),
    "UG_1_BL1": ("esp32-ug1-001", "BL1"),
    "UG_1_BL2": ("esp32-ug1-001", "BL2"),
    "UG_2_MT":  ("esp32-ug2-001", "MT"),
    "UG_2_BL1": ("esp32-ug2-001", "BL1"),
    "UG_2_BL2": ("esp32-ug2-001", "BL2"),
}

REGIMES           = ["MT", "BL1", "BL2"]
NOISE_SIGMA_PCT   = 0.02   # 2% ruido normal
ANOMALY_SIGMA_PCT = 0.20   # 20% para anomalías inyectadas

# ── Carga de datos ────────────────────────────────────────────────────────────

def load_nominals() -> dict:
    """Devuelve {equipment_id: {regime: [sensor_point, ...]}}"""
    xlsx = pd.ExcelFile(XLSX)
    nominals: dict = {}

    for sheet_name, (equipment_id, regime) in SHEET_MAP.items():
        df   = pd.read_excel(xlsx, sheet_name=sheet_name, header=None)
        data = df.iloc[8:].copy()
        data.columns = df.iloc[7].values
        data = data.dropna(how="all")

        points = []
        for _, row in data.iterrows():
            tag     = row.iloc[6]
            nominal = row.iloc[5]
            if not isinstance(nominal, (int, float)) or pd.isna(nominal):
                continue
            if pd.isna(tag) or str(tag).strip() in ("", "nan"):
                continue
            points.append({
                "tag":               str(tag).strip(),
                "variable":          str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else "",
                "variable_medicion": str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else "",
                "unit":              str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else "",
                "nominal_value":     float(nominal),
                "desde":             str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else "",
                "hasta":             str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else "",
            })

        nominals.setdefault(equipment_id, {})[regime] = points

    return nominals


def make_reading(equipment_id: str, regime: str, point: dict, anomaly_rate: float) -> dict:
    is_anomaly = random.random() < anomaly_rate
    sigma      = abs(point["nominal_value"]) * (ANOMALY_SIGMA_PCT if is_anomaly else NOISE_SIGMA_PCT)
    value      = point["nominal_value"] + random.gauss(0, sigma) if sigma > 0 else point["nominal_value"]

    nom = point["nominal_value"]
    deviation_pct = round((value - nom) / abs(nom) * 100, 2) if nom != 0 else 0.0

    return {
        "reading_id":        str(uuid.uuid4()),
        "equipment_id":      equipment_id,
        "tag":               point["tag"],
        "variable":          point["variable"],
        "variable_medicion": point["variable_medicion"],
        "value":             round(value, 3),
        "unit":              point["unit"],
        "regime":            regime,
        "nominal_value":     nom,
        "deviation_pct":     deviation_pct,
        "is_anomaly":        1 if is_anomaly else 0,
        "desde":             point["desde"],
        "hasta":             point["hasta"],
        "timestamp":         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ── MQTT ──────────────────────────────────────────────────────────────────────

def build_client() -> mqtt.Client:
    client = mqtt.Client(client_id=f"ug-simulator-{uuid.uuid4().hex[:8]}")
    client.tls_set(
        ca_certs = str(CERTS / "aws_root_ca.pem"),
        certfile = str(CERTS / "device_cert.pem"),
        keyfile  = str(CERTS / "device_key.pem"),
    )
    client.connect(IOT_ENDPOINT, IOT_PORT)
    client.loop_start()
    return client


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Simulador UG agua-vapor COMASA")
    parser.add_argument("--anomaly-rate", type=float, default=0.05,
                        help="Prob. de inyectar anomalía por lectura (default 0.05)")
    parser.add_argument("--cycle-secs",   type=int,   default=120,
                        help="Segundos entre cambios de régimen MT→BL1→BL2 (default 120)")
    parser.add_argument("--interval",     type=int,   default=10,
                        help="Segundos entre publicaciones (default 10)")
    args = parser.parse_args()

    print("Cargando nominales del xlsx...")
    nominals   = load_nominals()
    total_tags = sum(len(pts) for eq in nominals.values() for pts in eq.values())
    print(f"  {len(nominals)} equipos | {total_tags} puntos de sensor cargados")

    print("Conectando a AWS IoT Core...")
    client = build_client()
    time.sleep(2)
    print(f"  Conectado → {IOT_ENDPOINT}:{IOT_PORT}")
    print(f"  Topic     → {TOPIC}")
    print(f"\nCiclo régimen cada {args.cycle_secs}s | publish cada {args.interval}s | anomaly_rate={args.anomaly_rate}")
    print("-" * 64)

    regime_idx  = {eq: 0 for eq in nominals}
    last_switch = {eq: time.time() for eq in nominals}
    running     = True

    def _stop(sig, frame):
        nonlocal running
        print("\nDeteniendo simulador...")
        running = False

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        now = time.time()
        for equipment_id, regimes_data in nominals.items():
            if now - last_switch[equipment_id] >= args.cycle_secs:
                regime_idx[equipment_id] = (regime_idx[equipment_id] + 1) % len(REGIMES)
                last_switch[equipment_id] = now
                new_regime = REGIMES[regime_idx[equipment_id]]
                print(f"  [{equipment_id}] cambio régimen → {new_regime}")

            regime = REGIMES[regime_idx[equipment_id]]
            points = regimes_data.get(regime, [])

            anomalies = 0
            for point in points:
                reading = make_reading(equipment_id, regime, point, args.anomaly_rate)
                client.publish(TOPIC, json.dumps(reading), qos=1)
                if reading["is_anomaly"]:
                    anomalies += 1

            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(f"[{ts}] {equipment_id} | {regime:3s} | {len(points)} TAGs | {anomalies} anomalías")

        time.sleep(args.interval)

    client.loop_stop()
    client.disconnect()
    print("Simulador detenido.")


if __name__ == "__main__":
    main()

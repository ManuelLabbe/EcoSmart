# EcoSmart — ESP32 Firmware (ESP-IDF)

Firmware C para ESP32 que simula lecturas de sensores industriales y las publica
vía MQTT/TLS hacia AWS IoT Core → tópico `ecosmart/sensors/readings`.

## Requisitos

- ESP-IDF v5.x instalado y `IDF_PATH` configurado
- ESP32 conectado por USB
- Stack de infraestructura desplegado (`make deploy` en `infrastructure/`)

## Pasos para flashear

### 1. Despliega la infraestructura primero

El Thing, la Policy y las IoT Rules ya están definidos en el SAM template.
Si aún no lo hiciste:

```bash
cd ../infrastructure
make deploy KEY_PAIR=ecosmart-key
```

### 2. Provisiona el certificado del dispositivo

Usa el output `IoTAttachCertCommand` que imprime el deploy, o ejecuta:

```bash
# Genera cert + private key y los guarda directamente en main/certs/
aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile main/certs/device_cert.pem \
  --private-key-outfile main/certs/device_key.pem \
  --query certificateArn --output text
# Guarda el ARN que devuelve ↑

# Adjunta la policy al certificado
aws iot attach-policy \
  --policy-name ecosmart-esp32-policy \
  --target <CERT_ARN>

# Adjunta el certificado al Thing
aws iot attach-thing-principal \
  --thing-name ecosmart-esp32-$(aws sts get-caller-identity --query Account --output text) \
  --principal <CERT_ARN>
```

### 3. Descarga el Root CA de Amazon

```bash
curl -o main/certs/aws_root_ca.pem \
  https://www.amazontrust.com/repository/AmazonRootCA1.pem
```

### 4. Configura WiFi y endpoint

Edita `sdkconfig.defaults`:

```
CONFIG_ESP_WIFI_SSID="tu_red"
CONFIG_ESP_WIFI_PASSWORD="tu_password"
CONFIG_DEVICE_ID="esp32-mach-001"
```

Obtén el endpoint MQTT (output `IoTEndpointCommand` del deploy, o):

```bash
aws iot describe-endpoint --endpoint-type iot:Data-ATS \
  --query endpointAddress --output text
# Pega el resultado en CONFIG_AWS_IOT_ENDPOINT
```

### 5. Build & flash

```bash
cd esp32_firmware
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

## Estructura

```
esp32_firmware/
├── CMakeLists.txt
├── sdkconfig.defaults
└── main/
    ├── CMakeLists.txt      # embebe los certs como binarios
    ├── main.c              # app_main: WiFi → MQTT → loop de sensores
    ├── wifi_manager.c/h    # conexión WiFi STA con reintentos
    ├── mqtt_manager.c/h    # cliente MQTT TLS + publicación JSON
    ├── sensor_sim.c/h      # generador de lecturas con ~5% anomalías
    └── certs/              # certificados (no commitear a git)
```

## Tópicos MQTT

| Tópico | Contenido |
|---|---|
| `ecosmart/sensors/readings` | Lectura completa del sensor + scores del modelo |
| `ecosmart/sensors/alerts` | Alerta cuando `anomaly_score >= 0.65` |

## Flujo de datos

```
ESP32 → MQTT/TLS → AWS IoT Core → IoT Rule → S3
                                           sensor_readings/{equipment_id}/{timestamp}.json
                                           alerts/{equipment_id}/{timestamp}.json
                                     ↓
                                  Athena → Metabase
```

Las IoT Rules ya están definidas en el SAM template — no hace falta crearlas manualmente.

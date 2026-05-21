# Infrastructure — EcoSmart POC

Stack serverless con **Metabase en EC2** conectado a **Amazon Athena** sobre datos en **S3**.

## Arquitectura

```
ESP32 → MQTT/TLS → IoT Core → IoT Rules → S3 → Athena → Metabase (EC2)
```

## Costo estimado

| Recurso | Cuando apagado | Cuando encendido |
|---|---|---|
| EC2 t3.micro | $0.00/hora | $0.0104/hora |
| EBS 20GB | ~$1.60/mes | ~$1.60/mes |
| S3 (~1MB datos) | ~$0.00/mes | ~$0.00/mes |
| Athena queries | $0 | ~$0.00005/query |
| **Total demo** | **~$1.60/mes** | **+$0.02/hora** |

## Prerrequisitos

```bash
# SAM CLI
pip install aws-sam-cli

# Key Pair EC2 (crear en consola AWS o con CLI)
aws ec2 create-key-pair --key-name ecosmart-key \
  --query KeyMaterial --output text \
  --profile labbelopez.manuel@gmail.com > ~/.ssh/ecosmart-key.pem
chmod 400 ~/.ssh/ecosmart-key.pem
```

## Deploy

```bash
cd infrastructure/

# Deploy completo (solo la primera vez)
make deploy KEY_PAIR=ecosmart-key

# Ver outputs (URL, IPs, comandos)
make url
```

## Uso diario

```bash
# Encender para trabajar / demo
make start

# Ver URL de Metabase y estado
make status

# Apagar cuando termines
make stop
```

## Subir datos a S3

```bash
make upload
```

## Crear tablas en Athena

Después del deploy, ejecutar los DDLs en la consola de Athena o via CLI:

```bash
# Tabla sensor_readings
aws athena start-query-execution \
  --query-string file://tables/sensor_readings.sql \
  --work-group ecosmart-workgroup \
  --profile labbelopez.manuel@gmail.com

# Tabla alerts
aws athena start-query-execution \
  --query-string file://tables/alerts.sql \
  --work-group ecosmart-workgroup \
  --profile labbelopez.manuel@gmail.com
```

## Conectar Metabase a Athena

1. Abrir `http://<IP>:3000` en el browser
2. Settings → Databases → Add database
3. Tipo: **Amazon Athena**
4. Region: `us-east-1`
5. S3 staging directory: `s3://ecosmart-sensor-data-<ACCOUNT_ID>/query-results/`
6. Workgroup: `ecosmart-workgroup`
7. *(La instancia ya tiene IAM role — no necesitás access keys)*

## Destruir stack

```bash
make destroy
```

## Conectar ESP32 (después del deploy)

El SAM template ya crea el **Thing**, la **Policy** y las **IoT Rules** automáticamente.
Solo falta provisionar el certificado del dispositivo:

```bash
# 1. Genera cert y private key
aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile ../esp32_firmware/main/certs/device_cert.pem \
  --private-key-outfile ../esp32_firmware/main/certs/device_key.pem \
  --query certificateArn --output text
# Guarda el ARN que devuelve ↑

# 2. Adjunta policy y Thing al certificado
aws iot attach-policy --policy-name ecosmart-esp32-policy --target <CERT_ARN>
aws iot attach-thing-principal \
  --thing-name ecosmart-esp32-$(aws sts get-caller-identity --query Account --output text) \
  --principal <CERT_ARN>

# 3. Obtén el endpoint MQTT para el firmware
aws iot describe-endpoint --endpoint-type iot:Data-ATS \
  --query endpointAddress --output text
```

Luego sigue las instrucciones en `../esp32_firmware/README.md`.

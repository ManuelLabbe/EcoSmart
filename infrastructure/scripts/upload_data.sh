#!/bin/bash
# Sube los datos de sensores enriquecidos a S3
# Uso: ./scripts/upload_data.sh <account_id> [region]

set -e

ACCOUNT_ID=${1:?'Uso: ./upload_data.sh <account_id> [region]'}
REGION=${2:-us-east-1}
BUCKET="ecosmart-sensor-data-${ACCOUNT_ID}"
PROFILE="labbelopez.manuel@gmail.com"

echo "Subiendo datos a s3://${BUCKET}/"

# Datos históricos de sensores
aws s3 cp ../predictive_maintenance/outputs/predictions.csv \
  s3://${BUCKET}/sensor_readings/predictions.csv \
  --profile ${PROFILE} --region ${REGION}

echo "✅ Datos subidos."
echo ""
echo "Próximo paso: ejecutar el DDL en Athena:"
echo "  aws athena start-query-execution \\"
echo "    --query-string file://tables/sensor_readings.sql \\"
echo "    --work-group ecosmart-workgroup \\"
echo "    --profile ${PROFILE}"

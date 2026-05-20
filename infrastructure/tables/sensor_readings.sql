-- Tabla principal: lecturas de sensores enriquecidas con predicciones del modelo
-- Ejecutar en Athena una vez después del deploy

CREATE EXTERNAL TABLE IF NOT EXISTS ecosmart_sensors.sensor_readings (
  reading_id      BIGINT,
  equipment_id    STRING,
  equipment_type  STRING,
  timestamp       TIMESTAMP,
  air_temp_k      DOUBLE,
  process_temp_k  DOUBLE,
  rpm             INT,
  torque_nm       DOUBLE,
  tool_wear_min   INT,
  product_type    STRING,
  -- Predicciones del SensorTransformer
  anomaly_score   DOUBLE,
  predicted_failure INT,
  -- Modos de falla (ground truth si disponible)
  machine_failure INT,
  twf             INT,
  hdf             INT,
  pwf             INT,
  osf             INT,
  rnf             INT,
  -- Probabilidades por modo (output del modelo)
  prob_twf        DOUBLE,
  prob_hdf        DOUBLE,
  prob_pwf        DOUBLE,
  prob_osf        DOUBLE,
  prob_rnf        DOUBLE
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://ecosmart-sensor-data-ACCOUNT_ID/sensor_readings/'
TBLPROPERTIES (
  'skip.header.line.count' = '1',
  'classification' = 'csv'
);

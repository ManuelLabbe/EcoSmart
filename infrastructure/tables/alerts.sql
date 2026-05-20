-- Tabla de alertas generadas por el modelo
-- Se alimenta cuando anomaly_score supera el threshold

CREATE EXTERNAL TABLE IF NOT EXISTS ecosmart_sensors.alerts (
  alert_id        STRING,
  equipment_id    STRING,
  timestamp       TIMESTAMP,
  failure_mode    STRING,     -- TWF | HDF | PWF | OSF | RNF | MULTIPLE
  probability     DOUBLE,
  severity        STRING,     -- low | medium | high | critical
  anomaly_score   DOUBLE,
  air_temp_k      DOUBLE,
  process_temp_k  DOUBLE,
  rpm             INT,
  torque_nm       DOUBLE,
  tool_wear_min   INT,
  resolved        INT,        -- 0 = activa, 1 = resuelta
  resolved_at     TIMESTAMP
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
STORED AS TEXTFILE
LOCATION 's3://ecosmart-sensor-data-ACCOUNT_ID/alerts/'
TBLPROPERTIES (
  'skip.header.line.count' = '1',
  'classification' = 'csv'
);

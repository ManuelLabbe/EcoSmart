-- Tabla de lecturas del ciclo agua-vapor (Gateway UG1 / UG2)
-- Alimentada por el simulador ug_simulator.py via IoT Core → S3
-- Ejecutar en Athena una vez después del deploy

CREATE EXTERNAL TABLE IF NOT EXISTS ecosmart_sensors.process_readings (
  reading_id         STRING,
  equipment_id       STRING,    -- esp32-ug1-001 | esp32-ug2-001
  tag                STRING,    -- TAG del instrumento (FT_5001, TT_3101-1, ...)
  variable           STRING,    -- tipo de fluido (Agua Industrial, Vapor Sobrecalentado, ...)
  variable_medicion  STRING,    -- tipo de medición (Flujo, Presión, Temperatura, ...)
  value              DOUBLE,    -- valor medido con ruido simulado
  unit               STRING,    -- unidad (m3/h, bar, °C, %, ton/h, ...)
  regime             STRING,    -- régimen operacional: MT | BL1 | BL2
  nominal_value      DOUBLE,    -- valor de diseño del balance de planta
  deviation_pct      DOUBLE,    -- desviación % respecto al nominal
  is_anomaly         INT,       -- 1 = anomalía inyectada, 0 = operación normal
  desde              STRING,    -- origen del tramo (e.g. Pozo 1)
  hasta              STRING,    -- destino del tramo (e.g. Captación de Agua)
  timestamp          STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
STORED AS TEXTFILE
LOCATION 's3://ecosmart-sensor-data-390844787410/process_readings/'
;

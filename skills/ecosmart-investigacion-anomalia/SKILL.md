---
name: ecosmart-investigacion-anomalia
description: Análisis de causa raíz de anomalías para COMASA desde el MCP de EcoSmart: línea de tiempo, sensor disparador e hipótesis. Úsala para "investigar alerta", "causa raíz", "RCA" o "por qué falló".
---

# Investigación de Causa Raíz de Anomalías — EcoSmart / COMASA

Esta skill responde el "¿por qué pasó?" después de un evento de anomalía. El destinatario es ingeniería de confiabilidad: el informe debe ser técnico, basado en evidencia, y construir memoria institucional sobre fallas recurrentes. A diferencia del informe ejecutivo (alto nivel) y la orden de trabajo (acción), aquí el foco es el análisis profundo de qué ocurrió en los sensores.

## Contexto del sistema

COMASA, termoeléctrica a biomasa. SensorTransformer on-device predice 5 modos de falla por nodo LoRa. El MCP `ecomasa` expone los tools de sensores, alertas y tendencias.

Nodos: `lora-cal-001` (Caldera N°1), `lora-mol-001` (Molino Biomasa), `lora-cin-001` (Cinta Transportadora), `lora-gen-001` (Generador Turbina).

## Flujo de trabajo

Si el MCP solo muestra 3 tools, pide reconectar (`/mcp`) — faltan los de diagnóstico/tendencia.

1. **`query_alerts`** (filtra por node_id si se conoce, o por severity) — identifica la alerta a investigar: equipo, modo de falla, score, severidad, y los valores de sensor en el momento del disparo.
2. **`get_node_trend`** (limit 200) sobre el nodo — obtén la ventana amplia antes/durante/después del evento. Esta serie temporal es el corazón de la investigación: permite ver la **evolución** y detectar cuál variable empezó a desviarse primero.
3. **`run_diagnostic`** sobre el nodo — confirma modo de falla dominante y probabilidades, para contrastar con tu hipótesis.
4. (Opcional) **`query_sensor_readings`** sobre el nodo en el pico — valores crudos exactos para citar en el informe.

Si el usuario no indica qué anomalía investigar, llama `query_alerts` (severity=critical) y propón investigar la más severa, o pregunta.

## Análisis: cómo encontrar la causa raíz

Lee **`references/rangos-normales.md`** para los rangos normales y la firma de sensores de cada modo de falla. El método:

1. **Línea de tiempo.** Recorre la serie de `get_node_trend` y ubica cuándo el anomaly score empezó a subir. ¿Fue abrupto (evento transitorio) o gradual (degradación)?
2. **Variable disparadora.** Compara cada sensor (air_temp, process_temp, rpm, torque, tool_wear) contra su rango normal. Identifica cuál se salió primero y por cuánto. Calcula el delta vs. el rango. La firma de sensores por modo de falla (en la referencia) te dice qué esperar.
3. **Correlación.** ¿Se movieron varias variables juntas? Ej: torque alto + tool_wear alto → OSF; ΔT pequeño + RPM bajas → HDF.
4. **Hipótesis.** Formula la causa más probable basada en la evidencia, no en el modo de falla que reportó el modelo a ciegas. El modelo da una pista; tú la confirmas o matizas con los datos.
5. **Descarta falsos positivos.** Si el score subió pero ningún sensor salió de rango, considera ruido del sensor o falla del nodo LoRa (no del equipo).

## Formato de salida

Genera un archivo HTML autónomo (CSS inline, imprimible). Lee `assets/template.html`, copia estructura y estilos, reemplaza el contenido. El template trae layout técnico con línea de tiempo, tabla de desviación de sensores y bloque de hipótesis.

Estructura obligatoria:
1. **Cabecera** — equipo, nodo, alerta investigada (folio/fecha), modo de falla reportado
2. **Línea de tiempo del evento** — cómo evolucionó el score y cuándo se gatilló la alerta
3. **Desviación de sensores** — tabla: variable, valor en el evento, rango normal, desviación, ¿disparadora?
4. **Hipótesis de causa raíz** — la conclusión razonada, citando la evidencia
5. **Recomendación** — acción correctiva y si corresponde generar una OT (referencia a skill de orden de trabajo)
6. **Pie** — nota de que alimenta la base de conocimiento de fallas

Guarda como `RCA-AAAAMMDD-<equipo>.html` y di la ruta. Ofrece abrirlo.

## Principio

Cada afirmación de causa debe apoyarse en un dato observado. Distingue claramente entre lo que el dato muestra (hechos) y tu interpretación (hipótesis). Una buena RCA es honesta sobre su nivel de certeza: si la evidencia es ambigua, dilo y propón qué medir para confirmar.

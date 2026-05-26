---
name: ecosmart-informe-ejecutivo
description: Genera un informe ejecutivo HTML de salud de planta para COMASA desde el MCP de EcoSmart. Úsala para "informe ejecutivo", "reporte de planta", "estado general" o "resumen para gerencia".
---

# Informe Ejecutivo de Salud de Planta — EcoSmart / COMASA

Esta skill convierte los datos crudos de sensores del MCP de EcoSmart en un briefing que un gerente lee en 2 minutos y con el que toma decisiones (parada de planta, presupuesto de mantención, priorización). El lector NO es técnico: evita jerga, traduce todo a impacto operacional y riesgo.

## Contexto del sistema

COMASA es una termoeléctrica a biomasa en Lautaro, Araucanía. Un ESP32 actúa como gateway LoRa que agrega lecturas de 4 nodos en planta y corre un SensorTransformer on-device que predice 5 modos de falla. Los datos llegan a AWS y se exponen vía el MCP `ecomasa`.

Nodos LoRa típicos:
- `lora-cal-001` — Caldera N°1
- `lora-mol-001` — Molino Biomasa
- `lora-cin-001` — Cinta Transportadora
- `lora-gen-001` — Generador Turbina

Modos de falla (traducir SIEMPRE al lenguaje de negocio en el informe):
- **TWF** → desgaste de herramienta/componente
- **HDF** → problema de disipación de calor / refrigeración
- **PWF** → falla de potencia / sistema eléctrico-motriz
- **OSF** → sobreesfuerzo / sobrecarga mecánica
- **RNF** → falla aleatoria sin patrón claro

Estado de salud (umbral de anomaly score):
- **NORMAL** (verde): score promedio < 0.65
- **ALERTA** (amarillo): 0.65 – 0.80
- **CRÍTICO** (rojo): > 0.80

## Flujo de trabajo

Ejecuta los tools del MCP `ecomasa` en este orden. Si el MCP solo muestra 3 tools, pídele al usuario que reconecte el servidor (`/mcp`) porque faltan los tools de diagnóstico.

1. **`get_top_risk_equipment`** (limit 5) — obtén el ranking de nodos por riesgo. Esta es la columna vertebral del informe.
2. **`run_diagnostic`** sobre los 2-3 nodos de mayor riesgo — para cada uno consigue estado, modo de falla dominante, tendencia de las últimas 20 lecturas y alertas recientes.
3. **`get_failure_mode_heatmap`** — panorama de qué tipo de falla domina en cada nodo, para la sección de patrones.
4. **`query_alerts`** (severity=critical, limit 10) — alertas críticas abiertas (resolved=0) que requieren acción inmediata.

Si algún tool devuelve vacío (datos sin `node_id` porque el firmware aún no envía nodos), usa `get_equipment_summary` y `query_alerts` sin filtro como respaldo, y nótalo discretamente al pie del informe.

## Síntesis: cómo pensar el informe

No vuelques los datos crudos. Interpreta:
- Si el top risk tiene un nodo CRÍTICO, ese es el titular del informe.
- Traduce score a riesgo de negocio: "Caldera N°1 opera con 23% de sus lecturas en zona de alerta" comunica más que "avg_score 0.71".
- Para cada equipo en riesgo da UNA acción recomendada concreta y su urgencia.
- Si todo está NORMAL, dilo claramente y con confianza — un informe que dice "todo bien" también tiene valor.

## Formato de salida

Genera un archivo HTML autónomo (CSS inline, imprimible a PDF desde el navegador). Lee `assets/template.html`, copia su estructura y estilos, y reemplaza el contenido con los datos reales. El template ya trae la identidad visual de COMASA/EcoSmart, los badges de estado con color y el layout de 1 página.

Estructura obligatoria del informe:
1. **Encabezado** — título, fecha/hora, semáforo global de planta
2. **Resumen ejecutivo** — 2-3 frases: estado general + el hallazgo más importante
3. **Equipos que requieren atención** — tarjetas con los top 2-3 nodos: nombre, estado (badge), modo de falla en lenguaje de negocio, acción recomendada, urgencia
4. **Alertas críticas abiertas** — tabla breve solo si hay; si no, indícalo
5. **Pie** — nota de origen de datos y que es generado automáticamente por EcoSmart

Guarda el archivo como `informe-ejecutivo-AAAA-MM-DD.html` en el directorio de trabajo y dile al usuario la ruta. Ofrece abrirlo en el navegador para revisión/impresión a PDF.

## Tono

Profesional, directo, orientado a decisión. Como un jefe de operaciones informando al directorio: claro sobre el riesgo, sin alarmismo, siempre con la acción siguiente clara.

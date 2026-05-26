---
name: ecosmart-orden-trabajo
description: Genera órdenes de trabajo de mantención para COMASA desde el MCP de EcoSmart, con modo de falla, urgencia, checklist y repuestos. Úsala para "orden de trabajo", "OT" o instrucción al técnico.
---

# Orden de Trabajo Predictiva — EcoSmart / COMASA

Esta skill cierra la brecha entre "el modelo predijo una falla" y "el técnico sabe exactamente qué hacer". El destinatario es un técnico o supervisor de mantención: necesita instrucciones claras, no análisis de datos. Una buena OT se puede imprimir y entregar al turno sin explicación adicional.

## Contexto del sistema

COMASA, termoeléctrica a biomasa. El SensorTransformer on-device predice 5 modos de falla por nodo LoRa. El MCP `ecomasa` expone los tools de diagnóstico.

Nodos: `lora-cal-001` (Caldera N°1), `lora-mol-001` (Molino Biomasa), `lora-cin-001` (Cinta Transportadora), `lora-gen-001` (Generador Turbina).

## Flujo de trabajo

Si el MCP solo muestra 3 tools, pide al usuario reconectar (`/mcp`) — faltan los de diagnóstico.

1. **`run_diagnostic`** sobre el nodo/equipo objetivo — obtén estado, modo de falla dominante, severidad, stats promedio y alertas recientes. Es la fuente principal de la OT.
2. **`get_node_trend`** (limit 50) sobre el mismo nodo — confirma si la tendencia del anomaly score es ascendente. La **pendiente** define la ventana de urgencia:
   - Tendencia plana en zona normal → preventivo programable
   - Ascenso lento → ventana de días
   - Ascenso marcado o ya en CRÍTICO → ventana de horas / inmediato
3. Mapea el modo de falla dominante a la intervención concreta leyendo **`references/modos-falla.md`**. Ese archivo tiene el checklist y repuestos por cada modo (TWF/HDF/PWF/OSF/RNF). Léelo siempre antes de redactar la OT.

Si el usuario no especifica equipo, primero llama `get_top_risk_equipment` y genera la OT para el nodo más crítico (o pregunta cuál).

## Cómo construir la ventana de urgencia

Combina severidad actual + dirección de la tendencia. No inventes plazos arbitrarios; justifícalos con el dato:
- "Score subió de 0.41 a 0.78 en las últimas 50 lecturas → intervención dentro de 24h"
- "Score estable en 0.30 → incluir en mantención preventiva del próximo ciclo"

## Formato de salida

Genera un archivo HTML autónomo (CSS inline, imprimible). Lee `assets/template.html`, copia estructura y estilos, reemplaza el contenido. El template trae el formato de OT con folio, datos del equipo, checklist con casillas y campos de firma.

Estructura obligatoria:
1. **Cabecera** — folio (OT-AAAAMMDD-XXX), equipo, ubicación, fecha de emisión, prioridad
2. **Diagnóstico** — modo de falla detectado, evidencia (score, tendencia, sensores fuera de rango), ventana de urgencia justificada
3. **Checklist de intervención** — pasos accionables del modo de falla (desde la referencia), con casillas
4. **Repuestos / insumos probables** — lista del modo de falla
5. **Registro de ejecución** — campos en blanco: técnico asignado, fecha ejecución, observaciones, firma

Guarda como `OT-AAAAMMDD-<equipo>.html` y di la ruta al usuario. Ofrece abrirla para imprimir.

## Principio

Toda afirmación de la OT debe ser ejecutable o verificable por el técnico. Si escribes "revisar sistema", especifica qué componente y qué buscar. La OT es tan buena como la claridad de su checklist.

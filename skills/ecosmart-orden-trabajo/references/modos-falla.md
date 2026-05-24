# Modos de falla → intervención concreta

Mapeo de cada modo de falla del SensorTransformer (dataset AI4I 2020, adaptado a equipos de termoeléctrica a biomasa) a un checklist accionable y repuestos probables. Usa la sección del modo de falla **dominante** que devuelve `run_diagnostic`. Si hay dos modos con probabilidad similar, incluye ambos checklists.

Rangos normales de operación (referencia para la sección de evidencia):
- Temperatura aire: 295–304 K
- Temperatura proceso: 305–313 K
- RPM: 1168–2886
- Torque: 3.8–76.6 Nm
- Desgaste herramienta: 0–253 min

---

## TWF — Tool Wear Failure (desgaste de herramienta/componente)

**Qué significa:** el componente de contacto (cuchilla de molino, rodillo, inserto) superó su vida útil. Indicador clave: `tool_wear_min` alto (>200) junto con torque elevado.

**Checklist de intervención:**
1. Detener el equipo de forma segura siguiendo procedimiento LOTO (bloqueo/etiquetado).
2. Inspeccionar visualmente el componente de desgaste (cuchillas, insertos, rodillos).
3. Medir el desgaste contra la especificación del fabricante.
4. Reemplazar el componente si supera el límite de desgaste.
5. Verificar alineación y torque de apriete tras el reemplazo.
6. Registrar las horas de operación del componente reemplazado.

**Repuestos / insumos probables:** juego de cuchillas/insertos, pernos de fijación, grasa/lubricante de montaje, EPP de corte.

---

## HDF — Heat Dissipation Failure (disipación de calor / refrigeración)

**Qué significa:** el sistema no logra evacuar calor. Indicador clave: diferencia pequeña entre temperatura de proceso y de aire (< ~8.6 K) con RPM bajas. Riesgo de sobrecalentamiento.

**Checklist de intervención:**
1. Verificar nivel y estado del refrigerante / fluido térmico.
2. Inspeccionar ventiladores y extractores: giro libre, ruido, vibración.
3. Limpiar intercambiadores de calor / radiadores (acumulación de biomasa y polvo es común en planta).
4. Revisar filtros de aire y reemplazar si están obstruidos.
5. Comprobar termostatos y sensores de temperatura.
6. Confirmar caudal de ventilación tras la limpieza.

**Repuestos / insumos probables:** filtros de aire, refrigerante, correa de ventilador, termostato, kit de limpieza de intercambiador.

---

## PWF — Power Failure (potencia / sistema eléctrico-motriz)

**Qué significa:** la potencia entregada (torque × velocidad) se sale del rango operativo. Indicador clave: combinación anómala de RPM bajas y torque alto, o caídas de potencia.

**Checklist de intervención:**
1. Inspeccionar conexiones eléctricas del motor: apriete, oxidación, puntos calientes.
2. Medir corriente y voltaje en las tres fases; comparar con placa.
3. Revisar variador de frecuencia (VFD) / arrancador: códigos de falla, ventilación.
4. Verificar acoplamiento motor-carga: desgaste, holgura, alineación.
5. Inspeccionar rodamientos del motor (temperatura, ruido, vibración).
6. Confirmar parámetros de potencia tras la intervención.

**Repuestos / insumos probables:** contactores, fusibles, rodamientos de motor, acoplamiento elástico, terminales eléctricos.

---

## OSF — Overstrain Failure (sobreesfuerzo / sobrecarga mecánica)

**Qué significa:** carga mecánica acumulada excesiva (producto de desgaste × torque sobre el umbral del tipo de producto). Riesgo de fractura o deformación.

**Checklist de intervención:**
1. Detener y aplicar LOTO.
2. Inspeccionar elementos estructurales y de transmisión por fisuras o deformación.
3. Verificar que la carga de alimentación de biomasa no exceda la nominal.
4. Revisar tensión de correas/cadenas y estado de poleas/piñones.
5. Comprobar protecciones de sobrecarga (limitadores de torque, embragues).
6. Ajustar parámetros de alimentación para no exceder carga nominal.

**Repuestos / insumos probables:** correas/cadenas de transmisión, limitador de torque, poleas/piñones, elementos de sujeción estructural.

---

## RNF — Random Failure (falla aleatoria sin patrón)

**Qué significa:** anomalía sin perfil de sensor característico. Puede ser ruido, evento transitorio o falla incipiente no tipificada. Requiere inspección general, no una acción única.

**Checklist de intervención:**
1. Realizar inspección general del equipo (visual, auditiva, térmica).
2. Revisar registros recientes en busca de eventos correlacionados.
3. Verificar sensores y cableado del nodo LoRa (posible falsa lectura).
4. Comprobar parámetros generales: vibración, temperatura, ruido anormal.
5. Si no se halla causa, programar monitoreo reforzado del nodo por 48–72h.
6. Escalar a ingeniería de confiabilidad si la anomalía persiste (ver skill de investigación de anomalías).

**Repuestos / insumos probables:** indeterminado hasta inspección; tener a mano kit de diagnóstico y repuestos de sensor LoRa.

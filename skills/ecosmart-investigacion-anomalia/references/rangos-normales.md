# Rangos normales de operación y firma de sensores por modo de falla

Base de referencia para el análisis de causa raíz. Los rangos provienen del dataset AI4I 2020 que entrenó al SensorTransformer, adaptado a equipos de termoeléctrica a biomasa.

## Rangos normales de operación

| Variable | Símbolo | Rango normal | Unidad |
|---|---|---|---|
| Temperatura de aire | `air_temp_k` | 295 – 304 | K |
| Temperatura de proceso | `process_temp_k` | 305 – 313 | K |
| Velocidad de rotación | `rpm` | 1168 – 2886 | rpm |
| Torque | `torque_nm` | 3.8 – 76.6 | Nm |
| Desgaste de herramienta | `tool_wear_min` | 0 – 253 | min |

Derivadas útiles:
- **ΔT = process_temp_k − air_temp_k.** Normal ≈ 8.6 – 12 K. Un ΔT pequeño (<8.6 K) con RPM bajas es firma de HDF.
- **Potencia ≈ torque_nm × rpm × 2π/60 (W).** Rango sano ≈ 3500 – 9000 W. Fuera de ese rango → firma de PWF.

## Firma de sensores por modo de falla

Qué esperar en los sensores cuando cada modo está realmente presente. Úsalo para confirmar o matizar la predicción del modelo.

### TWF — Tool Wear Failure
- **Disparador:** `tool_wear_min` muy alto (>200), típicamente con `torque_nm` elevado (>60).
- **Patrón temporal:** degradación **gradual** — el desgaste sube lento y monótono hasta gatillar.
- **Confirma si:** tool_wear cerca del tope del rango y la subida del score acompaña la subida del desgaste.

### HDF — Heat Dissipation Failure
- **Disparador:** ΔT pequeño (process − air < 8.6 K) junto con `rpm` bajas (<1380).
- **Patrón temporal:** puede ser gradual (ensuciamiento de intercambiador) o escalonado (falla de ventilador).
- **Confirma si:** las dos temperaturas convergen y/o el aire no logra subir mientras el proceso se mantiene.

### PWF — Power Failure
- **Disparador:** potencia (torque × velocidad) fuera de 3500–9000 W. Suele verse como RPM bajas + torque alto, o caídas bruscas.
- **Patrón temporal:** frecuentemente **abrupto** (evento eléctrico, disparo de protección).
- **Confirma si:** el producto torque×rpm cruza el límite justo cuando sube el score.

### OSF — Overstrain Failure
- **Disparador:** producto `tool_wear_min × torque_nm` sobre el umbral (sobrecarga acumulada).
- **Patrón temporal:** gradual con posible quiebre abrupto al fracturar.
- **Confirma si:** torque y desgaste altos simultáneos; la carga mecánica acumulada es el factor.

### RNF — Random Failure
- **Disparador:** ninguno característico. El score sube sin que ningún sensor salga claramente de rango.
- **Patrón temporal:** transitorio o errático.
- **Confirma si:** NO encuentras una variable disparadora clara. Sospecha de ruido del sensor o falla del nodo LoRa antes que del equipo. Recomienda monitoreo reforzado en vez de intervención mecánica inmediata.

## Cómo reportar la desviación

Para cada variable en la tabla del informe, calcula:
- **Valor en el evento** (del query_alerts o del pico de la tendencia)
- **Rango normal** (de la tabla de arriba)
- **Desviación**: cuánto se salió (ej. "+18% sobre el máximo", "dentro de rango")
- **¿Disparadora?**: marca la(s) variable(s) que iniciaron la cadena causal

La variable disparadora no siempre es la más desviada al final — busca cuál se movió **primero** en la serie temporal.

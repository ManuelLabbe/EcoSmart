#pragma once
#include <stdint.h>

/*
 * SensorTransformer inference en C para ESP32-S3.
 * Arquitectura: 3 encoder layers, d_model=64, 4 heads, dim_ff=256, window=20, 6 features.
 * Input: últimas 20 lecturas (air_temp_k, process_temp_k, rpm, torque_nm, tool_wear_min, type_enc).
 * Output: probabilidades de falla [TWF, HDF, PWF, OSF, RNF] en [0,1].
 */

typedef struct {
    float air_temp_k;
    float process_temp_k;
    float rpm;
    float torque_nm;
    float tool_wear_min;
    float type_enc;   /* L=0, M=1, H=2 */
} st_sample_t;

typedef struct {
    float twf, hdf, pwf, osf, rnf;
    float anomaly_score;   /* max de las 5 probabilidades */
    int   predicted_failure;
} st_result_t;

/* Inicializa el buffer circular interno (llama una vez al arrancar). */
void st_init(void);

/* Agrega una lectura al buffer y corre inferencia cuando el buffer está lleno.
 * Retorna 1 si hay resultado nuevo, 0 si el buffer aún no tiene 20 muestras. */
int st_push_and_infer(const st_sample_t *sample, st_result_t *result);

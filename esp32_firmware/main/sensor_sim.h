#pragma once
#include <stdint.h>

typedef struct {
    float   air_temp_k;
    float   process_temp_k;
    int     rpm;
    float   torque_nm;
    int     tool_wear_min;
    // Simulated model output
    float   anomaly_score;
    int     predicted_failure;
    float   prob_twf;
    float   prob_hdf;
    float   prob_pwf;
    float   prob_osf;
    float   prob_rnf;
    // Ground truth flags (known only in simulation)
    int     machine_failure;
    int     twf, hdf, pwf, osf, rnf;
} sensor_reading_t;

void sensor_sim_init(void);
void sensor_sim_next(sensor_reading_t *out);

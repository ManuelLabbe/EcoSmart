#include "sensor_sim.h"
#include "esp_random.h"
#include <string.h>

static uint32_t reading_counter = 0;

/* LoRa sensor nodes aggregated by this ESP32 gateway */
typedef struct { const char *id; const char *name; } lora_node_t;
static const lora_node_t LORA_NODES[] = {
    { "lora-cal-001",  "Caldera N\xc2\xb01"          },
    { "lora-mol-001",  "Molino Biomasa"               },
    { "lora-cin-001",  "Cinta Transportadora"         },
    { "lora-gen-001",  "Generador Turbina"            },
};
#define N_NODES (sizeof(LORA_NODES) / sizeof(LORA_NODES[0]))

/* Linear congruential float in [lo, hi] using esp_random() */
static float rand_float(float lo, float hi)
{
    float t = (float)(esp_random() & 0xFFFF) / 65535.0f;
    return lo + t * (hi - lo);
}

static int rand_int(int lo, int hi)
{
    return lo + (int)(esp_random() % (uint32_t)(hi - lo + 1));
}

void sensor_sim_init(void)
{
    reading_counter = 0;
}

void sensor_sim_next(sensor_reading_t *out)
{
    memset(out, 0, sizeof(*out));
    reading_counter++;

    /* Assign LoRa node round-robin */
    const lora_node_t *node = &LORA_NODES[reading_counter % N_NODES];
    strncpy(out->node_id,   node->id,   sizeof(out->node_id)   - 1);
    strncpy(out->node_name, node->name, sizeof(out->node_name) - 1);

    /* ~5 % de lecturas inyectan una anomalía */
    int inject = (esp_random() % 100) < 5;
    int failure_mode = inject ? (int)(esp_random() % 5) : -1; /* 0=TWF 1=HDF 2=PWF 3=OSF 4=RNF */

    /* --- Sensores base (rangos del dataset AI4I 2020) --- */
    out->air_temp_k     = rand_float(295.0f, 304.0f);
    out->process_temp_k = rand_float(305.0f, 313.0f);
    out->rpm            = rand_int(1168, 2886);
    out->torque_nm      = rand_float(3.8f, 76.6f);
    out->tool_wear_min  = rand_int(0, 253);

    /* --- Perfiles de falla (desplazan el rango del sensor) --- */
    if (inject) {
        switch (failure_mode) {
        case 0: /* TWF — desgaste extremo de herramienta */
            out->tool_wear_min = rand_int(200, 253);
            out->torque_nm     = rand_float(60.0f, 76.6f);
            break;
        case 1: /* HDF — disipación de calor baja */
            out->air_temp_k     = rand_float(295.0f, 296.5f);
            out->process_temp_k = rand_float(311.0f, 313.0f);
            break;
        case 2: /* PWF — falla de potencia */
            out->rpm       = rand_int(1168, 1400);
            out->torque_nm = rand_float(60.0f, 76.6f);
            break;
        case 3: /* OSF — sobrecarga */
            out->tool_wear_min = rand_int(180, 253);
            out->torque_nm     = rand_float(55.0f, 76.6f);
            break;
        case 4: /* RNF — falla aleatoria, sin perfil específico */
        default:
            break;
        }
    }

    /* --- Output simulado del SensorTransformer --- */
    if (inject) {
        out->anomaly_score      = rand_float(0.65f, 0.98f);
        out->predicted_failure  = 1;
        out->prob_twf = rand_float(0.1f, 0.9f);
        out->prob_hdf = rand_float(0.1f, 0.9f);
        out->prob_pwf = rand_float(0.1f, 0.9f);
        out->prob_osf = rand_float(0.1f, 0.9f);
        out->prob_rnf = rand_float(0.1f, 0.9f);
    } else {
        out->anomaly_score      = rand_float(0.02f, 0.30f);
        out->predicted_failure  = 0;
        out->prob_twf = rand_float(0.0f, 0.05f);
        out->prob_hdf = rand_float(0.0f, 0.05f);
        out->prob_pwf = rand_float(0.0f, 0.05f);
        out->prob_osf = rand_float(0.0f, 0.05f);
        out->prob_rnf = rand_float(0.0f, 0.05f);
    }

    /* --- Ground truth (solo visible en simulación) --- */
    out->machine_failure = inject ? 1 : 0;
    out->twf = (failure_mode == 0) ? 1 : 0;
    out->hdf = (failure_mode == 1) ? 1 : 0;
    out->pwf = (failure_mode == 2) ? 1 : 0;
    out->osf = (failure_mode == 3) ? 1 : 0;
    out->rnf = (failure_mode == 4) ? 1 : 0;
}

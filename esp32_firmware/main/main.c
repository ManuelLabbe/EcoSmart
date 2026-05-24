#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "wifi_manager.h"
#include "mqtt_manager.h"
#include "sensor_sim.h"
#include "sensor_transformer.h"

static const char *TAG = "main";

void app_main(void)
{
    ESP_LOGI(TAG, "EcoSmart ESP32-S3 — SensorTransformer on-device — device: %s", CONFIG_DEVICE_ID);

    wifi_init_sta();
    mqtt_app_start();
    sensor_sim_init();
    st_init();

    sensor_reading_t raw;
    st_result_t      result;
    uint32_t         seq = 0;

    while (1) {
        /* 1. Genera valores de sensores (físicos, sin scores simulados) */
        sensor_sim_next(&raw);

        /* 2. Alimenta el buffer del Transformer y corre inferencia */
        st_sample_t sample = {
            .air_temp_k     = raw.air_temp_k,
            .process_temp_k = raw.process_temp_k,
            .rpm            = (float)raw.rpm,
            .torque_nm      = raw.torque_nm,
            .tool_wear_min  = (float)raw.tool_wear_min,
            .type_enc       = 0.0f,   /* producto tipo L */
        };

        if (st_push_and_infer(&sample, &result)) {
            /* Buffer lleno — reemplaza los scores simulados con los reales */
            raw.anomaly_score     = result.anomaly_score;
            raw.predicted_failure = result.predicted_failure;
            raw.prob_twf = result.twf;
            raw.prob_hdf = result.hdf;
            raw.prob_pwf = result.pwf;
            raw.prob_osf = result.osf;
            raw.prob_rnf = result.rnf;
        }
        /* Antes de tener 20 muestras usa los scores del simulador como warm-up */

        mqtt_publish_reading(&raw, ++seq);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SENSOR_INTERVAL_MS));
    }
}

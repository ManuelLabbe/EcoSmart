#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "wifi_manager.h"
#include "mqtt_manager.h"
#include "sensor_sim.h"

static const char *TAG = "main";

void app_main(void)
{
    ESP_LOGI(TAG, "EcoSmart ESP32 sensor node starting — device: %s", CONFIG_DEVICE_ID);

    wifi_init_sta();
    mqtt_app_start();
    sensor_sim_init();

    sensor_reading_t reading;
    uint32_t seq = 0;

    while (1) {
        sensor_sim_next(&reading);
        mqtt_publish_reading(&reading, ++seq);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SENSOR_INTERVAL_MS));
    }
}

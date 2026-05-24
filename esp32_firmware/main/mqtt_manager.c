#include "mqtt_manager.h"

#include "esp_log.h"
#include "esp_tls.h"
#include "mqtt_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include <stdio.h>
#include <time.h>

static const char *TAG = "mqtt";

/* Certificados embebidos (generados por CMakeLists target_add_binary_data) */
extern const uint8_t aws_root_ca_start[]   asm("_binary_aws_root_ca_pem_start");
extern const uint8_t aws_root_ca_end[]     asm("_binary_aws_root_ca_pem_end");
extern const uint8_t device_cert_start[]   asm("_binary_device_cert_pem_start");
extern const uint8_t device_cert_end[]     asm("_binary_device_cert_pem_end");
extern const uint8_t device_key_start[]    asm("_binary_device_key_pem_start");
extern const uint8_t device_key_end[]      asm("_binary_device_key_pem_end");

#define TOPIC_READINGS "ecosmart/sensors/readings"
#define TOPIC_ALERTS   "ecosmart/sensors/alerts"
#define ALERT_THRESHOLD 0.65f

static esp_mqtt_client_handle_t s_client = NULL;
static EventGroupHandle_t s_mqtt_event_group;
#define MQTT_CONNECTED_BIT BIT0

static void mqtt_event_handler(void *arg, esp_event_base_t base,
                                int32_t id, void *data)
{
    esp_mqtt_event_handle_t event = data;
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "Connected to AWS IoT Core");
        xEventGroupSetBits(s_mqtt_event_group, MQTT_CONNECTED_BIT);
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "Disconnected");
        xEventGroupClearBits(s_mqtt_event_group, MQTT_CONNECTED_BIT);
        break;
    case MQTT_EVENT_PUBLISHED:
        ESP_LOGD(TAG, "msg_id=%d published", event->msg_id);
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT error");
        break;
    default:
        break;
    }
}

void mqtt_app_start(void)
{
    s_mqtt_event_group = xEventGroupCreate();

    char broker_uri[128];
    snprintf(broker_uri, sizeof(broker_uri), "mqtts://%s:%d",
             CONFIG_AWS_IOT_ENDPOINT, CONFIG_AWS_IOT_PORT);

    esp_mqtt_client_config_t cfg = {
        .broker = {
            .address.uri = broker_uri,
            .verification = {
                .certificate     = (const char *)aws_root_ca_start,
                .certificate_len = aws_root_ca_end - aws_root_ca_start,
            },
        },
        .credentials = {
            .client_id       = CONFIG_DEVICE_ID,
            .authentication  = {
                .certificate     = (const char *)device_cert_start,
                .certificate_len = device_cert_end - device_cert_start,
                .key             = (const char *)device_key_start,
                .key_len         = device_key_end - device_key_start,
            },
        },
    };

    s_client = esp_mqtt_client_init(&cfg);
    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    esp_mqtt_client_start(s_client);

    ESP_LOGI(TAG, "Waiting for MQTT connection…");
    xEventGroupWaitBits(s_mqtt_event_group, MQTT_CONNECTED_BIT,
                        pdFALSE, pdTRUE, portMAX_DELAY);
}

/* Construye y publica el JSON de lectura de sensor */
void mqtt_publish_reading(const sensor_reading_t *r, uint32_t seq)
{
    char payload[640];
    int n = snprintf(payload, sizeof(payload),
        "{"
        "\"reading_id\":%lu,"
        "\"equipment_id\":\"%s\","
        "\"node_id\":\"%s\","
        "\"node_name\":\"%s\","
        "\"equipment_type\":\"lathe\","
        "\"product_type\":\"L\","
        "\"air_temp_k\":%.2f,"
        "\"process_temp_k\":%.2f,"
        "\"rpm\":%d,"
        "\"torque_nm\":%.2f,"
        "\"tool_wear_min\":%d,"
        "\"anomaly_score\":%.4f,"
        "\"predicted_failure\":%d,"
        "\"machine_failure\":%d,"
        "\"twf\":%d,\"hdf\":%d,\"pwf\":%d,\"osf\":%d,\"rnf\":%d,"
        "\"prob_twf\":%.4f,\"prob_hdf\":%.4f,\"prob_pwf\":%.4f,"
        "\"prob_osf\":%.4f,\"prob_rnf\":%.4f"
        "}",
        (unsigned long)seq,
        CONFIG_DEVICE_ID,
        r->node_id,
        r->node_name,
        r->air_temp_k, r->process_temp_k,
        r->rpm, r->torque_nm, r->tool_wear_min,
        r->anomaly_score, r->predicted_failure,
        r->machine_failure,
        r->twf, r->hdf, r->pwf, r->osf, r->rnf,
        r->prob_twf, r->prob_hdf, r->prob_pwf, r->prob_osf, r->prob_rnf
    );

    esp_mqtt_client_publish(s_client, TOPIC_READINGS, payload, n, 1, 0);
    ESP_LOGI(TAG, "reading #%lu  score=%.3f", (unsigned long)seq, r->anomaly_score);

    /* Genera alerta si supera el threshold */
    if (r->anomaly_score >= ALERT_THRESHOLD) {
        /* Detectar modo de falla dominante */
        const char *mode = "MULTIPLE";
        float max_p = 0.0f;
        #define CHECK(field, name) if (r->prob_##field > max_p) { max_p = r->prob_##field; mode = name; }
        CHECK(twf, "TWF") CHECK(hdf, "HDF") CHECK(pwf, "PWF")
        CHECK(osf, "OSF") CHECK(rnf, "RNF")
        #undef CHECK

        const char *severity = r->anomaly_score >= 0.90f ? "critical"
                             : r->anomaly_score >= 0.80f ? "high"
                             : r->anomaly_score >= 0.65f ? "medium" : "low";

        char alert[512];
        int m = snprintf(alert, sizeof(alert),
            "{"
            "\"equipment_id\":\"%s\","
            "\"node_id\":\"%s\","
            "\"node_name\":\"%s\","
            "\"failure_mode\":\"%s\","
            "\"probability\":%.4f,"
            "\"severity\":\"%s\","
            "\"anomaly_score\":%.4f,"
            "\"air_temp_k\":%.2f,\"process_temp_k\":%.2f,"
            "\"rpm\":%d,\"torque_nm\":%.2f,\"tool_wear_min\":%d,"
            "\"resolved\":0"
            "}",
            CONFIG_DEVICE_ID, r->node_id, r->node_name, mode, max_p, severity,
            r->anomaly_score,
            r->air_temp_k, r->process_temp_k,
            r->rpm, r->torque_nm, r->tool_wear_min
        );
        esp_mqtt_client_publish(s_client, TOPIC_ALERTS, alert, m, 1, 0);
        ESP_LOGW(TAG, "ALERT  mode=%s  severity=%s", mode, severity);
    }
}

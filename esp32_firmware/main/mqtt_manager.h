#pragma once
#include "sensor_sim.h"

void mqtt_app_start(void);
void mqtt_publish_reading(const sensor_reading_t *r, uint32_t seq);

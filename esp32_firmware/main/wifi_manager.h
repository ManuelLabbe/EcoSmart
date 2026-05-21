#pragma once

/* Bloquea hasta conseguir IP. Llama esp_event_loop_create_default() internamente. */
void wifi_init_sta(void);

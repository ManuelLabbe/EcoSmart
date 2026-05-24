idf_component_register(
    SRCS
        "main.c"
        "wifi_manager.c"
        "mqtt_manager.c"
        "sensor_sim.c"
        "sensor_transformer.c"
    INCLUDE_DIRS "."
)

# Embed certificates as binary data into the firmware
target_add_binary_data(${COMPONENT_LIB} "certs/aws_root_ca.pem"    TEXT)
target_add_binary_data(${COMPONENT_LIB} "certs/device_cert.pem"    TEXT)
target_add_binary_data(${COMPONENT_LIB} "certs/device_key.pem"     TEXT)

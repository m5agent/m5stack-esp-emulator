idf_component_register(
    SRCS "core2_openeth_probe.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_netif esp_event esp_timer esp_http_client esp_eth
)

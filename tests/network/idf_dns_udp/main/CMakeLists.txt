idf_component_register(
    SRCS "dns_udp_probe.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_netif esp_event esp_wifi lwip
)

idf_component_register(
    SRCS "dhcp_renewal_probe.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_netif esp_event esp_wifi lwip
)

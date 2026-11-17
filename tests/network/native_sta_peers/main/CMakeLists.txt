idf_component_register(SRCS "probe.c" INCLUDE_DIRS "." REQUIRES esp_wifi esp_netif esp_event nvs_flash lwip)
if(DEFINED M5_FIXTURE_WPA2)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE M5_FIXTURE_WPA2=1)
endif()

if(M5_NAMESPACE_DNS)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE M5_NAMESPACE_DNS=1)
endif()

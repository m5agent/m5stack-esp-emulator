idf_component_register(SRCS "probe.c" INCLUDE_DIRS "." REQUIRES esp_wifi esp_netif esp_event nvs_flash lwip esp_driver_gpio)

if(M5_FIXTURE_STICKS3_BUTTON)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE M5_FIXTURE_STICKS3_BUTTON=1)
endif()

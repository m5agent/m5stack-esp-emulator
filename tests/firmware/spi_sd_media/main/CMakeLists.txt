idf_component_register(SRCS "main.c"
                       PRIV_REQUIRES fatfs esp_driver_spi esp_driver_sdspi)
if(PROBE_PAPER)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_PAPER=1)
endif()

idf_component_register(SRCS "main.c"
                       PRIV_REQUIRES fatfs esp_driver_spi esp_driver_sdspi esp_driver_gpio)
if(PROBE_PAPERDIY)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_PAPER=1 PROBE_PAPERDIY=1)
elseif(PROBE_PAPER)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_PAPER=1)
endif()

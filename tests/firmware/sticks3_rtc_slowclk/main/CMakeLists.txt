idf_component_register(SRCS "main.c" REQUIRES esp_hw_support esp_system esp_timer freertos)
idf_component_get_property(esp_timer_component esp_timer COMPONENT_DIR)
target_include_directories(${COMPONENT_LIB} PRIVATE "${esp_timer_component}/private_include")

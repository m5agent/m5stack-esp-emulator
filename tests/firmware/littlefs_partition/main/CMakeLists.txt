idf_component_register(SRCS "main.c" INCLUDE_DIRS "." REQUIRES esp_partition)
littlefs_create_partition_image(storage ../flash_data)

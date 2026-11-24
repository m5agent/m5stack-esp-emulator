idf_component_register(SRCS "review_main.c" INCLUDE_DIRS "."
                       REQUIRES esp_wifi esp_netif esp_event nvs_flash lwip esp_driver_gpio)

# ESP-IDF first evaluates this file in a requirements scan that cannot see
# command-line cache variables. Validate and configure only in the real pass.
if(CMAKE_BUILD_EARLY_EXPANSION)
    return()
endif()

set(review_modes good wrong setup offline)
if(NOT DEFINED REVIEW_MODE OR NOT REVIEW_MODE IN_LIST review_modes)
    message(FATAL_ERROR "Set -D REVIEW_MODE=good|wrong|setup|offline")
endif()

string(TOUPPER "${REVIEW_MODE}" review_mode_upper)
target_compile_definitions(${COMPONENT_LIB} PRIVATE "REVIEW_MODE_${review_mode_upper}=1")

# The offline control references no Wi-Fi or socket API, so the linker keeps
# no radio code. The other modes use the shared fixture operations.
if(NOT REVIEW_MODE STREQUAL "offline")
    target_sources(${COMPONENT_LIB} PRIVATE "review_ops.c")
endif()

if(REVIEW_MODE STREQUAL "setup")
    if(NOT DEFINED REVIEW_SETUP_GPIO)
        message(FATAL_ERROR "REVIEW_MODE=setup requires -D REVIEW_SETUP_GPIO=<active-low button GPIO>")
    endif()
    target_compile_definitions(${COMPONENT_LIB} PRIVATE "REVIEW_SETUP_GPIO=${REVIEW_SETUP_GPIO}")
endif()

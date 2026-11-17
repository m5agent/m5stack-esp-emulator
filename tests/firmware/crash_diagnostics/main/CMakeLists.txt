idf_component_register(SRCS "main.c" INCLUDE_DIRS ".")
if(CRASH_PROBE_WATCHDOG)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE CRASH_PROBE_WATCHDOG=1)
endif()

#include <stdio.h>
#include <stdlib.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static __attribute__((noinline, noreturn)) void trigger_riscv_abort(void)
{
    puts("RISCV_C6_CRASH_PROBE_ARMED");
    fflush(stdout);
    abort();
}

void app_main(void)
{
    puts("RISCV_C6_CRASH_PROBE_BOOT");
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(750));
    trigger_riscv_abort();
}

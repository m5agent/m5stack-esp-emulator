#include <stdio.h>
#include <stdlib.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static void trigger_fault(void *arg)
{
    (void)arg;
    printf("CRASH_PROBE_ARMED cpu=%d\n", (int)xPortGetCoreID());
    fflush(stdout);
#ifdef CRASH_PROBE_WATCHDOG
    portDISABLE_INTERRUPTS();
    for (;;) {
        __asm__ volatile("nop");
    }
#else
    abort();
#endif
}

void app_main(void)
{
    printf("CRASH_PROBE_BOOT\n");
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(400));
    BaseType_t result = xTaskCreatePinnedToCore(
        trigger_fault, "fixture_fault", 4096, NULL, 2, NULL, 1
    );
    configASSERT(result == pdPASS);
}

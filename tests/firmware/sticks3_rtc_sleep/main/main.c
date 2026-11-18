#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>

#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static bool verify_timer_wake(unsigned iteration, int64_t timeout_us)
{
    const int64_t tolerance_us = 5000;
    esp_err_t status = esp_sleep_enable_timer_wakeup(timeout_us);
    if (status != ESP_OK) {
        printf("RTC_SLEEP_FAIL iteration=%u phase=configure status=%d\n", iteration, status);
        fflush(stdout);
        return false;
    }

    printf("RTC_SLEEP_ENTER iteration=%u requested_us=%" PRId64 "\n", iteration, timeout_us);
    fflush(stdout);
    int64_t start_us = esp_timer_get_time();
    status = esp_light_sleep_start();
    int64_t elapsed_us = esp_timer_get_time() - start_us;
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    printf("RTC_SLEEP_RETURN iteration=%u status=%d cause=%d elapsed_us=%" PRId64 "\n",
           iteration, status, (int)cause, elapsed_us);

    if (status != ESP_OK || cause != ESP_SLEEP_WAKEUP_TIMER || elapsed_us < timeout_us - tolerance_us) {
        printf("RTC_SLEEP_FAIL iteration=%u phase=return\n", iteration);
        fflush(stdout);
        return false;
    }

    fflush(stdout);
    return true;
}

void app_main(void)
{
    printf("RTC_SLEEP_BOOT reset_reason=%d timer_cause=%d\n", (int)esp_reset_reason(), (int)ESP_SLEEP_WAKEUP_TIMER);
    fflush(stdout);

    if (!verify_timer_wake(1, 100000)) {
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
    if (!verify_timer_wake(2, 220000)) {
        return;
    }

    printf("RTC_SLEEP_PASS iterations=2\n");
    fflush(stdout);
}

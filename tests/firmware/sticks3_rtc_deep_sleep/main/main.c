#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "esp_attr.h"
#include "esp_rtc_time.h"
#include "esp_sleep.h"
#include "esp_system.h"

#define RETAINED_COOKIE UINT32_C(0x7c83e419)
#define VOLATILE_COOKIE UINT32_C(0x1a2f9e51)

static RTC_NOINIT_ATTR uint32_t retained_cookie;
static RTC_NOINIT_ATTR uint32_t sleep_iteration;
static RTC_NOINIT_ATTR uint64_t entered_us;
static RTC_NOINIT_ATTR uint64_t requested_us;
static volatile uint32_t volatile_cookie;

static void verify(int condition, const char *check)
{
    if (!condition) {
        printf("RTC_DEEP_FAIL %s\n", check);
        fflush(stdout);
        abort();
    }
}

void app_main(void)
{
    esp_reset_reason_t reset = esp_reset_reason();
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    uint64_t now = esp_rtc_get_time_us();
    printf("RTC_DEEP_BOOT reset=%d cause=%d rtc_us=%" PRIu64 "\n", reset, cause, now);
    verify(volatile_cookie == 0, "digital_bss_was_not_reinitialized");

    if (reset == ESP_RST_POWERON) {
        verify(cause == ESP_SLEEP_WAKEUP_UNDEFINED, "cold_wakeup_cause");
        retained_cookie = RETAINED_COOKIE;
        sleep_iteration = 0;
    } else {
        verify(reset == ESP_RST_DEEPSLEEP, "expected_deep_sleep_reset");
        verify(cause == ESP_SLEEP_WAKEUP_TIMER, "timer_wakeup_cause");
        verify(retained_cookie == RETAINED_COOKIE, "rtc_cookie_lost");
        verify(sleep_iteration >= 1 && sleep_iteration <= 2, "rtc_iteration_lost");
        verify(now >= entered_us, "rtc_time_reversed");
        uint64_t elapsed = now - entered_us;
        printf("RTC_DEEP_WAKE step=%" PRIu32 " requested_us=%" PRIu64
               " elapsed_us=%" PRIu64 " rtc_cookie=0x%08" PRIx32 "\n",
               sleep_iteration, requested_us, elapsed, retained_cookie);
        verify(elapsed + 30000 >= requested_us && elapsed <= requested_us + 850000,
               "rtc_elapsed_outside_window");
    }

    if (sleep_iteration == 2) {
        puts("RTC_DEEP_PASS cycles=2");
        fflush(stdout);
        return;
    }

    ++sleep_iteration;
    requested_us = sleep_iteration == 1 ? 650000 : 1500000;
    volatile_cookie = VOLATILE_COOKIE;
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup(requested_us));
    entered_us = esp_rtc_get_time_us();
    printf("RTC_DEEP_ENTER step=%" PRIu32 " requested_us=%" PRIu64 "\n",
           sleep_iteration, requested_us);
    fflush(stdout);
    esp_deep_sleep_start();
    verify(0, "deep_sleep_returned");
}

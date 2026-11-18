#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "esp_private/esp_clk.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/rtc.h"

#ifdef M5_RTC_MIXED_REJECT
#include "soc/rtc_cntl_reg.h"
#endif

static const gpio_num_t button_b = GPIO_NUM_12;
static const uint64_t cancelled_timer_us = 2000000;

typedef struct {
    uint64_t start_ticks;
    uint32_t slowclk_period;
} sleep_observation_t;

#ifdef M5_RTC_MIXED_REJECT
static const uint64_t rejected_timer_us = 1400000;

static bool verify_mixed_reject(sleep_observation_t *observation)
{
    int level = gpio_get_level(button_b);
    uint32_t before = REG_GET_FIELD(RTC_CNTL_SLP_REJECT_CAUSE_REG, RTC_CNTL_REJECT_CAUSE);
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup(rejected_timer_us));
    uint64_t start_ticks = rtc_time_get();
    printf("RTC_MIXED_REJECT_ENTER requested_us=%" PRIu64 " b_level=%d before_cause=0x%" PRIx32
           " start_ticks=%" PRIu64 "\n", rejected_timer_us, level, before, start_ticks);
    fflush(stdout);
    if (level != 0 || before != 0) {
        printf("RTC_MIXED_FAIL step=2 phase=reject_precondition\n");
        fflush(stdout);
        return false;
    }

    esp_err_t status = esp_light_sleep_start();
    uint64_t end_ticks = rtc_time_get();
    uint32_t slowclk_period = esp_clk_slowclk_cal_get();
    uint32_t cause = REG_GET_FIELD(RTC_CNTL_SLP_REJECT_CAUSE_REG, RTC_CNTL_REJECT_CAUSE);
    uint32_t raw = REG_READ(RTC_CNTL_INT_RAW_REG) &
                   (RTC_CNTL_SLP_REJECT_INT_RAW | RTC_CNTL_SLP_WAKEUP_INT_RAW);
    level = gpio_get_level(button_b);
    printf("RTC_MIXED_REJECT_RETURN status=%d cause=0x%" PRIx32 " sleep_raw=0x%" PRIx32 " b_level=%d"
           " end_ticks=%" PRIu64 " slowclk_period=%" PRIu32 "\n", status, cause, raw, level, end_ticks, slowclk_period);
    REG_SET_BIT(RTC_CNTL_STATE0_REG, RTC_CNTL_SLP_REJECT_CAUSE_CLR);
    uint32_t after = REG_GET_FIELD(RTC_CNTL_SLP_REJECT_CAUSE_REG, RTC_CNTL_REJECT_CAUSE);
    printf("RTC_MIXED_REJECT_CLEAR cause=0x%" PRIx32 "\n", after);
    uint64_t rejected_elapsed_us = end_ticks >= start_ticks ?
        rtc_time_slowclk_to_us(end_ticks - start_ticks, slowclk_period) : UINT64_MAX;
    if (status != ESP_ERR_SLEEP_REJECT || cause != RTC_GPIO_TRIG_EN || raw != 0 || level != 0 ||
        after != 0 || slowclk_period == 0 || rejected_elapsed_us >= 500000) {
        printf("RTC_MIXED_FAIL step=2 phase=reject_return\n");
        fflush(stdout);
        return false;
    }
    *observation = (sleep_observation_t){.start_ticks = start_ticks, .slowclk_period = slowclk_period};
    printf("RTC_MIXED_REJECT_PASS elapsed_us=%" PRIu64 "\n", rejected_elapsed_us);
    fflush(stdout);
    return true;
}
#endif

static bool sleep_with_gpio_and_timer(unsigned step, uint64_t requested_us,
                                      esp_sleep_wakeup_cause_t expected,
                                      sleep_observation_t *observation)
{
    int level = gpio_get_level(button_b);
    if (level != 1) {
        printf("RTC_MIXED_FAIL step=%u phase=enter b_level=%d\n", step, level);
        fflush(stdout);
        return false;
    }
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup(requested_us));
    printf("RTC_MIXED_ENTER step=%u requested_us=%" PRIu64 " b_level=%d\n", step, requested_us, level);
    fflush(stdout);

    uint64_t start_ticks = rtc_time_get();
    int64_t start_us = esp_timer_get_time();
    esp_err_t status = esp_light_sleep_start();
    int64_t elapsed_us = esp_timer_get_time() - start_us;
    uint64_t end_ticks = rtc_time_get();
    uint32_t slowclk_period = esp_clk_slowclk_cal_get();
    uint64_t rtc_elapsed_us = end_ticks >= start_ticks ?
                              rtc_time_slowclk_to_us(end_ticks - start_ticks, slowclk_period) : 0;
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    level = gpio_get_level(button_b);
    printf("RTC_MIXED_RETURN step=%u status=%d cause=%d b_level=%d start_ticks=%" PRIu64
           " end_ticks=%" PRIu64 " slowclk_period=%" PRIu32 " rtc_elapsed_us=%" PRIu64
           " esp_elapsed_us=%" PRId64 "\n",
           step, status, (int)cause, level, start_ticks, end_ticks, slowclk_period, rtc_elapsed_us, elapsed_us);

    // Allow for SDK entry/exit overhead while distinguishing the old deadline.
    const uint64_t early_tolerance_us = 10000;
    const uint64_t late_tolerance_us = 80000;
    bool elapsed_valid = elapsed_us > 0 && rtc_elapsed_us > 0 && slowclk_period > 0;
    bool expected_timing = expected == ESP_SLEEP_WAKEUP_TIMER ?
        rtc_elapsed_us + early_tolerance_us >= requested_us && rtc_elapsed_us <= requested_us + late_tolerance_us :
        rtc_elapsed_us + early_tolerance_us < requested_us;
    if (status != ESP_OK || cause != expected || level != (expected == ESP_SLEEP_WAKEUP_TIMER) ||
        !elapsed_valid || !expected_timing) {
        printf("RTC_MIXED_FAIL step=%u phase=return\n", step);
        fflush(stdout);
        return false;
    }
    if (observation) {
        *observation = (sleep_observation_t){.start_ticks = start_ticks, .slowclk_period = slowclk_period};
    }
    fflush(stdout);
    return true;
}

static bool wait_for_b_release(void)
{
    int64_t deadline_us = esp_timer_get_time() + 1200000;
    while (gpio_get_level(button_b) == 0) {
        if (esp_timer_get_time() >= deadline_us) {
            printf("RTC_MIXED_FAIL step=2 phase=release\n");
            fflush(stdout);
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    return true;
}

void app_main(void)
{
    const gpio_config_t input = {
        .pin_bit_mask = 1ULL << button_b,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    printf("RTC_MIXED_BOOT reset_reason=%d timer_cause=%d gpio_cause=%d\n", (int)esp_reset_reason(),
           (int)ESP_SLEEP_WAKEUP_TIMER, (int)ESP_SLEEP_WAKEUP_GPIO);
    fflush(stdout);

    ESP_ERROR_CHECK(gpio_config(&input));
    ESP_ERROR_CHECK(gpio_wakeup_enable(button_b, GPIO_INTR_LOW_LEVEL));
    ESP_ERROR_CHECK(esp_sleep_enable_gpio_wakeup());
    sleep_observation_t cancelled;
    sleep_observation_t followup;
    if (!sleep_with_gpio_and_timer(1, 120000, ESP_SLEEP_WAKEUP_TIMER, NULL) ||
        !sleep_with_gpio_and_timer(2, cancelled_timer_us, ESP_SLEEP_WAKEUP_GPIO, &cancelled)) {
        return;
    }
#ifdef M5_RTC_MIXED_REJECT
    sleep_observation_t rejected;
    if (!verify_mixed_reject(&rejected)) {
        return;
    }
#endif
    if (!wait_for_b_release() ||
        !sleep_with_gpio_and_timer(3, 3000000, ESP_SLEEP_WAKEUP_TIMER, &followup)) {
        return;
    }

    uint64_t gap_us = followup.start_ticks > cancelled.start_ticks ?
        rtc_time_slowclk_to_us(followup.start_ticks - cancelled.start_ticks, cancelled.slowclk_period) : 0;
    if (gap_us == 0 || gap_us > cancelled_timer_us - 50000) {
        printf("RTC_MIXED_FAIL step=3 phase=stale_timer_setup gap_us=%" PRIu64 "\n", gap_us);
        fflush(stdout);
        return;
    }
#ifdef M5_RTC_MIXED_REJECT
    uint64_t reject_gap_us = followup.start_ticks > rejected.start_ticks ?
        rtc_time_slowclk_to_us(followup.start_ticks - rejected.start_ticks, rejected.slowclk_period) : 0;
    if (reject_gap_us == 0 || reject_gap_us > rejected_timer_us - 50000) {
        printf("RTC_MIXED_FAIL step=3 phase=rejected_timer_setup gap_us=%" PRIu64 "\n", reject_gap_us);
        fflush(stdout);
        return;
    }
    printf("RTC_MIXED_REJECT_DEADLINE old_timer_us=%" PRIu64 " gap_us=%" PRIu64 "\n", rejected_timer_us, reject_gap_us);
#endif
    printf("RTC_MIXED_PASS old_timer_us=%" PRIu64 " gap_us=%" PRIu64 "\n", cancelled_timer_us, gap_us);
    fflush(stdout);
}

#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/rtc.h"
#include "soc/rtc_cntl_reg.h"
#include "soc/soc.h"

static const uint32_t sleep_clear_mask =
    RTC_CNTL_SLP_WAKEUP_INT_CLR | RTC_CNTL_SLP_REJECT_INT_CLR;
static const uint32_t sleep_raw_mask =
    RTC_CNTL_SLP_WAKEUP_INT_RAW | RTC_CNTL_SLP_REJECT_INT_RAW;

static bool require(bool value, const char *phase)
{
    if (!value) {
        printf("RTC_AWAKE_FAIL phase=%s raw=%08" PRIx32 "\n",
               phase, REG_READ(RTC_CNTL_INT_RAW_REG));
    }
    return value;
}

static void program_compare(uint64_t target, bool strobe)
{
    uint32_t high = (uint32_t)(target >> 32) & RTC_CNTL_SLP_VAL_HI_V;

    REG_WRITE(RTC_CNTL_SLP_TIMER0_REG, (uint32_t)target);
    if (strobe) {
        high |= RTC_CNTL_MAIN_TIMER_ALARM_EN;
    }
    REG_WRITE(RTC_CNTL_SLP_TIMER1_REG, high);
}

static bool readback_compare(uint64_t target)
{
    return REG_READ(RTC_CNTL_SLP_TIMER0_REG) == (uint32_t)target &&
           REG_READ(RTC_CNTL_SLP_TIMER1_REG) ==
               ((uint32_t)(target >> 32) & RTC_CNTL_SLP_VAL_HI_V);
}

static bool alarm_raw(void)
{
    return REG_GET_BIT(RTC_CNTL_INT_RAW_REG, RTC_CNTL_MAIN_TIMER_INT_RAW) != 0;
}

static bool wait_quiet(uint64_t through)
{
    const int64_t deadline = esp_timer_get_time() + 1900000;
    do {
        if (alarm_raw()) {
            return false;
        }
        if (rtc_time_get() >= through) {
            return true;
        }
        vTaskDelay(1);
    } while (esp_timer_get_time() < deadline);
    return false;
}

static uint64_t wait_alarm(void)
{
    const int64_t deadline = esp_timer_get_time() + 1900000;
    do {
        if (alarm_raw()) {
            return rtc_time_get();
        }
        vTaskDelay(1);
    } while (esp_timer_get_time() < deadline);
    return 0;
}

void app_main(void)
{
    const uint64_t hz = rtc_clk_slow_freq_get_hz();
    printf("RTC_AWAKE_BOOT slow_hz=%" PRIu64 "\n", hz);
    if (!require(hz > 10000, "slow-clock-rate")) {
        return;
    }

    /* Leave the IRQ masked so the probe observes the raw condition without
     * a handler consuming it. Sleep wake and reject interrupts are untouched. */
    const bool main_mask_was_enabled =
        REG_GET_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_MAIN_TIMER_INT_ENA) != 0;
    REG_CLR_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_MAIN_TIMER_INT_ENA);
    REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_MAIN_TIMER_INT_CLR);
    const uint64_t register_pattern = UINT64_C(0x5aa589abcdef);
    program_compare(register_pattern, false);
    if (!require(readback_compare(register_pattern), "programmed-low32-high16")) {
        return;
    }
    printf("RTC_AWAKE_READBACK low=%08" PRIx32 " high=%04" PRIx32 "\n",
           REG_READ(RTC_CNTL_SLP_TIMER0_REG), REG_READ(RTC_CNTL_SLP_TIMER1_REG));

    const uint64_t staged = rtc_time_get() + hz / 25;
    program_compare(staged, false);
    if (!require(wait_quiet(staged + hz / 15), "staged-without-strobe")) {
        return;
    }
    printf("RTC_AWAKE_STAGED_PAST deadline=%" PRIu64 " counter=%" PRIu64 "\n",
           staged, rtc_time_get());

    const uint64_t now = rtc_time_get();
    const uint64_t armed = now + hz / 6;
    const uint64_t alternate = now + hz / 2;
    program_compare(armed, true);
    if (!require(readback_compare(armed), "write-only-strobe")) {
        return;
    }
    program_compare(alternate, false);
    if (!require(readback_compare(alternate) &&
                     wait_quiet(armed - hz / 20),
                 "staged-while-armed")) {
        return;
    }
    const uint64_t fired = wait_alarm();
    if (!require(fired >= armed && fired < alternate, "awake-raw-alarm")) {
        return;
    }
    const uint32_t raw_before_clear = REG_READ(RTC_CNTL_INT_RAW_REG);
    REG_WRITE(RTC_CNTL_INT_CLR_REG, sleep_clear_mask);
    if (!require(alarm_raw(), "sleep-w1c-preserves-main-raw")) {
        return;
    }
    const uint32_t sleep_after_clear = REG_READ(RTC_CNTL_INT_RAW_REG) & sleep_raw_mask;
    REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_MAIN_TIMER_INT_CLR);
    const uint32_t raw_after_clear = REG_READ(RTC_CNTL_INT_RAW_REG);
    if (!require(!(raw_after_clear & RTC_CNTL_MAIN_TIMER_INT_RAW) &&
                     (raw_after_clear & sleep_raw_mask) == sleep_after_clear,
                 "main-w1c-clears-main-raw")) {
        return;
    }
    printf("RTC_AWAKE_FIRED armed=%" PRIu64 " staged_alternate=%" PRIu64
           " fired=%" PRIu64 " raw_before=%08" PRIx32 " raw_after=%08" PRIx32 "\n",
           armed, alternate, fired, raw_before_clear, raw_after_clear);

    const uint64_t replacement_base = rtc_time_get();
    const uint64_t canceled = replacement_base + hz / 6;
    const uint64_t replacement = replacement_base + hz / 2;
    program_compare(canceled, true);
    vTaskDelay(pdMS_TO_TICKS(20));
    program_compare(replacement, true);
    if (!require(readback_compare(replacement) &&
                     wait_quiet(canceled + hz / 20),
                 "old-deadline-replaced")) {
        return;
    }
    const uint64_t fired_replacement = wait_alarm();
    if (!require(fired_replacement >= replacement, "replacement-raw-alarm")) {
        return;
    }
    REG_WRITE(RTC_CNTL_INT_CLR_REG, RTC_CNTL_MAIN_TIMER_INT_CLR);
    if (!require(!alarm_raw(), "replacement-w1c")) {
        return;
    }
    if (main_mask_was_enabled) {
        REG_SET_BIT(RTC_CNTL_INT_ENA_REG, RTC_CNTL_MAIN_TIMER_INT_ENA);
    }
    printf("RTC_AWAKE_REPLACED canceled=%" PRIu64 " replacement=%" PRIu64
           " fired=%" PRIu64 "\n",
           canceled, replacement, fired_replacement);
    printf("RTC_AWAKE_PASS\n");
}

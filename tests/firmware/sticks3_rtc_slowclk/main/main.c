#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "esp_private/esp_clk.h"
#include "esp_private/systimer.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_timer_impl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "soc/rtc.h"

#define RTC_MASK ((UINT64_C(1) << 48) - 1)
#define CALIBRATION_CYCLES 1024
#define AWAKE_DELAY_MS 200
#define TIMER_WAKE_US UINT64_C(500000)

typedef struct {
    uint64_t systimer_ticks;
    uint64_t rtc_ticks;
} clock_sample_t;

static clock_sample_t sample_clocks(void)
{
    clock_sample_t sample;
    sample.systimer_ticks = esp_timer_impl_get_counter_reg();
    sample.rtc_ticks = rtc_time_get();
    return sample;
}

static bool near(uint64_t actual, uint64_t expected)
{
    uint64_t tolerance = expected / 10;
    return actual >= expected - tolerance && actual <= expected + tolerance;
}

void app_main(void)
{
#if CONFIG_RTC_CLK_SRC_INT_8MD256
    const soc_rtc_slow_clk_src_t expected_source = SOC_RTC_SLOW_CLK_SRC_RC_FAST_D256;
    const char *variant = "rc_fast_div256";
#else
    const soc_rtc_slow_clk_src_t expected_source = SOC_RTC_SLOW_CLK_SRC_RC_SLOW;
    const char *variant = "rc_slow";
#endif
    const soc_rtc_slow_clk_src_t selected = rtc_clk_slow_src_get();
    const uint32_t nominal_hz = rtc_clk_slow_freq_get_hz();
    const uint32_t sdk_period_q19 = esp_clk_slowclk_cal_get();
    const uint32_t measured_period_q19 = rtc_clk_cal(RTC_CAL_RTC_MUX, CALIBRATION_CYCLES);
    printf("RTC_CLOCK_PROBE_BOOT variant=%s reset=%d expected_source=%d selected_source=%d "
           "nominal_hz=%" PRIu32 " sdk_period_q19=%" PRIu32 " measured_period_q19=%" PRIu32
           " cal_cycles=%d\n", variant, (int)esp_reset_reason(), (int)expected_source,
           (int)selected, nominal_hz, sdk_period_q19, measured_period_q19, CALIBRATION_CYCLES);
    fflush(stdout);
    if (selected != expected_source || !nominal_hz || !sdk_period_q19 || !measured_period_q19) {
        printf("RTC_CLOCK_PROBE_DONE result=FAIL phase=clock_selection_or_calibration\n");
        fflush(stdout);
        return;
    }

    clock_sample_t start = sample_clocks();
    vTaskDelay(pdMS_TO_TICKS(AWAKE_DELAY_MS));
    clock_sample_t end = sample_clocks();
    uint64_t systimer_us = systimer_ticks_to_us(end.systimer_ticks - start.systimer_ticks);
    uint64_t rtc_delta = (end.rtc_ticks - start.rtc_ticks) & RTC_MASK;
    uint64_t observed_hz = systimer_us ? rtc_delta * UINT64_C(1000000) / systimer_us : 0;
    uint64_t calibration_hz = (UINT64_C(1000000) << RTC_CLK_CAL_FRACT) / measured_period_q19;
    uint64_t calibrated_us = rtc_time_slowclk_to_us(rtc_delta, measured_period_q19);
    bool awake_ok = systimer_us > 0 && near(observed_hz, nominal_hz) &&
                    near(observed_hz, calibration_hz) && near(calibrated_us, systimer_us);
    printf("RTC_CLOCK_AWAKE rtc_start=%" PRIu64 " rtc_end=%" PRIu64 " rtc_delta=%" PRIu64
           " systimer_start=%" PRIu64 " systimer_end=%" PRIu64 " systimer_us=%" PRIu64
           " observed_hz=%" PRIu64 " calibration_hz=%" PRIu64 " calibrated_us=%" PRIu64
           " awake_ok=%d\n", start.rtc_ticks, end.rtc_ticks, rtc_delta, start.systimer_ticks,
           end.systimer_ticks, systimer_us, observed_hz, calibration_hz, calibrated_us, awake_ok);
    fflush(stdout);

    esp_err_t status = esp_sleep_enable_timer_wakeup(TIMER_WAKE_US);
    if (status != ESP_OK) {
        printf("RTC_CLOCK_PROBE_DONE result=FAIL phase=configure_timer status=%d\n", status);
        fflush(stdout);
        return;
    }
    printf("RTC_CLOCK_SLEEP_ENTER requested_us=%" PRIu64 " timer_cause=%d\n",
           TIMER_WAKE_US, (int)ESP_SLEEP_WAKEUP_TIMER);
    fflush(stdout);
    start = sample_clocks();
    status = esp_light_sleep_start();
    end = sample_clocks();
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    rtc_delta = (end.rtc_ticks - start.rtc_ticks) & RTC_MASK;
    systimer_us = systimer_ticks_to_us(end.systimer_ticks - start.systimer_ticks);
    bool timer_ok = status == ESP_OK && cause == ESP_SLEEP_WAKEUP_TIMER;
    printf("RTC_CLOCK_SLEEP_RETURN status=%d cause=%d timer_ok=%d"
           " rtc_start=%" PRIu64 " rtc_end=%" PRIu64 " rtc_delta=%" PRIu64
           " systimer_start=%" PRIu64 " systimer_end=%" PRIu64 " systimer_sdk_us=%" PRIu64
           " calibrated_rtc_us=%" PRIu64 "\n", status, (int)cause, timer_ok,
           start.rtc_ticks, end.rtc_ticks, rtc_delta, start.systimer_ticks,
           end.systimer_ticks, systimer_us, rtc_time_slowclk_to_us(rtc_delta, measured_period_q19));
    printf("RTC_CLOCK_PROBE_DONE result=%s awake_ok=%d timer_ok=%d\n",
           awake_ok && timer_ok ? "PASS" : "FAIL", awake_ok, timer_ok);
    fflush(stdout);
}

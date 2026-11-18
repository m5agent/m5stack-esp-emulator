#include <inttypes.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_timer.h"

void app_main(void)
{
    const gpio_num_t button_b = GPIO_NUM_12;
    const gpio_config_t input = {
        .pin_bit_mask = 1ULL << button_b,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    printf("RTC_GPIO_SLEEP_BOOT reset_reason=%d gpio_cause=%d\n",
           (int)esp_reset_reason(), (int)ESP_SLEEP_WAKEUP_GPIO);

    ESP_ERROR_CHECK(gpio_config(&input));
    ESP_ERROR_CHECK(gpio_wakeup_enable(button_b, GPIO_INTR_LOW_LEVEL));
    ESP_ERROR_CHECK(esp_sleep_enable_gpio_wakeup());
    int level = gpio_get_level(button_b);
    if (level != 1) {
        printf("RTC_GPIO_SLEEP_FAIL phase=precondition b_level=%d\n", level);
        fflush(stdout);
        return;
    }

    printf("RTC_GPIO_SLEEP_ENTER pin=%d active_low=1 b_level=%d\n", (int)button_b, level);
    fflush(stdout);
    int64_t start_us = esp_timer_get_time();
    esp_err_t status = esp_light_sleep_start();
    int64_t elapsed_us = esp_timer_get_time() - start_us;
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    printf("RTC_GPIO_SLEEP_RETURN status=%d cause=%d b_level=%d elapsed_us=%" PRId64 "\n",
           status, (int)cause, gpio_get_level(button_b), elapsed_us);

    if (status != ESP_OK || cause != ESP_SLEEP_WAKEUP_GPIO) {
        printf("RTC_GPIO_SLEEP_FAIL phase=return\n");
        fflush(stdout);
        return;
    }

    printf("RTC_GPIO_SLEEP_PASS\n");
    fflush(stdout);
}

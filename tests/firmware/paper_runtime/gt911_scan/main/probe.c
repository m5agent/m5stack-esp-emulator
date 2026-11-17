#include <inttypes.h>
#include <stdio.h>

#include "driver/i2c.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum {
    GT911_ADDRESS = 0x5d,
    GT911_RATE = 0x8056,
    GT911_STATUS = 0x814e,
    REPORT_READY = 0x80,
    REPORT_ONE_POINT = REPORT_READY | 1,
    SAMPLES = 8,
};

static uint8_t read_register(uint16_t reg)
{
    const uint8_t address[] = {reg >> 8, reg & 0xff};
    uint8_t value;
    ESP_ERROR_CHECK(i2c_master_write_read_device(I2C_NUM_0, GT911_ADDRESS,
        address, sizeof(address), &value, sizeof(value), pdMS_TO_TICKS(100)));
    return value;
}

static void write_register(uint16_t reg, uint8_t value)
{
    const uint8_t bytes[] = {reg >> 8, reg & 0xff, value};
    ESP_ERROR_CHECK(i2c_master_write_to_device(I2C_NUM_0, GT911_ADDRESS,
        bytes, sizeof(bytes), pdMS_TO_TICKS(100)));
}

static uint8_t wait_report(int64_t timeout_us)
{
    const int64_t deadline = esp_timer_get_time() + timeout_us;
    while (esp_timer_get_time() < deadline) {
        uint8_t status = read_register(GT911_STATUS);
        if (status & REPORT_READY) {
            return status;
        }
        vTaskDelay(1);
    }
    return 0;
}

void app_main(void)
{
    const i2c_config_t config = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = 41,
        .scl_io_num = 42,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = 400000,
    };
    ESP_ERROR_CHECK(i2c_param_config(I2C_NUM_0, &config));
    ESP_ERROR_CHECK(i2c_driver_install(I2C_NUM_0, config.mode, 0, 0, 0));
    write_register(GT911_RATE, (read_register(GT911_RATE) & 0xf0) | 0x0f);
    write_register(GT911_STATUS, 0);
    printf("PAPER_SCAN_READY rate=%u\n", read_register(GT911_RATE) & 0x0f);
    fflush(stdout);

    unsigned spaced_reports = 0;
    unsigned held_reports = 0;
    uint8_t status = wait_report(30000000);
    for (unsigned sample = 0; sample < SAMPLES && status == REPORT_ONE_POINT; ++sample) {
        ++held_reports;
        esp_rom_delay_us(5000);
        write_register(GT911_STATUS, 0);
        const int64_t cleared_at = esp_timer_get_time();
        status = wait_report(200000);
        const int64_t interval = esp_timer_get_time() - cleared_at;
        if (status == REPORT_ONE_POINT && interval >= 9000) {
            ++spaced_reports;
        }
        printf("PAPER_SCAN_SAMPLE %u status=%u us=%" PRId64 "\n", sample, status, interval);
    }

    const int64_t release_timeout = esp_timer_get_time() + 8000000;
    while (status == REPORT_ONE_POINT && esp_timer_get_time() < release_timeout) {
        write_register(GT911_STATUS, 0);
        status = wait_report(200000);
    }
    if (status == REPORT_READY) {
        write_register(GT911_STATUS, 0);
    }
    printf("PAPER_SCAN_DONE held=%u spaced=%u release=%u idle=%u\n",
           held_reports, spaced_reports, status, read_register(GT911_STATUS));
}

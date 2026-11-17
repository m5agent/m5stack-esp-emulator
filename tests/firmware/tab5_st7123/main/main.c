#include <stdbool.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#define ST7123_ADDRESS 0x55
#define ST7123_STATUS 0x0010
#define ST7123_FIRST_POINT 0x0014
#define ST7123_INT GPIO_NUM_23

static SemaphoreHandle_t pending_report;

static void IRAM_ATTR touch_irq(void *arg)
{
    (void)arg;
    BaseType_t higher_priority = pdFALSE;
    xSemaphoreGiveFromISR(pending_report, &higher_priority);
    if (higher_priority == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

static void read_register(i2c_master_dev_handle_t device, uint16_t address,
                          uint8_t *data, size_t len)
{
    const uint8_t index[] = {address >> 8, address & 0xff};
    ESP_ERROR_CHECK(i2c_master_transmit_receive(device, index, sizeof(index),
                                               data, len, 1000));
}

static unsigned read_be16(const uint8_t *data)
{
    return ((unsigned)data[0] << 8) | data[1];
}

void app_main(void)
{
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t device;
    const i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_1,
        .sda_io_num = GPIO_NUM_31,
        .scl_io_num = GPIO_NUM_32,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    const i2c_device_config_t part_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = ST7123_ADDRESS,
        .scl_speed_hz = 400000,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &bus));
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &part_config, &device));

    uint8_t version;
    uint8_t geometry[5];
    read_register(device, 0x0000, &version, 1);
    read_register(device, 0x0005, geometry, sizeof(geometry));
    const unsigned xmax = read_be16(geometry);
    const unsigned ymax = read_be16(geometry + 2);
    printf("ST7123_PROBE_ID version=%u xmax=%u ymax=%u slots=%u\n",
           version, xmax, ymax, geometry[4]);
    configASSERT(version == 3 && xmax == 719 && ymax == 1279 && geometry[4] == 1);

    pending_report = xSemaphoreCreateBinary();
    configASSERT(pending_report);
    const gpio_config_t interrupt_config = {
        .pin_bit_mask = 1ULL << ST7123_INT,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = true,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&interrupt_config));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(ST7123_INT, touch_irq, NULL));
    printf("ST7123_PROBE_WAIT irq=%d level=%d\n", ST7123_INT, gpio_get_level(ST7123_INT));

    unsigned samples = 0;
    unsigned first_x = 0;
    unsigned first_y = 0;
    unsigned last_x = 0;
    unsigned last_y = 0;
    unsigned moves = 0;
    int64_t pressed_at = 0;
    for (;;) {
        if (xSemaphoreTake(pending_report, pdMS_TO_TICKS(1000)) != pdTRUE) {
            puts("ST7123_PROBE_NO_IRQ");
            continue;
        }
        const int level = gpio_get_level(ST7123_INT);
        uint8_t status;
        read_register(device, ST7123_STATUS, &status, 1);
        if (status & 0x08) {
            uint8_t report[7];
            read_register(device, ST7123_FIRST_POINT, report, sizeof(report));
            configASSERT(report[0] & 0x80);
            report[0] &= 0x3f;
            const unsigned x = read_be16(report);
            const unsigned y = read_be16(report + 2);
            if (samples == 0) {
                first_x = x;
                first_y = y;
                pressed_at = esp_timer_get_time();
            } else if (x != last_x || y != last_y) {
                moves++;
            }
            last_x = x;
            last_y = y;
            samples++;
            printf("ST7123_PROBE_POINT x=%u y=%u area=%u irq_level=%d\n",
                   x, y, report[4], level);
        } else {
            printf("ST7123_PROBE_RELEASE status=0x%02x irq_level=%d\n", status, level);
            if (samples > 0) {
                if (moves > 0) {
                    printf("ST7123_PROBE_DRAG x1=%u y1=%u x2=%u y2=%u moves=%u\n",
                           first_x, first_y, last_x, last_y, moves);
                }
                printf("ST7123_PROBE_CONTACT samples=%u duration_us=%" PRId64 "\n",
                       samples, esp_timer_get_time() - pressed_at);
                samples = 0;
                moves = 0;
            }
        }
    }
}

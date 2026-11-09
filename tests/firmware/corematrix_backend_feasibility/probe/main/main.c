#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include "driver/i2c_master.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static i2c_master_dev_handle_t add_dev(i2c_master_bus_handle_t bus, uint8_t address)
{
    i2c_device_config_t config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = address,
        .scl_speed_hz = 100000,
    };
    i2c_master_dev_handle_t dev;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &config, &dev));
    return dev;
}

static void send(i2c_master_dev_handle_t dev, const uint8_t *data, size_t len)
{
    ESP_ERROR_CHECK(i2c_master_transmit(dev, data, len, 500));
}

static uint8_t read_reg(i2c_master_dev_handle_t dev, uint8_t reg)
{
    uint8_t result = 0;
    ESP_ERROR_CHECK(i2c_master_transmit_receive(dev, &reg, 1, &result, 1, 500));
    return result;
}

static void set_pixel(uint8_t *frame, unsigned x, unsigned y)
{
    frame[1 + 2 * y + x / 8] |= 1U << ((x & 7) ^ 4);
}

static void draw(i2c_master_dev_handle_t matrix, uint8_t keys)
{
    uint8_t frame[33] = {0};
    set_pixel(frame, 0, 0);
    set_pixel(frame, 15, 15);
    for (unsigned i = 0; i < 3; ++i) {
        if (!(keys & (1U << i))) {
            set_pixel(frame, 2 + 5 * i, 1 + 3 * i);
        }
    }
    send(matrix, frame, sizeof(frame));
}

void app_main(void)
{
    i2c_master_bus_config_t config = {
        .i2c_port = 0,
        .sda_io_num = 0,
        .scl_io_num = 1,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    ESP_ERROR_CHECK(i2c_new_master_bus(&config, &bus));

    i2c_master_dev_handle_t pm = add_dev(bus, 0x6e);
    i2c_master_dev_handle_t ioe = add_dev(bus, 0x4f);
    i2c_master_dev_handle_t matrix = add_dev(bus, 0x72);
    ESP_ERROR_CHECK(i2c_master_probe(bus, 0x72, 500) == ESP_ERR_NOT_FOUND
                    ? ESP_OK : ESP_FAIL);
    printf("CM_IDS PM1=%02x%02x IOE=%02x%02x OFF_NACK=1\n",
           read_reg(pm, 1), read_reg(pm, 0), read_reg(ioe, 1), read_reg(ioe, 0));
    send(ioe, (const uint8_t[]){0x03, 0x10}, 2);
    send(ioe, (const uint8_t[]){0x05, 0x10}, 2);
    ESP_ERROR_CHECK(i2c_master_probe(bus, 0x72, 500));
    send(matrix, (const uint8_t[]){0x80, 0xa4, 0x98, 0x81, 0xbf, 0x83}, 6);

    uint8_t previous = 0xff;
    for (;;) {
        uint8_t keys = read_reg(pm, 0x12);
        if (keys != previous) {
            uint8_t flags = read_reg(pm, 0x40);
            draw(matrix, keys);
            printf("CM_FRAME keys=%02x irq=%02x\n", keys, flags);
            send(pm, (const uint8_t[]){0x40, (uint8_t)~flags}, 2);
            previous = keys;
        }
        vTaskDelay(pdMS_TO_TICKS(30));
    }
}

#include <inttypes.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#define GT911_ADDR 0x14
#define GT911_ID 0x8140
#define GT911_STATUS 0x814e
#define GT911_FIRST_POINT 0x814f
#define GT911_INT GPIO_NUM_23

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
    uint8_t index[] = {address >> 8, address & 0xff};
    ESP_ERROR_CHECK(i2c_master_transmit_receive(device, index, sizeof(index),
                                               data, len, 1000));
}

static uint16_t read_le16(const uint8_t *data)
{
    return data[0] | ((uint16_t)data[1] << 8);
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
        .device_address = GT911_ADDR,
        .scl_speed_hz = 400000,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &bus));
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &part_config, &device));

    uint8_t id[4];
    read_register(device, GT911_ID, id, sizeof(id));
    printf("GT911_PROBE_ID %02x%02x%02x%02x\n", id[0], id[1], id[2], id[3]);
    configASSERT(id[0] == '9' && id[1] == '1' && id[2] == '1');

    pending_report = xSemaphoreCreateBinary();
    configASSERT(pending_report);
    const gpio_config_t interrupt_config = {
        .pin_bit_mask = 1ULL << GT911_INT,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = true,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&interrupt_config));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(GT911_INT, touch_irq, NULL));
    printf("GT911_PROBE_WAIT irq=%d level=%d\n", GT911_INT,
           gpio_get_level(GT911_INT));

    for (;;) {
        if (xSemaphoreTake(pending_report, pdMS_TO_TICKS(1000)) != pdTRUE) {
            puts("GT911_PROBE_NO_IRQ");
            continue;
        }
        int level = gpio_get_level(GT911_INT);
        uint8_t status;
        read_register(device, GT911_STATUS, &status, 1);
        if (!(status & 0x80)) {
            printf("GT911_PROBE_IRQ_WITHOUT_READY level=%d\n", level);
            continue;
        }
        const uint8_t count = status & 0xf;
        configASSERT(count <= 1);
        if (count) {
            uint8_t point[8];
            read_register(device, GT911_FIRST_POINT, point, sizeof(point));
            printf("GT911_PROBE_POINT x=%u y=%u id=%u size=%u irq_level=%d\n",
                   read_le16(&point[1]), read_le16(&point[3]), point[0],
                   read_le16(&point[5]), level);
        } else {
            printf("GT911_PROBE_RELEASE irq_level=%d\n", level);
        }
        const uint8_t ack[] = {GT911_STATUS >> 8, GT911_STATUS & 0xff, 0};
        ESP_ERROR_CHECK(i2c_master_transmit(device, ack, sizeof(ack), 1000));
        read_register(device, GT911_STATUS, &status, 1);
        printf("GT911_PROBE_ACK status=0x%02x\n", status);
    }
}

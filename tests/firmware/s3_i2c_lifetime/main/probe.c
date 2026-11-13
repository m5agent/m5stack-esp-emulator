#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"

static i2c_master_dev_handle_t touch;
static volatile uint8_t receive_buffer[25];
static void reader(void *arg) {
    uint32_t errors = 0;
    for (unsigned n = 0; n < 30000; n++) {
        uint8_t reg = 2, returned[25];
        memset((void *)receive_buffer, 0xa5, sizeof(receive_buffer));
        esp_err_t ret = i2c_master_transmit_receive(touch, &reg, 1,
            (uint8_t *)receive_buffer, sizeof(receive_buffer), 10);
        for (unsigned k = 0; k < sizeof(returned); k++) returned[k] = receive_buffer[k];
        if (ret != ESP_OK) errors++;
        vTaskDelay(1);
        for (unsigned k = 0; k < sizeof(returned); k++) {
            if (returned[k] != receive_buffer[k]) {
                printf("I2C_BUFFER_CHANGED_AFTER_RETURN n=%u ret=%d offset=%u before=%02x after=%02x core=%u errors=%lu\n",
                    n, ret, k, returned[k], receive_buffer[k], xPortGetCoreID(), (unsigned long)errors);
                vTaskDelete(NULL);
            }
        }
        if (!(n % 1000)) printf("I2C_LIFETIME_PROGRESS n=%u errors=%lu\n", n, (unsigned long)errors);
    }
    printf("I2C_LIFETIME_NO_CHANGE errors=%lu\n", (unsigned long)errors);
    vTaskDelete(NULL);
}
void app_main(void) {
    i2c_master_bus_handle_t bus;
    i2c_master_bus_config_t config = {.i2c_port=I2C_NUM_0,.sda_io_num=12,.scl_io_num=11,
       .clk_source=I2C_CLK_SRC_DEFAULT,.glitch_ignore_cnt=7,.flags.enable_internal_pullup=true};
    ESP_ERROR_CHECK(i2c_new_master_bus(&config, &bus));
    i2c_device_config_t dev = {.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x38,.scl_speed_hz=400000};
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dev, &touch));
    printf("I2C_LIFETIME_BEGIN interrupt_core=%u reader_core=1\n", xPortGetCoreID());
    xTaskCreatePinnedToCore(reader,"read",4096,NULL,5,NULL,1);
}

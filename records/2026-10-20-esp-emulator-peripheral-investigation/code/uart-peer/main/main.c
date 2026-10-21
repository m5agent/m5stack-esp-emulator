#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_log.h"

static const char *TAG = "uart_peer_demo";
#define UART_PORT UART_NUM_1
#define TX_PIN 10
#define RX_PIN 11

void app_main(void)
{
    const uart_config_t cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_PORT, 2048, 2048, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_PORT, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_PORT, TX_PIN, RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    ESP_LOGI(TAG, "waiting for virtual peripheral on UART1");
    bool ok = false;
    for (int attempt = 0; attempt < 10 && !ok; ++attempt) {
        const char ping[] = "PING\n";
        uart_write_bytes(UART_PORT, ping, sizeof(ping) - 1);
        uint8_t buf[64] = {0};
        int n = uart_read_bytes(UART_PORT, buf, sizeof(buf) - 1, pdMS_TO_TICKS(500));
        if (n > 0) {
            buf[n] = 0;
            ESP_LOGI(TAG, "UART1 RX: %s", (char *)buf);
            if (strstr((char *)buf, "PONG") != NULL) ok = true;
        }
    }
    if (ok) {
        ESP_LOGI(TAG, "UART_PEER_OK");
    } else {
        ESP_LOGE(TAG, "UART_PEER_FAIL");
    }
}

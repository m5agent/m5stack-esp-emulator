/*
 * Classic ESP32 QEMU OpenETH probe.
 *
 * This exercises the QEMU virtual Ethernet data plane. It does not exercise
 * the ESP32 WiFi MAC/PHY and must not be reported as a WiFi result.
 */
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_eth.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs_flash.h"

#define TEST_URL "http://10.0.2.2:8070/bigfile"
#define EXPECTED_BYTES 1048576

static const char *TAG = "core2_openeth";
static SemaphoreHandle_t got_ip;

static void on_got_ip(
    void *arg,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
) {
    const ip_event_got_ip_t *event = event_data;
    ESP_LOGI(TAG, "GOT_IP " IPSTR, IP2STR(&event->ip_info.ip));
    xSemaphoreGive(got_ip);
}

static bool start_ethernet(void) {
    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_ETH();
    esp_netif_t *netif = esp_netif_new(&netif_config);
    if (netif == NULL) {
        return false;
    }

    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.autonego_timeout_ms = 100;

    esp_eth_mac_t *mac = esp_eth_mac_new_openeth(&mac_config);
    esp_eth_phy_t *phy = esp_eth_phy_new_dp83848(&phy_config);
    if (mac == NULL || phy == NULL) {
        return false;
    }

    esp_eth_handle_t eth = NULL;
    esp_eth_config_t eth_config = ETH_DEFAULT_CONFIG(mac, phy);
    if (esp_eth_driver_install(&eth_config, &eth) != ESP_OK) {
        return false;
    }
    if (esp_netif_attach(netif, esp_eth_new_netif_glue(eth)) != ESP_OK) {
        return false;
    }
    return esp_eth_start(eth) == ESP_OK;
}

static bool download_once(void) {
    esp_http_client_config_t config = {
        .url = TEST_URL,
        .timeout_ms = 30000,
        .buffer_size = 4096,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL) {
        return false;
    }

    if (esp_http_client_open(client, 0) != ESP_OK) {
        esp_http_client_cleanup(client);
        return false;
    }
    int content_length = (int)esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    printf(
        "CORE2_OPENETH_HTTP: status=%d content_length=%d\n",
        status,
        content_length
    );

    static char buffer[4096];
    int total = 0;
    while (true) {
        int received = esp_http_client_read(client, buffer, sizeof(buffer));
        if (received < 0) {
            printf("CORE2_OPENETH_READ_ERROR: after=%d\n", total);
            esp_http_client_cleanup(client);
            return false;
        }
        if (received == 0) {
            break;
        }
        total += received;
    }
    bool complete = esp_http_client_is_complete_data_received(client);
    esp_http_client_cleanup(client);
    printf(
        "CORE2_OPENETH_TRANSFER: bytes=%d expected=%d complete=%d\n",
        total,
        EXPECTED_BYTES,
        complete
    );
    return status == 200
        && content_length == EXPECTED_BYTES
        && total == EXPECTED_BYTES
        && complete;
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    got_ip = xSemaphoreCreateBinary();
    if (got_ip == NULL) {
        printf("CORE2_OPENETH_RESULT: FAILED (event semaphore)\n");
        return;
    }
    ESP_ERROR_CHECK(
        esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP, on_got_ip, NULL)
    );

    printf("CORE2_OPENETH_START\n");
    if (!start_ethernet()) {
        printf("CORE2_OPENETH_RESULT: FAILED (ethernet init)\n");
        return;
    }
    if (xSemaphoreTake(got_ip, pdMS_TO_TICKS(20000)) != pdTRUE) {
        printf("CORE2_OPENETH_RESULT: FAILED (no DHCP lease)\n");
        return;
    }
    if (!download_once()) {
        printf("CORE2_OPENETH_RESULT: FAILED (transfer)\n");
        return;
    }
    printf("CORE2_OPENETH_RESULT: PASSED\n");
}

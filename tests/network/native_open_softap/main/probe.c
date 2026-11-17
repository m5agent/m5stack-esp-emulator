#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"
#include "lwip/sockets.h"

static void network_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_AP_START) {
        puts("AP_FIXTURE_STARTED");
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STACONNECTED) {
        const wifi_event_ap_staconnected_t *row = data;
        printf("AP_FIXTURE_JOINED aid=%u\n", row->aid);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STADISCONNECTED) {
        puts("AP_FIXTURE_LEFT");
    } else if (base == IP_EVENT && id == IP_EVENT_AP_STAIPASSIGNED) {
        puts("AP_FIXTURE_LEASED");
    }
}

void app_main(void)
{
    puts("AP_FIXTURE_BOOT");
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    assert(esp_netif_create_default_wifi_ap() != NULL);
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, network_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_AP_STAIPASSIGNED, network_event, NULL));
    wifi_init_config_t setup = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&setup));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    wifi_config_t local = {.ap = {
        .ssid = "fixture-ap-test",
        .channel = 1,
        .authmode = WIFI_AUTH_OPEN,
        .max_connection = 1,
        .beacon_interval = 100,
    }};
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &local));
    ESP_ERROR_CHECK(esp_wifi_start());
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    assert(listener >= 0);
    struct sockaddr_in endpoint = {.sin_family = AF_INET, .sin_port = htons(80)};
    assert(bind(listener, (const struct sockaddr *)&endpoint, sizeof(endpoint)) == 0);
    assert(listen(listener, 1) == 0);
    puts("AP_FIXTURE_HTTP_READY");
    int connection = accept(listener, NULL, NULL);
    if (connection >= 0) {
        char request[128] = {0};
        size_t length = recv(connection, request, sizeof(request)-1, 0);
        if (length > 0 && !strncmp(request, "GET /proof ", 11)) {
            const char response[] = "HTTP/1.0 200 OK\r\nContent-Length: 13\r\n\r\nAP_FIXTURE_OK";
            if (send(connection,response,sizeof(response)-1,0) == sizeof(response)-1) {
                puts("AP_FIXTURE_HTTP_SENT");
            }
        }
        close(connection);
    }
    close(listener);
}

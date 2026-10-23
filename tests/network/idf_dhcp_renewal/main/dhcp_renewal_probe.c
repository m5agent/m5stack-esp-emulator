#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "lwip/dhcp.h"
#include "lwip/netifapi.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"

#define HTTP_HOST "10.0.2.2"
#define HTTP_PORT 18080

static const char *TAG = "dhcp_renewal_probe";
static SemaphoreHandle_t s_got_ip;
static esp_netif_t *s_station_netif;

static void on_got_ip(
    void *arg,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
) {
    const ip_event_got_ip_t *event = event_data;
    s_station_netif = event->esp_netif;
    ESP_LOGI(TAG, "GOT_IP " IPSTR, IP2STR(&event->ip_info.ip));
    xSemaphoreGive(s_got_ip);
}

static void on_wifi(
    void *arg,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
) {
    if (
        event_id == WIFI_EVENT_STA_START
        || event_id == WIFI_EVENT_STA_DISCONNECTED
    ) {
        esp_wifi_connect();
    }
}

static bool start_wifi(void) {
    esp_netif_create_default_wifi_sta();
    ESP_ERROR_CHECK(
        esp_event_handler_register(
            WIFI_EVENT,
            ESP_EVENT_ANY_ID,
            on_wifi,
            NULL
        )
    );
    ESP_ERROR_CHECK(
        esp_event_handler_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            on_got_ip,
            NULL
        )
    );

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&init) != ESP_OK) {
        return false;
    }
    wifi_config_t station = {
        .sta = {
            .ssid = "myssid",
        },
    };
    return esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK
        && esp_wifi_set_config(WIFI_IF_STA, &station) == ESP_OK
        && esp_wifi_start() == ESP_OK;
}

static bool controlled_http(void) {
    int socket_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (socket_fd < 0) {
        printf("DHCP_RENEW_HTTP: SOCKET_FAILED %d\n", errno);
        return false;
    }
    struct timeval timeout = {
        .tv_sec = 5,
        .tv_usec = 0,
    };
    setsockopt(
        socket_fd,
        SOL_SOCKET,
        SO_RCVTIMEO,
        &timeout,
        sizeof(timeout)
    );
    struct sockaddr_in destination = {
        .sin_family = AF_INET,
        .sin_port = htons(HTTP_PORT),
        .sin_addr.s_addr = inet_addr(HTTP_HOST),
    };
    bool okay = connect(
        socket_fd,
        (struct sockaddr *)&destination,
        sizeof(destination)
    ) == 0;
    if (okay) {
        const char request[] =
            "GET /dhcp-renew HTTP/1.0\r\n"
            "Host: qemu.test\r\n"
            "\r\n";
        okay = send(socket_fd, request, strlen(request), 0) > 0;
    }
    char response[128] = {0};
    if (okay) {
        int received = recv(socket_fd, response, sizeof(response) - 1, 0);
        okay = received > 0 && strncmp(response, "HTTP/", 5) == 0;
    }
    close(socket_fd);
    printf(
        "DHCP_RENEW_HTTP: %s %s\n",
        okay ? "PASSED" : "FAILED",
        response[0] ? response : "no-response"
    );
    return okay;
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    s_got_ip = xSemaphoreCreateBinary();
    if (s_got_ip == NULL || !start_wifi()) {
        printf("DHCP_RENEW_RESULT: FAILED wifi\n");
        return;
    }
    if (xSemaphoreTake(s_got_ip, pdMS_TO_TICKS(20000)) != pdTRUE) {
        printf("DHCP_RENEW_RESULT: FAILED initial-dhcp\n");
        return;
    }

    esp_netif_t *station_netif = s_station_netif;
    if (station_netif == NULL) {
        station_netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    }
    struct netif *lwip_netif = station_netif
        ? (struct netif *)esp_netif_get_netif_impl(station_netif)
        : NULL;
    struct dhcp *dhcp = lwip_netif ? netif_dhcp_data(lwip_netif) : NULL;
    if (lwip_netif == NULL || dhcp == NULL) {
        printf("DHCP_RENEW_RESULT: FAILED no-dhcp-state\n");
        return;
    }

    printf(
        "DHCP_RENEW_INITIAL: supplied=%u xid=%08lx lease=%lu t1=%lu t2=%lu\n",
        dhcp_supplied_address(lwip_netif),
        (unsigned long)dhcp->xid,
        (unsigned long)dhcp->offered_t0_lease,
        (unsigned long)dhcp->offered_t1_renew,
        (unsigned long)dhcp->offered_t2_rebind
    );
    vTaskDelay(pdMS_TO_TICKS(1000));
    err_t renew_error = netifapi_dhcp_renew(lwip_netif);
    printf(
        "DHCP_RENEW_SENT: err=%d xid=%08lx\n",
        renew_error,
        (unsigned long)dhcp->xid
    );
    if (renew_error != ERR_OK) {
        printf("DHCP_RENEW_RESULT: FAILED renew-api\n");
        return;
    }

    vTaskDelay(pdMS_TO_TICKS(2500));
    printf(
        "DHCP_RENEW_AFTER: supplied=%u xid=%08lx lease=%lu t1=%lu t2=%lu\n",
        dhcp_supplied_address(lwip_netif),
        (unsigned long)dhcp->xid,
        (unsigned long)dhcp->offered_t0_lease,
        (unsigned long)dhcp->offered_t1_renew,
        (unsigned long)dhcp->offered_t2_rebind
    );
    bool okay = dhcp_supplied_address(lwip_netif) && controlled_http();
    printf("DHCP_RENEW_RESULT: %s\n", okay ? "PASSED" : "FAILED");
}

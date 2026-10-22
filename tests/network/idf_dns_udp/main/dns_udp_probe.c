#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "lwip/inet.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"

#define UDP_TEST_PORT 19000
#define UDP_TEST_PAYLOAD "M5_DNS_UDP_PROBE"
#define UDP_REPLY_PREFIX "UDP_REPLY:"

static const char *TAG = "dns_udp_probe";
static SemaphoreHandle_t s_got_ip;

static void on_got_ip(
    void *arg,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
) {
    const ip_event_got_ip_t *event = event_data;
    ESP_LOGI(TAG, "GOT_IP " IPSTR, IP2STR(&event->ip_info.ip));
    xSemaphoreGive(s_got_ip);
}

static void on_wifi(
    void *arg,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
) {
    if (event_id == WIFI_EVENT_STA_START || event_id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();
    }
}

static bool start_wifi(void) {
    esp_netif_create_default_wifi_sta();
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_got_ip, NULL));

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&init) != ESP_OK) {
        return false;
    }
    wifi_config_t station = {
        .sta = {
            .ssid = "myssid",
            .password = "mypassword",
        },
    };
    return esp_wifi_set_mode(WIFI_MODE_STA) == ESP_OK
        && esp_wifi_set_config(WIFI_IF_STA, &station) == ESP_OK
        && esp_wifi_start() == ESP_OK;
}

static bool check_dns(char *resolved, size_t resolved_size) {
    struct addrinfo hints = {
        .ai_family = AF_INET,
        .ai_socktype = SOCK_STREAM,
    };
    struct addrinfo *result = NULL;
    int error = getaddrinfo("example.com", "80", &hints, &result);
    if (error != 0 || result == NULL) {
        printf("DNS_FAILED: %d\n", error);
        return false;
    }
    const struct sockaddr_in *address = (const struct sockaddr_in *)result->ai_addr;
    const char *text = inet_ntoa(address->sin_addr);
    snprintf(resolved, resolved_size, "%s", text);
    freeaddrinfo(result);
    printf("DNS_OK: %s\n", resolved);
    return true;
}

static bool check_udp(void) {
    int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) {
        printf("UDP_SOCKET_FAILED: %d\n", errno);
        return false;
    }
    struct timeval timeout = {
        .tv_sec = 5,
        .tv_usec = 0,
    };
    setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    struct sockaddr_in destination = {
        .sin_family = AF_INET,
        .sin_port = htons(UDP_TEST_PORT),
        .sin_addr.s_addr = htonl(0xC0A80401),
    };
    int sent = sendto(
        socket_fd,
        UDP_TEST_PAYLOAD,
        strlen(UDP_TEST_PAYLOAD),
        0,
        (struct sockaddr *)&destination,
        sizeof(destination)
    );
    if (sent < 0) {
        printf("UDP_SEND_FAILED: %d\n", errno);
        close(socket_fd);
        return false;
    }

    char reply[256] = {0};
    int received = recvfrom(socket_fd, reply, sizeof(reply) - 1, 0, NULL, NULL);
    close(socket_fd);
    if (received <= 0) {
        printf("UDP_RECV_FAILED: %d\n", errno);
        return false;
    }
    reply[received] = '\0';
    printf("UDP_REPLY: %s\n", reply);
    bool okay = strncmp(reply, UDP_REPLY_PREFIX, strlen(UDP_REPLY_PREFIX)) == 0
        && strstr(reply, UDP_TEST_PAYLOAD) != NULL;
    printf("UDP_RESULT: %s\n", okay ? "PASSED" : "FAILED");
    return okay;
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    s_got_ip = xSemaphoreCreateBinary();
    if (s_got_ip == NULL || !start_wifi()) {
        printf("DNS_UDP_RESULT: FAILED (wifi)\n");
        return;
    }
    if (xSemaphoreTake(s_got_ip, pdMS_TO_TICKS(20000)) != pdTRUE) {
        printf("DNS_UDP_RESULT: FAILED (dhcp)\n");
        return;
    }

    char resolved[32] = {0};
    bool dns_okay = check_dns(resolved, sizeof(resolved));
    bool udp_okay = check_udp();
    printf("DNS_UDP_RESULT: %s\n", dns_okay && udp_okay ? "PASSED" : "FAILED");
}

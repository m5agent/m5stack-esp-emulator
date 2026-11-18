#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"

#ifdef M5_FIXTURE_LOCAL_STREAMS
#include "local_streams.h"
#endif

#define CONNECTED BIT0
#define GOT_IPV4 BIT1
#define DISCONNECTED BIT2
#define SERVICE_IP "10.0.2.2"
#define SERVICE_PORT 18192
#ifdef M5_NAMESPACE_DNS
#define DNS_IP "10.0.2.3"
#define DNS_PORT 53
#else
#define DNS_IP SERVICE_IP
#define DNS_PORT 15353
#endif
#define UDP_PORT 19192

static EventGroupHandle_t wifi_events;

static void on_network(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        puts("STA_FIXTURE_START");
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        const wifi_event_sta_connected_t *event = data;
        printf("STA_FIXTURE_ASSOC channel=%u auth=%u\n", event->channel, event->authmode);
        xEventGroupSetBits(wifi_events, CONNECTED);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *event = data;
        printf("STA_FIXTURE_DISCONNECTED reason=%u\n", event->reason);
        xEventGroupSetBits(wifi_events, DISCONNECTED);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = data;
        printf("STA_FIXTURE_DHCP octet=%u\n", esp_ip4_addr4(&event->ip_info.ip));
        xEventGroupSetBits(wifi_events, GOT_IPV4);
    }
}

#ifndef M5_FIXTURE_UDP_ONLY
static bool fixed_http(void)
{
    const char request[] = "GET /native-sta HTTP/1.0\r\nHost: native-sta.test\r\n\r\n";
    const char expected[] = "M5_NATIVE_STA_BODY_V1\n";
    struct sockaddr_in endpoint = {
        .sin_family = AF_INET,
        .sin_port = htons(SERVICE_PORT),
        .sin_addr.s_addr = inet_addr(SERVICE_IP),
    };
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        return false;
    }
    struct timeval timeout = {.tv_sec = 5, .tv_usec = 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    bool okay = connect(fd, (const struct sockaddr *)&endpoint, sizeof(endpoint)) == 0
        && send(fd, request, sizeof(request) - 1, 0) == sizeof(request) - 1;
    char response[512] = {0};
    char length_field[32];
    snprintf(length_field, sizeof(length_field), "\r\nContent-Length: %u",
             (unsigned)sizeof(expected) - 1);
    size_t used = 0;
    bool exact = false;
    while (okay && used < sizeof(response) - 1) {
        int size = recv(fd, response + used, sizeof(response) - 1 - used, 0);
        if (size < 0) {
            okay = false;
            break;
        }
        if (!size) {
            break;
        }
        used += size;
        char *header_end = strstr(response, "\r\n\r\n");
        const char *declared_length = strstr(response, length_field);
        // The fixed chardev is a stream and need not expose TCP EOF.
        if (header_end && used >= (size_t)(header_end + 4 - response) + sizeof(expected) - 1) {
            exact = declared_length && declared_length < header_end
                && declared_length[strlen(length_field)] == '\r'
                && !strcmp(header_end + 4, expected)
                && !strncmp(response, "HTTP/1.0 200 ", sizeof("HTTP/1.0 200 ") - 1);
            break;
        }
    }
    close(fd);
    printf("STA_FIXTURE_HTTP response_bytes=%u body_match=%u\n", (unsigned)used, okay && exact);
    return okay && exact;
}

#endif

static int fixed_udp_exchange(const char *host, int port, const unsigned char *request, size_t request_size,
                              unsigned char *response, size_t response_size)
{
    struct sockaddr_in endpoint = {
        .sin_family = AF_INET,
        .sin_port = htons(port),
        .sin_addr.s_addr = inet_addr(host),
    };
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        return -1;
    }
    struct timeval timeout = {.tv_sec = 4, .tv_usec = 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    int result = -1;
    if (connect(fd, (const struct sockaddr *)&endpoint, sizeof(endpoint)) == 0 &&
        send(fd, request, request_size, 0) == request_size) {
        result = recv(fd, response, response_size, 0);
    }
    close(fd);
    return result;
}

static bool fixed_dns(bool allow)
{
    unsigned char question[] = {
        0x78, 0x21, 0x01, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0,
        3,'l','a','b', 4,'t','e','s','t', 0, 0,1, 0,1,
    };
    if (!allow) {
        question[0] = 0x79;
        memcpy(question + 13, "off", 3);
    }
    static const unsigned char record[] = {0xc0,12, 0,1, 0,1, 0,0,0,30, 0,4, 10,0,2,2};
    unsigned char response[96];
    int count = fixed_udp_exchange(DNS_IP, DNS_PORT, question, sizeof(question), response, sizeof(response));
    if (count < (int)sizeof(question) || memcmp(response, question, 2) ||
        !(response[2] & 0x80) || memcmp(response + 12, question + 12, sizeof(question) - 12)) {
        return false;
    }
    if (!allow) {
        return count == sizeof(question) && (response[3] & 0xf) == 3 && response[7] == 0;
    }
    size_t p = sizeof(question);
    return count == p + sizeof(record) && (response[3] & 0xf) == 0 &&
        response[7] == 1 && !memcmp(response + p, record, 6) &&
        !memcmp(response + p + 10, record + 10, sizeof(record) - 10);
}

static bool fixed_datagram(void)
{
    static const unsigned char sent[] = {0x4d,0x35,0x2d,0,0x7f,0xfe,0xff,0x41,0x42};
    static const unsigned char expected[] = {0x41,0x43,0x4b,0x4d,0x35,0x2d,0,0x7f,0xfe,0xff,0x41,0x42};
    unsigned char response[64];
    int count = fixed_udp_exchange(SERVICE_IP, UDP_PORT, sent, sizeof(sent), response, sizeof(response));
    return count == sizeof(expected) && !memcmp(response, expected, sizeof(expected));
}

void app_main(void)
{
    puts("STA_FIXTURE_BOOT");
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_events = xEventGroupCreate();
    assert(wifi_events != NULL);
    assert(esp_netif_create_default_wifi_sta() != NULL);
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_network, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_network, NULL));
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    wifi_config_t station = {.sta = {
        .ssid = "m5-native-sta",
#ifdef M5_FIXTURE_WPA2
        .password = "local-test-pass-v1",
        .threshold.authmode = WIFI_AUTH_WPA2_PSK,
#else
        .threshold.authmode = WIFI_AUTH_OPEN,
#endif
    }};
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &station));
    ESP_ERROR_CHECK(esp_wifi_start());
    EventBits_t observed = xEventGroupWaitBits(wifi_events, GOT_IPV4 | DISCONNECTED, pdFALSE, pdFALSE,
                                               pdMS_TO_TICKS(15000));
    if ((observed & (CONNECTED | GOT_IPV4)) != (CONNECTED | GOT_IPV4)) {
        printf("STA_FIXTURE_RESULT NO_LEASE\n");
        return;
    }
#ifndef M5_FIXTURE_UDP_ONLY
    bool http = fixed_http();
#endif
    bool dns_allow = fixed_dns(true);
    bool dns_deny = fixed_dns(false);
    bool udp = fixed_datagram();
#ifdef M5_FIXTURE_UDP_ONLY
    printf("STA_FIXTURE_PEERS dns_a=%u dns_nxdomain=%u udp=%u\n", dns_allow, dns_deny, udp);
    printf("STA_FIXTURE_RESULT %s\n", (dns_allow && dns_deny && udp) ? "PASS" : "NO_FIXTURE");
#else
    printf("STA_FIXTURE_PEERS http=%u dns_a=%u dns_nxdomain=%u udp=%u\n", http, dns_allow, dns_deny, udp);
    bool complete = http && dns_allow && dns_deny && udp;
#ifdef M5_FIXTURE_LOCAL_STREAMS
    bool post = native_sta_post_matches();
    bool tcp = native_sta_tcp_matches();
    printf("STA_FIXTURE_HTTP_POST matched=%u\n", post);
    printf("STA_FIXTURE_TCP matched=%u\n", tcp);
    complete = complete && post && tcp;
#endif
    printf("STA_FIXTURE_RESULT %s\n", complete ? "PASS" : "NO_FIXTURE");
#endif
}

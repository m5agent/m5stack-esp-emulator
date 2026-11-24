#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"
#include "review_contract.h"
#include "review_ops.h"

#if !defined(REVIEW_MODE_GOOD) && !defined(REVIEW_MODE_WRONG) && !defined(REVIEW_MODE_SETUP) \
    && !defined(REVIEW_MODE_OFFLINE)
#error "Define exactly one REVIEW_MODE_*"
#endif

#if defined(REVIEW_MODE_GOOD)
#define MODE_NAME "good"
#elif defined(REVIEW_MODE_WRONG)
#define MODE_NAME "wrong"
#elif defined(REVIEW_MODE_SETUP)
#define MODE_NAME "setup"
#else
#define MODE_NAME "offline"
#endif

#define GOT_IPV4 BIT0
#define GAVE_UP BIT1

#ifndef REVIEW_MODE_OFFLINE
static EventGroupHandle_t wifi_events;
static int connect_attempts;

static void on_network(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        connect_attempts = 1;
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        const wifi_event_sta_connected_t *event = data;
        printf("REVIEW_CTRL associated channel=%u auth=%u\n", event->channel, event->authmode);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *event = data;
        printf("REVIEW_CTRL disconnected reason=%u\n", event->reason);
        if (connect_attempts < REVIEW_MAX_CONNECT_ATTEMPTS) {
            connect_attempts++;
            esp_wifi_connect();
        } else {
            xEventGroupSetBits(wifi_events, GAVE_UP);
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = data;
        printf("REVIEW_CTRL lease ip=" IPSTR " gw=" IPSTR "\n",
               IP2STR(&event->ip_info.ip), IP2STR(&event->ip_info.gw));
        xEventGroupSetBits(wifi_events, GOT_IPV4);
    }
}
#endif

#ifdef REVIEW_MODE_SETUP
#ifndef REVIEW_SETUP_GPIO
#error "REVIEW_MODE_SETUP requires REVIEW_SETUP_GPIO (active-low button)"
#endif
#define SETUP_HOLD_MS 1500
#define SETUP_WAIT_MS 120000

/* Block until the active-low setup button is held for SETUP_HOLD_MS. */
static bool wait_for_setup_hold(void)
{
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << REVIEW_SETUP_GPIO,
        .mode = GPIO_MODE_INPUT,
        /* Classic ESP32 GPIO34-39 are input-only and have no pull resistor. */
        .pull_up_en = GPIO_IS_VALID_OUTPUT_GPIO(REVIEW_SETUP_GPIO) ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&config));
    printf("REVIEW_CTRL SETUP_WAIT gpio=%d hold_ms=%d\n", REVIEW_SETUP_GPIO, SETUP_HOLD_MS);
    int held_ms = 0;
    for (int waited = 0; waited < SETUP_WAIT_MS; waited += 20) {
        held_ms = gpio_get_level(REVIEW_SETUP_GPIO) == 0 ? held_ms + 20 : 0;
        if (held_ms >= SETUP_HOLD_MS) {
            printf("REVIEW_CTRL SETUP_HOLD ok=1 gpio=%d\n", REVIEW_SETUP_GPIO);
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    printf("REVIEW_CTRL SETUP_HOLD ok=0 gpio=%d\n", REVIEW_SETUP_GPIO);
    return false;
}
#endif

#ifndef REVIEW_MODE_OFFLINE
static bool join_station(void)
{
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
        .ssid = REVIEW_SSID,
#ifdef REVIEW_MODE_WRONG
        .password = REVIEW_WRONG_PASSPHRASE,
#else
        .password = REVIEW_PASSPHRASE,
#endif
        .threshold.authmode = WIFI_AUTH_WPA2_PSK,
    }};
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &station));
    ESP_ERROR_CHECK(esp_wifi_start());
    EventBits_t bits = xEventGroupWaitBits(wifi_events, GOT_IPV4 | GAVE_UP, pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(REVIEW_LEASE_WAIT_MS));
    if (!(bits & GOT_IPV4)) {
        printf("REVIEW_CTRL RESULT NO_LEASE attempts=%d\n", connect_attempts);
        return false;
    }
    return true;
}
#endif

void app_main(void)
{
    printf("REVIEW_CTRL BOOT mode=%s\n", MODE_NAME);
    ESP_ERROR_CHECK(nvs_flash_init());
#ifdef REVIEW_MODE_OFFLINE
    /* No Wi-Fi driver is linked or started: the radio must stay silent. */
    for (int tick = 1; tick <= 3; tick++) {
        printf("REVIEW_CTRL OFFLINE_TICK n=%d\n", tick);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    printf("REVIEW_CTRL RESULT OFFLINE\n");
#else
#ifdef REVIEW_MODE_SETUP
    if (!wait_for_setup_hold()) {
        printf("REVIEW_CTRL RESULT NO_SETUP\n");
        return;
    }
#endif
    if (!join_station()) {
        return;
    }
#ifdef REVIEW_MODE_WRONG
    /* Unreachable with a correct AP model: a wrong passphrase must not lease. */
    printf("REVIEW_CTRL RESULT UNEXPECTED_LEASE\n");
#else
    char address[16];
    bool dns = review_dns_resolves(REVIEW_DNS_NAME, address, sizeof(address));
    bool absent = review_dns_absent(REVIEW_DNS_ABSENT);
    const char *target = dns ? address : REVIEW_GATEWAY;
    bool get = review_http_get(target);
#ifdef REVIEW_MODE_GOOD
    bool post = review_http_post(target);
    bool tcp = review_tcp_exchange(target);
    bool udp = review_udp_exchange(target);
    bool mqtt = review_mqtt_publish(target);
    bool pass = dns && absent && get && post && tcp && udp && mqtt;
#else
    bool pass = dns && absent && get;
#endif
    printf("REVIEW_CTRL RESULT %s\n", pass ? "PASS" : "FAIL");
#endif
#endif
}

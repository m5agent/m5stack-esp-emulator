#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "nvs_flash.h"

#define BEACON_IE_OFFSET 36
#define FIXTURE_SSID "m5-monitor-lab"
#define MAX_MPDU_SIZE 128
#define MAC_HEADER_SIZE 24

static const uint8_t fixture_action[] = "\x7f\x02\x00\x00" "m5-raw-lab";

struct monitor_frame {
    uint16_t length;
    int8_t rssi;
    uint8_t channel;
    uint8_t mpdu[MAX_MPDU_SIZE];
};

static QueueHandle_t frames;

static void monitor_receive(void *data, wifi_promiscuous_pkt_type_t type)
{
    if (type != WIFI_PKT_MGMT) {
        return;
    }

    const wifi_promiscuous_pkt_t *packet = data;
    const uint8_t *payload = packet->payload;
    const unsigned ssid_length = sizeof(FIXTURE_SSID) - 1;

    const uint16_t length = packet->rx_ctrl.sig_len;
    if (length < MAC_HEADER_SIZE + 4 || length > MAX_MPDU_SIZE) {
        return;
    }
    const bool beacon = payload[0] == 0x80 &&
        length >= BEACON_IE_OFFSET + 2 + ssid_length + 4 &&
        payload[BEACON_IE_OFFSET] == 0 &&
        payload[BEACON_IE_OFFSET + 1] == ssid_length &&
        !memcmp(payload + BEACON_IE_OFFSET + 2, FIXTURE_SSID, ssid_length);
    const bool action = payload[0] == 0xd0 &&
        length >= MAC_HEADER_SIZE + sizeof(fixture_action) - 1 + 4 &&
        !memcmp(payload + MAC_HEADER_SIZE, fixture_action, sizeof(fixture_action) - 1);
    if (!beacon && !action) {
        return;
    }

    struct monitor_frame frame = {
        .length = packet->rx_ctrl.sig_len,
        .rssi = packet->rx_ctrl.rssi,
        .channel = packet->rx_ctrl.channel,
    };
    memcpy(frame.mpdu, payload, frame.length);
    xQueueSend(frames, &frame, 0);
}

static void send_probe_request(void)
{
    const unsigned ssid_length = sizeof(FIXTURE_SSID) - 1;
    uint8_t frame[24 + 2 + sizeof(FIXTURE_SSID) - 1 + 3] = {0x40};
    memset(frame + 4, 0xff, 6);  /* Broadcast receiver. */
    memset(frame + 16, 0xff, 6); /* Wildcard BSSID. */
    frame[25] = ssid_length;
    memcpy(frame + 26, FIXTURE_SSID, ssid_length);
    frame[26 + ssid_length] = 1;  /* Supported Rates IE. */
    frame[27 + ssid_length] = 1;
    frame[28 + ssid_length] = 0x82;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, frame + 10));
    ESP_ERROR_CHECK(esp_wifi_80211_tx(WIFI_IF_STA, frame, sizeof(frame), true));
    printf("MONITOR_TX probe-request len=%u\n", (unsigned)sizeof(frame));
    vTaskDelay(pdMS_TO_TICKS(200));
}

void app_main(void)
{
    struct monitor_frame frame;
    wifi_init_config_t wifi = WIFI_INIT_CONFIG_DEFAULT();
    wifi_promiscuous_filter_t filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT,
    };

    frames = xQueueCreate(8, sizeof(frame));
    configASSERT(frames);
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(esp_wifi_init(&wifi));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_NULL));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_rx_cb(monitor_receive));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(false));

    const bool disabled_rx = xQueueReceive(frames, &frame, pdMS_TO_TICKS(600)) == pdTRUE;
    printf("MONITOR_DISABLED matched=%u\n", (unsigned)disabled_rx);
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    printf("MONITOR_ENABLED\n");
    const bool enabled_rx = xQueueReceive(frames, &frame, pdMS_TO_TICKS(3000)) == pdTRUE;
    if (enabled_rx) {
        if (frame.mpdu[0] == 0xd0) {
            printf("MONITOR_RX action ch=%u rssi=%d len=%u\n",
                   (unsigned)frame.channel, frame.rssi, (unsigned)frame.length);
        } else {
            printf("MONITOR_RX beacon ssid=%s ch=%u rssi=%d len=%u\n",
                   FIXTURE_SSID, (unsigned)frame.channel, frame.rssi, (unsigned)frame.length);
        }
        printf("MONITOR_MPDU ");
        for (unsigned i = 0; i < frame.length; ++i) {
            printf("%02x", (unsigned)frame.mpdu[i]);
        }
        putchar('\n');
    }
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(false));
    if (enabled_rx && !disabled_rx && frame.channel == 1) {
        send_probe_request();
    }
    if (disabled_rx || (enabled_rx && frame.channel != 1)) {
        puts("MONITOR_RESULT FAIL");
    } else {
        puts(enabled_rx ? "MONITOR_RESULT PASS" : "MONITOR_RESULT NO_BEACON");
    }
}

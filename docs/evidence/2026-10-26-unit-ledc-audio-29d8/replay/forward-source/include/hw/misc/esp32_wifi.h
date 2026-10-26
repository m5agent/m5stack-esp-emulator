#pragma once

#include "hw/hw.h"
#include "hw/registerfields.h"
#include "hw/sysbus.h"
#include "sysemu/sysemu.h"
#include "net/net.h"

#define TYPE_ESP32_WIFI "misc.esp32_wifi"
#define ESP32_WIFI(obj) OBJECT_CHECK(Esp32WifiState, (obj), TYPE_ESP32_WIFI)

typedef struct dma_list_item {
    unsigned size:12;
    unsigned length:12;
    unsigned :6;
    unsigned eof:1;
    unsigned owner:1;
    uint32_t address;
    uint32_t next;
} QEMU_PACKED dma_list_item;

enum esp32_wifi_wpa_state {
    ESP32_WIFI_WPA_IDLE,
    ESP32_WIFI_WPA_WAIT_M2,
    ESP32_WIFI_WPA_WAIT_M4,
    ESP32_WIFI_WPA_READY,
};

typedef struct Esp32WifiState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    int raw_interrupt;
    qemu_irq irq;
    uint32_t mem[1024];
    int dma_inlink_address;
    uint32_t dma_inlink_ptr;
    uint32_t ap_state;
    int inject_queue_size;
    struct mac80211_frame *inject_queue;
    int inject_timer_running;
    uint32_t rx_frame_us;
    bool access_points;
    bool is_s3;
    bool radio_enabled;
    bool wlan_closed;
    unsigned int inject_sequence_number;
    int beacon_ap;

    hwaddr receive_queue_address;
    uint32_t receive_queue_count;
    NICConf conf;
    NICState *nic;
    MemReentrancyGuard reentrancy_guard;
    // various timers
    QEMUTimer *beacon_timer;
    QEMUTimer *inject_timer;
    uint8_t ipaddr[4];
    uint8_t macaddr[6];

    uint8_t ap_ipaddr[4];
    uint8_t ap_macaddr[6];

    uint8_t associated_ap_macaddr[6];

    char wifi_ssid[33];
    char wifi_password[64];
    bool wifi_secured;
    enum esp32_wifi_wpa_state wpa_state;
    uint8_t station_macaddr[6];
    /* Guest supplicant address; current S3 model exposes a zero eFuse MAC. */
    uint8_t wpa_station_addr[6];
    uint8_t pmk[32];
    uint8_t anonce[32];
    uint8_t snonce[32];
    uint8_t ptk[48];
    uint8_t gtk[16];
    uint64_t wpa_replay_counter;
    uint64_t ap_pn;

} Esp32WifiState;


void Esp32_WLAN_handle_frame(Esp32WifiState *s, struct mac80211_frame *frame);
void Esp32_WLAN_setup_ap(DeviceState *dev,Esp32WifiState *s);
void Esp32_sendFrame(Esp32WifiState *s, struct mac80211_frame *frame,int length, int signal_strength);
void Esp32_S3_sendFrame(Esp32WifiState *s, struct mac80211_frame *frame,
                        int length, int signal_strength);

REG32(WIFI_DMA_IN_STATUS, 0x84);
REG32(WIFI_DMA_INLINK, 0x88);
REG32(WIFI_DMA_INT_STATUS, 0xc48);
REG32(WIFI_DMA_INT_CLR, 0xc4c);
REG32(WIFI_STATUS, 0xcc8);
REG32(WIFI_DMA_OUTLINK, 0xd20);
REG32(WIFI_DMA_OUT_STATUS, 0xd24);

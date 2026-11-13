#pragma once

#include "hw/sysbus.h"
#include "net/net.h"

#define TYPE_ESP32C6_WIFI "misc.esp32c6.wifi"
#define ESP32C6_WIFI(obj) OBJECT_CHECK(Esp32C6WifiState, (obj), TYPE_ESP32C6_WIFI)
#define ESP32C6_WIFI_IO_SIZE 0x2000
#define ESP32C6_WIFI_PHY_IO_SIZE 0x2000
#define ESP32C6_WIFI_AGC_IO_SIZE 0x1000
#define ESP32C6_WIFI_MAC_IO_SIZE 0x2000
#define ESP32C6_WIFI_MODEM_IO_SIZE 0x1000
#define ESP32C6_WIFI_RF_IO_SIZE 0x1000

typedef struct Esp32C6WifiPendingFrame {
    uint16_t length;
    uint8_t data[1600];
} Esp32C6WifiPendingFrame;

typedef struct Esp32C6WifiState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    MemoryRegion phy_iomem;
    MemoryRegion agc_iomem;
    MemoryRegion mac_iomem;
    MemoryRegion modem_iomem;
    MemoryRegion rf_iomem;
    qemu_irq irq;
    uint32_t regs[ESP32C6_WIFI_IO_SIZE / sizeof(uint32_t)];
    uint32_t phy_regs[ESP32C6_WIFI_PHY_IO_SIZE / sizeof(uint32_t)];
    uint32_t agc_regs[ESP32C6_WIFI_AGC_IO_SIZE / sizeof(uint32_t)];
    uint32_t mac_regs[ESP32C6_WIFI_MAC_IO_SIZE / sizeof(uint32_t)];
    uint32_t modem_regs[ESP32C6_WIFI_MODEM_IO_SIZE / sizeof(uint32_t)];
    uint32_t rf_regs[ESP32C6_WIFI_RF_IO_SIZE / sizeof(uint32_t)];
    uint32_t raw_interrupt;
    uint32_t rx_dma_ptr;
    uint32_t rx_ring_head;
    uint32_t beacon_count;
    QEMUTimer *beacon_timer;
    bool associated;
    bool peer_enabled;
    uint16_t sequence;
    uint8_t macaddr[6];
    Esp32C6WifiPendingFrame rx_queue[8];
    uint8_t rx_queue_head;
    uint8_t rx_queue_tail;
    NICConf conf;
    NICState *nic;
    MemReentrancyGuard reentrancy_guard;
} Esp32C6WifiState;

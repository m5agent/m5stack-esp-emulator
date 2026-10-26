/*
 * ESP32-S3 WiFi MAC/DMA model.
 *
 * The register and DMA layout follows the open ESP32-S3 model used by
 * eink-qemu and is adapted to the M5 QEMU tree.  The management/data frame
 * state machine is shared with the OpenMAC-derived ESP32 model.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/error-report.h"
#include "qemu/guest-random.h"
#include "qapi/error.h"
#include "hw/hw.h"
#include "hw/irq.h"
#include "hw/sysbus.h"
#include "hw/qdev-properties.h"
#include "hw/misc/esp32s3_wifi.h"
#include "exec/address-spaces.h"
#include "esp32_wlan.h"
#include "esp32_wlan_packet.h"

#define S3_DMA_RX_COMPLETE 0x01004000u
#define S3_DMA_TX_COMPLETE 0x00000080u

static void s3_wifi_set_interrupt(Esp32WifiState *s, uint32_t event)
{
    if (getenv("M5SW_S3_WIFI_TRACE")) {
        fprintf(stderr, "[esp32s3-wifi] IRQ raw |= %08x -> %08x\n",
                event, s->raw_interrupt | event);
    }
    s->raw_interrupt |= event;
    qemu_set_irq(s->irq, 1);
}

static uint64_t esp32s3_wifi_read(void *opaque, hwaddr addr, unsigned size)
{
    Esp32WifiState *s = ESP32S3_WIFI(opaque);
    uint32_t value = s->mem[addr / 4];

    switch (addr) {
    case A_S3_WIFI_DMA_IN_STATUS:
        value &= ~1u;
        break;
    case A_S3_WIFI_DMA_INT_STATUS:
    case A_S3_WIFI_DMA_INT_CLR:
        value = s->raw_interrupt;
        if (getenv("M5SW_S3_WIFI_TRACE")) {
            fprintf(stderr, "[esp32s3-wifi] IRQ read %08x -> %08x\n",
                    (unsigned)addr, value);
        }
        break;
    case A_S3_WIFI_STATUS:
    case A_S3_WIFI_DMA_OUT_STATUS:
        value = 1;
        break;
    case A_S3_WIFI_DMA_INLINK:
        value = s->dma_inlink_address;
        break;
    default:
        break;
    }
    return value;
}

static bool s3_wifi_descriptor_valid(const dma_list_item *item)
{
    return item->address >= 0x3f000000u && item->length <= 2316u;
}

static void s3_wifi_receive_frame(Esp32WifiState *s,
                                  struct mac80211_frame *frame,
                                  int signal_strength)
{
    dma_list_item item = { 0 };
    uint8_t packet[sizeof(wifi_pkt_rx_ctrl_s3_t) + 2316];
    wifi_pkt_rx_ctrl_s3_t *rx = (wifi_pkt_rx_ctrl_s3_t *)packet;
    uint32_t descriptor = s->dma_inlink_ptr;
    uint32_t control;
    uint32_t rx_word0;
    size_t total;

    if (!Esp32_WLAN_prepare_s3_rx(s, frame)) {
        return;
    }
    if (!descriptor || !frame->frame_length ||
        frame->frame_length > 2316) {
        return;
    }
    if (address_space_read(&address_space_memory, descriptor,
                           MEMTXATTRS_UNSPECIFIED, &item,
                           sizeof(item)) != MEMTX_OK ||
        !s3_wifi_descriptor_valid(&item)) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32s3-wifi: invalid RX descriptor %08x\n",
                      descriptor);
        return;
    }
    total = sizeof(*rx) + frame->frame_length;
    if (total > item.size) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32s3-wifi: RX descriptor buffer %u < %zu\n",
                      item.size, total);
        return;
    }

    memset(packet, 0, sizeof(packet));
    *rx = (wifi_pkt_rx_ctrl_s3_t) {
        .rssi = signal_strength,
        .rate = 11,
        .sig_len = frame->frame_length,
        .noise_floor = -97,
        .channel = esp32_wifi_channel,
        .timestamp = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / 1000,
    };
    memcpy(&rx_word0, packet, sizeof(rx_word0));
    rx_word0 |= (frame->frame_length & 0xfff) << 16;
    if (!memcmp(frame->receiver_address, BROADCAST, 6)) {
        rx_word0 |= 0xf0000000u;
    } else {
        if (!memcmp(frame->receiver_address, (uint8_t *)s->mem + 0x40, 6) ||
            !memcmp(frame->receiver_address, s->macaddr, 6)) {
            rx_word0 |= 1u << 28;
        }
        if (!memcmp(frame->receiver_address, (uint8_t *)s->mem + 0x48, 6) ||
            !memcmp(frame->receiver_address, s->macaddr, 6)) {
            rx_word0 |= 1u << 29;
        }
        if (!memcmp(frame->address_3, (uint8_t *)s->mem + 0x40, 6)) {
            rx_word0 |= 1u << 30;
        }
        if (!memcmp(frame->address_3, (uint8_t *)s->mem + 0x48, 6)) {
            rx_word0 |= 1u << 31;
        }
        /*
         * The synthetic AP is the only radio source in this model.  Report
         * destination and BSSID matches once the exact filter registers have
         * not yet been populated by the S3 PHY stub.
         */
        rx_word0 |= 0xf0000000u;
    }
    memcpy(packet, &rx_word0, sizeof(rx_word0));
    memcpy(packet + sizeof(*rx), frame, frame->frame_length);
    if (address_space_write(&address_space_memory, item.address,
                            MEMTXATTRS_UNSPECIFIED, packet,
                            total) != MEMTX_OK) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32s3-wifi: RX DMA write failed\n");
        return;
    }
    if (getenv("M5SW_S3_WIFI_TRACE")) {
        uint32_t words[4] = { 0 };
        address_space_read(&address_space_memory, item.address,
                           MEMTXATTRS_UNSPECIFIED, words, sizeof(words));
        fprintf(stderr,
                "[esp32s3-wifi] RX DMA descriptor=%08x buffer=%08x "
                "size=%u length=%zu words=%08x,%08x,%08x,%08x\n",
                descriptor, item.address, item.size, total,
                words[0], words[1], words[2], words[3]);
    }
    item.length = total;
    item.eof = 1;
    memcpy(&control, &item, sizeof(control));
    if (address_space_write(&address_space_memory, descriptor,
                            MEMTXATTRS_UNSPECIFIED, &control,
                            sizeof(control)) != MEMTX_OK) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32s3-wifi: RX descriptor write failed\n");
        return;
    }
    s->dma_inlink_ptr = item.next ? item.next : s->dma_inlink_address;
    s->mem[A_S3_WIFI_NEXT_RX_DSCR / 4] = s->dma_inlink_ptr;
    s->mem[A_S3_WIFI_LAST_RX_DSCR / 4] = descriptor;
    s3_wifi_set_interrupt(s, S3_DMA_RX_COMPLETE);
}

void Esp32_S3_sendFrame(Esp32WifiState *s, struct mac80211_frame *frame,
                        int length, int signal_strength)
{
    if (getenv("M5SW_S3_WIFI_TRACE")) {
        fprintf(stderr,
                "[esp32s3-wifi] RX frame type=%u subtype=%u len=%d "
                "rssi=%d descriptor=%08x "
                "dst=%02x:%02x:%02x:%02x:%02x:%02x "
                "src=%02x:%02x:%02x:%02x:%02x:%02x "
                "bssid=%02x:%02x:%02x:%02x:%02x:%02x\n",
                frame->frame_control.type,
                frame->frame_control.sub_type,
                length, signal_strength, s->dma_inlink_ptr,
                frame->receiver_address[0], frame->receiver_address[1],
                frame->receiver_address[2], frame->receiver_address[3],
                frame->receiver_address[4], frame->receiver_address[5],
                frame->transmitter_address[0], frame->transmitter_address[1],
                frame->transmitter_address[2], frame->transmitter_address[3],
                frame->transmitter_address[4], frame->transmitter_address[5],
                frame->address_3[0], frame->address_3[1],
                frame->address_3[2], frame->address_3[3],
                frame->address_3[4], frame->address_3[5]);
    }
    s3_wifi_receive_frame(s, frame, signal_strength);
}

static void esp32s3_wifi_tx(Esp32WifiState *s, uint32_t outlink)
{
    struct mac80211_frame frame = { 0 };
    dma_list_item item = { 0 };
    uint32_t descriptor = 0x3fc00000u | (outlink & 0xfffffu);

    if (address_space_read(&address_space_memory, descriptor,
                           MEMTXATTRS_UNSPECIFIED, &item,
                           sizeof(item)) != MEMTX_OK ||
        !s3_wifi_descriptor_valid(&item)) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32s3-wifi: invalid TX descriptor %08x\n",
                      descriptor);
        s3_wifi_set_interrupt(s, S3_DMA_TX_COMPLETE);
        return;
    }
    if (address_space_read(&address_space_memory, item.address,
                           MEMTXATTRS_UNSPECIFIED, &frame,
                           item.length) != MEMTX_OK) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32s3-wifi: TX DMA read failed\n");
        s3_wifi_set_interrupt(s, S3_DMA_TX_COMPLETE);
        return;
    }
    frame.frame_length = item.length;
    frame.next_frame = NULL;
    /*
     * S3 TX descriptors carry the source address in hardware state rather
     * than in the frame bytes.  The MAC engine inserts it before over-the-air
     * transmission; do the same here when the guest left the field zeroed.
     */
    if (!memcmp(frame.transmitter_address, "\0\0\0\0\0\0", 6)) {
        memcpy(frame.transmitter_address, s->macaddr, 6);
    }
    if (getenv("M5SW_S3_WIFI_TRACE")) {
        fprintf(stderr,
                "[esp32s3-wifi] TX frame type=%u subtype=%u len=%u "
                "dst=%02x:%02x:%02x:%02x:%02x:%02x "
                "src=%02x:%02x:%02x:%02x:%02x:%02x\n",
                frame.frame_control.type,
                frame.frame_control.sub_type,
                frame.frame_length,
                frame.receiver_address[0], frame.receiver_address[1],
                frame.receiver_address[2], frame.receiver_address[3],
                frame.receiver_address[4], frame.receiver_address[5],
                frame.transmitter_address[0], frame.transmitter_address[1],
                frame.transmitter_address[2], frame.transmitter_address[3],
                frame.transmitter_address[4], frame.transmitter_address[5]);
    }
    Esp32_WLAN_handle_frame(s, &frame);
    s3_wifi_set_interrupt(s, S3_DMA_TX_COMPLETE);
}

static void esp32s3_wifi_write(void *opaque, hwaddr addr,
                               uint64_t value64, unsigned size)
{
    Esp32WifiState *s = ESP32S3_WIFI(opaque);
    uint32_t value = value64;

    switch (addr) {
    case A_S3_WIFI_DMA_INLINK:
        if (getenv("M5SW_S3_WIFI_TRACE")) {
            fprintf(stderr, "[esp32s3-wifi] RX DMA base=%08x\n", value);
        }
        s->dma_inlink_address = value;
        s->dma_inlink_ptr = value;
        s->mem[A_S3_WIFI_NEXT_RX_DSCR / 4] = value;
        break;
    case A_S3_WIFI_DMA_INT_CLR:
        if (getenv("M5SW_S3_WIFI_TRACE")) {
            fprintf(stderr, "[esp32s3-wifi] IRQ clear %08x raw=%08x\n",
                    value, s->raw_interrupt);
        }
        s->raw_interrupt &= ~value;
        if (!s->raw_interrupt) {
            qemu_set_irq(s->irq, 0);
        }
        break;
    case A_S3_WIFI_DMA_OUTLINK:
        if (getenv("M5SW_S3_WIFI_TRACE")) {
            fprintf(stderr, "[esp32s3-wifi] TX DMA outlink=%08x\n", value);
        }
        if (value & 0xc0000000u) {
            esp32s3_wifi_tx(s, value);
        }
        break;
    case A_S3_WIFI_TX_CLR:
        break;
    default:
        break;
    }
    s->mem[addr / 4] = value;
}

static const MemoryRegionOps esp32s3_wifi_ops = {
    .read = esp32s3_wifi_read,
    .write = esp32s3_wifi_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
};

static void esp32s3_wifi_reset_enter(Object *obj, ResetType type)
{
    Esp32WifiState *s = ESP32S3_WIFI(obj);

    s->raw_interrupt = 0;
    s->dma_inlink_address = 0;
    s->dma_inlink_ptr = 0;
    memset(s->mem, 0, sizeof(s->mem));
}

static void esp32s3_wifi_realize(DeviceState *dev, Error **errp)
{
    Esp32WifiState *s = ESP32S3_WIFI(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    s->rx_frame_us = 5000;
    s->access_points = true;
    s->is_s3 = true;
    memory_region_init_io(&s->iomem, OBJECT(dev), &esp32s3_wifi_ops, s,
                          TYPE_ESP32S3_WIFI, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    Esp32_WLAN_setup_ap(dev, s);
    /*
     * The current S3 PHY stub does not decode the RF channel fields yet.
     * Keep the virtual AP on the same fixed channel until that register path
     * is modelled; scan/association frames still traverse the real DMA path.
     */
    esp32_wifi_channel = 1;
}

static Property esp32s3_wifi_properties[] = {
    DEFINE_NIC_PROPERTIES(Esp32WifiState, conf),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32s3_wifi_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = esp32s3_wifi_realize;
    dc->desc = "ESP32-S3 WiFi MAC";
    set_bit(DEVICE_CATEGORY_NETWORK, dc->categories);
    device_class_set_props(dc, esp32s3_wifi_properties);
    ResettableClass *rc = RESETTABLE_CLASS(klass);
    rc->phases.enter = esp32s3_wifi_reset_enter;
}

static const TypeInfo esp32s3_wifi_info = {
    .name = TYPE_ESP32S3_WIFI,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32WifiState),
    .class_init = esp32s3_wifi_class_init,
};

static void esp32s3_wifi_register_types(void)
{
    type_register_static(&esp32s3_wifi_info);
}

type_init(esp32s3_wifi_register_types)

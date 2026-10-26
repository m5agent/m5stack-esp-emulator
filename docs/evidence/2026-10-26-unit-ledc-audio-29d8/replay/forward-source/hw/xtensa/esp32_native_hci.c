/*
 * Classic ESP32 native HCI transport.
 *
 * The transport accepts controller-to-host H4 packets from a chardev,
 * exposes bounded queues and delivers them through the firmware's registered
 * classic ESP32 VHCI receive callback.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/main-loop.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "exec/cpu-common.h"
#include "exec/exec-all.h"
#include "exec/address-spaces.h"
#include "exec/memory.h"
#include "exec/tb-flush.h"
#include "hw/qdev-properties.h"
#include "hw/qdev-properties-system.h"
#include "hw/xtensa/esp32_native_hci.h"
#include "target/xtensa/cpu.h"

enum {
    ESP32_NATIVE_HCI_ERROR_NONE = 0,
    ESP32_NATIVE_HCI_ERROR_MALFORMED = 1,
    ESP32_NATIVE_HCI_ERROR_QUEUE_FULL = 2,
    ESP32_NATIVE_HCI_ERROR_WRITE = 3,
    ESP32_NATIVE_HCI_ERROR_CALLBACK_MISSING = 4,
    ESP32_NATIVE_HCI_ERROR_CALLBACK_FAULT = 5,
    ESP32_NATIVE_HCI_ERROR_CALLBACK_REJECTED = 6,
};

#define ESP32_VHCI_ENV_BUFFER_OFFSET 40
#define ESP32_VHCI_ENV_LENGTH_OFFSET 0x4d8
#define ESP32_VHCI_CALLBACK_OFFSET 0x4e4
#define ESP32_VHCI_POLL_INTERVAL_NS 100000
#define ESP32_NATIVE_HCI_C2H_SETTLE_NS 20000000
#define ESP32_NATIVE_HCI_CALLBACK_STEPS 100000
#define ESP32_NATIVE_HCI_HLI_POLL_NS 1000000
#define ESP32_NATIVE_HCI_EVENT_MAX 256
/*
 * 32-bit NimBLE os_mbuf layout used by the matching ESP-IDF v5.5.4 build.
 * Preallocated guest objects let the HLI path avoid nested guest calls while
 * CPU0 is executing cache-sensitive controller code.
 */
#define ESP32_OS_MBUF_DATA_OFFSET 0
#define ESP32_OS_MBUF_PKTHDR_LEN_OFFSET 5
#define ESP32_OS_MBUF_LEN_OFFSET 6
#define ESP32_OS_MBUF_POOL_OFFSET 8
#define ESP32_OS_MBUF_NEXT_OFFSET 12
#define ESP32_OS_MBUF_DATA_BUF_OFFSET 16
#define ESP32_OS_MBUF_PKTLEN_OFFSET ESP32_OS_MBUF_DATA_BUF_OFFSET
#define ESP32_OS_MBUF_POOL_DATABUF_LEN_OFFSET 0
#define ESP32_OS_MBUF_PKTHDR_SIZE 8

#define ESP32_HLI_ELEMENT_SIZE_OFFSET 0
#define ESP32_HLI_BEGIN_OFFSET 4
#define ESP32_HLI_END_OFFSET 8
#define ESP32_HLI_BUFEND_OFFSET 12
#define ESP32_HLI_BUFFER_OFFSET 24

static void esp32_native_hci_schedule_c2h(Esp32NativeHciState *s);
static void esp32_native_hci_c2h_retry(void *opaque);
static void esp32_native_hci_tx_retry(void *opaque);
static bool esp32_native_hci_flush_tx(Esp32NativeHciState *s, Error **errp);
static void esp32_native_hci_post_hli(CPUState *cs,
                                      run_on_cpu_data data);
static bool esp32_native_hci_guest_call(CPUState *cs, uint32_t function,
                                        uint32_t arg0, uint32_t arg1,
                                        uint32_t arg2, uint32_t arg3,
                                        uint32_t *status, uint32_t *steps);
static bool esp32_native_hci_read_u32(CPUState *cs, uint32_t address,
                                      uint32_t *value);

static void esp32_native_hci_trace(void *opaque,
                                   CPUState *cs,
                                   uint32_t pc,
                                   uint32_t a2,
                                   uint32_t a3,
                                   uint32_t a4,
                                   uint32_t a5)
{
    Esp32NativeHciState *s = opaque;
    struct {
        const char *name;
        uint64_t pc;
        uint64_t *counter;
    } traces[] = {
        {"acl_process", s->trace_acl_process_pc, &s->trace_acl_process},
        {"hci_cmd_tx", s->trace_hci_cmd_tx_pc, &s->trace_hci_cmd_tx},
        {"hs_sched_reset", s->trace_hs_sched_reset_pc,
         &s->trace_hs_sched_reset},
        {"gap_adv_start", s->trace_gap_adv_start_pc,
         &s->trace_gap_adv_start},
        {"gap_adv_stop", s->trace_gap_adv_stop_pc,
         &s->trace_gap_adv_stop},
        {"l2cap_rx", s->trace_l2cap_rx_pc, &s->trace_l2cap_rx},
        {"l2cap_incomplete", s->trace_l2cap_incomplete_pc,
         &s->trace_l2cap_incomplete},
        {"l2cap_chan_found", s->trace_l2cap_chan_found_pc,
         &s->trace_l2cap_chan_found},
        {"l2cap_mtu_reject", s->trace_l2cap_mtu_reject_pc,
         &s->trace_l2cap_mtu_reject},
        {"l2cap_rxfn", s->trace_l2cap_rxfn_pc, &s->trace_l2cap_rxfn},
        {"att_rx", s->trace_att_rx_pc, &s->trace_att_rx},
        {"att_write", s->trace_att_write_pc, &s->trace_att_write},
        {"att_write_no_rsp", s->trace_att_write_no_rsp_pc,
         &s->trace_att_write_no_rsp},
        {"att_find_handle", s->trace_att_find_handle_pc,
         &s->trace_att_find_handle},
        {"att_write_handle", s->trace_att_write_handle_pc,
         &s->trace_att_write_handle},
        {"python_gatts_on_write", s->trace_python_gatts_on_write_pc,
         &s->trace_python_gatts_on_write},
        {"python_irq", s->trace_python_irq_pc, &s->trace_python_irq},
        {"python_notify", s->trace_python_notify_pc,
         &s->trace_python_notify},
        {"nimble_gatts_notify", s->trace_nimble_gatts_notify_pc,
         &s->trace_nimble_gatts_notify},
        {"hci_rx_evt", s->trace_hci_rx_evt_pc,
         &s->trace_hci_rx_evt},
        {"hci_rx_ack_check", s->trace_hci_rx_ack_check_pc,
         &s->trace_hci_rx_ack_check},
    };
    size_t i;

    for (i = 0; i < ARRAY_SIZE(traces); i++) {
        if (!traces[i].pc || pc != traces[i].pc) {
            continue;
        }
        (*traces[i].counter)++;
        fprintf(stderr,
                "esp32-native-hci-trace name=%s t=%" PRId64
                " pc=0x%08x cpu=%d a2=0x%08x a3=0x%08x"
                " a4=0x%08x a5=0x%08x a6=0x%08x a10=0x%08x"
                " a0=0x%08x a1=0x%08x\n",
                traces[i].name,
                qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
                pc, cs->cpu_index, a2, a3, a4, a5,
                cpu_env(cs)->regs[6], cpu_env(cs)->regs[10],
                cpu_env(cs)->regs[0], cpu_env(cs)->regs[1]);
        if (s->ble_hs_hci_ctx_address) {
            uint32_t hci_ctx = 0;
            uint32_t hci_ack = 0;

            if (esp32_native_hci_read_u32(
                    cs, (uint32_t)s->ble_hs_hci_ctx_address,
                    &hci_ctx) &&
                hci_ctx &&
                esp32_native_hci_read_u32(
                    cs, hci_ctx + 136, &hci_ack)) {
                fprintf(stderr,
                        "esp32-native-hci-trace-hci-state"
                        " t=%" PRId64 " name=%s ctx=0x%08x"
                        " ack=0x%08x sem_count_reg=0x%08x\n",
                        qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
                        traces[i].name, hci_ctx, hci_ack,
                        cpu_env(cs)->regs[10]);
            }
        }
        if (strcmp(traces[i].name, "acl_process") == 0) {
            uint32_t data_address = 0;
            uint16_t data_length = 0;
            uint8_t data[64] = {0};
            char hex[sizeof(data) * 2 + 1] = {0};
            size_t data_size = 0;
            size_t j;

            if (esp32_native_hci_read_u32(
                    cs, a2, &data_address) &&
                data_address &&
                cpu_memory_rw_debug(
                    cs, a2 + 6, (uint8_t *)&data_length,
                    sizeof(data_length), false) == 0) {
                data_size = MIN((size_t)data_length, sizeof(data));
                if (cpu_memory_rw_debug(
                        cs, data_address, data, data_size, false) == 0) {
                    for (j = 0; j < data_size; j++) {
                        snprintf(hex + j * 2, sizeof(hex) - j * 2,
                                 "%02x", data[j]);
                    }
                    fprintf(stderr,
                            "esp32-native-hci-trace-acl t=%" PRId64
                            " om=0x%08x data=0x%08x len=%u hex=%s\n",
                            qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
                            a2, data_address, data_length, hex);
                }
            }
        }
        if (strcmp(traces[i].name, "att_write") == 0) {
            uint32_t rxom_address = 0;
            uint32_t om_address = 0;
            uint32_t data_address = 0;
            uint16_t data_length = 0;
            uint8_t data[64] = {0};
            char hex[sizeof(data) * 2 + 1] = {0};
            size_t data_size = 0;
            size_t j;

            if (esp32_native_hci_read_u32(cs, a4, &rxom_address) &&
                rxom_address &&
                esp32_native_hci_read_u32(cs, rxom_address, &om_address) &&
                om_address &&
                esp32_native_hci_read_u32(cs, om_address, &data_address) &&
                data_address &&
                cpu_memory_rw_debug(
                    cs, om_address + 6, (uint8_t *)&data_length,
                    sizeof(data_length), false) == 0) {
                data_size = MIN((size_t)data_length, sizeof(data));
                if (cpu_memory_rw_debug(
                        cs, data_address, data, data_size, false) == 0) {
                    for (j = 0; j < data_size; j++) {
                        snprintf(hex + j * 2, sizeof(hex) - j * 2,
                                 "%02x", data[j]);
                    }
                    fprintf(stderr,
                            "esp32-native-hci-trace-att-write"
                            " t=%" PRId64 " om=0x%08x data=0x%08x"
                            " len=%u hex=%s\n",
                            qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
                            om_address, data_address, data_length, hex);
                }
            }
        }
        if (strcmp(traces[i].name, "l2cap_rx") == 0 &&
            s->trace_hs_conns_address) {
            uint32_t conn = 0;
            uint32_t rx_frags = 0;
            uint16_t rx_len = 0;
            uint16_t rx_cid = 0;

            if (esp32_native_hci_read_u32(
                    cs, (uint32_t)s->trace_hs_conns_address,
                    &conn) &&
                conn &&
                esp32_native_hci_read_u32(
                    cs, conn + 60, &rx_frags) &&
                cpu_memory_rw_debug(
                    cs, conn + 64, (uint8_t *)&rx_len,
                    sizeof(rx_len), false) == 0 &&
                cpu_memory_rw_debug(
                    cs, conn + 66, (uint8_t *)&rx_cid,
                    sizeof(rx_cid), false) == 0) {
                fprintf(stderr,
                        "esp32-native-hci-trace-l2cap-state"
                        " t=%" PRId64 " conn=0x%08x rx_frags=0x%08x"
                        " rx_len=%u rx_cid=%u\n",
                        qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
                        conn, rx_frags, rx_len, rx_cid);
            }
        }
        return;
    }
}

static void esp32_native_hci_schedule_hli(Esp32NativeHciState *s)
{
    if (!s->scheduler_queue_address ||
        !s->meta_queue_pointer_address ||
        !s->vhci_env_address ||
        !s->h2c_packets ||
        !s->hli_valid ||
        s->hli_scheduled ||
        s->hli_post_pending ||
        (!s->hli_c2h && s->hli_test_event == UINT32_MAX) ||
        (s->hli_c2h && !s->rx_queue_count &&
         s->hli_event_prealloc_count >=
             ESP32_NATIVE_HCI_HLI_EVENT_PREALLOC &&
         s->hli_acl_prealloc_count >=
             ESP32_NATIVE_HCI_HLI_ACL_PREALLOC)) {
        return;
    }
    s->hli_scheduled = true;
    async_run_on_cpu(first_cpu, esp32_native_hci_post_hli,
                     RUN_ON_CPU_HOST_PTR(s));
}

static size_t h4_packet_length(const uint8_t *data, size_t available)
{
    size_t payload;

    if (available < 1) {
        return 0;
    }
    switch (data[0]) {
    case 0x01:
        if (available < 4) {
            return 0;
        }
        return 4 + data[3];
    case 0x02:
        if (available < 5) {
            return 0;
        }
        payload = data[3] | ((size_t)data[4] << 8);
        return 5 + payload;
    case 0x03:
        if (available < 4) {
            return 0;
        }
        return 4 + data[3];
    case 0x04:
        if (available < 3) {
            return 0;
        }
        return 3 + data[2];
    default:
        return SIZE_MAX;
    }
}

static void esp32_native_hci_trace_packet(
    Esp32NativeHciState *s,
    const char *direction,
    const uint8_t *data,
    size_t length)
{
    uint8_t shown[64];
    char hex[sizeof(shown) * 2 + 1] = {0};
    size_t shown_size;
    size_t index;

    if (!s->hci_packet_trace ||
        s->hci_trace_packets >= s->hci_trace_limit ||
        !data ||
        !length) {
        return;
    }
    shown_size = MIN(length, sizeof(shown));
    memcpy(shown, data, shown_size);
    for (index = 0; index < shown_size; index++) {
        snprintf(hex + index * 2, sizeof(hex) - index * 2,
                 "%02x", shown[index]);
    }
    s->hci_trace_packets++;
    fprintf(stderr,
            "esp32-native-hci-packet t=%" PRId64
            " direction=%s seq=%" PRIu64
            " len=%zu shown=%zu hex=%s\n",
            qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
            direction, s->hci_trace_packets, length, shown_size, hex);
}

static void consume_rx_buffer(Esp32NativeHciState *s)
{
    while (s->rx_buffer_length) {
        size_t length = h4_packet_length(s->rx_buffer, s->rx_buffer_length);
        Esp32NativeHciPacket *packet;
        uint32_t tail;

        if (length == 0) {
            return;
        }
        if (length == SIZE_MAX ||
            length > ESP32_NATIVE_HCI_PACKET_MAX) {
            s->malformed_packets++;
            s->last_error = ESP32_NATIVE_HCI_ERROR_MALFORMED;
            s->rx_buffer_length--;
            memmove(s->rx_buffer, s->rx_buffer + 1,
                    s->rx_buffer_length);
            continue;
        }
        if (length > s->rx_buffer_length) {
            return;
        }
        if (s->rx_queue_count == ESP32_NATIVE_HCI_QUEUE_DEPTH) {
            s->dropped_packets++;
            s->last_error = ESP32_NATIVE_HCI_ERROR_QUEUE_FULL;
        } else {
            tail = (s->rx_queue_head + s->rx_queue_count) %
                   ESP32_NATIVE_HCI_QUEUE_DEPTH;
            packet = &s->rx_queue[tail];
            packet->length = length;
            memcpy(packet->data, s->rx_buffer, length);
            esp32_native_hci_trace_packet(
                s, "bumble-to-device", packet->data, packet->length);
            s->rx_queue_count++;
            s->rx_packets++;
        }
        s->rx_buffer_length -= length;
        memmove(s->rx_buffer, s->rx_buffer + length,
                s->rx_buffer_length);
    }
}

static int esp32_native_hci_can_receive(void *opaque)
{
    Esp32NativeHciState *s = opaque;

    return sizeof(s->rx_buffer) - s->rx_buffer_length;
}

static void esp32_native_hci_receive(void *opaque, const uint8_t *buf,
                                     int size)
{
    Esp32NativeHciState *s = opaque;
    size_t take;
    size_t room;

    if (size <= 0) {
        return;
    }
    room = sizeof(s->rx_buffer) - s->rx_buffer_length;
    take = MIN((size_t)size, room);
    if (take < size) {
        s->malformed_packets++;
        s->dropped_packets += size - take;
        s->last_error = ESP32_NATIVE_HCI_ERROR_QUEUE_FULL;
    }
    memcpy(s->rx_buffer + s->rx_buffer_length, buf, take);
    s->rx_buffer_length += take;
    s->rx_bytes += take;
    consume_rx_buffer(s);
    if (s->rx_queue_count && !s->hli_c2h) {
        timer_mod(s->c2h_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_NATIVE_HCI_C2H_SETTLE_NS);
    }
}

static void esp32_native_hci_event(void *opaque, QEMUChrEvent event)
{
    Esp32NativeHciState *s = opaque;
    Error *error = NULL;

    switch (event) {
    case CHR_EVENT_OPENED:
        s->peer_opened++;
        qemu_chr_fe_accept_input(&s->chr);
        esp32_native_hci_flush_tx(s, &error);
        if (error) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "esp32-native-hci: TX flush failed: %s\n",
                          error_get_pretty(error));
            error_free(error);
            error = NULL;
        }
        break;
    case CHR_EVENT_CLOSED:
        s->peer_closed++;
        s->rx_buffer_length = 0;
        s->tx_queue_head = 0;
        s->tx_queue_count = 0;
        s->tx_queue_offset = 0;
        timer_del(s->tx_timer);
        break;
    default:
        break;
    }
}

static bool esp32_native_hci_read_u32(CPUState *cs, uint32_t address,
                                      uint32_t *value)
{
    return cpu_memory_rw_debug(cs, address, (uint8_t *)value,
                               sizeof(*value), false) == 0;
}

static bool esp32_native_hci_write_u32(CPUState *cs, uint32_t address,
                                       uint32_t value)
{
    return cpu_memory_rw_debug(cs, address, (uint8_t *)&value,
                               sizeof(value), true) == 0;
}

static bool esp32_native_hci_parse_hex_bytes(
    const char *text,
    uint8_t *output,
    size_t capacity,
    size_t *length)
{
    size_t count = 0;

    if (!text) {
        *length = 0;
        return true;
    }
    while (*text) {
        int high;
        int low;

        while (*text && (g_ascii_isspace(*text) ||
                         *text == ':' || *text == '-')) {
            text++;
        }
        if (!*text) {
            break;
        }
        if (!g_ascii_isxdigit(text[0]) ||
            !g_ascii_isxdigit(text[1]) ||
            count == capacity) {
            return false;
        }
        high = g_ascii_xdigit_value(text[0]);
        low = g_ascii_xdigit_value(text[1]);
        if (high < 0 || low < 0) {
            return false;
        }
        output[count++] = (uint8_t)((high << 4) | low);
        text += 2;
    }
    *length = count;
    return true;
}

static bool esp32_native_hci_hli_queue_put(
    CPUState *cs,
    uint32_t queue_address,
    const uint8_t *payload,
    size_t payload_size,
    uint32_t *new_end,
    bool *was_empty)
{
    uint32_t element_size;
    uint32_t begin;
    uint32_t end;
    uint32_t bufend;
    uint32_t next;

    if (!queue_address ||
        !esp32_native_hci_read_u32(
            cs, queue_address + ESP32_HLI_ELEMENT_SIZE_OFFSET,
            &element_size) ||
        !esp32_native_hci_read_u32(
            cs, queue_address + ESP32_HLI_BEGIN_OFFSET, &begin) ||
        !esp32_native_hci_read_u32(
            cs, queue_address + ESP32_HLI_END_OFFSET, &end) ||
        !esp32_native_hci_read_u32(
            cs, queue_address + ESP32_HLI_BUFEND_OFFSET, &bufend) ||
        element_size < payload_size ||
        end < queue_address + ESP32_HLI_BUFFER_OFFSET ||
        end > bufend ||
        begin < queue_address + ESP32_HLI_BUFFER_OFFSET ||
        begin > bufend) {
        return false;
    }

    next = end + element_size;
    if (next == bufend) {
        next = queue_address + ESP32_HLI_BUFFER_OFFSET;
    }
    if (next == begin) {
        return false;
    }
    *was_empty = begin == end;
    if (cpu_memory_rw_debug(cs, end, (uint8_t *)payload,
                            payload_size, true) != 0 ||
        !esp32_native_hci_write_u32(
            cs, queue_address + ESP32_HLI_END_OFFSET, next)) {
        return false;
    }
    *new_end = next;
    return true;
}

static bool esp32_native_hci_hli_meta_contains(
    CPUState *cs,
    uint32_t meta_queue,
    uint32_t queue)
{
    uint32_t element_size;
    uint32_t begin;
    uint32_t end;
    uint32_t bufend;

    if (!esp32_native_hci_read_u32(
            cs, meta_queue + ESP32_HLI_ELEMENT_SIZE_OFFSET,
            &element_size) ||
        !esp32_native_hci_read_u32(
            cs, meta_queue + ESP32_HLI_BEGIN_OFFSET, &begin) ||
        !esp32_native_hci_read_u32(
            cs, meta_queue + ESP32_HLI_END_OFFSET, &end) ||
        !esp32_native_hci_read_u32(
            cs, meta_queue + ESP32_HLI_BUFEND_OFFSET, &bufend) ||
        element_size != sizeof(queue)) {
        return false;
    }
    while (begin != end) {
        uint32_t item;

        if (!esp32_native_hci_read_u32(cs, begin, &item)) {
            return false;
        }
        if (item == queue) {
            return true;
        }
        begin += element_size;
        if (begin == bufend) {
            begin = meta_queue + ESP32_HLI_BUFFER_OFFSET;
        }
    }
    return false;
}

static bool esp32_native_hci_hli_ensure_scratch(
    CPUState *cs,
    Esp32NativeHciState *s)
{
    uint32_t status = 0;
    uint32_t steps = 0;

    if (!s->c2h_allocator_address) {
        return false;
    }
    if (!s->c2h_scratch_address) {
        if (!esp32_native_hci_guest_call(
                cs, s->c2h_allocator_address,
            s->c2h_scratch_size, 0, 0, 0, &status, &steps) ||
            !status) {
            return false;
        }
        s->c2h_scratch_address = status;
    }
    if (!s->hli_descriptor_pool_address) {
        if (!s->hli_descriptor_pool_size ||
            s->hli_descriptor_pool_size < 8 ||
            !esp32_native_hci_guest_call(
                cs, s->c2h_allocator_address,
                s->hli_descriptor_pool_size, 0, 0, 0,
                &status, &steps) ||
            !status) {
            return false;
        }
        s->hli_descriptor_pool_address = status;
        s->hli_descriptor_cursor = 0;
    }
    return true;
}

static uint64_t esp32_native_hci_hli_take_prealloc(uint64_t *pool,
                                                   uint32_t *count)
{
    uint64_t address;

    if (!*count) {
        return 0;
    }
    address = pool[*count - 1];
    pool[*count - 1] = 0;
    (*count)--;
    return address;
}

static bool esp32_native_hci_hli_refill(CPUState *cs,
                                        Esp32NativeHciState *s,
                                        uint64_t allocator,
                                        uint64_t *pool,
                                        uint32_t *count,
                                        uint32_t target)
{
    uint32_t status;
    uint32_t steps;

    while (*count < target) {
        if (!allocator ||
            !esp32_native_hci_guest_call(
                cs, allocator, 0, 0, 0, 0, &status, &steps) ||
            !status) {
            s->hli_prealloc_failures++;
            return false;
        }
        pool[(*count)++] = status;
    }
    return true;
}

static bool esp32_native_hci_hli_fill_acl_mbuf(
    CPUState *cs,
    uint32_t mbuf,
    const uint8_t *payload,
    size_t payload_length)
{
    uint32_t data;
    uint32_t pool;
    uint32_t next;
    uint16_t databuf_length;
    uint16_t mbuf_length;
    uint16_t packet_length;
    uint16_t available;
    uint16_t new_length;
    uint8_t pkthdr_length;
    uint32_t databuf;

    if (!mbuf ||
        payload_length > UINT16_MAX ||
        !esp32_native_hci_read_u32(
            cs, mbuf + ESP32_OS_MBUF_DATA_OFFSET, &data) ||
        !esp32_native_hci_read_u32(
            cs, mbuf + ESP32_OS_MBUF_POOL_OFFSET, &pool) ||
        !esp32_native_hci_read_u32(
            cs, mbuf + ESP32_OS_MBUF_NEXT_OFFSET, &next) ||
        !data || !pool || next ||
        cpu_memory_rw_debug(
            cs, mbuf + ESP32_OS_MBUF_PKTHDR_LEN_OFFSET,
            &pkthdr_length, sizeof(pkthdr_length), false) != 0 ||
        cpu_memory_rw_debug(
            cs, mbuf + ESP32_OS_MBUF_LEN_OFFSET,
            &mbuf_length, sizeof(mbuf_length), false) != 0 ||
        cpu_memory_rw_debug(
            cs, mbuf + ESP32_OS_MBUF_PKTLEN_OFFSET,
            &packet_length, sizeof(packet_length), false) != 0 ||
        cpu_memory_rw_debug(
            cs, pool + ESP32_OS_MBUF_POOL_DATABUF_LEN_OFFSET,
            &databuf_length, sizeof(databuf_length), false) != 0 ||
        mbuf_length || packet_length ||
        pkthdr_length < ESP32_OS_MBUF_PKTHDR_SIZE) {
        return false;
    }
    databuf = mbuf + ESP32_OS_MBUF_DATA_BUF_OFFSET;
    if (data < databuf + pkthdr_length ||
        data > databuf + databuf_length) {
        return false;
    }
    available = databuf + databuf_length - data;
    new_length = (uint16_t)payload_length;
    if (available < payload_length ||
        cpu_memory_rw_debug(
            cs, data, (uint8_t *)payload, payload_length, true) != 0 ||
        cpu_memory_rw_debug(
            cs, mbuf + ESP32_OS_MBUF_LEN_OFFSET,
            &new_length, sizeof(new_length), true) != 0 ||
        cpu_memory_rw_debug(
            cs, mbuf + ESP32_OS_MBUF_PKTLEN_OFFSET,
            &new_length, sizeof(new_length), true) != 0) {
        return false;
    }
    return true;
}

static uint32_t esp32_native_hci_hli_descriptor(
    Esp32NativeHciState *s)
{
    uint32_t count = s->hli_descriptor_pool_size / 8;
    uint32_t address =
        (uint32_t)s->hli_descriptor_pool_address +
        (s->hli_descriptor_cursor % count) * 8;

    s->hli_descriptor_cursor = (s->hli_descriptor_cursor + 1) % count;
    return address;
}

static void esp32_native_hci_post_hli(CPUState *cs,
                                      run_on_cpu_data data)
{
    Esp32NativeHciState *s = data.host_ptr;
    CPUXtensaState *env = cpu_env(cs);
    Esp32NativeHciPacket *packet = NULL;
    uint8_t event[8] = {0};
    uint32_t queue_item;
    uint32_t queue;
    uint32_t meta_queue;
    uint32_t descriptor_address;
    uint32_t new_end = 0;
    uint32_t status = 0;
    uint32_t steps = 0;
    uint32_t callback = 0;
    uint32_t callback_argument = 0;
    uint32_t work_event;
    uint8_t event_data[ESP32_NATIVE_HCI_EVENT_MAX] = {0};
    size_t event_length = 0;
    size_t payload_length;
    bool was_empty = false;
    bool fast_path = false;
    uint64_t preallocated_address = 0;

    s->hli_scheduled = false;
    if (cs->halted) {
        esp32_native_hci_hli_refill(
            cs, s, s->hli_event_allocator_address,
            s->hli_event_prealloc, &s->hli_event_prealloc_count,
            ESP32_NATIVE_HCI_HLI_EVENT_PREALLOC);
        esp32_native_hci_hli_refill(
            cs, s, s->hli_acl_allocator_address,
            s->hli_acl_prealloc, &s->hli_acl_prealloc_count,
            ESP32_NATIVE_HCI_HLI_ACL_PREALLOC);
    }
    if (s->hli_c2h && s->rx_queue_count) {
        packet = &s->rx_queue[s->rx_queue_head];
        fast_path =
            (packet->data[0] == 0x04 && s->hli_event_prealloc_count) ||
            (packet->data[0] == 0x02 && s->hli_acl_prealloc_count);
    }
    if (!cs->halted && !fast_path) {
        s->hli_deferred_not_halted++;
        timer_mod(s->hli_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_NATIVE_HCI_HLI_POLL_NS);
        return;
    }
    if (!esp32_native_hci_read_u32(
            cs, s->scheduler_queue_address, &queue_item) ||
        !queue_item ||
        !esp32_native_hci_read_u32(cs, queue_item, &queue) ||
        !queue ||
        !esp32_native_hci_read_u32(
            cs, s->meta_queue_pointer_address, &meta_queue) ||
        !meta_queue) {
        s->hli_errors++;
        return;
    }
    if (s->hli_c2h) {
        if (!s->rx_queue_count) {
            return;
        }
        if ((!s->c2h_scratch_address ||
             !s->hli_descriptor_pool_address) &&
            !cs->halted) {
            s->hli_deferred_not_halted++;
            return;
        }
        if (!esp32_native_hci_hli_ensure_scratch(cs, s)) {
            s->hli_errors++;
            return;
        }
        esp32_native_hci_trace_packet(
            s, "device-to-hli", packet->data, packet->length);
        payload_length = packet->length - 1;
        work_event = 13;
        if (packet->data[0] == 0x04) {
            if (packet->length < 3 ||
                payload_length != 2 + packet->data[2] ||
                !s->hli_event_allocator_address ||
                !s->hli_test_callback ||
                !s->hli_event_buffer_size ||
                s->hli_event_buffer_size > sizeof(event_data) ||
                s->hli_event_buffer_size < payload_length) {
                s->hli_errors++;
                return;
            }
            if (!s->hli_event_prealloc_count) {
                if (!esp32_native_hci_guest_call(
                        cs, s->hli_event_allocator_address,
                        0, 0, 0, 0, &status, &steps) ||
                    !status) {
                    s->hli_errors++;
                    return;
                }
                s->hli_event_buffer_address = status;
            } else {
                s->hli_event_buffer_address =
                    esp32_native_hci_hli_take_prealloc(
                        s->hli_event_prealloc,
                        &s->hli_event_prealloc_count);
                s->hli_fast_path_events++;
            }
            s->hli_event_length = payload_length;
            if (cpu_memory_rw_debug(
                    cs, s->hli_event_buffer_address,
                    packet->data + 1, payload_length, true) != 0) {
                s->hli_errors++;
                return;
            }
            s->hli_event_buffers++;
            s->hli_c2h_events++;
            callback = s->hli_test_callback;
            callback_argument = (uint32_t)s->hli_event_buffer_address;
        } else if (packet->data[0] == 0x02) {
            if (packet->length < 5 ||
                payload_length !=
                    4 + (packet->data[3] |
                         ((size_t)packet->data[4] << 8)) ||
                !s->hli_acl_allocator_address ||
                !s->hli_acl_callback ||
                !s->hli_os_mbuf_append_address) {
                s->hli_errors++;
                return;
            }
            if (s->hli_acl_prealloc_count) {
                preallocated_address = s->hli_acl_prealloc[
                    s->hli_acl_prealloc_count - 1];
                if (!esp32_native_hci_hli_fill_acl_mbuf(
                        cs, (uint32_t)preallocated_address,
                        packet->data + 1, payload_length)) {
                    s->hli_errors++;
                    return;
                }
                esp32_native_hci_hli_take_prealloc(
                    s->hli_acl_prealloc,
                    &s->hli_acl_prealloc_count);
                s->hli_acl_mbuf_address = preallocated_address;
                s->hli_fast_path_acls++;
            } else {
                if (!esp32_native_hci_guest_call(
                        cs, s->hli_acl_allocator_address,
                        0, 0, 0, 0, &status, &steps) ||
                    !status) {
                    s->hli_errors++;
                    return;
                }
                s->hli_acl_mbuf_address = status;
                if (cpu_memory_rw_debug(
                        cs, s->c2h_scratch_address,
                        packet->data + 1, payload_length, true) != 0 ||
                    !esp32_native_hci_guest_call(
                        cs, s->hli_os_mbuf_append_address,
                        (uint32_t)s->hli_acl_mbuf_address,
                        (uint32_t)s->c2h_scratch_address,
                        (uint32_t)payload_length, 0, &status, &steps) ||
                    status != 0) {
                    s->hli_errors++;
                    return;
                }
            }
            s->hli_acl_buffers++;
            s->hli_c2h_acls++;
            callback = s->hli_acl_callback;
            callback_argument = (uint32_t)s->hli_acl_mbuf_address;
        } else {
            s->hli_errors++;
            return;
        }
    } else if (s->hli_test_event == 13) {
        if (!esp32_native_hci_parse_hex_bytes(
                s->hli_event_data, event_data, sizeof(event_data),
                &event_length) ||
            event_length < 2 ||
            event_length != 2 + event_data[1] ||
            !s->hli_event_buffer_size ||
            s->hli_event_buffer_size > sizeof(event_data) ||
            s->hli_event_buffer_size < event_length) {
            s->hli_errors++;
            return;
        }
        s->hli_event_length = event_length;
        if (!s->hli_test_callback ||
            (!s->hli_test_argument &&
             !s->hli_event_allocator_address) ||
            (!s->c2h_scratch_address &&
             !s->c2h_allocator_address)) {
            s->hli_errors++;
            return;
        }
        if (!esp32_native_hci_hli_ensure_scratch(cs, s)) {
            s->hli_errors++;
            return;
        }
        if (s->hli_event_allocator_address) {
            if (!esp32_native_hci_guest_call(
                    cs, s->hli_event_allocator_address, 0, 0,
                    0, 0, &status, &steps) ||
                !status) {
                s->hli_errors++;
                return;
            }
            s->hli_event_buffer_address = status;
            if (s->hli_event_buffer_size < s->hli_event_length ||
                cpu_memory_rw_debug(
                    cs, s->hli_event_buffer_address, event_data,
                    s->hli_event_buffer_size, true) != 0) {
                s->hli_errors++;
                return;
            }
            s->hli_event_buffers++;
            callback = s->hli_test_callback;
            callback_argument = (uint32_t)s->hli_event_buffer_address;
        } else {
            callback = s->hli_test_callback;
            callback_argument = (uint32_t)s->hli_test_argument;
        }
        work_event = 13;
    } else {
        work_event = s->hli_test_event;
    }
    if (work_event == 13) {
        if (s->hli_c2h) {
            descriptor_address = esp32_native_hci_hli_descriptor(s);
        } else {
            descriptor_address =
                (uint32_t)s->c2h_scratch_address;
        }
        if (!esp32_native_hci_write_u32(
                cs, descriptor_address,
                callback_argument) ||
            !esp32_native_hci_write_u32(
                cs, descriptor_address + 4, callback)) {
            s->hli_errors++;
            return;
        }
        s->hli_last_descriptor_address = descriptor_address;
        s->hli_last_descriptor_argument = callback_argument;
        s->hli_last_descriptor_callback = callback;
        event[0] = 13;
        memcpy(event + 4, &descriptor_address, sizeof(uint32_t));
    } else {
        event[0] = work_event;
    }
    if (!esp32_native_hci_hli_queue_put(
            cs, queue, event, sizeof(event),
            &new_end, &was_empty)) {
        s->hli_errors++;
        return;
    }
    if (was_empty &&
        !esp32_native_hci_hli_meta_contains(
            cs, meta_queue, queue)) {
        uint32_t ignored_end;
        bool ignored_empty;

        if (!esp32_native_hci_hli_queue_put(
                cs, meta_queue, (const uint8_t *)&queue,
                sizeof(queue), &ignored_end, &ignored_empty)) {
            s->hli_errors++;
            return;
        }
        qatomic_or(&env->sregs[INTSET], BIT(29));
        check_interrupts(env);
    }
    if (s->hli_c2h) {
        s->rx_queue_head =
            (s->rx_queue_head + 1) % ESP32_NATIVE_HCI_QUEUE_DEPTH;
        s->rx_queue_count--;
        s->c2h_delivered++;
    }
    s->hli_last_event = work_event;
    if (!s->hli_c2h) {
        s->hli_test_event = UINT32_MAX;
    }
    s->hli_post_end = new_end;
    s->hli_posted = true;
    s->hli_post_pending = true;
    s->hli_posts++;
}

static void esp32_native_hci_observe_hli(Esp32NativeHciState *s)
{
    uint32_t queue_item;
    uint32_t queue;
    uint32_t meta_queue;
    uint32_t begin;
    uint32_t end;
    uint32_t bufend;
    uint32_t element_size;
    uint32_t queue_begin;

    s->hli_valid = false;
    if (!s->scheduler_queue_address ||
        !s->meta_queue_pointer_address ||
        address_space_read(
            &address_space_memory, s->scheduler_queue_address,
            MEMTXATTRS_UNSPECIFIED, &queue_item,
            sizeof(queue_item)) != MEMTX_OK ||
        !queue_item ||
        address_space_read(
            &address_space_memory, queue_item,
            MEMTXATTRS_UNSPECIFIED, &queue,
            sizeof(queue)) != MEMTX_OK ||
        !queue ||
        address_space_read(
            &address_space_memory, s->meta_queue_pointer_address,
            MEMTXATTRS_UNSPECIFIED, &meta_queue,
            sizeof(meta_queue)) != MEMTX_OK ||
        !meta_queue ||
        address_space_read(
            &address_space_memory,
            queue + ESP32_HLI_ELEMENT_SIZE_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &element_size,
            sizeof(element_size)) != MEMTX_OK ||
        address_space_read(
            &address_space_memory, queue + ESP32_HLI_BEGIN_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &begin,
            sizeof(begin)) != MEMTX_OK ||
        address_space_read(
            &address_space_memory, queue + ESP32_HLI_END_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &end,
            sizeof(end)) != MEMTX_OK ||
        address_space_read(
            &address_space_memory, queue + ESP32_HLI_BUFEND_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &bufend,
            sizeof(bufend)) != MEMTX_OK ||
        !element_size || begin > bufend || end > bufend) {
        return;
    }

    s->hli_queue_address = queue;
    s->hli_queue_element_size = element_size;
    s->hli_queue_begin = begin;
    s->hli_queue_end = end;
    queue_begin = begin;
    s->hli_queue_depth = end >= begin
        ? (end - begin) / element_size
        : ((bufend - begin) + (end - queue - ESP32_HLI_BUFFER_OFFSET))
          / element_size;
    s->meta_queue_address = meta_queue;
    if (address_space_read(
            &address_space_memory,
            meta_queue + ESP32_HLI_ELEMENT_SIZE_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &element_size,
            sizeof(element_size)) == MEMTX_OK) {
        s->meta_queue_element_size = element_size;
    }
    if (address_space_read(
            &address_space_memory,
            meta_queue + ESP32_HLI_BEGIN_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &begin,
            sizeof(begin)) == MEMTX_OK) {
        s->meta_queue_begin = begin;
    }
    if (address_space_read(
            &address_space_memory,
            meta_queue + ESP32_HLI_END_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &end,
            sizeof(end)) == MEMTX_OK) {
        s->meta_queue_end = end;
    }
    if (address_space_read(
            &address_space_memory,
            meta_queue + ESP32_HLI_BUFEND_OFFSET,
            MEMTXATTRS_UNSPECIFIED, &bufend,
            sizeof(bufend)) == MEMTX_OK &&
        s->meta_queue_element_size) {
        s->meta_queue_depth = end >= begin
            ? (end - begin) / s->meta_queue_element_size
            : ((bufend - begin)
               + (end - meta_queue - ESP32_HLI_BUFFER_OFFSET))
              / s->meta_queue_element_size;
    }
    s->hli_valid = true;
    if (s->hli_post_pending && queue_begin == s->hli_post_end) {
        s->hli_post_pending = false;
        s->hli_consumed++;
    }
}

static void esp32_native_hci_sample_ble_pools(Esp32NativeHciState *s)
{
    uint32_t conn_ctx = 0;
    uint32_t l2cap_pool = 0;
    uint32_t gatts_ctx = 0;
    uint32_t gatts_pool = 0;
    uint16_t pool_free = 0;

    s->conn_pool_valid = false;
    s->l2cap_pool_valid = false;
    s->gatts_pool_valid = false;
    s->hs_conns_head = 0;
    s->conn_pool_free = 0;
    s->l2cap_pool_free = 0;
    s->gatts_pool_free = 0;
    if (s->trace_hs_conns_address &&
        address_space_read(
            &address_space_memory, s->trace_hs_conns_address,
            MEMTXATTRS_UNSPECIFIED, &s->hs_conns_head,
            sizeof(s->hs_conns_head)) != MEMTX_OK) {
        s->hs_conns_head = 0;
    }
    if (!s->ble_hs_conn_ctx_address ||
        address_space_read(
            &address_space_memory, s->ble_hs_conn_ctx_address,
            MEMTXATTRS_UNSPECIFIED, &conn_ctx,
            sizeof(conn_ctx)) != MEMTX_OK ||
        !conn_ctx ||
        address_space_read(
            &address_space_memory, conn_ctx + 6,
            MEMTXATTRS_UNSPECIFIED, &pool_free,
            sizeof(pool_free)) != MEMTX_OK) {
        return;
    }
    s->conn_pool_free = pool_free;
    s->conn_pool_valid = true;

    if (s->ble_l2cap_pool_slot_address &&
        address_space_read(
            &address_space_memory, s->ble_l2cap_pool_slot_address,
            MEMTXATTRS_UNSPECIFIED, &l2cap_pool,
            sizeof(l2cap_pool)) == MEMTX_OK &&
        l2cap_pool &&
        address_space_read(
            &address_space_memory, l2cap_pool + 10,
            MEMTXATTRS_UNSPECIFIED, &pool_free,
            sizeof(pool_free)) == MEMTX_OK) {
        s->l2cap_pool_free = pool_free;
        s->l2cap_pool_valid = true;
    }

    if (s->ble_gatts_pool_slot_address &&
        address_space_read(
            &address_space_memory, s->ble_gatts_pool_slot_address,
            MEMTXATTRS_UNSPECIFIED, &gatts_ctx,
            sizeof(gatts_ctx)) == MEMTX_OK &&
        gatts_ctx &&
        address_space_read(
            &address_space_memory, gatts_ctx + 52,
            MEMTXATTRS_UNSPECIFIED, &gatts_pool,
            sizeof(gatts_pool)) == MEMTX_OK) {
        s->gatts_pool_valid = gatts_pool != 0;
        if (s->gatts_pool_valid &&
            address_space_read(
                &address_space_memory, gatts_ctx + 22,
                MEMTXATTRS_UNSPECIFIED, &pool_free,
                sizeof(pool_free)) == MEMTX_OK) {
            s->gatts_pool_free = pool_free;
        }
    }
}

static void esp32_native_hci_hli_poll(void *opaque)
{
    Esp32NativeHciState *s = opaque;

    esp32_native_hci_observe_hli(s);
    esp32_native_hci_sample_ble_pools(s);
    esp32_native_hci_schedule_hli(s);
    timer_mod(s->hli_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              ESP32_NATIVE_HCI_HLI_POLL_NS);
}

static bool esp32_native_hci_guest_call(CPUState *cs, uint32_t function,
                                        uint32_t arg0, uint32_t arg1,
                                        uint32_t arg2, uint32_t arg3,
                                        uint32_t *status, uint32_t *steps)
{
    CPUXtensaState *env = cpu_env(cs);
    static const uint32_t caller_saved_sregs[] = {
        LBEG, LEND, LCOUNT, SAR, BR, LITBASE, SCOMPARE1,
        ACCLO, ACCHI, MR, MR + 1, MR + 2, MR + 3,
        THREADPTR, ATOMCTL, CPENABLE,
    };
    uint32_t return_pc = env->pc;
    uint32_t saved_phys_regs[MAX_NAREG];
    uint32_t saved_sregs[ARRAY_SIZE(caller_saved_sregs)];
    uint32_t saved_windowbase_next = env->windowbase_next;
    uint32_t saved_windowbase = env->sregs[WINDOW_BASE];
    uint32_t saved_windowstart = env->sregs[WINDOW_START];
    uint32_t saved_ps = env->sregs[PS];
    uint32_t saved_icount = env->sregs[ICOUNT];
    uint16_t icount_low = cs->neg.icount_decr.u16.low;
    uint16_t icount_high = cs->neg.icount_decr.u16.high;
    int64_t icount_extra = cs->icount_extra;
    uint32_t interrupt_request = cs->interrupt_request;
    bool exit_request = cs->exit_request;
    bool halted = cs->halted;
    int exception_index = cs->exception_index;
    bool had_bql = bql_locked();
    bool returned = false;
    int ret = 0;

    if (!function) {
        return false;
    }
    xtensa_sync_phys_from_window(env);
    memcpy(saved_phys_regs, env->phys_regs,
           env->config->nareg * sizeof(uint32_t));
    for (size_t i = 0; i < ARRAY_SIZE(caller_saved_sregs); i++) {
        saved_sregs[i] = env->sregs[caller_saved_sregs[i]];
    }

    env->sregs[PS] =
        (env->sregs[PS] & ~PS_CALLINC) |
        (2U << PS_CALLINC_SHIFT);
    env->regs[8] = (return_pc & 0x3fffffffU) | (2U << 30);
    /*
     * call8 maps the caller's a10/a11 into the callee's a2/a3.
     * The return address and return value use the same overlap.
     */
    env->regs[10] = arg0;
    env->regs[11] = arg1;
    env->regs[12] = arg2;
    env->regs[13] = arg3;
    env->pc = function;
    env->windowbase_next = env->sregs[WINDOW_BASE] + 2;
    cs->exception_index = -1;
    cs->neg.icount_decr.u16.low = 0;
    cs->neg.icount_decr.u16.high = 0;
    cs->icount_extra = 0;
    cs->interrupt_request = 0;
    cs->exit_request = false;
    cs->halted = false;
    /*
     * The normal vCPU loop executes guest code with the BQL released.
     * This work item runs with it held, so release it for the nested run
     * and reacquire it before returning to the device model.
     */
    if (had_bql) {
        bql_unlock();
    }

    for (*steps = 0; *steps < ESP32_NATIVE_HCI_CALLBACK_STEPS;
         (*steps)++) {
        if (env->pc == return_pc) {
            returned = true;
            break;
        }
        if (cs->exception_index != -1) {
            break;
        }
        cs->exception_index = -1;
        cs->exit_request = false;
        cs->interrupt_request = 0;
        cs->neg.icount_decr.u16.low = 0;
        cs->icount_extra = 1;
        ret = cpu_exec(cs);
        if (ret == EXCP_HALTED) {
            break;
        }
    }
    if (had_bql) {
        bql_lock();
    }
    if (env->pc == return_pc) {
        returned = true;
    }
    /*
     * After retw the caller window is restored. For call8, the callee's
     * a2 return value aliases the caller's a10 register.
     */
    *status = env->regs[10];

    memcpy(env->phys_regs, saved_phys_regs,
           env->config->nareg * sizeof(uint32_t));
    env->sregs[WINDOW_BASE] = saved_windowbase;
    xtensa_sync_window_from_phys(env);
    env->windowbase_next = saved_windowbase_next;
    env->sregs[WINDOW_START] = saved_windowstart;
    for (size_t i = 0; i < ARRAY_SIZE(caller_saved_sregs); i++) {
        env->sregs[caller_saved_sregs[i]] = saved_sregs[i];
    }
    env->sregs[PS] = saved_ps;
    env->sregs[ICOUNT] = saved_icount;
    env->pc = return_pc;
    cs->neg.icount_decr.u16.low = icount_low;
    cs->neg.icount_decr.u16.high = icount_high;
    cs->icount_extra = icount_extra;
    cs->interrupt_request = interrupt_request;
    cs->exit_request = exit_request;
    cs->halted = halted;
    cs->exception_index = exception_index;
    return returned;
}

static void esp32_native_hci_deliver_c2h(CPUState *cs,
                                         run_on_cpu_data data)
{
    Esp32NativeHciState *s = data.host_ptr;
    Esp32NativeHciPacket *packet;
    uint32_t env_address = 0;
    uint32_t callback = 0;
    uint32_t receive = 0;
    uint32_t send_available = 0;
    uint32_t status = 0;
    uint32_t steps = 0;
    bool injected;
    bool batch_delivered = false;

    s->c2h_scheduled = false;
    if (!s->env_pointer_address ||
        (!s->c2h_scratch_address && !s->c2h_allocator_address) ||
        !s->rx_queue_count) {
        return;
    }
    s->c2h_observed_pc = cpu_env(cs)->pc;
    s->c2h_observed_halted = cs->halted;
    if (!cs->halted) {
        timer_mod(s->c2h_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_VHCI_POLL_INTERVAL_NS);
        return;
    }
    if (!esp32_native_hci_read_u32(cs, s->env_pointer_address,
                                   &env_address) ||
        !env_address ||
        !esp32_native_hci_read_u32(
            cs, env_address + ESP32_VHCI_CALLBACK_OFFSET,
            &callback) ||
        !callback ||
        !esp32_native_hci_read_u32(
            cs, callback, &send_available) ||
        !esp32_native_hci_read_u32(
            cs, callback + 4, &receive) ||
        !receive) {
        s->last_error = ESP32_NATIVE_HCI_ERROR_CALLBACK_MISSING;
        s->c2h_errors++;
        timer_mod(s->c2h_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_VHCI_POLL_INTERVAL_NS);
        return;
    }
    if (!s->c2h_scratch_address) {
        s->c2h_inflight = true;
        injected = esp32_native_hci_guest_call(
            cs, s->c2h_allocator_address, s->c2h_scratch_size, 0, 0,
            0, &status, &steps);
        s->c2h_inflight = false;
        if (!injected || !status) {
            s->last_error = ESP32_NATIVE_HCI_ERROR_CALLBACK_FAULT;
            s->c2h_errors++;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "esp32-native-hci: C2H buffer allocation failed "
                          "allocator=0x%08x status=0x%08x steps=%u\n",
                          (uint32_t)s->c2h_allocator_address,
                          status, steps);
            return;
        }
        s->c2h_scratch_address = status;
        qemu_log_mask(LOG_UNIMP,
                      "esp32-native-hci: C2H buffer=0x%08x size=%u\n",
                      (uint32_t)s->c2h_scratch_address,
                      s->c2h_scratch_size);
    }
    s->c2h_inflight = true;
    while (s->rx_queue_count) {
        packet = &s->rx_queue[s->rx_queue_head];
        if (cpu_memory_rw_debug(cs, s->c2h_scratch_address,
                                packet->data, packet->length, true)) {
            s->last_error = ESP32_NATIVE_HCI_ERROR_WRITE;
            s->c2h_errors++;
            s->c2h_inflight = false;
            return;
        }
        s->c2h_last_pc = receive;
        s->c2h_return_pc = cpu_env(cs)->pc;
        injected = esp32_native_hci_guest_call(
            cs, receive, s->c2h_scratch_address, packet->length, 0,
            0, &status, &steps);
        s->c2h_last_status = status;
        s->c2h_exit_pc = cpu_env(cs)->pc;
        s->c2h_exception_index = (uint32_t)cs->exception_index;
        s->c2h_steps = steps;
        if (!injected || status != 0) {
            s->last_error =
                injected ? ESP32_NATIVE_HCI_ERROR_CALLBACK_REJECTED :
                           ESP32_NATIVE_HCI_ERROR_CALLBACK_FAULT;
            s->c2h_errors++;
            s->c2h_inflight = false;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "esp32-native-hci: C2H callback failed "
                          "receive=0x%08x status=%u steps=%u "
                          "exit=0x%08x exception=%u\n",
                          receive, status, steps, s->c2h_exit_pc,
                          s->c2h_exception_index);
            return;
        }
        s->rx_queue_head =
            (s->rx_queue_head + 1) % ESP32_NATIVE_HCI_QUEUE_DEPTH;
        s->rx_queue_count--;
        s->c2h_delivered++;
        batch_delivered = true;
    }
    s->c2h_inflight = false;

    if (batch_delivered && send_available) {
        injected = esp32_native_hci_guest_call(
            cs, send_available, 0, 0, 0, 0, &status, &steps);
        if (!injected) {
            s->last_error = ESP32_NATIVE_HCI_ERROR_CALLBACK_FAULT;
            s->c2h_errors++;
            return;
        }
        s->c2h_send_available++;
    }
    s->last_error = ESP32_NATIVE_HCI_ERROR_NONE;

    if (s->rx_queue_count) {
        timer_mod(s->c2h_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_VHCI_POLL_INTERVAL_NS);
    }
}

static void esp32_native_hci_schedule_c2h(Esp32NativeHciState *s)
{
    CPUState *target_cpu;
    CPUState *next_cpu;

    if (s->hli_c2h ||
        !s->env_pointer_address ||
        (!s->c2h_scratch_address && !s->c2h_allocator_address) ||
        !s->rx_queue_count ||
        s->c2h_scheduled || s->c2h_inflight) {
        return;
    }
    target_cpu = first_cpu;
    next_cpu = CPU_NEXT(target_cpu);
    if (!target_cpu->halted && next_cpu && next_cpu->halted) {
        target_cpu = next_cpu;
    }
    if (!target_cpu->halted) {
        timer_mod(s->c2h_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_VHCI_POLL_INTERVAL_NS);
        return;
    }
    s->c2h_scheduled = true;
    async_run_on_cpu(target_cpu, esp32_native_hci_deliver_c2h,
                     RUN_ON_CPU_HOST_PTR(s));
}

static void esp32_native_hci_c2h_retry(void *opaque)
{
    esp32_native_hci_schedule_c2h(opaque);
}

static uint64_t esp32_native_hci_h2c_length_read(void *opaque,
                                                 hwaddr addr,
                                                 unsigned int size)
{
    Esp32NativeHciState *s = opaque;

    return s->h2c_length_value;
}

static void esp32_native_hci_h2c_length_write(void *opaque,
                                              hwaddr addr,
                                              uint64_t value,
                                              unsigned int size)
{
    Esp32NativeHciState *s = opaque;
    uint8_t packet[ESP32_NATIVE_HCI_PACKET_MAX];
    uint32_t length = value;
    size_t packet_length;
    Error *error = NULL;

    s->h2c_length_value = length;
    if (s->api_vhci_send_hook_pc) {
        return;
    }
    if (!length) {
        return;
    }
    if (length > ESP32_NATIVE_HCI_PACKET_MAX) {
        s->malformed_packets++;
        s->last_error = ESP32_NATIVE_HCI_ERROR_MALFORMED;
        return;
    }
    if (address_space_read(&address_space_memory,
                           s->vhci_env_address +
                           ESP32_VHCI_ENV_BUFFER_OFFSET,
                           MEMTXATTRS_UNSPECIFIED,
                           packet, length) != MEMTX_OK) {
        s->last_error = ESP32_NATIVE_HCI_ERROR_WRITE;
        return;
    }
    packet_length = h4_packet_length(packet, length);
    if (packet_length == 0) {
        s->h2c_incomplete_writes++;
        return;
    }
    if (packet_length != length) {
        s->malformed_packets++;
        s->last_error = ESP32_NATIVE_HCI_ERROR_MALFORMED;
        return;
    }
    if (!esp32_native_hci_send_h2c(s, packet, length, &error)) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32-native-hci: H2C send failed: %s\n",
                      error_get_pretty(error));
        error_free(error);
        return;
    }
    s->h2c_packets++;
    s->h2c_bytes += length;
    s->last_error = ESP32_NATIVE_HCI_ERROR_NONE;
}

static const MemoryRegionOps esp32_native_hci_h2c_length_ops = {
    .read = esp32_native_hci_h2c_length_read,
    .write = esp32_native_hci_h2c_length_write,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32_native_hci_unmap_h2c_length(Esp32NativeHciState *s)
{
    if (!s->h2c_length_mapped) {
        return;
    }
    memory_region_del_subregion(get_system_memory(),
                                &s->h2c_length_mmio);
    object_unparent(OBJECT(&s->h2c_length_mmio));
    s->h2c_length_mapped = false;
    s->vhci_env_address = 0;
}

static void esp32_native_hci_poll(void *opaque)
{
    Esp32NativeHciState *s = opaque;
    uint32_t env = 0;

    if (!s->env_pointer_address) {
        return;
    }
    if (address_space_read(&address_space_memory,
                           s->env_pointer_address,
                           MEMTXATTRS_UNSPECIFIED,
                           &env, sizeof(env)) != MEMTX_OK ||
        !env) {
        goto reschedule;
    }
    if (env != s->vhci_env_address) {
        esp32_native_hci_unmap_h2c_length(s);
        s->vhci_env_address = env;
        memory_region_init_io(
            &s->h2c_length_mmio, OBJECT(s),
            &esp32_native_hci_h2c_length_ops, s,
            "esp32-native-hci.h2c-length", sizeof(uint32_t));
        memory_region_add_subregion_overlap(
            get_system_memory(),
            env + ESP32_VHCI_ENV_LENGTH_OFFSET,
            &s->h2c_length_mmio, 1);
        s->h2c_length_mapped = true;
        return;
    }
    return;

reschedule:
    timer_mod(s->poll_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              ESP32_VHCI_POLL_INTERVAL_NS);
}

static bool esp32_native_hci_flush_tx(Esp32NativeHciState *s, Error **errp)
{
    while (s->tx_queue_count) {
        Esp32NativeHciPacket *packet =
            &s->tx_queue[s->tx_queue_head];
        int written = qemu_chr_fe_write(
            &s->chr,
            packet->data + s->tx_queue_offset,
            packet->length - s->tx_queue_offset);

        if (written < 0 &&
            errno != EAGAIN && errno != EWOULDBLOCK) {
            s->last_tx_errno = errno;
            s->last_error = ESP32_NATIVE_HCI_ERROR_WRITE;
            qemu_log_mask(LOG_GUEST_ERROR,
                          "esp32-native-hci: TX write failed "
                          "written=%d errno=%u pending=%u offset=%u\n",
                          written, errno, s->tx_queue_count,
                          s->tx_queue_offset);
            error_setg(errp, "esp32-native-hci: chardev write failed");
            return false;
        }
        if (written <= 0) {
            if (written == 0) {
                s->tx_zero_writes++;
            }
            return true;
        }
        s->tx_bytes += written;
        s->tx_queue_offset += written;
        if (s->tx_queue_offset < packet->length) {
            return true;
        }
        s->tx_packets++;
        s->tx_queue_offset = 0;
        s->tx_queue_head =
            (s->tx_queue_head + 1) % ESP32_NATIVE_HCI_QUEUE_DEPTH;
        s->tx_queue_count--;
    }
    return true;
}

static void esp32_native_hci_tx_retry(void *opaque)
{
    Esp32NativeHciState *s = opaque;
    Error *error = NULL;

    if (!s->tx_queue_count) {
        return;
    }
    s->tx_retry_count++;
    if (!esp32_native_hci_flush_tx(s, &error)) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32-native-hci: TX flush failed: %s\n",
                      error_get_pretty(error));
        error_free(error);
        return;
    }
    if (s->tx_queue_count) {
        timer_mod(s->tx_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_REALTIME) +
                  ESP32_NATIVE_HCI_HLI_POLL_NS);
    }
}

bool esp32_native_hci_send_h2c(Esp32NativeHciState *s,
                               const uint8_t *data, size_t size,
                               Error **errp)
{
    uint32_t tail;

    if (!data || !size || size > ESP32_NATIVE_HCI_PACKET_MAX) {
        error_setg(errp, "esp32-native-hci: invalid H2C packet");
        return false;
    }
    if (!qemu_chr_fe_backend_connected(&s->chr)) {
        s->last_error = ESP32_NATIVE_HCI_ERROR_WRITE;
        error_setg(errp, "esp32-native-hci: HCI peer is disconnected");
        return false;
    }
    if (s->tx_queue_count == ESP32_NATIVE_HCI_QUEUE_DEPTH) {
        s->last_error = ESP32_NATIVE_HCI_ERROR_QUEUE_FULL;
        error_setg(errp, "esp32-native-hci: H2C queue is full");
        return false;
    }
    tail = (s->tx_queue_head + s->tx_queue_count) %
           ESP32_NATIVE_HCI_QUEUE_DEPTH;
    esp32_native_hci_trace_packet(s, "guest-to-bumble", data, size);
    s->tx_queue[tail].length = size;
    if (s->tx_queue_count == 0) {
        s->tx_queue_offset = 0;
    }
    memcpy(s->tx_queue[tail].data, data, size);
    s->tx_queue_count++;
    if (!esp32_native_hci_flush_tx(s, errp)) {
        return false;
    }
    if (s->tx_queue_count) {
        timer_mod(s->tx_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_REALTIME) +
                  ESP32_NATIVE_HCI_HLI_POLL_NS);
    }
    return true;
}

static bool esp32_native_hci_api_send_packet(
    void *opaque,
    CPUState *cs,
    uint32_t data,
    uint32_t length)
{
    Esp32NativeHciState *s = opaque;
    CPUXtensaState *env = cpu_env(cs);
    uint8_t packet[ESP32_NATIVE_HCI_PACKET_MAX];
    size_t packet_length;
    Error *error = NULL;

    length &= 0xffff;
    if (!data || !length || length > sizeof(packet) ||
        cpu_memory_rw_debug(cs, data, packet, length, false) != 0) {
        s->api_h2c_errors++;
        s->last_error = ESP32_NATIVE_HCI_ERROR_WRITE;
        return false;
    }
    packet_length = h4_packet_length(packet, length);
    if (packet_length == 0 ||
        packet_length != length) {
        s->api_h2c_errors++;
        s->last_error = ESP32_NATIVE_HCI_ERROR_MALFORMED;
        return false;
    }
    if (s->hci_packet_trace &&
        s->api_send_trace_packets < s->hci_trace_limit) {
        uint16_t opcode = packet[0] == 0x01 && length >= 3 ?
                          packet[1] | ((uint16_t)packet[2] << 8) : 0;
        s->api_send_trace_packets++;
        fprintf(stderr,
                "esp32-native-hci-api-send t=%" PRId64
                " seq=%" PRIu64 " cpu=%d pc=0x%08x a0=0x%08x"
                " a1=0x%08x type=0x%02x op=0x%04x len=%u\n",
                qemu_clock_get_ns(QEMU_CLOCK_REALTIME),
                s->api_send_trace_packets, cs->cpu_index,
                env->pc, env->regs[0], env->regs[1],
                packet[0], opcode, length);
    }
    if (!esp32_native_hci_send_h2c(s, packet, length, &error)) {
        s->api_h2c_errors++;
        qemu_log_mask(LOG_GUEST_ERROR,
                      "esp32-native-hci: API H2C send failed: %s\n",
                      error_get_pretty(error));
        error_free(error);
        return false;
    }
    s->h2c_packets++;
    s->h2c_bytes += length;
    s->api_h2c_packets++;
    s->last_error = ESP32_NATIVE_HCI_ERROR_NONE;
    return true;
}

static void esp32_native_hci_realize(DeviceState *dev, Error **errp)
{
    Esp32NativeHciState *s = ESP32_NATIVE_HCI(dev);
    CPUState *cpu;

    qemu_chr_fe_set_handlers(&s->chr,
                             esp32_native_hci_can_receive,
                             esp32_native_hci_receive,
                             esp32_native_hci_event,
                             NULL, s, NULL, true);
    if (s->api_vhci_send_hook_pc) {
        if (!s->api_vhci_send_return_pc) {
            error_setg(errp,
                       "esp32-native-hci: API send hook requires a return PC");
            return;
        }
        CPU_FOREACH(cpu) {
            CPUXtensaState *env = cpu_env(cpu);

            env->native_hci_send_hook_pc =
                (uint32_t)s->api_vhci_send_hook_pc;
            env->native_hci_send_return_pc =
                (uint32_t)s->api_vhci_send_return_pc;
            env->native_hci_cmd_semaphore_hook_pc =
                (uint32_t)s->cmd_semaphore_hook_pc;
            env->native_hci_cmd_semaphore_return_pc =
                (uint32_t)s->cmd_semaphore_return_pc;
            env->native_hci_acl_semaphore_hook_pc =
                (uint32_t)s->acl_semaphore_hook_pc;
            env->native_hci_acl_semaphore_return_pc =
                (uint32_t)s->acl_semaphore_return_pc;
            env->native_hci_recycle_hook_pc =
                (uint32_t)s->recycle_hook_pc;
            env->native_hci_recycle_return_pc =
                (uint32_t)s->recycle_return_pc;
            env->native_hci_sleep_post_hook_pc =
                (uint32_t)s->sleep_post_hook_pc;
            env->native_hci_sleep_post_return_pc =
                (uint32_t)s->sleep_post_return_pc;
            QEMU_BUILD_BUG_ON(
                ARRAY_SIZE(env->native_hci_trace_pcs) !=
                ESP32_NATIVE_HCI_TRACE_SLOTS);
            env->native_hci_trace_pcs[0] =
                (uint32_t)s->trace_hci_cmd_tx_pc;
            env->native_hci_trace_pcs[1] =
                (uint32_t)s->trace_hs_sched_reset_pc;
            env->native_hci_trace_pcs[2] =
                (uint32_t)s->trace_gap_adv_start_pc;
            env->native_hci_trace_pcs[3] =
                (uint32_t)s->trace_gap_adv_stop_pc;
            env->native_hci_trace_pcs[4] =
                (uint32_t)s->trace_acl_process_pc;
            env->native_hci_trace_pcs[5] =
                (uint32_t)s->trace_l2cap_rx_pc;
            env->native_hci_trace_pcs[6] =
                (uint32_t)s->trace_l2cap_incomplete_pc;
            env->native_hci_trace_pcs[7] =
                (uint32_t)s->trace_l2cap_chan_found_pc;
            env->native_hci_trace_pcs[8] =
                (uint32_t)s->trace_l2cap_mtu_reject_pc;
            env->native_hci_trace_pcs[9] =
                (uint32_t)s->trace_l2cap_rxfn_pc;
            env->native_hci_trace_pcs[10] =
                (uint32_t)s->trace_att_rx_pc;
            env->native_hci_trace_pcs[11] =
                (uint32_t)s->trace_att_write_pc;
            env->native_hci_trace_pcs[12] =
                (uint32_t)s->trace_att_write_no_rsp_pc;
            env->native_hci_trace_pcs[13] =
                (uint32_t)s->trace_att_find_handle_pc;
            env->native_hci_trace_pcs[14] =
                (uint32_t)s->trace_att_write_handle_pc;
            env->native_hci_trace_pcs[15] =
                (uint32_t)s->trace_python_gatts_on_write_pc;
            env->native_hci_trace_pcs[16] =
                (uint32_t)s->trace_python_irq_pc;
            env->native_hci_trace_pcs[17] =
                (uint32_t)s->trace_python_notify_pc;
            env->native_hci_trace_pcs[18] =
                (uint32_t)s->trace_nimble_gatts_notify_pc;
            env->native_hci_trace_pcs[19] =
                (uint32_t)s->trace_hci_rx_evt_pc;
            env->native_hci_trace_pcs[20] =
                (uint32_t)s->trace_hci_rx_ack_check_pc;
            env->native_hci_send_callback =
                esp32_native_hci_api_send_packet;
            env->native_hci_send_opaque = s;
            env->native_hci_trace_callback =
                esp32_native_hci_trace;
            env->native_hci_trace_opaque = s;
            tb_flush(cpu);
        }
    }
    object_property_add_uint64_ptr(
        OBJECT(dev), "rx-bytes", &s->rx_bytes, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "rx-packets", &s->rx_packets, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "tx-bytes", &s->tx_bytes, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "tx-packets", &s->tx_packets, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "malformed-packets", &s->malformed_packets,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "dropped-packets", &s->dropped_packets,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "peer-opened", &s->peer_opened,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "peer-closed", &s->peer_closed,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "h2c-packets", &s->h2c_packets,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "h2c-bytes", &s->h2c_bytes,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "h2c-duplicates", &s->h2c_duplicates,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "h2c-incomplete-writes",
        &s->h2c_incomplete_writes, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "c2h-delivered", &s->c2h_delivered,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "c2h-errors", &s->c2h_errors,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "c2h-send-available", &s->c2h_send_available,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-last-status", &s->c2h_last_status,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-last-pc", &s->c2h_last_pc,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-observed-pc", &s->c2h_observed_pc,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-observed-halted", &s->c2h_observed_halted,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-return-pc", &s->c2h_return_pc,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-exit-pc", &s->c2h_exit_pc,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-steps", &s->c2h_steps,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "c2h-exception-index", &s->c2h_exception_index,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "rx-queue-depth", &s->rx_queue_count,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "tx-queue-depth", &s->tx_queue_count,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "tx-queue-offset", &s->tx_queue_offset,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "last-tx-errno", &s->last_tx_errno,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "tx-retry-count", &s->tx_retry_count,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "tx-zero-writes", &s->tx_zero_writes,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "last-error", &s->last_error,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "vhci-env-address", &s->vhci_env_address,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "vhci-callback-address",
        &s->vhci_callback_address, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "vhci-receive-address",
        &s->vhci_receive_address, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-posts", &s->hli_posts,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-consumed", &s->hli_consumed,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-event-buffers", &s->hli_event_buffers,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-acl-buffers", &s->hli_acl_buffers,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-c2h-events", &s->hli_c2h_events,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-c2h-acls", &s->hli_c2h_acls,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "api-h2c-packets", &s->api_h2c_packets,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "api-h2c-errors", &s->api_h2c_errors,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-errors", &s->hli_errors,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-deferred-not-halted",
        &s->hli_deferred_not_halted, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-fast-path-events", &s->hli_fast_path_events,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-fast-path-acls", &s->hli_fast_path_acls,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-prealloc-failures",
        &s->hli_prealloc_failures, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hci-trace-packets", &s->hci_trace_packets,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "api-send-trace-packets", &s->api_send_trace_packets,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-acl-process", &s->trace_acl_process,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-hci-cmd-tx", &s->trace_hci_cmd_tx,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-hs-sched-reset", &s->trace_hs_sched_reset,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-gap-adv-start", &s->trace_gap_adv_start,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-gap-adv-stop", &s->trace_gap_adv_stop,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-l2cap-rx", &s->trace_l2cap_rx,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-l2cap-incomplete",
        &s->trace_l2cap_incomplete, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-l2cap-chan-found",
        &s->trace_l2cap_chan_found, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-l2cap-mtu-reject",
        &s->trace_l2cap_mtu_reject, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-l2cap-rxfn",
        &s->trace_l2cap_rxfn, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-att-rx", &s->trace_att_rx,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-att-write", &s->trace_att_write,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-att-write-no-rsp",
        &s->trace_att_write_no_rsp, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-att-find-handle",
        &s->trace_att_find_handle, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-att-write-handle",
        &s->trace_att_write_handle, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-python-gatts-on-write",
        &s->trace_python_gatts_on_write, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-python-irq", &s->trace_python_irq,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-python-notify",
        &s->trace_python_notify, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "trace-nimble-gatts-notify",
        &s->trace_nimble_gatts_notify, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-valid", &s->hli_valid,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-event-prealloc-depth",
        &s->hli_event_prealloc_count, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-acl-prealloc-depth",
        &s->hli_acl_prealloc_count, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-last-event", &s->hli_last_event,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-queue-address", &s->hli_queue_address,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-queue-element-size",
        &s->hli_queue_element_size, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-queue-begin", &s->hli_queue_begin,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-queue-end", &s->hli_queue_end,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-queue-depth", &s->hli_queue_depth,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "meta-queue-address", &s->meta_queue_address,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "meta-queue-element-size",
        &s->meta_queue_element_size, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "meta-queue-begin", &s->meta_queue_begin,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "meta-queue-end", &s->meta_queue_end,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "meta-queue-depth", &s->meta_queue_depth,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "conn-pool-valid", &s->conn_pool_valid,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hs-conns-head", &s->hs_conns_head,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "conn-pool-free", &s->conn_pool_free,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "l2cap-pool-valid", &s->l2cap_pool_valid,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "l2cap-pool-free", &s->l2cap_pool_free,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "gatts-pool-valid", &s->gatts_pool_valid,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "gatts-pool-free", &s->gatts_pool_free,
        OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-event-buffer-address",
        &s->hli_event_buffer_address, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-acl-mbuf-address",
        &s->hli_acl_mbuf_address, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-descriptor-pool-address",
        &s->hli_descriptor_pool_address, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-last-descriptor-address",
        &s->hli_last_descriptor_address, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-last-descriptor-argument",
        &s->hli_last_descriptor_argument, OBJ_PROP_FLAG_READ);
    object_property_add_uint64_ptr(
        OBJECT(dev), "hli-last-descriptor-callback",
        &s->hli_last_descriptor_callback, OBJ_PROP_FLAG_READ);
    object_property_add_uint32_ptr(
        OBJECT(dev), "hli-event-length", &s->hli_event_length,
        OBJ_PROP_FLAG_READ);
    if (s->env_pointer_address) {
        timer_mod(s->poll_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_VHCI_POLL_INTERVAL_NS);
    }
    if (s->scheduler_queue_address &&
        s->meta_queue_pointer_address) {
        timer_mod(s->hli_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_NATIVE_HCI_HLI_POLL_NS);
    }
}

static void esp32_native_hci_unrealize(DeviceState *dev)
{
    Esp32NativeHciState *s = ESP32_NATIVE_HCI(dev);
    CPUState *cpu;

    qemu_chr_fe_set_handlers(&s->chr, NULL, NULL, NULL, NULL,
                             NULL, NULL, false);
    CPU_FOREACH(cpu) {
        CPUXtensaState *env = cpu_env(cpu);

        if (env->native_hci_send_opaque == s) {
            env->native_hci_send_hook_pc = 0;
            env->native_hci_send_return_pc = 0;
            env->native_hci_cmd_semaphore_hook_pc = 0;
            env->native_hci_cmd_semaphore_return_pc = 0;
            env->native_hci_acl_semaphore_hook_pc = 0;
            env->native_hci_acl_semaphore_return_pc = 0;
            env->native_hci_recycle_hook_pc = 0;
            env->native_hci_recycle_return_pc = 0;
            env->native_hci_sleep_post_hook_pc = 0;
            env->native_hci_sleep_post_return_pc = 0;
            memset(env->native_hci_trace_pcs, 0,
                   sizeof(env->native_hci_trace_pcs));
            env->native_hci_send_callback = NULL;
            env->native_hci_send_opaque = NULL;
            env->native_hci_trace_callback = NULL;
            env->native_hci_trace_opaque = NULL;
            tb_flush(cpu);
        }
    }
    timer_del(s->poll_timer);
    timer_del(s->c2h_timer);
    timer_del(s->hli_timer);
    timer_del(s->tx_timer);
    esp32_native_hci_unmap_h2c_length(s);
}

static void esp32_native_hci_reset(DeviceState *dev)
{
    Esp32NativeHciState *s = ESP32_NATIVE_HCI(dev);

    s->rx_buffer_length = 0;
    s->rx_queue_head = 0;
    s->rx_queue_count = 0;
    s->tx_queue_head = 0;
    s->tx_queue_count = 0;
    s->tx_queue_offset = 0;
    timer_del(s->tx_timer);
    s->h2c_length_value = 0;
    s->last_error = ESP32_NATIVE_HCI_ERROR_NONE;
    esp32_native_hci_unmap_h2c_length(s);
    if (s->env_pointer_address) {
        timer_mod(s->poll_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_VHCI_POLL_INTERVAL_NS);
    }
    s->c2h_scheduled = false;
    s->c2h_inflight = false;
    s->c2h_last_status = 0;
    s->c2h_last_pc = 0;
    s->c2h_observed_pc = 0;
    s->c2h_observed_halted = 0;
    s->c2h_return_pc = 0;
    s->c2h_exit_pc = 0;
    s->c2h_steps = 0;
    s->c2h_exception_index = 0;
    s->hli_scheduled = false;
    s->hli_posted = false;
    s->hli_post_pending = false;
    s->hli_valid = false;
    s->hli_queue_depth = 0;
    s->conn_pool_valid = false;
    s->l2cap_pool_valid = false;
    s->gatts_pool_valid = false;
    s->hs_conns_head = 0;
    s->conn_pool_free = 0;
    s->l2cap_pool_free = 0;
    s->gatts_pool_free = 0;
    s->meta_queue_depth = 0;
    s->hli_event_buffer_address = 0;
    s->hli_acl_mbuf_address = 0;
    s->hli_descriptor_pool_address = 0;
    s->hli_descriptor_cursor = 0;
    memset(s->hli_event_prealloc, 0, sizeof(s->hli_event_prealloc));
    memset(s->hli_acl_prealloc, 0, sizeof(s->hli_acl_prealloc));
    s->hli_event_prealloc_count = 0;
    s->hli_acl_prealloc_count = 0;
    s->hli_deferred_not_halted = 0;
    s->hci_trace_packets = 0;
    s->api_send_trace_packets = 0;
    if (s->scheduler_queue_address &&
        s->meta_queue_pointer_address) {
        timer_mod(s->hli_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  ESP32_NATIVE_HCI_HLI_POLL_NS);
    }
}

static Property esp32_native_hci_properties[] = {
    DEFINE_PROP_CHR("chardev", Esp32NativeHciState, chr),
    DEFINE_PROP_UINT64("env-pointer-address",
                       Esp32NativeHciState, env_pointer_address, 0),
    DEFINE_PROP_UINT64("c2h-scratch-address",
                       Esp32NativeHciState, c2h_scratch_address, 0),
    DEFINE_PROP_UINT64("c2h-allocator-address",
                       Esp32NativeHciState, c2h_allocator_address, 0),
    DEFINE_PROP_UINT64("scheduler-queue-address",
                       Esp32NativeHciState, scheduler_queue_address, 0),
    DEFINE_PROP_UINT64("meta-queue-pointer-address",
                       Esp32NativeHciState, meta_queue_pointer_address, 0),
    DEFINE_PROP_UINT64("trace-hs-conns-address",
                       Esp32NativeHciState, trace_hs_conns_address, 0),
    DEFINE_PROP_UINT64("ble-hs-conn-ctx-address",
                       Esp32NativeHciState, ble_hs_conn_ctx_address, 0),
    DEFINE_PROP_UINT64("ble-l2cap-pool-slot-address",
                       Esp32NativeHciState, ble_l2cap_pool_slot_address, 0),
    DEFINE_PROP_UINT64("ble-gatts-pool-slot-address",
                       Esp32NativeHciState, ble_gatts_pool_slot_address, 0),
    DEFINE_PROP_UINT64("api-vhci-send-hook-pc",
                       Esp32NativeHciState, api_vhci_send_hook_pc, 0),
    DEFINE_PROP_UINT64("api-vhci-send-return-pc",
                       Esp32NativeHciState, api_vhci_send_return_pc, 0),
    DEFINE_PROP_UINT64("cmd-semaphore-hook-pc",
                       Esp32NativeHciState, cmd_semaphore_hook_pc, 0),
    DEFINE_PROP_UINT64("cmd-semaphore-return-pc",
                       Esp32NativeHciState, cmd_semaphore_return_pc, 0),
    DEFINE_PROP_UINT64("acl-semaphore-hook-pc",
                       Esp32NativeHciState, acl_semaphore_hook_pc, 0),
    DEFINE_PROP_UINT64("acl-semaphore-return-pc",
                       Esp32NativeHciState, acl_semaphore_return_pc, 0),
    DEFINE_PROP_UINT64("recycle-hook-pc",
                       Esp32NativeHciState, recycle_hook_pc, 0),
    DEFINE_PROP_UINT64("recycle-return-pc",
                       Esp32NativeHciState, recycle_return_pc, 0),
    DEFINE_PROP_UINT64("sleep-post-hook-pc",
                       Esp32NativeHciState, sleep_post_hook_pc, 0),
    DEFINE_PROP_UINT64("sleep-post-return-pc",
                       Esp32NativeHciState, sleep_post_return_pc, 0),
    DEFINE_PROP_UINT64("trace-acl-process-pc",
                       Esp32NativeHciState, trace_acl_process_pc, 0),
    DEFINE_PROP_UINT64("trace-hci-cmd-tx-pc",
                       Esp32NativeHciState, trace_hci_cmd_tx_pc, 0),
    DEFINE_PROP_UINT64("trace-hs-sched-reset-pc",
                       Esp32NativeHciState, trace_hs_sched_reset_pc, 0),
    DEFINE_PROP_UINT64("trace-gap-adv-start-pc",
                       Esp32NativeHciState, trace_gap_adv_start_pc, 0),
    DEFINE_PROP_UINT64("trace-gap-adv-stop-pc",
                       Esp32NativeHciState, trace_gap_adv_stop_pc, 0),
    DEFINE_PROP_UINT64("trace-l2cap-rx-pc",
                       Esp32NativeHciState, trace_l2cap_rx_pc, 0),
    DEFINE_PROP_UINT64("trace-l2cap-incomplete-pc",
                       Esp32NativeHciState, trace_l2cap_incomplete_pc, 0),
    DEFINE_PROP_UINT64("trace-l2cap-chan-found-pc",
                       Esp32NativeHciState, trace_l2cap_chan_found_pc, 0),
    DEFINE_PROP_UINT64("trace-l2cap-mtu-reject-pc",
                       Esp32NativeHciState, trace_l2cap_mtu_reject_pc, 0),
    DEFINE_PROP_UINT64("trace-l2cap-rxfn-pc",
                       Esp32NativeHciState, trace_l2cap_rxfn_pc, 0),
    DEFINE_PROP_UINT64("trace-att-rx-pc",
                       Esp32NativeHciState, trace_att_rx_pc, 0),
    DEFINE_PROP_UINT64("trace-att-write-pc",
                       Esp32NativeHciState, trace_att_write_pc, 0),
    DEFINE_PROP_UINT64("trace-att-write-no-rsp-pc",
                       Esp32NativeHciState, trace_att_write_no_rsp_pc, 0),
    DEFINE_PROP_UINT64("trace-att-find-handle-pc",
                       Esp32NativeHciState, trace_att_find_handle_pc, 0),
    DEFINE_PROP_UINT64("trace-att-write-handle-pc",
                       Esp32NativeHciState, trace_att_write_handle_pc, 0),
    DEFINE_PROP_UINT64("trace-python-gatts-on-write-pc",
                       Esp32NativeHciState,
                       trace_python_gatts_on_write_pc, 0),
    DEFINE_PROP_UINT64("trace-python-irq-pc",
                       Esp32NativeHciState, trace_python_irq_pc, 0),
    DEFINE_PROP_UINT64("trace-python-notify-pc",
                       Esp32NativeHciState, trace_python_notify_pc, 0),
    DEFINE_PROP_UINT64("trace-nimble-gatts-notify-pc",
                       Esp32NativeHciState,
                       trace_nimble_gatts_notify_pc, 0),
    DEFINE_PROP_UINT64("trace-hci-rx-evt-pc",
                       Esp32NativeHciState, trace_hci_rx_evt_pc, 0),
    DEFINE_PROP_UINT64("trace-hci-rx-ack-check-pc",
                       Esp32NativeHciState, trace_hci_rx_ack_check_pc, 0),
    DEFINE_PROP_UINT64("ble-hs-hci-ctx-address",
                       Esp32NativeHciState, ble_hs_hci_ctx_address, 0),
    DEFINE_PROP_UINT64("hli-event-allocator-address",
                       Esp32NativeHciState, hli_event_allocator_address, 0),
    DEFINE_PROP_UINT64("hli-acl-allocator-address",
                       Esp32NativeHciState, hli_acl_allocator_address, 0),
    DEFINE_PROP_UINT64("hli-os-mbuf-append-address",
                       Esp32NativeHciState, hli_os_mbuf_append_address, 0),
    DEFINE_PROP_UINT64("hli-acl-callback",
                       Esp32NativeHciState, hli_acl_callback, 0),
    DEFINE_PROP_BOOL("hli-c2h", Esp32NativeHciState, hli_c2h, false),
    DEFINE_PROP_BOOL("hci-packet-trace",
                     Esp32NativeHciState, hci_packet_trace, false),
    DEFINE_PROP_UINT32("hci-trace-limit",
                       Esp32NativeHciState, hci_trace_limit, 512),
    DEFINE_PROP_UINT32("hli-test-event",
                       Esp32NativeHciState, hli_test_event,
                       UINT32_MAX),
    DEFINE_PROP_UINT64("hli-test-callback",
                       Esp32NativeHciState, hli_test_callback, 0),
    DEFINE_PROP_UINT64("hli-test-argument",
                       Esp32NativeHciState, hli_test_argument, 0),
    DEFINE_PROP_STRING("hli-event-data",
                       Esp32NativeHciState, hli_event_data),
    DEFINE_PROP_UINT32("hli-event-buffer-size",
                       Esp32NativeHciState, hli_event_buffer_size, 70),
    DEFINE_PROP_UINT32("hli-descriptor-pool-size",
                       Esp32NativeHciState, hli_descriptor_pool_size,
                       256),
    DEFINE_PROP_UINT32("c2h-scratch-size",
                       Esp32NativeHciState, c2h_scratch_size,
                       ESP32_NATIVE_HCI_PACKET_MAX),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32_native_hci_init(Object *obj)
{
    Esp32NativeHciState *s = ESP32_NATIVE_HCI(obj);

    s->poll_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                 esp32_native_hci_poll, s);
    s->c2h_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                esp32_native_hci_c2h_retry, s);
    s->hli_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                esp32_native_hci_hli_poll, s);
    s->tx_timer = timer_new_ns(QEMU_CLOCK_REALTIME,
                               esp32_native_hci_tx_retry, s);
}

static void esp32_native_hci_finalize(Object *obj)
{
    Esp32NativeHciState *s = ESP32_NATIVE_HCI(obj);

    timer_free(s->poll_timer);
    timer_free(s->c2h_timer);
    timer_free(s->hli_timer);
    timer_free(s->tx_timer);
    s->poll_timer = NULL;
    s->c2h_timer = NULL;
    s->hli_timer = NULL;
    s->tx_timer = NULL;
}

static void esp32_native_hci_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = esp32_native_hci_realize;
    dc->unrealize = esp32_native_hci_unrealize;
    dc->user_creatable = true;
    device_class_set_legacy_reset(dc, esp32_native_hci_reset);
    device_class_set_props(dc, esp32_native_hci_properties);
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
}

static const TypeInfo esp32_native_hci_info = {
    .name = TYPE_ESP32_NATIVE_HCI,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(Esp32NativeHciState),
    .instance_init = esp32_native_hci_init,
    .instance_finalize = esp32_native_hci_finalize,
    .class_init = esp32_native_hci_class_init,
};

static void esp32_native_hci_register_types(void)
{
    type_register_static(&esp32_native_hci_info);
}

type_init(esp32_native_hci_register_types)

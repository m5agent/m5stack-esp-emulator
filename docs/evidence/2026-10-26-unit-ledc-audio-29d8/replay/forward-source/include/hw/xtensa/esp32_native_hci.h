/*
 * Classic ESP32 native HCI transport.
 *
 * This frontend owns H4 packet framing, bounded host/guest queues and the
 * classic ESP32 VHCI shared-memory adapter.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_XTENSA_ESP32_NATIVE_HCI_H
#define HW_XTENSA_ESP32_NATIVE_HCI_H

#include "chardev/char-fe.h"
#include "exec/memory.h"
#include "hw/qdev-core.h"
#include "qemu/timer.h"
#include "qom/object.h"

#define TYPE_ESP32_NATIVE_HCI "esp32-native-hci"
OBJECT_DECLARE_SIMPLE_TYPE(Esp32NativeHciState, ESP32_NATIVE_HCI)

#define ESP32_NATIVE_HCI_QUEUE_DEPTH 32
#define ESP32_NATIVE_HCI_PACKET_MAX 2048
#define ESP32_NATIVE_HCI_RX_BUFFER_SIZE 8192
#define ESP32_NATIVE_HCI_TRACE_SLOTS 21
/*
 * Four simultaneous cold starts can consume the initial HCI command ACKs
 * before CPU0 reaches another safe idle point. Keep enough real guest
 * transport objects to cover the startup burst without nested guest calls.
 */
#define ESP32_NATIVE_HCI_HLI_EVENT_PREALLOC 8
#define ESP32_NATIVE_HCI_HLI_ACL_PREALLOC 4

typedef struct Esp32NativeHciPacket {
    uint16_t length;
    uint8_t data[ESP32_NATIVE_HCI_PACKET_MAX];
} Esp32NativeHciPacket;

struct Esp32NativeHciState {
    DeviceState parent_obj;

    CharBackend chr;
    QEMUTimer *poll_timer;
    QEMUTimer *c2h_timer;
    QEMUTimer *hli_timer;
    QEMUTimer *tx_timer;
    MemoryRegion h2c_length_mmio;
    Esp32NativeHciPacket tx_queue[ESP32_NATIVE_HCI_QUEUE_DEPTH];
    Esp32NativeHciPacket rx_queue[ESP32_NATIVE_HCI_QUEUE_DEPTH];
    uint8_t rx_buffer[ESP32_NATIVE_HCI_RX_BUFFER_SIZE];

    uint32_t rx_buffer_length;
    uint32_t rx_queue_head;
    uint32_t rx_queue_count;
    uint32_t tx_queue_head;
    uint32_t tx_queue_count;
    uint32_t tx_queue_offset;
    uint32_t last_tx_errno;
    uint32_t last_error;
    uint64_t env_pointer_address;
    uint32_t vhci_env_address;
    uint32_t h2c_length_value;
    uint64_t c2h_scratch_address;
    uint64_t c2h_allocator_address;
    uint64_t scheduler_queue_address;
    uint64_t meta_queue_pointer_address;
    uint64_t trace_hs_conns_address;
    uint64_t ble_hs_conn_ctx_address;
    uint64_t ble_l2cap_pool_slot_address;
    uint64_t ble_gatts_pool_slot_address;
    uint64_t api_vhci_send_hook_pc;
    uint64_t api_vhci_send_return_pc;
    uint64_t cmd_semaphore_hook_pc;
    uint64_t cmd_semaphore_return_pc;
    uint64_t acl_semaphore_hook_pc;
    uint64_t acl_semaphore_return_pc;
    uint64_t recycle_hook_pc;
    uint64_t recycle_return_pc;
    uint64_t sleep_post_hook_pc;
    uint64_t sleep_post_return_pc;
    uint64_t vhci_send_semaphore_address;
    uint64_t sleep_disable_address;
    uint64_t hli_event_allocator_address;
    uint64_t hli_acl_allocator_address;
    uint64_t hli_os_mbuf_append_address;
    uint64_t hli_acl_callback;
    uint64_t hli_send_available_callback;
    uint64_t hli_task_post_address;
    uint64_t hli_test_callback;
    uint64_t hli_test_argument;
    uint64_t trace_acl_process_pc;
    uint64_t trace_hci_cmd_tx_pc;
    uint64_t trace_hs_sched_reset_pc;
    uint64_t trace_gap_adv_start_pc;
    uint64_t trace_gap_adv_stop_pc;
    uint64_t trace_l2cap_rx_pc;
    uint64_t trace_l2cap_incomplete_pc;
    uint64_t trace_l2cap_chan_found_pc;
    uint64_t trace_l2cap_mtu_reject_pc;
    uint64_t trace_l2cap_rxfn_pc;
    uint64_t trace_att_rx_pc;
    uint64_t trace_att_write_pc;
    uint64_t trace_att_write_no_rsp_pc;
    uint64_t trace_att_find_handle_pc;
    uint64_t trace_att_write_handle_pc;
    uint64_t trace_python_gatts_on_write_pc;
    uint64_t trace_python_irq_pc;
    uint64_t trace_python_notify_pc;
    uint64_t trace_nimble_gatts_notify_pc;
    uint64_t trace_hci_rx_evt_pc;
    uint64_t trace_hci_rx_ack_check_pc;
    uint64_t ble_hs_hci_ctx_address;
    uint64_t hli_event_buffer_address;
    uint64_t hli_acl_mbuf_address;
    uint64_t hli_descriptor_pool_address;
    uint64_t hli_last_descriptor_address;
    uint64_t hli_last_descriptor_argument;
    uint64_t hli_last_descriptor_callback;
    uint64_t hli_event_prealloc[
        ESP32_NATIVE_HCI_HLI_EVENT_PREALLOC];
    uint64_t hli_acl_prealloc[
        ESP32_NATIVE_HCI_HLI_ACL_PREALLOC];
    char *hli_event_data;
    uint32_t vhci_callback_address;
    uint32_t vhci_receive_address;
    uint32_t c2h_scratch_size;
    uint32_t hli_descriptor_pool_size;
    uint32_t hli_descriptor_cursor;
    uint32_t api_h2c_credits;
    uint32_t hci_trace_limit;
    uint32_t hli_event_buffer_size;
    uint32_t hli_event_length;
    uint32_t c2h_last_status;
    uint32_t c2h_last_pc;
    uint32_t c2h_observed_pc;
    uint32_t c2h_observed_halted;
    uint32_t c2h_return_pc;
    uint32_t c2h_exit_pc;
    uint32_t c2h_steps;
    uint32_t c2h_exception_index;
    uint32_t hli_test_event;
    uint32_t hli_last_event;
    uint32_t hli_queue_address;
    uint32_t hli_queue_element_size;
    uint32_t hli_queue_begin;
    uint32_t hli_queue_end;
    uint32_t hli_queue_depth;
    uint32_t meta_queue_address;
    uint32_t meta_queue_element_size;
    uint32_t meta_queue_begin;
    uint32_t meta_queue_end;
    uint32_t meta_queue_depth;
    uint32_t hs_conns_head;
    uint32_t conn_pool_free;
    uint32_t conn_pool_valid;
    uint32_t l2cap_pool_free;
    uint32_t l2cap_pool_valid;
    uint32_t gatts_pool_free;
    uint32_t gatts_pool_valid;
    uint32_t hli_post_end;
    uint32_t hli_valid;
    uint32_t hli_event_prealloc_count;
    uint32_t hli_acl_prealloc_count;
    bool hli_c2h;
    bool h2c_length_mapped;
    bool c2h_scheduled;
    bool c2h_inflight;
    bool hli_scheduled;
    bool hli_posted;
    bool hli_post_pending;
    bool hli_send_available_pending;
    bool sleep_disabled;
    bool hci_packet_trace;

    uint64_t rx_bytes;
    uint64_t rx_packets;
    uint64_t tx_bytes;
    uint64_t tx_packets;
    uint64_t malformed_packets;
    uint64_t dropped_packets;
    uint64_t peer_opened;
    uint64_t peer_closed;
    uint64_t h2c_packets;
    uint64_t h2c_bytes;
    uint64_t h2c_duplicates;
    uint64_t h2c_incomplete_writes;
    uint64_t c2h_delivered;
    uint64_t c2h_errors;
    uint64_t c2h_send_available;
    uint64_t hli_posts;
    uint64_t hli_consumed;
    uint64_t hli_event_buffers;
    uint64_t hli_acl_buffers;
    uint64_t hli_c2h_events;
    uint64_t hli_c2h_acls;
    uint64_t hli_send_available_posts;
    uint64_t api_h2c_packets;
    uint64_t api_h2c_errors;
    uint64_t api_credit_refills;
    uint64_t api_sleep_disabled;
    uint64_t tx_retry_count;
    uint64_t tx_zero_writes;
    uint64_t hli_errors;
    uint64_t hli_deferred_not_halted;
    uint64_t hli_fast_path_events;
    uint64_t hli_fast_path_acls;
    uint64_t hli_prealloc_failures;
    uint64_t hci_trace_packets;
    uint64_t api_send_trace_packets;
    uint64_t trace_acl_process;
    uint64_t trace_hci_cmd_tx;
    uint64_t trace_hs_sched_reset;
    uint64_t trace_gap_adv_start;
    uint64_t trace_gap_adv_stop;
    uint64_t trace_l2cap_rx;
    uint64_t trace_l2cap_incomplete;
    uint64_t trace_l2cap_chan_found;
    uint64_t trace_l2cap_mtu_reject;
    uint64_t trace_l2cap_rxfn;
    uint64_t trace_att_rx;
    uint64_t trace_att_write;
    uint64_t trace_att_write_no_rsp;
    uint64_t trace_att_find_handle;
    uint64_t trace_att_write_handle;
    uint64_t trace_python_gatts_on_write;
    uint64_t trace_python_irq;
    uint64_t trace_python_notify;
    uint64_t trace_nimble_gatts_notify;
    uint64_t trace_hci_rx_evt;
    uint64_t trace_hci_rx_ack_check;
};

bool esp32_native_hci_send_h2c(Esp32NativeHciState *s,
                               const uint8_t *data, size_t size,
                               Error **errp);

#endif

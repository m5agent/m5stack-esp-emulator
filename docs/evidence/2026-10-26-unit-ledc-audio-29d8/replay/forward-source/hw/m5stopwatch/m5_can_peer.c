/*
 * Virtual CAN peer for M5Stack board models.
 *
 * The peer is a real client on QEMU's CAN bus.  When enabled, it echoes every
 * frame back to the controller, allowing the unmodified guest TWAI driver to
 * exercise TX, RX, filtering, interrupts and its receive FIFOs.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "net/can_emu.h"
#include "qom/object.h"
#include "m5stopwatch.h"

typedef struct M5CanPeer {
    CanBusClientState client;
    bool echo;
} M5CanPeer;

static bool m5_can_peer_can_receive(CanBusClientState *client)
{
    return true;
}

static ssize_t m5_can_peer_receive(CanBusClientState *client,
                                   const struct qemu_can_frame *frames,
                                   size_t frames_cnt)
{
    M5CanPeer *peer = container_of(client, M5CanPeer, client);

    if (peer->echo && frames_cnt) {
        can_bus_client_send(client, frames, frames_cnt);
    }
    return frames_cnt;
}

static CanBusClientInfo m5_can_peer_info = {
    .can_receive = m5_can_peer_can_receive,
    .receive = m5_can_peer_receive,
};

struct CanBusState *m5_can_bus_create(void)
{
    CanBusState *bus = CAN_BUS(object_new(TYPE_CAN_BUS));
    M5CanPeer *peer = g_new0(M5CanPeer, 1);

    object_property_add_child(qdev_get_machine(), "m5-canbus", OBJECT(bus));
    peer->echo = getenv("M5SW_CAN_ECHO") != NULL;
    peer->client.info = &m5_can_peer_info;
    can_bus_insert_client(bus, &peer->client);
    return bus;
}

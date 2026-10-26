/*
 * Byte-level UART peer used by RS485 and other half-duplex board buses.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/char/esp32_uart.h"
#include "m5stopwatch.h"

typedef struct M5UartPeer {
    ESP32UARTState *uart;
    bool echo;
} M5UartPeer;

static void m5_uart_peer_tx(void *opaque, uint8_t byte)
{
    M5UartPeer *peer = opaque;

    if (peer->echo) {
        esp32_uart_inject_rx(peer->uart, &byte, 1);
    }
}

void m5_uart_echo_attach(DeviceState *uart, const char *enable_env)
{
    M5UartPeer *peer = g_new0(M5UartPeer, 1);

    peer->uart = ESP32_UART(uart);
    peer->echo = enable_env && getenv(enable_env) != NULL;
    esp32_uart_set_tx_byte_callback(peer->uart, m5_uart_peer_tx, peer);
}

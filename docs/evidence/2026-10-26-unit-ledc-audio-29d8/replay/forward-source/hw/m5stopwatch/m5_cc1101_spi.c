/*
 * CC1101 Sub-GHz SPI transceiver model for UIFlow2 Cap CC1101.
 *
 * The model implements the configuration/status register map, command
 * strobes, FIFO transfers and a deterministic local TX-to-RX loopback. RF
 * propagation is intentionally out of scope; the SPI transport and packet
 * FIFO behavior are real guest-visible paths.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "hw/gpio/esp32_gpio.h"
#include "m5stopwatch.h"

#define CC1101_FIFO_SIZE 64

enum {
    CC_IDLE,
    CC_REG_WRITE,
    CC_REG_READ,
    CC_FIFO_WRITE,
    CC_FIFO_READ,
};

typedef struct M5Cc1101SpiState {
    uint8_t regs[0x40];
    uint8_t tx_fifo[CC1101_FIFO_SIZE];
    uint32_t tx_len;
    uint8_t air_fifo[CC1101_FIFO_SIZE];
    uint32_t air_len;
    bool air_pending;
    uint8_t rx_fifo[CC1101_FIFO_SIZE + 2];
    uint32_t rx_len;
    uint32_t rx_pos;
    uint8_t phase;
    uint8_t reg;
    uint8_t marc_state;
    uint8_t tx_poll_count;
    int gdo0_pin;
    bool packet_ready;
    QEMUTimer *rx_timer;
} M5Cc1101SpiState;

static void cc1101_rx_timer(void *opaque)
{
    M5Cc1101SpiState *s = opaque;

    if (s->packet_ready && s->gdo0_pin >= 0) {
        esp32_gpio_force_line(s->gdo0_pin, 1);
    }
}

static void cc1101_reset(M5Cc1101SpiState *s)
{
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x31] = 0x14; /* VERSION */
    s->regs[0x18] = 0x18; /* MCSM0 */
    s->regs[0x22] = 0x11; /* FREND0 */
    s->marc_state = 0x01; /* IDLE */
    s->tx_len = 0;
    s->air_len = 0;
    s->air_pending = false;
    s->rx_len = 0;
    s->rx_pos = 0;
    s->packet_ready = false;
    if (s->gdo0_pin >= 0) {
        esp32_gpio_force_line(s->gdo0_pin, 0);
    }
    if (s->rx_timer) {
        timer_del(s->rx_timer);
    }
}

static void cc1101_strobe(M5Cc1101SpiState *s, uint8_t command)
{
    if (getenv("M5SW_CC1101_TRACE")) {
        fprintf(stderr, "[cc1101] strobe=%02x state=%02x tx=%u rx=%u\n",
                command, s->marc_state, s->tx_len, s->rx_len);
    }
    switch (command) {
    case 0x30: /* SRES */
        cc1101_reset(s);
        break;
    case 0x31: /* SFSTXON */
        s->marc_state = 0x12;
        break;
    case 0x34: /* SRX */
        s->marc_state = 0x0d;
        if (s->air_pending) {
            s->rx_len = MIN(s->air_len + 2, sizeof(s->rx_fifo));
            memcpy(s->rx_fifo, s->air_fifo, s->air_len);
            if (s->rx_len >= 2) {
                s->rx_fifo[s->rx_len - 2] = 0x80;
                s->rx_fifo[s->rx_len - 1] = 0x80;
            }
            s->rx_pos = 0;
            s->packet_ready = true;
        }
        if (s->packet_ready && s->gdo0_pin >= 0) {
            esp32_gpio_force_line(s->gdo0_pin, 0);
            timer_mod(s->rx_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 5);
        }
        break;
    case 0x35: /* STX */
        s->marc_state = 0x13;
        s->tx_poll_count = 4;
        s->air_len = MIN(s->tx_len, sizeof(s->air_fifo));
        if (s->tx_len) {
            memcpy(s->air_fifo, s->tx_fifo, s->air_len);
        }
        s->air_pending = true;
        s->packet_ready = false;
        if (s->gdo0_pin >= 0) {
            esp32_gpio_force_line(s->gdo0_pin, 0);
        }
        break;
    case 0x36: /* SIDLE */
        s->marc_state = 0x01;
        break;
    case 0x3a: /* SFRX */
        s->rx_len = 0;
        s->rx_pos = 0;
        s->packet_ready = false;
        if (s->rx_timer) {
            timer_del(s->rx_timer);
        }
        if (s->gdo0_pin >= 0) {
            esp32_gpio_force_line(s->gdo0_pin, 0);
        }
        break;
    case 0x3b: /* SFTX */
        s->tx_len = 0;
        break;
    case 0x39: /* SPWD */
        s->marc_state = 0x00;
        break;
    default:
        break;
    }
}

static uint8_t cc1101_read_reg(M5Cc1101SpiState *s, uint8_t reg)
{
    uint8_t state;

    switch (reg & 0x3f) {
    case 0x30:
        return 0x00;
    case 0x31:
        return 0x14;
    case 0x33:
        return 0x80;
    case 0x34:
        return 0x80;
    case 0x35:
        state = s->marc_state;
        if (state == 0x13 && s->tx_poll_count) {
            if (--s->tx_poll_count == 0) {
                s->marc_state = 0x01;
            }
        }
        return s->marc_state;
    case 0x3a:
        return s->marc_state == 0x13 ? s->tx_len : 0;
    case 0x3b:
        return s->rx_len > s->rx_pos ? s->rx_len - s->rx_pos : 0;
    default:
        return s->regs[reg & 0x3f];
    }
}

static uint8_t cc1101_transfer(void *opaque, uint8_t tx)
{
    M5Cc1101SpiState *s = opaque;
    uint8_t value = 0;

    if (getenv("M5SW_CC1101_TRACE")) {
        fprintf(stderr, "[cc1101-spi] phase=%u tx=%02x\n", s->phase, tx);
    }

    if (s->phase == CC_IDLE) {
        if (tx >= 0x30 && tx <= 0x3d && !(tx & 0x80)) {
            cc1101_strobe(s, tx);
        } else if (tx & 0x80) {
            s->reg = tx & 0x3f;
            s->phase = s->reg == 0x3f ? CC_FIFO_READ : CC_REG_READ;
        } else {
            s->reg = tx & 0x3f;
            s->phase = s->reg == 0x3f ? CC_FIFO_WRITE : CC_REG_WRITE;
        }
        return 0;
    }

    switch (s->phase) {
    case CC_REG_WRITE:
        s->regs[s->reg] = tx;
        s->phase = CC_IDLE;
        break;
    case CC_REG_READ:
        value = cc1101_read_reg(s, s->reg++);
        break;
    case CC_FIFO_WRITE:
        if (s->tx_len < sizeof(s->tx_fifo)) {
            s->tx_fifo[s->tx_len++] = tx;
        }
        break;
    case CC_FIFO_READ:
        value = s->rx_pos < s->rx_len ? s->rx_fifo[s->rx_pos++] : 0;
        break;
    default:
        break;
    }
    return value;
}

static void cc1101_set_cs(void *opaque, int level)
{
    M5Cc1101SpiState *s = opaque;

    if (level) {
        s->phase = CC_IDLE;
        s->reg = 0;
    }
}

static const M5SpiSlaveOps cc1101_ops = {
    .set_cs = cc1101_set_cs,
    .transfer = cc1101_transfer,
};

void m5_cc1101_spi_attach(DeviceState *spi, int cs_pin, int gdo0_pin)
{
    M5Cc1101SpiState *s = g_new0(M5Cc1101SpiState, 1);

    s->gdo0_pin = gdo0_pin;
    s->rx_timer = timer_new_ms(QEMU_CLOCK_REALTIME, cc1101_rx_timer, s);
    cc1101_reset(s);
    esp32s3_gpspi_attach_spi_slave(spi, &cc1101_ops, s, cs_pin);
    esp32_gpio_set_input(gdo0_pin, 0);
    esp32_gpio_force_line(gdo0_pin, 0);
}

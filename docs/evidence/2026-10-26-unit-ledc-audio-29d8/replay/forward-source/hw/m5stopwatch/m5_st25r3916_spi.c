/*
 * ST25R3916 NFC reader SPI transport model.
 *
 * UIFlow2 uses command/register writes, register reads, Space-B accesses,
 * FIFO load/read and ISO14443A command responses over this transport. This
 * model keeps the same deterministic NTAG behavior as the I2C model while
 * allowing ST25R3916 to share an SPI bus with SD and CC1101 chip selects.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/gpio/esp32_gpio.h"
#include "m5stopwatch.h"

#define ST25_FIFO_SIZE 512
#define ST25_TAG_SIZE  180

enum {
    ST25_IDLE,
    ST25_REG_WRITE,
    ST25_REG_READ,
    ST25_SPACE_ADDR,
    ST25_SPACE_WRITE,
    ST25_SPACE_READ,
    ST25_FIFO_WRITE,
    ST25_FIFO_READ,
};

typedef struct M5St25r3916SpiState {
    uint8_t regs[64];
    uint8_t space_b[64];
    uint8_t tx[64];
    uint32_t tx_len;
    uint8_t rx[ST25_FIFO_SIZE];
    uint32_t rx_len;
    uint32_t rx_pos;
    uint8_t tag[ST25_TAG_SIZE];
    uint8_t phase;
    uint8_t reg;
    uint8_t space_addr;
    bool field_on;
    int irq_pin;
} M5St25r3916SpiState;

static void st25_set_fifo(M5St25r3916SpiState *s,
                          const uint8_t *data, uint32_t size)
{
    size = MIN(size, sizeof(s->rx));
    if (size) {
        memcpy(s->rx, data, size);
    }
    s->rx_len = size;
    s->rx_pos = 0;
    if (s->irq_pin >= 0) {
        esp32_gpio_force_line(s->irq_pin, size != 0);
    }
}

static void st25_set_fifo_byte(M5St25r3916SpiState *s, uint8_t value)
{
    st25_set_fifo(s, &value, 1);
}

static void st25_init_tag(M5St25r3916SpiState *s)
{
    static const uint8_t uid[4] = { 0xde, 0xad, 0xbe, 0xef };
    static const uint8_t page4[4] = { 'M', '5', 'N', '1' };

    memcpy(s->tag, uid, sizeof(uid));
    s->tag[4] = uid[0] ^ uid[1] ^ uid[2] ^ uid[3];
    s->tag[5] = 0x48;
    s->tag[12] = 0xe1;
    s->tag[13] = 0x10;
    s->tag[14] = 0x12;
    memcpy(&s->tag[16], page4, sizeof(page4));
}

static void st25_execute_command(M5St25r3916SpiState *s, uint8_t command)
{
    static const uint8_t atqa[2] = { 0x44, 0x00 };
    static const uint8_t version[10] = {
        0x00, 0x04, 0x04, 0x02, 0x02, 0x01, 0x0b, 0x03, 0x00, 0x00,
    };
    uint8_t response[18] = { 0 };

    switch (command) {
    case 0xc1: /* SET_DEFAULT */
        memset(s->regs, 0, sizeof(s->regs));
        memset(s->space_b, 0, sizeof(s->space_b));
        s->regs[0x3f] = 0x2a;
        st25_set_fifo(s, NULL, 0);
        break;
    case 0xc6: /* TRANSMIT_REQA */
    case 0xc7: /* TRANSMIT_WUPA */
        st25_set_fifo(s, atqa, sizeof(atqa));
        break;
    case 0xc5: /* TRANSMIT_WITHOUT_CRC */
        if (s->tx_len >= 1 && s->tx[0] == 0x93) {
            response[0] = s->tag[0];
            response[1] = s->tag[1];
            response[2] = s->tag[2];
            response[3] = s->tag[3];
            response[4] = s->tag[4];
            st25_set_fifo(s, response, 5);
        }
        s->tx_len = 0;
        break;
    case 0xc4: /* TRANSMIT_WITH_CRC */
        if (s->tx_len >= 2 && s->tx[0] == 0x93) {
            response[0] = 0x00;
            st25_set_fifo(s, response, 1);
        } else if (s->tx_len >= 1 && s->tx[0] == 0x60) {
            st25_set_fifo(s, version, sizeof(version));
        } else if (s->tx_len >= 2 && s->tx[0] == 0x30) {
            uint32_t base = (s->tx[1] & ~3u) * 4;
            uint32_t available = sizeof(s->tag) - MIN(base, sizeof(s->tag));
            uint32_t copy = MIN(available, 16);
            memcpy(response, &s->tag[base], copy);
            st25_set_fifo(s, response, copy + 2);
        } else if (s->tx_len >= 6 && s->tx[0] == 0xa2) {
            uint32_t offset = (s->tx[1] & 0x3f) * 4;
            if (offset + 4 <= sizeof(s->tag)) {
                memcpy(&s->tag[offset], &s->tx[2], 4);
            }
            st25_set_fifo_byte(s, 0x0a);
        } else if (s->tx_len >= 1 && s->tx[0] == 0x50) {
            st25_set_fifo(s, NULL, 0);
        }
        s->tx_len = 0;
        break;
    case 0xc8: /* NFC_INITIAL_FIELD_ON */
        s->field_on = true;
        s->regs[0x1a] |= 0x80;
        break;
    case 0xc2: /* STOP_ALL_ACTIVITIES */
        s->field_on = false;
        break;
    case 0xdb: /* CLEAR_FIFO */
        st25_set_fifo(s, NULL, 0);
        s->tx_len = 0;
        break;
    default:
        break;
    }
}

static uint8_t st25_read_reg(M5St25r3916SpiState *s, uint8_t reg)
{
    uint32_t count;

    switch (reg & 0x3f) {
    case 0x1e:
        count = MIN(s->rx_len, 0x3ff);
        return count >> 8;
    case 0x1f:
        count = MIN(s->rx_len, 0x3ff);
        return (count & 0x3f) << 6;
    case 0x1a:
        return s->regs[0x1a] |
               ((s->field_on || (s->regs[0x02] & 0x80)) ? 0x80 : 0);
    case 0x31:
        return 0x10;
    case 0x3f:
        return 0x2a;
    default:
        return s->regs[reg & 0x3f];
    }
}

static uint8_t st25_transfer(void *opaque, uint8_t tx)
{
    M5St25r3916SpiState *s = opaque;
    uint8_t value = 0;

    if (getenv("M5SW_SPI_XFER_TRACE")) {
        fprintf(stderr, "[st25-spi] phase=%u tx=%02x\n", s->phase, tx);
    }
    if (s->phase == ST25_IDLE) {
        if (tx <= 0x3f) {
            s->reg = tx & 0x3f;
            s->phase = ST25_REG_WRITE;
        } else if (tx <= 0x7f) {
            s->reg = tx & 0x3f;
            s->phase = ST25_REG_READ;
        } else if (tx == 0xfb) {
            s->phase = ST25_SPACE_ADDR;
        } else if (tx == 0x80) {
            s->tx_len = 0;
            s->phase = ST25_FIFO_WRITE;
        } else if (tx == 0x9f) {
            s->rx_pos = 0;
            s->phase = ST25_FIFO_READ;
        } else {
            st25_execute_command(s, tx);
        }
        return value;
    }

    switch (s->phase) {
    case ST25_REG_WRITE:
        s->regs[s->reg] = tx;
        s->phase = ST25_IDLE;
        break;
    case ST25_REG_READ:
        value = st25_read_reg(s, s->reg++);
        break;
    case ST25_SPACE_ADDR:
        s->space_addr = tx & 0x3f;
        s->phase = (tx & 0x40) ? ST25_SPACE_READ : ST25_SPACE_WRITE;
        break;
    case ST25_SPACE_WRITE:
        s->space_b[s->space_addr] = tx;
        s->phase = ST25_IDLE;
        break;
    case ST25_SPACE_READ:
        value = s->space_b[s->space_addr++ & 0x3f];
        break;
    case ST25_FIFO_WRITE:
        if (s->tx_len < sizeof(s->tx)) {
            s->tx[s->tx_len++] = tx;
        }
        break;
    case ST25_FIFO_READ:
        value = s->rx_pos < s->rx_len ? s->rx[s->rx_pos++] : 0;
        break;
    default:
        break;
    }
    return value;
}

static void st25_set_cs(void *opaque, int level)
{
    M5St25r3916SpiState *s = opaque;

    if (level) {
        s->phase = ST25_IDLE;
        s->reg = 0;
        s->space_addr = 0;
    }
}

static const M5SpiSlaveOps st25_ops = {
    .set_cs = st25_set_cs,
    .transfer = st25_transfer,
};

void m5_st25r3916_spi_attach(DeviceState *spi, int cs_pin, int irq_pin)
{
    M5St25r3916SpiState *s = g_new0(M5St25r3916SpiState, 1);

    s->irq_pin = irq_pin;
    s->regs[0x3f] = 0x2a;
    st25_init_tag(s);
    esp32s3_gpspi_attach_spi_slave(spi, &st25_ops, s, cs_pin);
    esp32_gpio_set_input(irq_pin, 0);
    esp32_gpio_force_line(irq_pin, 0);
}

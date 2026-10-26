/*
 * Minimal Semtech SX1262 SPI modem model for the UIFlow2 LoRa driver.
 *
 * This implements the command/status/register/FIFO protocol and a local TX
 * loopback packet path. RF modulation and multi-device propagation are not
 * modeled; packets sent by this modem become the next received packet.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "m5stopwatch.h"

#define SX1262_MAX_PACKET 255

typedef enum {
    SX_IDLE,
    SX_ARGS,
    SX_RESPONSE,
    SX_WRITE_BUFFER,
    SX_READ_BUFFER,
} Sx1262Mode;

typedef struct M5Sx1262State {
    const M5SpiSlaveOps *ops;
    Sx1262Mode mode;
    uint8_t opcode;
    uint8_t args[16];
    uint8_t arg_count;
    uint8_t expected_args;
    uint8_t response[264];
    uint16_t response_len;
    uint16_t response_pos;
    uint8_t tx_packet[SX1262_MAX_PACKET];
    uint8_t rx_packet[SX1262_MAX_PACKET];
    uint16_t tx_len;
    uint16_t rx_len;
    uint16_t rx_pos;
    uint16_t irq_status;
    uint16_t registers[16];
} M5Sx1262State;

static uint8_t sx1262_status(void)
{
    return 0x20; /* STDBY_RC, command status OK */
}

static void sx1262_set_response(M5Sx1262State *s,
                                const uint8_t *data, uint16_t size)
{
    memcpy(s->response, data, MIN(size, sizeof(s->response)));
    s->response_len = MIN(size, sizeof(s->response));
    s->response_pos = 0;
    s->mode = SX_RESPONSE;
}

static void sx1262_command(M5Sx1262State *s)
{
    uint8_t response[4] = { sx1262_status(), 0, 0, 0 };

    switch (s->opcode) {
    case 0x02: /* CLR_IRQ_STATUS */
        s->irq_status &= ~(((uint16_t)s->args[0] << 8) | s->args[1]);
        s->mode = SX_IDLE;
        break;
    case 0x07: /* CLR_ERRORS */
        s->mode = SX_IDLE;
        break;
    case 0x08: /* CFG_DIO_IRQ */
        s->mode = SX_IDLE;
        break;
    case 0x0d: { /* WRITE_REGISTER */
        uint16_t addr = ((uint16_t)s->args[0] << 8) | s->args[1];
        s->registers[(addr >> 4) & 0xf] = s->args[2];
        s->mode = SX_IDLE;
        break;
    }
    case 0x0e: /* WRITE_BUFFER */
        s->tx_len = 0;
        s->mode = SX_WRITE_BUFFER;
        break;
    case 0x12: /* GET_IRQ_STATUS */
        response[1] = s->irq_status >> 8;
        response[2] = s->irq_status;
        sx1262_set_response(s, response, 3);
        break;
    case 0x13: /* GET_RX_BUFFER_STATUS */
        response[1] = s->rx_len;
        response[2] = 0;
        sx1262_set_response(s, response, 3);
        break;
    case 0x14: /* GET_PACKET_STATUS */
        response[1] = 0xb0; /* RSSI */
        response[2] = 0x08; /* SNR */
        response[3] = 0xb0;
        sx1262_set_response(s, response, 4);
        break;
    case 0x17: /* GET_ERROR */
        sx1262_set_response(s, response, 3);
        break;
    case 0x1d: { /* READ_REGISTER */
        uint16_t addr = ((uint16_t)s->args[0] << 8) | s->args[1];
        response[0] = s->registers[(addr >> 4) & 0xf];
        sx1262_set_response(s, response, 1);
        break;
    }
    case 0x1e: /* READ_BUFFER */
        s->rx_pos = 0;
        response[0] = sx1262_status();
        sx1262_set_response(s, response, 1);
        s->mode = SX_READ_BUFFER;
        break;
    case 0x80: /* SET_STANDBY */
    case 0x84: /* SET_SLEEP */
    case 0x82: /* SET_RX */
    case 0x83: /* SET_TX */
    case 0x86: /* SET_RF_FREQUENCY */
    case 0x89: /* CALIBRATE */
    case 0x8a: /* SET_PACKET_TYPE */
    case 0x8b: /* SET_MODULATION_PARAMS */
    case 0x8c: /* SET_PACKET_PARAMS */
    case 0x8e: /* SET_TX_PARAMS */
    case 0x8f: /* SET_BUFFER_BASE_ADDRESS */
    case 0x95: /* SET_PA_CONFIG */
    case 0x97: /* SET_DIO3_AS_TCXO_CTRL */
    case 0x98: /* CALIBRATE_IMAGE */
    case 0x9d: /* SET_DIO2_AS_RF_SWITCH_CTRL */
        if (s->opcode == 0x83) {
            memcpy(s->rx_packet, s->tx_packet, s->tx_len);
            s->rx_len = s->tx_len;
            s->irq_status = 1; /* TX_DONE */
        } else if (s->opcode == 0x82 && s->rx_len) {
            s->irq_status = 2; /* RX_DONE */
        }
        s->mode = SX_IDLE;
        break;
    case 0xc0: /* GET_STATUS */
        response[0] = sx1262_status();
        sx1262_set_response(s, response, 1);
        break;
    default:
        s->mode = SX_IDLE;
        break;
    }
}

static uint8_t sx1262_transfer(void *opaque, uint8_t tx)
{
    M5Sx1262State *s = opaque;
    if (getenv("M5SW_SX1262_TRACE")) {
        fprintf(stderr, "[sx1262] mode=%d tx=%02x\n", s->mode, tx);
    }

    switch (s->mode) {
    case SX_IDLE:
        s->opcode = tx;
        s->arg_count = 0;
        s->expected_args = 0;
        s->response_pos = 0;
        s->response_len = 0;
        switch (tx) {
        case 0x02: s->expected_args = 2; break;
        case 0x07: s->expected_args = 1; break;
        case 0x08: s->expected_args = 8; break;
        case 0x0d: s->expected_args = 3; break;
        case 0x0e: s->expected_args = 1; break;
        case 0x1d: s->expected_args = 3; break;
        case 0x1e: s->expected_args = 1; break;
        case 0x80: s->expected_args = 1; break;
        case 0x82: s->expected_args = 3; break;
        case 0x83: s->expected_args = 3; break;
        case 0x84: s->expected_args = 1; break;
        case 0x86: s->expected_args = 4; break;
        case 0x89: s->expected_args = 1; break;
        case 0x8a: s->expected_args = 1; break;
        case 0x8b: s->expected_args = 4; break;
        case 0x8c: s->expected_args = 6; break;
        case 0x8e: s->expected_args = 2; break;
        case 0x8f: s->expected_args = 2; break;
        case 0x95: s->expected_args = 4; break;
        case 0x97: s->expected_args = 4; break;
        case 0x98: s->expected_args = 2; break;
        case 0x9d: s->expected_args = 1; break;
        default: break;
        }
        if (s->expected_args == 0) {
            sx1262_command(s);
        } else {
            s->mode = SX_ARGS;
        }
        return sx1262_status();
    case SX_ARGS:
        if (s->arg_count < sizeof(s->args)) {
            s->args[s->arg_count] = tx;
        }
        s->arg_count++;
        if (s->arg_count >= s->expected_args) {
            sx1262_command(s);
        }
        return sx1262_status();
    case SX_RESPONSE:
        if (s->response_pos < s->response_len) {
            return s->response[s->response_pos++];
        }
        return sx1262_status();
    case SX_WRITE_BUFFER:
        if (s->tx_len < SX1262_MAX_PACKET) {
            s->tx_packet[s->tx_len++] = tx;
        }
        return sx1262_status();
    case SX_READ_BUFFER:
        if (!s->response_pos) {
            s->response_pos++;
            return sx1262_status();
        }
        if (s->rx_pos < s->rx_len) {
            return s->rx_packet[s->rx_pos++];
        }
        return 0;
    default:
        return sx1262_status();
    }
}

static void sx1262_set_cs(void *opaque, int level)
{
    M5Sx1262State *s = opaque;
    if (level) {
        s->mode = SX_IDLE;
        s->response_pos = 0;
        s->response_len = 0;
    }
}

static const M5SpiSlaveOps sx1262_ops = {
    .set_cs = sx1262_set_cs,
    .transfer = sx1262_transfer,
};

void m5_sx1262_attach(DeviceState *spi, int cs_pin)
{
    M5Sx1262State *s = g_new0(M5Sx1262State, 1);
    s->ops = &sx1262_ops;
    esp32s3_gpspi_attach_spi_slave(spi, &sx1262_ops, s, cs_pin);
    esp32_gpio_set_input(21, 0); /* SX_BUSY: command processor ready */
    esp32_gpio_force_line(21, 0);
    esp32_gpio_set_input(5, 0);  /* DIO1 idle */
}

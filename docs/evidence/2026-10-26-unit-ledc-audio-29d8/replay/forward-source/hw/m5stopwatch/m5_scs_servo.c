/*
 * Minimal SCS serial servo bus peer for StackChan.
 *
 * The guest UART bytes are parsed as SCSCL packets. Servo ID 1/2 expose the
 * EEPROM/SRAM fields used by the UIFlow2 driver, including position, torque,
 * voltage, current and PWM-mode angle limits.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/char/esp32_uart.h"
#include "m5stopwatch.h"

#define SCS_MAX_PACKET 256
#define SCS_MEM_SIZE 71
#define SCS_ID_X 1
#define SCS_ID_Y 2

typedef struct M5ScsServoState {
    ESP32UARTState *uart;
    uint8_t packet[SCS_MAX_PACKET];
    uint16_t packet_len;
    uint8_t mem[3][SCS_MEM_SIZE];
} M5ScsServoState;

static void scs_put_be16(uint8_t *mem, int addr, uint16_t value)
{
    mem[addr] = value >> 8;
    mem[addr + 1] = value;
}

static uint16_t scs_get_be16(const uint8_t *mem, int addr)
{
    return ((uint16_t)mem[addr] << 8) | mem[addr + 1];
}

static void scs_init_mem(M5ScsServoState *s)
{
    for (int id = SCS_ID_X; id <= SCS_ID_Y; id++) {
        uint8_t *m = s->mem[id];
        memset(m, 0, SCS_MEM_SIZE);
        m[3] = 0x01;                         /* version low */
        m[4] = 0x01;                         /* version high */
        m[5] = id;
        m[6] = 1;                            /* baud-rate selector */
        scs_put_be16(m, 9, 0);               /* min angle limit */
        scs_put_be16(m, 11, 1000);           /* max angle limit */
        m[40] = 0;                           /* torque disabled */
        scs_put_be16(m, 42, id == SCS_ID_X ? 450 : 125);
        scs_put_be16(m, 56, id == SCS_ID_X ? 450 : 125);
        m[62] = 120;                         /* 12.0 V */
        m[63] = 35;                          /* 35 C */
        m[66] = 0;
        scs_put_be16(m, 69, 0);
    }
}

static void scs_send(M5ScsServoState *s, uint8_t id, uint8_t error,
                     const uint8_t *data, uint8_t data_len)
{
    uint8_t out[SCS_MAX_PACKET];
    uint8_t len = data_len + 2;
    uint8_t sum = 0;
    int pos = 0;

    out[pos++] = 0xff;
    out[pos++] = 0xff;
    out[pos++] = id;
    out[pos++] = len;
    out[pos++] = error;
    sum = id + len + error;
    for (int i = 0; i < data_len; i++) {
        out[pos++] = data[i];
        sum += data[i];
    }
    out[pos++] = ~sum;
    if (getenv("M5SW_SCS_TRACE")) {
        fprintf(stderr, "[scs] response id=%u err=%u len=%u\n",
                id, error, data_len);
    }
    esp32_uart_inject_rx(s->uart, out, pos);
}

static uint8_t *scs_mem_for(M5ScsServoState *s, uint8_t id)
{
    if (id != SCS_ID_X && id != SCS_ID_Y) {
        return NULL;
    }
    return s->mem[id];
}

static void scs_handle_packet(M5ScsServoState *s)
{
    uint8_t id = s->packet[2];
    uint8_t len = s->packet[3];
    uint8_t inst = s->packet[4];
    uint8_t addr = s->packet[5];
    uint8_t data_len;
    uint8_t *mem = scs_mem_for(s, id);

    if (getenv("M5SW_SCS_TRACE")) {
        fprintf(stderr, "[scs] packet id=%u inst=%02x len=%u addr=%u\n",
                id, inst, len, addr);
    }

    if (inst == 0x01) { /* PING */
        if (id != 0xfe) {
            scs_send(s, id, 0, NULL, 0);
        }
        return;
    }
    if (inst == 0x02) { /* READ */
        uint8_t response[SCS_MEM_SIZE];
        data_len = s->packet[6];
        if (!mem || data_len > sizeof(response) || addr + data_len > SCS_MEM_SIZE) {
            return;
        }
        memcpy(response, mem + addr, data_len);
        scs_send(s, id, 0, response, data_len);
        return;
    }
    if (inst == 0x03 || inst == 0x04) { /* WRITE / REG_WRITE */
        data_len = len - 3;
        if (mem && data_len && addr + data_len <= SCS_MEM_SIZE) {
            memcpy(mem + addr, s->packet + 6, data_len);
            if (addr <= 43 && addr + data_len > 42) {
                scs_put_be16(mem, 56, scs_get_be16(mem, 42));
            }
            if (id != 0xfe) {
                scs_send(s, id, 0, NULL, 0);
            }
        }
        return;
    }
    if (inst == 0x05) { /* REG_ACTION */
        return;
    }
    if (inst == 0x83) { /* SYNC_WRITE */
        data_len = s->packet[6];
        int count = (len - 4) / (data_len + 1);
        int pos = 7;
        for (int i = 0; i < count; i++) {
            uint8_t sid = s->packet[pos++];
            uint8_t *sm = scs_mem_for(s, sid);
            if (sm && data_len && addr + data_len <= SCS_MEM_SIZE) {
                memcpy(sm + addr, s->packet + pos, data_len);
                if (addr <= 43 && addr + data_len > 42) {
                    scs_put_be16(sm, 56, scs_get_be16(sm, 42));
                }
            }
            pos += data_len;
        }
    }
}

static void scs_uart_byte(void *opaque, uint8_t byte)
{
    M5ScsServoState *s = opaque;

    if (s->packet_len < sizeof(s->packet)) {
        s->packet[s->packet_len++] = byte;
    } else {
        s->packet_len = 0;
        return;
    }

    if (s->packet_len == 1 && s->packet[0] != 0xff) {
        s->packet_len = 0;
        return;
    }
    if (s->packet_len == 2 && s->packet[1] != 0xff) {
        s->packet_len = s->packet[1] == 0xff ? 1 : 0;
        return;
    }
    if (s->packet_len < 4) {
        return;
    }

    uint8_t payload_len = s->packet[3];
    uint16_t total = payload_len + 4;
    if (payload_len < 2 || total > sizeof(s->packet)) {
        s->packet_len = 0;
        return;
    }
    if (s->packet_len < total) {
        return;
    }

    uint8_t sum = 0;
    for (int i = 2; i < total - 1; i++) {
        sum += s->packet[i];
    }
    if ((uint8_t)~sum == s->packet[total - 1]) {
        scs_handle_packet(s);
    }
    s->packet_len = 0;
}

void m5_scs_servo_attach(DeviceState *uart)
{
    M5ScsServoState *s = g_new0(M5ScsServoState, 1);
    s->uart = ESP32_UART(uart);
    scs_init_mem(s);
    esp32_uart_set_tx_byte_callback(s->uart, scs_uart_byte, s);
}

/*
 * Software-I2C bridge for the M5Stack StopWatch board.
 *
 * M5GFX identifies the StopWatch before it opens the hardware I2C
 * controller.  Its autodetect path bit-bangs SDA/SCL on GPIO47/GPIO48
 * (probe_i2c_port == -1) and only hands the pins over to the ESP32-S3
 * I2C1 controller after the board has been identified.
 *
 * QEMU's GPIO model only tracks pin levels; it does not connect a
 * bit-banged bus to the I2C device models.  Without this bridge the
 * autodetect probes all miss, M5GFX never selects board_M5StopWatch,
 * and the AMOLED power/reset sequence is never run.
 *
 * This module decodes the GPIO-level I2C waveform and forwards complete
 * bytes to the real QEMU I2CBus, so the existing M5PM1/M5IOE1/RX8130/
 * BMI270/CST820 models answer the probe exactly as they do on hardware.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/i2c/i2c.h"
#include "m5stopwatch.h"

typedef enum {
    SOFT_I2C_IDLE,
    SOFT_I2C_ADDR,
    SOFT_I2C_TX,
    SOFT_I2C_RX,
    SOFT_I2C_ACK_ADDR,
    SOFT_I2C_ACK_TX,
    SOFT_I2C_ACK_RX,
} SoftI2CState;

typedef struct M5StopwatchSoftI2C {
    I2CBus *bus;
    bool hardware_active;
    struct M5StopwatchSoftI2C *next;
    int sda_pin;
    int scl_pin;
    int sda;
    int scl;
    bool active;
    bool in_xfer;
    bool read;
    SoftI2CState state;
    bool ack_pending;
    bool master_ack;
    unsigned ack_step;
    unsigned bit;
    uint8_t shift;
    uint8_t rx;
} M5StopwatchSoftI2C;

static M5StopwatchSoftI2C *soft_i2c_instance;

static void soft_i2c_trace(const char *fmt, ...)
{
    va_list ap;

    if (!getenv("M5SW_SOFT_I2C_TRACE")) {
        return;
    }
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

static void soft_i2c_release_sda(M5StopwatchSoftI2C *s)
{
    esp32_gpio_set_input(s->sda_pin, 1);
    s->sda = esp32_gpio_get_line(s->sda_pin);
}

static void soft_i2c_drive_sda(M5StopwatchSoftI2C *s, int level)
{
    esp32_gpio_set_input(s->sda_pin, level ? 1 : 0);
    s->sda = esp32_gpio_get_line(s->sda_pin);
}

static void soft_i2c_end(M5StopwatchSoftI2C *s)
{
    if (s->in_xfer) {
        soft_i2c_trace("[soft-i2c] end\n");
        i2c_end_transfer(s->bus);
        s->in_xfer = false;
    }
    soft_i2c_release_sda(s);
}

static void soft_i2c_line(void *opaque, int pin, int level)
{
    M5StopwatchSoftI2C *s = opaque;
    int old_sda = s->sda;
    int old_scl = s->scl;

    /*
     * M5GFX first bit-bangs the bus to identify the board, then hands the
     * same pins to the ESP32-S3 I2C controller.  Keep decoding only through
     * the hand-off: otherwise every hardware waveform is mirrored into the
     * same QEMU I2CBus and corrupts the controller transaction.
     */
    if (s->hardware_active) {
        if (pin == s->sda_pin) {
            s->sda = level;
        } else if (pin == s->scl_pin) {
            s->scl = level;
        }
        return;
    }

    if (pin == s->sda_pin) {
        s->sda = level;
    } else if (pin == s->scl_pin) {
        s->scl = level;
    } else {
        return;
    }
    soft_i2c_trace("[soft-i2c] %s=%d sda=%d scl=%d\n",
                   pin == s->sda_pin ? "sda" : "scl",
                   level, s->sda, s->scl);

    /* START: SDA falls while SCL is high. */
    if (old_scl && old_sda && !s->sda && s->scl) {
        soft_i2c_end(s);
        s->active = true;
        s->state = SOFT_I2C_ADDR;
        s->bit = 0;
        s->shift = 0;
        s->ack_step = false;
        soft_i2c_release_sda(s);
        return;
    }

    /* STOP: SDA rises while SCL is high. */
    if (old_scl && !old_sda && s->sda && s->scl) {
        soft_i2c_end(s);
        s->active = false;
        s->state = SOFT_I2C_IDLE;
        return;
    }

    if (!s->active) {
        return;
    }

    if (!old_scl && s->scl) {
        /* Rising edge: master samples SDA. */
        switch (s->state) {
        case SOFT_I2C_ADDR:
        case SOFT_I2C_TX:
            s->shift = (s->shift << 1) | (s->sda ? 1 : 0);
            if (++s->bit == 8) {
                if (s->state == SOFT_I2C_ADDR) {
                    uint8_t addr = s->shift >> 1;
                    s->read = s->shift & 1;
                    soft_i2c_trace("[soft-i2c] addr=%02x read=%d\n",
                                   addr, s->read);
                    s->in_xfer = (i2c_start_transfer(s->bus, addr,
                                                     s->read) == 0);
                    soft_i2c_trace("[soft-i2c] start-transfer=%d\n",
                                   s->in_xfer);
                    s->ack_pending = s->in_xfer;
                    s->ack_step = false;
                    soft_i2c_release_sda(s);
                    s->state = SOFT_I2C_ACK_ADDR;
                } else {
                    bool ack = s->in_xfer &&
                               i2c_send(s->bus, s->shift) == 0;
                    soft_i2c_trace("[soft-i2c] tx=%02x ack=%d\n",
                                   s->shift, ack);
                    s->ack_pending = ack;
                    s->ack_step = false;
                    soft_i2c_release_sda(s);
                    s->state = SOFT_I2C_ACK_TX;
                }
                s->bit = 0;
            }
            break;
        case SOFT_I2C_RX:
            s->shift = (s->shift << 1) | (s->sda ? 1 : 0);
            if (++s->bit == 8) {
                s->state = SOFT_I2C_ACK_RX;
                s->ack_step = false;
            }
            break;
        case SOFT_I2C_ACK_RX:
            /* Ninth clock: sample the master's ACK/NACK. */
            if (s->ack_step == 1) {
                s->master_ack = s->sda;
                s->ack_step = 2;
                s->bit = 0;
            }
            break;
        default:
            break;
        }
        return;
    }

    if (old_scl && !s->scl) {
        /* Falling edge: slave changes SDA for the next bit / ACK phase. */
        switch (s->state) {
        case SOFT_I2C_ACK_ADDR:
            if (!s->ack_step) {
                /* First falling edge after the address: drive ACK/NACK. */
                soft_i2c_drive_sda(s, s->ack_pending ? 0 : 1);
                s->ack_step = true;
            } else {
                /* Falling edge of the ACK clock: enter data phase. */
                soft_i2c_release_sda(s);
                if (s->read) {
                    s->rx = s->in_xfer ? i2c_recv(s->bus) : 0xff;
                    soft_i2c_trace("[soft-i2c] rx=%02x\n", s->rx);
                    s->state = SOFT_I2C_RX;
                    s->bit = 0;
                    soft_i2c_drive_sda(s, (s->rx >> 7) & 1);
                } else {
                    s->state = SOFT_I2C_TX;
                    s->bit = 0;
                }
            }
            break;
        case SOFT_I2C_ACK_TX:
            if (!s->ack_step) {
                soft_i2c_drive_sda(s, s->ack_pending ? 0 : 1);
                s->ack_step = true;
            } else {
                soft_i2c_release_sda(s);
                s->state = SOFT_I2C_TX;
                s->bit = 0;
            }
            break;
        case SOFT_I2C_RX:
            if (s->bit > 0 && s->bit < 8) {
                soft_i2c_drive_sda(s, (s->rx >> (7 - s->bit)) & 1);
            }
            break;
        case SOFT_I2C_ACK_RX:
            if (s->ack_step == 0) {
                /*
                 * The master has sampled the last data bit; release SDA
                 * only now so the final bit is not lost on the rising
                 * edge.  The master drives ACK/NACK on this phase.
                 */
                soft_i2c_release_sda(s);
                s->ack_step = 1;
                break;
            }
            if (s->ack_step != 2) {
                break;
            }
            if (!s->master_ack && s->in_xfer) {
                s->rx = i2c_recv(s->bus);
                s->state = SOFT_I2C_RX;
                s->bit = 0;
                soft_i2c_drive_sda(s, (s->rx >> 7) & 1);
            } else {
                if (s->master_ack && s->in_xfer) {
                    i2c_nack(s->bus);
                }
                s->state = SOFT_I2C_IDLE;
            }
            break;
        default:
            break;
        }
    }
}

void m5stopwatch_soft_i2c_init_pins(I2CBus *bus, int sda_pin, int scl_pin)
{
    M5StopwatchSoftI2C *s = g_new0(M5StopwatchSoftI2C, 1);

    s->bus = bus;
    s->sda_pin = sda_pin;
    s->scl_pin = scl_pin;
    s->sda = 1;
    s->scl = 1;
    esp32_gpio_set_open_drain(sda_pin, true);
    esp32_gpio_set_open_drain(scl_pin, true);
    esp32_gpio_add_out_listener(sda_pin, soft_i2c_line, s);
    esp32_gpio_add_out_listener(scl_pin, soft_i2c_line, s);
    s->next = soft_i2c_instance;
    soft_i2c_instance = s;
}

void m5stopwatch_soft_i2c_init(I2CBus *bus)
{
    m5stopwatch_soft_i2c_init_pins(bus, 47, 48);
}

void m5stopwatch_soft_i2c_set_hardware_active_on_bus(I2CBus *bus)
{
    for (M5StopwatchSoftI2C *s = soft_i2c_instance; s; s = s->next) {
        if (s->bus == bus && !s->hardware_active) {
            i2c_end_transfer(s->bus);
            s->in_xfer = false;
            s->active = false;
            s->state = SOFT_I2C_IDLE;
            s->hardware_active = true;
        }
    }
}

void m5stopwatch_soft_i2c_set_hardware_active(void)
{
    for (M5StopwatchSoftI2C *s = soft_i2c_instance; s; s = s->next) {
        m5stopwatch_soft_i2c_set_hardware_active_on_bus(s->bus);
    }
}

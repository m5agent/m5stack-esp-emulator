/*
 * MAX3421E USB host controller model for the CoreS3 M-Bus.
 *
 * UIFlow2 exposes USB HID through a MAX3421E connected to the shared
 * CoreS3 M-Bus SPI.  The model implements the register/FIFO interface,
 * USB Chapter 9 enumeration and one interrupt-IN HID mouse endpoint.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/qdev-properties.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "qom/object.h"
#include "m5stopwatch.h"

#define TYPE_M5_MAX3421E "m5.max3421e"
OBJECT_DECLARE_SIMPLE_TYPE(M5Max3421eState, M5_MAX3421E)

enum {
    R_RCVFIFO = 1,
    R_SNDFIFO = 2,
    R_SUDFIFO = 4,
    R_RCVBC = 6,
    R_SNDBC = 7,
    R_USBIRQ = 13,
    R_USBIEN = 14,
    R_USBCTL = 15,
    R_CPUCTL = 16,
    R_PINCTL = 17,
    R_REVISION = 18,
    R_IOPINS1 = 20,
    R_IOPINS2 = 21,
    R_GPINIRQ = 22,
    R_GPINIEN = 23,
    R_GPINPOL = 24,
    R_HIRQ = 25,
    R_HIEN = 26,
    R_MODE = 27,
    R_PERADDR = 28,
    R_HCTL = 29,
    R_HXFR = 30,
    R_HRSL = 31,
};

#define USBIRQ_OSCOKIRQ  BIT(0)
#define HIRQ_BUSEVENTIRQ BIT(0)
#define HIRQ_RWUIRQ      BIT(1)
#define HIRQ_RCVDAVIRQ   BIT(2)
#define HIRQ_SNDBAVIRQ   BIT(3)
#define HIRQ_SUSDNIRQ    BIT(4)
#define HIRQ_CONDETIRQ   BIT(5)
#define HIRQ_FRAMEIRQ    BIT(6)
#define HIRQ_HXFRDNIRQ   BIT(7)

#define USBCTL_CHIPRES   BIT(5)
#define HCTL_BUSRST      BIT(0)
#define HCTL_FRMRST      BIT(1)
#define HCTL_SAMPLEBUS   BIT(2)

#define TOK_SETUP  0x10
#define TOK_IN     0x00
#define TOK_OUT    0x20
#define TOK_INHS   0x80
#define TOK_OUTHS  0xA0

#define HRSL_JSTATUS 0x80
#define HRSL_KSTATUS 0x40
#define HRSL_NAK     0x04

#define MAX3421E_FIFO_SIZE 64

typedef struct M5Max3421eState {
    DeviceState parent_obj;
    M5SpiSlaveOps ops;
    int irq_pin;
    int cs_pin;
    uint8_t regs[32];
    uint8_t sudfifo[8];
    uint8_t sndfifo[MAX3421E_FIFO_SIZE];
    uint8_t rcvfifo[MAX3421E_FIFO_SIZE];
    uint8_t setup[8];
    uint8_t control_data[128];
    uint32_t control_len;
    uint32_t control_pos;
    uint32_t control_remaining;
    uint32_t snd_pos;
    uint32_t sud_pos;
    uint32_t rcv_pos;
    uint32_t rcv_len;
    uint32_t snd_len;
    uint32_t token_value;
    uint32_t current_reg;
    bool command_byte;
    bool write_byte;
    bool control_active;
    bool control_direction_in;
    bool control_status;
    bool configured;
    bool connected;
    int64_t mouse_x;
    int64_t mouse_y;
    int64_t mouse_buttons;
    int64_t enumerated;
    int64_t last_report;
} M5Max3421eState;

static const uint8_t max3421e_device_descriptor[18] = {
    18, 0x01, 0x00, 0x02, 0x00, 0x00, 0x00, 8,
    0x3a, 0x30, 0x01, 0x10, 0x00, 0x01,
    0x00, 0x00, 0x00, 0x01,
};

static const uint8_t max3421e_config_descriptor[] = {
    9, 0x02, 34, 0x00, 1, 1, 0, 0x80, 50,
    9, 0x04, 0, 0, 1, 0x03, 0x01, 0x02, 0,
    9, 0x21, 0x11, 0x01, 0x00, 1, 0x22, 52, 0,
    7, 0x05, 0x81, 0x03, 8, 0x00, 10,
};

static const uint8_t max3421e_mouse_report[] = {
    0x05, 0x01, 0x09, 0x02, 0xA1, 0x01, 0x09, 0x01, 0xA1, 0x00,
    0x05, 0x09, 0x19, 0x01, 0x29, 0x03, 0x15, 0x00, 0x25, 0x01,
    0x95, 0x03, 0x75, 0x01, 0x81, 0x02, 0x95, 0x01, 0x75, 0x05,
    0x81, 0x01, 0x05, 0x01, 0x09, 0x30, 0x09, 0x31, 0x15, 0x81,
    0x25, 0x7F, 0x75, 0x08, 0x95, 0x02, 0x81, 0x06, 0xC0, 0xC0,
};

static void max3421e_update_irq(M5Max3421eState *s)
{
    if (s->irq_pin >= 0) {
        esp32_gpio_force_line(
            s->irq_pin, (s->regs[R_HIRQ] & s->regs[R_HIEN]) ? 0 : 1);
    }
}

static void max3421e_set_cs(void *opaque, int level)
{
    M5Max3421eState *s = opaque;

    if (!level) {
        s->command_byte = true;
        s->current_reg = 0;
        s->rcv_pos = 0;
    }
}

static uint8_t max3421e_read_reg(M5Max3421eState *s, uint32_t reg)
{
    if (reg == R_RCVFIFO) {
        if (s->rcv_pos >= s->rcv_len) {
            return 0;
        }
        return s->rcvfifo[s->rcv_pos++];
    }
    if (reg == R_SNDFIFO || reg == R_SUDFIFO) {
        return 0;
    }
    if (reg == R_RCVBC) {
        return s->rcv_len;
    }
    if (reg == R_SNDBC) {
        return s->snd_len;
    }
    if (reg == R_HRSL) {
        return s->connected ? HRSL_JSTATUS : 0;
    }
    if (reg == R_USBIRQ) {
        return s->regs[R_USBIRQ] | USBIRQ_OSCOKIRQ;
    }
    return reg < ARRAY_SIZE(s->regs) ? s->regs[reg] : 0;
}

static void max3421e_prepare_control(M5Max3421eState *s)
{
    const uint8_t bm_request_type = s->setup[0];
    const uint8_t request = s->setup[1];
    const uint8_t value_hi = s->setup[3];
    const uint16_t length = s->setup[6] | ((uint16_t)s->setup[7] << 8);

    s->control_len = 0;
    s->control_pos = 0;
    s->control_remaining = 0;
    s->control_direction_in = !!(bm_request_type & 0x80);
    s->control_status = false;
    s->control_active = true;

    if (request == 0x06) {
        if (value_hi == 0x01) {
            s->control_len = sizeof(max3421e_device_descriptor);
            memcpy(s->control_data, max3421e_device_descriptor,
                   s->control_len);
        } else if (value_hi == 0x02) {
            s->control_len = sizeof(max3421e_config_descriptor);
            memcpy(s->control_data, max3421e_config_descriptor,
                   s->control_len);
        } else if (value_hi == 0x22) {
            s->control_len = sizeof(max3421e_mouse_report);
            memcpy(s->control_data, max3421e_mouse_report,
                   s->control_len);
        }
    } else if (request == 0x00) {
        s->control_len = 2;
        memset(s->control_data, 0, s->control_len);
    } else if (request == 0x08) {
        s->control_len = 1;
        s->control_data[0] = s->configured ? 1 : 0;
    }

    if (s->control_len > length) {
        s->control_len = length;
    }
    s->control_remaining = s->control_len;
    if (!s->control_remaining) {
        s->control_status = true;
    }
}

static void max3421e_fill_control(M5Max3421eState *s)
{
    uint32_t chunk;

    if (!s->control_active || !s->control_direction_in ||
        s->control_status || !s->control_remaining) {
        s->rcv_len = 0;
        return;
    }
    chunk = MIN(s->control_remaining, 8);
    memcpy(s->rcvfifo, s->control_data + s->control_pos, chunk);
    s->rcv_len = chunk;
    s->control_pos += chunk;
    s->control_remaining -= chunk;
    if (!s->control_remaining) {
        s->control_status = true;
    }
}

static void max3421e_fill_hid_report(M5Max3421eState *s)
{
    if (!s->connected || !s->configured ||
        (!s->mouse_buttons && !s->mouse_x && !s->mouse_y)) {
        s->rcv_len = 0;
        return;
    }
    s->rcvfifo[0] = s->mouse_buttons & 0xff;
    s->rcvfifo[1] = s->mouse_x & 0xff;
    s->rcvfifo[2] = s->mouse_y & 0xff;
    s->rcvfifo[3] = 0;
    s->rcv_len = 4;
    s->last_report = 1;
}

static void max3421e_process_token(M5Max3421eState *s, uint32_t value)
{
    const uint32_t token = value & 0xf0;
    const uint32_t ep = value & 0x0f;

    s->token_value = value;
    if (getenv("M5SW_MAX3421E_TRACE")) {
        fprintf(stderr, "[max3421e] token=%02x ep=%u setup=%02x/%02x/"
                "%02x%02x len=%u\n",
                token, ep, s->setup[0], s->setup[1],
                s->setup[3], s->setup[2],
                s->setup[6] | (s->setup[7] << 8));
    }
    s->regs[R_HIRQ] |= HIRQ_HXFRDNIRQ;
    s->regs[R_HRSL] = s->connected ? HRSL_JSTATUS : 0;

    if (token == TOK_SETUP) {
        memcpy(s->setup, s->sudfifo, sizeof(s->setup));
        s->sud_pos = 0;
        max3421e_prepare_control(s);
    } else if (token == TOK_IN || token == TOK_INHS) {
        if (s->control_active && s->control_direction_in &&
            !s->control_status) {
            max3421e_fill_control(s);
        } else if (s->control_active && s->control_status &&
                   !s->control_direction_in) {
            s->control_active = false;
            if (s->setup[1] == 0x09 && s->setup[2] == 1) {
                s->configured = true;
                s->enumerated = 1;
            }
            s->rcv_len = 0;
        } else if (!s->control_active && ep == 1) {
            max3421e_fill_hid_report(s);
        } else {
            s->rcv_len = 0;
        }
        if (s->rcv_len) {
            s->regs[R_HIRQ] |= HIRQ_RCVDAVIRQ;
        } else {
            s->regs[R_HIRQ] &= ~HIRQ_RCVDAVIRQ;
        }
    } else if (token == TOK_OUT || token == TOK_OUTHS) {
        if (s->control_active && s->control_status) {
            s->control_active = false;
            if (s->setup[1] == 0x09 && s->setup[2] == 1) {
                s->configured = true;
            }
        }
        s->snd_pos = 0;
    }
    max3421e_update_irq(s);
}

static void max3421e_write_reg(M5Max3421eState *s, uint32_t reg, uint8_t value)
{
    switch (reg) {
    case R_RCVFIFO:
        break;
    case R_SNDFIFO:
        if (s->snd_pos < sizeof(s->sndfifo)) {
            s->sndfifo[s->snd_pos++] = value;
        }
        break;
    case R_SUDFIFO:
        if (s->sud_pos >= sizeof(s->sudfifo)) {
            s->sud_pos = 0;
        }
        s->sudfifo[s->sud_pos++] = value;
        break;
    case R_SNDBC:
        s->snd_len = value;
        break;
    case R_RCVBC:
        break;
    case R_USBIRQ:
        s->regs[R_USBIRQ] &= ~value;
        break;
    case R_USBIEN:
    case R_CPUCTL:
    case R_PINCTL:
    case R_IOPINS1:
    case R_IOPINS2:
    case R_GPINIRQ:
    case R_GPINIEN:
    case R_GPINPOL:
    case R_PERADDR:
        s->regs[reg] = value;
        break;
    case R_USBCTL:
        if (value & USBCTL_CHIPRES) {
            s->regs[R_USBIRQ] = USBIRQ_OSCOKIRQ;
            s->regs[R_HIRQ] = HIRQ_CONDETIRQ;
            s->configured = false;
            s->control_active = false;
        }
        s->regs[reg] = value & ~USBCTL_CHIPRES;
        break;
    case R_HIRQ:
        s->regs[R_HIRQ] &= ~value;
        break;
    case R_HIEN:
        s->regs[R_HIEN] = value;
        break;
    case R_MODE:
        s->regs[R_MODE] = value;
        if ((value & 0x09) == 0x09) {
            s->regs[R_HIRQ] |= HIRQ_FRAMEIRQ;
        }
        break;
    case R_HCTL:
        if (value & HCTL_SAMPLEBUS) {
            s->regs[R_HRSL] = s->connected ? HRSL_JSTATUS : 0;
        }
        if (value & HCTL_BUSRST) {
            s->regs[R_HIRQ] |= HIRQ_BUSEVENTIRQ;
        }
        /* SAMPLEBUS is visible to the driver as a one-shot request bit. */
        s->regs[R_HCTL] = value & ~HCTL_BUSRST;
        break;
    case R_HXFR:
        max3421e_process_token(s, value);
        s->regs[R_HXFR] = 0;
        break;
    default:
        if (reg < ARRAY_SIZE(s->regs)) {
            s->regs[reg] = value;
        }
        break;
    }
    max3421e_update_irq(s);
}

static uint8_t max3421e_transfer(void *opaque, uint8_t tx)
{
    M5Max3421eState *s = opaque;
    uint8_t ret;

    if (s->command_byte) {
        const uint32_t command = tx;
        s->current_reg = (command >> 3) & 0x1f;
        s->write_byte = !!(command & 0x02);
        s->command_byte = false;
        if (s->current_reg == R_RCVFIFO) {
            s->rcv_pos = 0;
        }
        if (getenv("M5SW_MAX3421E_TRACE")) {
            fprintf(stderr, "[max3421e] cmd=%02x reg=%u %s\n", command,
                    s->current_reg, s->write_byte ? "wr" : "rd");
        }
        return 0;
    }
    if (s->write_byte) {
        if (getenv("M5SW_MAX3421E_TRACE")) {
            fprintf(stderr, "[max3421e] wr reg=%u val=%02x\n",
                    s->current_reg, tx);
        }
        max3421e_write_reg(s, s->current_reg, tx);
        return 0;
    }
    ret = max3421e_read_reg(s, s->current_reg);
    if (getenv("M5SW_MAX3421E_TRACE")) {
        fprintf(stderr, "[max3421e] rd reg=%u val=%02x\n",
                s->current_reg, ret);
    }
    return ret;
}

static void max3421e_reset(DeviceState *dev)
{
    M5Max3421eState *s = M5_MAX3421E(dev);

    memset(s->regs, 0, sizeof(s->regs));
    memset(s->sudfifo, 0, sizeof(s->sudfifo));
    memset(s->sndfifo, 0, sizeof(s->sndfifo));
    memset(s->rcvfifo, 0, sizeof(s->rcvfifo));
    memset(s->setup, 0, sizeof(s->setup));
    memset(s->control_data, 0, sizeof(s->control_data));
    s->regs[R_USBIRQ] = USBIRQ_OSCOKIRQ;
    s->regs[R_REVISION] = 0x13;
    s->regs[R_HIRQ] = HIRQ_CONDETIRQ;
    s->regs[R_HRSL] = HRSL_JSTATUS;
    s->regs[R_IOPINS2] = 0xf0;
    s->control_len = 0;
    s->control_pos = 0;
    s->control_remaining = 0;
    s->snd_pos = 0;
    s->sud_pos = 0;
    s->rcv_pos = 0;
    s->rcv_len = 0;
    s->snd_len = 0;
    s->token_value = 0;
    s->current_reg = 0;
    s->command_byte = true;
    s->write_byte = false;
    s->control_active = false;
    s->control_direction_in = false;
    s->control_status = false;
    s->configured = false;
    s->enumerated = 0;
    s->last_report = 0;
    max3421e_update_irq(s);
}

static void max3421e_prop_get_i64(Object *obj, Visitor *v, const char *name,
                                  void *opaque, Error **errp)
{
    visit_type_int64(v, name, (int64_t *)opaque, errp);
}

static void max3421e_prop_set_i64(Object *obj, Visitor *v, const char *name,
                                  void *opaque, Error **errp)
{
    int64_t value;

    if (visit_type_int64(v, name, &value, errp)) {
        *(int64_t *)opaque = value;
    }
}

static void max3421e_init(Object *obj)
{
    M5Max3421eState *s = M5_MAX3421E(obj);

    s->irq_pin = -1;
    s->cs_pin = -1;
    s->connected = true;
    object_property_add(obj, "mouse-x", "int", max3421e_prop_get_i64,
                        max3421e_prop_set_i64, NULL, &s->mouse_x);
    object_property_add(obj, "mouse-y", "int", max3421e_prop_get_i64,
                        max3421e_prop_set_i64, NULL, &s->mouse_y);
    object_property_add(obj, "mouse-buttons", "int",
                        max3421e_prop_get_i64, max3421e_prop_set_i64,
                        NULL, &s->mouse_buttons);
    object_property_add(obj, "enumerated", "int",
                        max3421e_prop_get_i64, NULL, NULL, &s->enumerated);
    object_property_add(obj, "last-report", "int",
                        max3421e_prop_get_i64, NULL, NULL, &s->last_report);
}

static void max3421e_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, max3421e_reset);
}

static const TypeInfo max3421e_info = {
    .name = TYPE_M5_MAX3421E,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(M5Max3421eState),
    .instance_init = max3421e_init,
    .class_init = max3421e_class_init,
};

static M5SpiSlaveOps max3421e_ops = {
    .set_cs = max3421e_set_cs,
    .transfer = max3421e_transfer,
};

void m5_max3421e_attach(DeviceState *spi, int cs_pin, int irq_pin)
{
    DeviceState *dev = qdev_new(TYPE_M5_MAX3421E);
    M5Max3421eState *s;

    object_property_add_child(qdev_get_machine(), "max3421e-usb",
                              OBJECT(dev));
    qdev_realize(dev, NULL, &error_fatal);
    s = M5_MAX3421E(dev);
    s->irq_pin = irq_pin;
    s->cs_pin = cs_pin;
    s->ops = max3421e_ops;
    esp32s3_gpspi_attach_spi_slave(spi, &s->ops, s, cs_pin);
    esp32_gpio_set_input(irq_pin, 1);
    esp32_gpio_force_line(irq_pin, 1);
}

static void max3421e_register_types(void)
{
    type_register_static(&max3421e_info);
}

type_init(max3421e_register_types)

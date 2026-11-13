/*
 * Minimal I2C devices used by the Arduino Nesso N1 board.
 *
 * The board detector needs PI4IOE1/PI4IOE2 ACKs and the board's
 * FT5x06-compatible touch controller.  The models are deliberately
 * register-level rather than full peripheral emulations so firmware can
 * complete autodetection and UI input without a physical board.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include <math.h>
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "hw/i2c/i2c.h"
#include "hw/qdev-properties.h"
#include "hw/gpio/esp32_gpio.h"
#include "hw/misc/esp32c6_board_i2c.h"

enum {
    C6_DEV_GENERIC,
    C6_DEV_FT5X06,
    C6_DEV_PI4IOE,
    C6_DEV_BMI270,
    C6_DEV_BQ27220,
    C6_DEV_AW32001,
};

typedef struct C6BoardI2CDev {
    I2CSlave parent_obj;
    char *model_name;
    int model;
    uint8_t regs[256];
    uint8_t ptr;
    uint8_t read_start;
    bool ptr_set;
    uint8_t bq_write_count;
    uint16_t bq_subreg;
    int64_t battery_mv;
    int64_t battery_current_ma;
    int64_t battery_level;
    double accel[3];
    double gyro[3];
    bool charging;
} C6BoardI2CDev;

OBJECT_DECLARE_SIMPLE_TYPE(C6BoardI2CDev, ESP32C6_BOARD_I2C_DEV)

static C6BoardI2CDev *g_ft;
static int g_touch_pressed;
static int g_touch_x;
static int g_touch_y;
static uint8_t g_buttons = 0x03;
static C6BoardI2CDev *g_nesso_pi4ioe[2];
static C6BoardI2CDev *g_nesso_aw32001;

static uint8_t nesso_pi4ioe_input(C6BoardI2CDev *s)
{
    uint8_t external = (s == g_nesso_pi4ioe[0]) ? g_buttons : 0xff;
    return external & ~s->regs[0x03];
}

static void nesso_shared_irq_update(void)
{
    C6BoardI2CDev *buttons = g_nesso_pi4ioe[0];
    uint8_t pending = buttons ? buttons->regs[0x13] &
                               ~buttons->regs[0x11] &
                               ~buttons->regs[0x03] : 0;

    /* SYS_IRQ is an active-low, shared open-drain pad. The board's 0x44
     * expander is not wired here. BMI270 interrupt generation is unmodeled;
     * combine only the touch and button sources that actually exist. */
    esp32_gpio_force_line(3, !(g_touch_pressed || pending));
}

static void nesso_pi4ioe_update_irq(C6BoardI2CDev *s)
{
    if (s == g_nesso_pi4ioe[0]) {
        nesso_shared_irq_update();
    }
}

void esp32c6_ft_touch_set(int pressed, int x, int y)
{
    g_touch_pressed = pressed;
    g_touch_x = x;
    g_touch_y = y;
    if (g_ft) {
        g_ft->regs[0x02] = pressed ? 1 : 0;
        g_ft->regs[0x03] = (x >> 8) & 0x0f;
        g_ft->regs[0x04] = x & 0xff;
        g_ft->regs[0x05] = (y >> 8) & 0x0f;
        g_ft->regs[0x06] = y & 0xff;
    }
    nesso_shared_irq_update();
}

void esp32c6_pi4ioe_button_set(int button, bool pressed)
{
    uint8_t old;

    if (button < 0 || button > 1) {
        return;
    }
    old = g_buttons;
    if (pressed) {
        g_buttons &= ~(1u << button);
    } else {
        g_buttons |= 1u << button;
    }
    if (g_nesso_pi4ioe[0] && old != g_buttons) {
        C6BoardI2CDev *s = g_nesso_pi4ioe[0];
        /* DS40583: only an input's default-to-opposite transition latches
         * status. A read clears it; a held pin does not immediately relatch.
         * Masking suppresses the INT pad, not the status latch. */
        uint8_t edge = (old ^ g_buttons) & (g_buttons ^ s->regs[0x09]) &
                       ~s->regs[0x03];
        s->regs[0x13] |= edge;
        nesso_pi4ioe_update_irq(s);
    }
}

static uint8_t c6_i2c_read(C6BoardI2CDev *s, uint8_t reg)
{
    if (getenv("M5SW_C6_I2C_TRACE")) {
        fprintf(stderr, "[c6-i2c] read model=%d reg=%02x\n", s->model, reg);
    }
    if (s->model == C6_DEV_FT5X06) {
        switch (reg) {
        case 0x02:
            return g_touch_pressed ? 1 : 0;
        case 0x03:
            return (g_touch_x >> 8) & 0x0f;
        case 0x04:
            return g_touch_x & 0xff;
        case 0x05:
            return (g_touch_y >> 8) & 0x0f;
        case 0x06:
            return g_touch_y & 0xff;
        case 0xA3:
            return 0x51;
        case 0xA6:
            return 0x10;
        case 0xA8:
            return 0x11;
        default:
            break;
        }
    } else if (s->model == C6_DEV_PI4IOE) {
        if (reg == 0x01) {
            uint8_t value = s->regs[reg];
            s->regs[reg] &= ~0x02;
            return value;
        }
        if (reg == 0x0f) {
            return nesso_pi4ioe_input(s);
        }
        if (reg == 0x13) {
            uint8_t value = s->regs[reg];
            s->regs[reg] = 0;
            nesso_pi4ioe_update_irq(s);
            return value;
        }
    } else if (s->model == C6_DEV_BMI270) {
        if (reg >= 0x0c && reg <= 0x17) {
            int index = (reg - 0x0c) / 2;
            double value = index < 3
                ? s->accel[index] * 32768.0 / 8.0
                : s->gyro[index - 3] * 32768.0 / 2000.0;
            int32_t raw = (int32_t)lrint(value);
            raw = MAX(-32768, MIN(raw, 32767));
            return ((reg - 0x0c) & 1)
                ? ((uint16_t)raw >> 8) : ((uint16_t)raw & 0xff);
        }
        if (reg == 0x1d) {
            return 0xc0;                    /* ACC and GYR data ready */
        }
        if (reg == 0x21) {
            return s->regs[0x59] & 1 ? 1 : 0;
        }
        if (reg == 0x03) {
            return 0xc0;
        }
    } else if (s->model == C6_DEV_BQ27220) {
        if (s->read_start == 0x3e) {
            unsigned offset = reg - 0x3e;
            static const uint8_t device_type[4] = { 0x20, 0x00, 0x00, 0x00 };
            return offset < sizeof(device_type) ? device_type[offset] : 0;
        }
        if (reg == 0x08 || reg == 0x09) {
            uint16_t value = s->battery_mv;
            return reg == 0x08 ? value & 0xff : value >> 8;
        }
        if (reg == 0x14 || reg == 0x15) {
            uint16_t value = (int16_t)s->battery_current_ma;
            return reg == 0x14 ? value & 0xff : value >> 8;
        }
        if (reg == 0x2c || reg == 0x2d) {
            uint16_t value = s->battery_level;
            return reg == 0x2c ? value & 0xff : value >> 8;
        }
    } else if (s->model == C6_DEV_AW32001) {
        if (reg == 0x08) {
            return s->charging ? 0x10 : 0x00;
        }
    }
    return s->regs[reg];
}

static int c6_i2c_event(I2CSlave *i2c, enum i2c_event event)
{
    C6BoardI2CDev *s = (C6BoardI2CDev *)i2c;

    if (event == I2C_START_SEND) {
        s->ptr_set = false;
        s->bq_write_count = 0;
    } else if (event == I2C_START_RECV) {
        s->read_start = s->ptr;
    }
    return 0;
}

static uint8_t c6_i2c_recv(I2CSlave *i2c)
{
    C6BoardI2CDev *s = (C6BoardI2CDev *)i2c;
    uint8_t value;

    if (s->model == C6_DEV_BQ27220 && s->read_start == 0x3e
        && s->ptr < 0x40) {
        value = c6_i2c_read(s, s->ptr++);
        return value;
    }
    value = c6_i2c_read(s, s->ptr++);
    return value;
}

static int c6_i2c_send(I2CSlave *i2c, uint8_t data)
{
    C6BoardI2CDev *s = (C6BoardI2CDev *)i2c;

    if (s->model == C6_DEV_BQ27220) {
        if (s->bq_write_count == 0) {
            s->ptr = data;
            s->ptr_set = true;
            if (data != 0x3e) {
                s->bq_subreg = 0;
            }
        } else if (s->bq_write_count == 1) {
            s->bq_subreg = data;
        } else if (s->bq_write_count == 2) {
            s->bq_subreg |= data << 8;
        }
        s->bq_write_count++;
        return 0;
    }
    if (!s->ptr_set) {
        s->ptr = data;
        s->ptr_set = true;
        return 0;
    }
    if (getenv("M5SW_C6_I2C_TRACE")) {
        fprintf(stderr, "[c6-i2c] write model=%d reg=%02x data=%02x\n",
                s->model, s->ptr, data);
    }
    if (s->model == C6_DEV_BMI270) {
        if (s->ptr == 0x5e) {
            return 0;                       /* INIT_DATA burst */
        }
        if (s->ptr == 0x7e && data == 0xb6) {
            s->regs[0x7c] = 0x03;
            s->ptr++;
            return 0;
        }
    }
    if (s->model == C6_DEV_PI4IOE && s->ptr == 0x01 && (data & BIT(0))) {
        memset(s->regs, 0, sizeof(s->regs));
        s->regs[0x01] = 0xa2;
        s->regs[0x07] = 0xff;
        s->regs[0x0b] = 0xff;
        s->ptr++;
        nesso_pi4ioe_update_irq(s);
        return 0;
    }
    if (s->model == C6_DEV_PI4IOE && (s->ptr == 0x0f || s->ptr == 0x13)) {
        s->ptr++;
        return 0;
    }
    uint8_t reg = s->ptr;
    s->regs[s->ptr++] = data;
    if (s->model == C6_DEV_PI4IOE &&
        (reg == 0x03 || reg == 0x09 || reg == 0x11)) {
        /* Configuration writes do not invent external input edges. Keep an
         * existing status latched until read/reset; direction and mask gate
         * the shared pad independently of that latch. */
        nesso_pi4ioe_update_irq(s);
    }
    return 0;
}

static void c6_prop_get_i64(Object *o, Visitor *v, const char *name,
                            void *op, Error **errp)
{
    visit_type_int64(v, name, (int64_t *)op, errp);
}

static void c6_prop_get_num(Object *o, Visitor *v, const char *name,
                            void *op, Error **errp)
{
    visit_type_number(v, name, (double *)op, errp);
}

static void c6_prop_set_num(Object *o, Visitor *v, const char *name,
                            void *op, Error **errp)
{
    double value;

    if (visit_type_number(v, name, &value, errp)) {
        *(double *)op = value;
    }
}

static void c6_prop_set_i64(Object *o, Visitor *v, const char *name,
                            void *op, Error **errp)
{
    int64_t value;

    if (visit_type_int64(v, name, &value, errp)) {
        *(int64_t *)op = value;
    }
}

static void c6_prop_get_bool(Object *o, Visitor *v, const char *name,
                             void *op, Error **errp)
{
    visit_type_bool(v, name, (bool *)op, errp);
}

static void c6_prop_set_bool(Object *o, Visitor *v, const char *name,
                             void *op, Error **errp)
{
    bool value;

    if (visit_type_bool(v, name, &value, errp)) {
        *(bool *)op = value;
    }
}

static void c6_i2c_realize(DeviceState *dev, Error **errp)
{
    C6BoardI2CDev *s = (C6BoardI2CDev *)dev;
    const char *model = s->model_name ? s->model_name : "generic";

    s->model = C6_DEV_GENERIC;
    if (!strcmp(model, "ft5x06")) {
        s->model = C6_DEV_FT5X06;
        g_ft = s;
    } else if (!strcmp(model, "pi4ioe")) {
        s->model = C6_DEV_PI4IOE;
        s->regs[0x01] = 0xa2;
        s->regs[0x07] = 0xff;
        s->regs[0x0b] = 0xff;
        if (s->parent_obj.address == 0x43) {
            g_nesso_pi4ioe[0] = s;
            nesso_shared_irq_update();
        } else if (s->parent_obj.address == 0x44) {
            g_nesso_pi4ioe[1] = s;
        }
    } else if (!strcmp(model, "bmi270")) {
        static const char *accel_names[] = {
            "accel-x", "accel-y", "accel-z"
        };
        static const char *gyro_names[] = {
            "gyro-x", "gyro-y", "gyro-z"
        };

        s->model = C6_DEV_BMI270;
        s->regs[0x00] = 0x24;
        s->regs[0x03] = 0xc0;
        s->regs[0x7c] = 0x03;
        s->regs[0x1d] = 0xc0;
        s->accel[2] = 1.0;
        for (int i = 0; i < 3; i++) {
            object_property_add(OBJECT(s), accel_names[i], "number",
                                c6_prop_get_num, c6_prop_set_num,
                                NULL, &s->accel[i]);
            object_property_add(OBJECT(s), gyro_names[i], "number",
                                c6_prop_get_num, c6_prop_set_num,
                                NULL, &s->gyro[i]);
        }
    } else if (!strcmp(model, "bq27220")) {
        s->model = C6_DEV_BQ27220;
        s->battery_mv = 4000;
        s->battery_current_ma = 250;
        s->battery_level = 87;
        object_property_add(OBJECT(s), "battery-mv", "int", c6_prop_get_i64,
                            c6_prop_set_i64, NULL, &s->battery_mv);
        object_property_add(OBJECT(s), "current-ma", "int", c6_prop_get_i64,
                            c6_prop_set_i64, NULL, &s->battery_current_ma);
        object_property_add(OBJECT(s), "battery-level", "int", c6_prop_get_i64,
                            c6_prop_set_i64, NULL, &s->battery_level);
    } else if (!strcmp(model, "aw32001")) {
        s->model = C6_DEV_AW32001;
        s->regs[0x01] = 0;
        s->regs[0x02] = 11;                         /* 100 mA */
        s->regs[0x04] = 39;                         /* 4200 mV */
        s->regs[0x0a] = 0x49;
        s->charging = true;
        object_property_add(OBJECT(s), "charging", "bool", c6_prop_get_bool,
                            c6_prop_set_bool, NULL, &s->charging);
        g_nesso_aw32001 = s;
    }
}

static Property c6_i2c_props[] = {
    DEFINE_PROP_STRING("model", C6BoardI2CDev, model_name),
    DEFINE_PROP_END_OF_LIST(),
};

static void c6_i2c_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    I2CSlaveClass *k = I2C_SLAVE_CLASS(klass);

    dc->realize = c6_i2c_realize;
    device_class_set_props(dc, c6_i2c_props);
    k->event = c6_i2c_event;
    k->recv = c6_i2c_recv;
    k->send = c6_i2c_send;
}

static const TypeInfo c6_i2c_info = {
    .name = TYPE_ESP32C6_BOARD_I2C_DEV,
    .parent = TYPE_I2C_SLAVE,
    .instance_size = sizeof(C6BoardI2CDev),
    .class_init = c6_i2c_class_init,
};

static void c6_i2c_register_types(void)
{
    type_register_static(&c6_i2c_info);
}

type_init(c6_i2c_register_types)

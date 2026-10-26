/*
 * Generic M5Stack e-paper display sink.
 *
 * Supports the two controller families used by the ESP32-S3 Paper devices:
 *  - SSD1677 4-gray: RAM command 0x24/0x26 carry 1-bit LSB/MSB planes;
 *  - ED2208 Spectra 6: command 0x10 carries packed 4-bit color indices.
 *
 * The model exposes the post-refresh optical image through a QEMU console.
 * It intentionally ignores waveform timing and renders the requested target
 * image when the controller is activated.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/qdev-core.h"
#include "hw/qdev-properties.h"
#include "ui/console.h"
#include "ui/input.h"
#include "m5stopwatch.h"

struct M5EpdPanelState {
    DeviceState parent_obj;
    QemuConsole *con;
    uint8_t *lsb;
    uint8_t *msb;
    uint8_t *packed;
    uint32_t native_w, native_h;
    uint32_t out_w, out_h;
    uint32_t plane_size;
    uint32_t packed_size;
    bool color;
    bool rotate;
    bool dirty;
    bool touch;
    uint32_t touch_int_pin;
    uint32_t busy_pin;
    bool busy_ready_level;
    uint32_t key_a_pin, key_b_pin, key_c_pin;
    int mouse_x, mouse_y;
    bool mouse_btn;
    uint8_t cmd;
    uint32_t data_index;
};

static uint32_t epd_pixel(M5EpdPanelState *s, uint32_t x, uint32_t y)
{
    uint32_t idx;
    uint8_t v;

    if (s->color) {
        idx = y * (s->native_w / 2) + x / 2;
        if (idx >= s->packed_size) {
            return 0xffffffffu;
        }
        v = s->packed[idx];
        v = (x & 1) ? (v & 0x0f) : (v >> 4);
        switch (v) {
        case 0x0: return 0xff000000u; /* black */
        case 0x1: return 0xffffffffu; /* white */
        case 0x2: return 0xfffff338u; /* yellow */
        case 0x3: return 0xffbf0000u; /* red */
        case 0x5: return 0xff6440ffu; /* blue */
        case 0x6: return 0xff438a1cu; /* green */
        default:  return 0xffffffffu;
        }
    }

    idx = y * ((s->native_w + 7) >> 3) + (x >> 3);
    if (idx >= s->plane_size) {
        return 0xffffffffu;
    }
    uint8_t mask = 0x80u >> (x & 7);
    /* M5GFX sends the SSD1677 planes inverted on the wire. */
    uint8_t l = !(s->lsb[idx] & mask);
    uint8_t m = !(s->msb[idx] & mask);
    switch ((m << 1) | l) {
    case 0: return 0xff000000u;
    case 1: return 0xff505050u;
    case 2: return 0xffb0b0b0u;
    default: return 0xffffffffu;
    }
}

static void m5_epd_update(void *opaque)
{
    M5EpdPanelState *s = opaque;
    DisplaySurface *surf = qemu_console_surface(s->con);

    if (!surf || surface_bits_per_pixel(surf) != 32 ||
        surface_width(surf) != s->out_w || surface_height(surf) != s->out_h) {
        surf = qemu_create_displaysurface(s->out_w, s->out_h);
        dpy_gfx_replace_surface(s->con, surf);
        s->dirty = true;
    }
    if (!s->dirty) {
        return;
    }
    s->dirty = false;
    uint32_t *dst = (uint32_t *)surface_data(surf);
    int stride = surface_stride(surf) / 4;
    for (uint32_t y = 0; y < s->out_h; y++) {
        uint32_t *d = dst + y * stride;
        for (uint32_t x = 0; x < s->out_w; x++) {
            uint32_t sx = x, sy = y;
            if (s->rotate) {
                sx = y;
                sy = s->native_h - 1 - x;
            }
            d[x] = epd_pixel(s, sx, sy);
        }
    }
    dpy_gfx_update(s->con, 0, 0, s->out_w, s->out_h);
}

static void m5_epd_invalidate(void *opaque)
{
    ((M5EpdPanelState *)opaque)->dirty = true;
}

static const GraphicHwOps m5_epd_ops = {
    .invalidate = m5_epd_invalidate,
    .gfx_update = m5_epd_update,
};

void m5_epd_panel_write(M5EpdPanelState *s, const uint8_t *buf, uint32_t len,
                        bool command_phase)
{
    for (uint32_t i = 0; i < len; i++) {
        uint8_t b = buf[i];
        if (command_phase) {
            s->cmd = b;
            if (b == 0x10 || b == 0x24 || b == 0x26) {
                s->data_index = 0;
            }
            if (b == 0x12 || b == 0x20) {
                s->dirty = true;
            }
            continue;
        }

        if (s->color && s->cmd == 0x10) {
            if (s->data_index < s->packed_size) {
                s->packed[s->data_index++] = b;
            }
            continue;
        }
        if (!s->color && s->cmd == 0x24) {
            if (s->data_index < s->plane_size) {
                s->lsb[s->data_index++] = b;
            }
            continue;
        }
        if (!s->color && s->cmd == 0x26) {
            if (s->data_index < s->plane_size) {
                s->msb[s->data_index++] = b;
            }
        }
    }
}

static void m5_epd_input(DeviceState *dev, QemuConsole *src, InputEvent *evt)
{
    M5EpdPanelState *s = M5_EPD_PANEL(dev);
    switch (evt->type) {
    case INPUT_EVENT_KIND_KEY: {
        InputKeyEvent *key = evt->u.key.data;
        int q = qemu_input_key_value_to_qcode(key->key);
        int down = key->down;
        if (getenv("M5SW_EPD_INPUT_TRACE")) {
            fprintf(stderr, "[m5epd-input] qcode=%d down=%d\n", q, down);
        }
        uint32_t pin = UINT32_MAX;
        if (q == Q_KEY_CODE_A || q == Q_KEY_CODE_1 || q == Q_KEY_CODE_LEFT) {
            pin = s->key_a_pin;
        } else if (q == Q_KEY_CODE_B || q == Q_KEY_CODE_2 || q == Q_KEY_CODE_RIGHT) {
            pin = s->key_b_pin;
        } else if (q == Q_KEY_CODE_C || q == Q_KEY_CODE_3) {
            pin = s->key_c_pin;
        } else if (q == Q_KEY_CODE_P) {
            m5sw_pwr_button(down);
            break;
        }
        if (pin != UINT32_MAX) {
            /*
             * Buttons are external mechanical pulls.  Force the line so an
             * output latch left enabled by the guest cannot mask a press.
             */
            esp32_gpio_force_line(pin, !down);
            if (getenv("M5SW_EPD_INPUT_TRACE")) {
                fprintf(stderr, "[m5epd-input] pin=%u level=%d line=%d\n",
                        pin, !down, esp32_gpio_get_line(pin));
            }
        }
        break;
    }
    case INPUT_EVENT_KIND_ABS: {
        InputMoveEvent *m = evt->u.abs.data;
        if (m->axis == INPUT_AXIS_X) {
            s->mouse_x = qemu_input_scale_axis(m->value, INPUT_EVENT_ABS_MIN,
                                               INPUT_EVENT_ABS_MAX, 0, s->out_w - 1);
        } else if (m->axis == INPUT_AXIS_Y) {
            s->mouse_y = qemu_input_scale_axis(m->value, INPUT_EVENT_ABS_MIN,
                                               INPUT_EVENT_ABS_MAX, 0, s->out_h - 1);
        }
        break;
    }
    case INPUT_EVENT_KIND_BTN: {
        InputBtnEvent *b = evt->u.btn.data;
        if (b->button == INPUT_BUTTON_LEFT) {
            s->mouse_btn = b->down;
        }
        break;
    }
    default:
        break;
    }
}

static void m5_epd_input_sync(DeviceState *dev)
{
    M5EpdPanelState *s = M5_EPD_PANEL(dev);
    if (s->touch) {
        m5sw_ft_touch_set_pin(s->mouse_btn, s->mouse_x, s->mouse_y,
                              s->touch_int_pin);
    }
}

static const QemuInputHandler m5_epd_input_handler = {
    .name = "M5Stack e-paper touch/keys",
    .mask = INPUT_EVENT_MASK_KEY | INPUT_EVENT_MASK_BTN | INPUT_EVENT_MASK_ABS,
    .event = m5_epd_input,
    .sync = m5_epd_input_sync,
};

static void m5_epd_realize(DeviceState *dev, Error **errp)
{
    M5EpdPanelState *s = M5_EPD_PANEL(dev);
    s->plane_size = ((s->native_w + 7) >> 3) * s->native_h;
    s->packed_size = s->native_w * s->native_h / 2;
    s->lsb = g_new0(uint8_t, s->plane_size);
    s->msb = g_new0(uint8_t, s->plane_size);
    s->packed = g_new0(uint8_t, s->packed_size);
    memset(s->packed, 0xff, s->packed_size);
    s->dirty = true;
    esp32_gpio_set_input(s->busy_pin, s->busy_ready_level);
    esp32_gpio_set_open_drain(s->busy_pin, true);
    esp32_gpio_force_line(s->busy_pin, s->busy_ready_level);
    if (s->key_a_pin != UINT32_MAX) {
        esp32_gpio_force_line(s->key_a_pin, 1);
    }
    if (s->key_b_pin != UINT32_MAX) {
        esp32_gpio_force_line(s->key_b_pin, 1);
    }
    if (s->key_c_pin != UINT32_MAX) {
        esp32_gpio_force_line(s->key_c_pin, 1);
    }
    s->con = graphic_console_init(dev, 0, &m5_epd_ops, s);
    qemu_console_resize(s->con, s->out_w, s->out_h);
    QemuInputHandlerState *hs = qemu_input_handler_register(dev, &m5_epd_input_handler);
    qemu_input_handler_activate(hs);
}

static Property m5_epd_props[] = {
    DEFINE_PROP_UINT32("native-width", M5EpdPanelState, native_w, 400),
    DEFINE_PROP_UINT32("native-height", M5EpdPanelState, native_h, 600),
    DEFINE_PROP_UINT32("out-width", M5EpdPanelState, out_w, 400),
    DEFINE_PROP_UINT32("out-height", M5EpdPanelState, out_h, 600),
    DEFINE_PROP_BOOL("color", M5EpdPanelState, color, true),
    DEFINE_PROP_BOOL("rotate", M5EpdPanelState, rotate, false),
    DEFINE_PROP_BOOL("touch", M5EpdPanelState, touch, false),
    DEFINE_PROP_UINT32("touch-int-pin", M5EpdPanelState, touch_int_pin, 4),
    DEFINE_PROP_UINT32("busy-pin", M5EpdPanelState, busy_pin, 18),
    DEFINE_PROP_BOOL("busy-ready-level", M5EpdPanelState, busy_ready_level, true),
    DEFINE_PROP_UINT32("key-a-pin", M5EpdPanelState, key_a_pin, 10),
    DEFINE_PROP_UINT32("key-b-pin", M5EpdPanelState, key_b_pin, 9),
    DEFINE_PROP_UINT32("key-c-pin", M5EpdPanelState, key_c_pin, 1),
    DEFINE_PROP_END_OF_LIST(),
};

static void m5_epd_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    dc->realize = m5_epd_realize;
    device_class_set_props(dc, m5_epd_props);
}

static const TypeInfo m5_epd_info = {
    .name = TYPE_M5_EPD_PANEL,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(M5EpdPanelState),
    .class_init = m5_epd_class_init,
};

static void m5_epd_register(void)
{
    type_register_static(&m5_epd_info);
}
type_init(m5_epd_register)

/*
 * Generic SPI display panel for M5Stack ESP32-S3 boards.
 *
 * The StopWatch uses a QSPI CO5300 panel.  StickS3/AtomS3R/CoreS3 use
 * ordinary SPI panels (ST7789/GC9107/ILI9342) with the command/data
 * distinction carried by the GP-SPI command and MOSI phases.
 *
 * This model implements the common MIPI-DCS command subset used by
 * M5GFX: CASET, RASET, RAMWR, MADCTL, COLMOD, sleep/display on/off and
 * inversion.  It keeps a controller-sized RGB565 framebuffer and exposes
 * the visible window (panel width/height with controller offsets) through
 * a QEMU console.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/main-loop.h"
#include "qapi/error.h"
#include "qemu/timer.h"
#include "hw/qdev-core.h"
#include "hw/qdev-properties.h"
#include "ui/console.h"
#include "ui/input.h"
#include "m5stopwatch.h"

static unsigned m5_panel_trace_count;

static void m5_panel_update(void *opaque);

struct M5SpiPanelState {
    DeviceState parent_obj;
    QemuConsole *con;
    QEMUTimer *refresh_timer;
    QEMUBH *refresh_bh;
    uint16_t *mem;
    uint32_t mem_w, mem_h;
    uint32_t vis_w, vis_h;
    uint32_t off_x, off_y;
    bool physical_invert;
    bool controller_invert;
    bool dirty;
    bool disp_on;
    bool sleep;
    uint8_t madctl;
    uint8_t colmod;
    uint8_t cmd;
    uint8_t params[4];
    unsigned pidx;
    uint16_t xs, xe, ys, ye, cx, cy;
    bool pixel_mode;
    uint8_t pix_hi;
    bool pix_half;
    uint32_t key_a_pin, key_b_pin;
    uint32_t read_id;
    uint32_t glass_rotation;
    bool apply_madctl;
    bool touch;
    uint32_t touch_int_pin;
    bool immediate_update;
    bool keyboard;
    bool plc_keys;
    bool infer_command;
    uint32_t infer_params_left;
    uint32_t pending_pixel_bytes;
    int mouse_x, mouse_y;
    bool mouse_btn;
    char *dump_path;
};

static bool m5_panel_is_dcs_command(uint8_t cmd)
{
    switch (cmd) {
    case 0x01:
    case 0x10:
    case 0x11:
    case 0x13:
    case 0x20:
    case 0x21:
    case 0x28:
    case 0x29:
    case 0x2A:
    case 0x2B:
    case 0x2C:
    case 0x36:
    case 0x3A:
    case 0xB1:
    case 0xB2:
    case 0xB3:
    case 0xB4:
    case 0xB6:
    case 0xC0:
    case 0xC1:
    case 0xC2:
    case 0xC3:
    case 0xC4:
    case 0xC5:
    case 0xE0:
    case 0xE1:
    case 0xFC:
        return true;
    default:
        return false;
    }
}

static uint32_t m5_panel_dcs_param_count(uint8_t cmd)
{
    switch (cmd) {
    case 0x2A:
    case 0x2B:
        return 4;
    case 0xB1:
    case 0xB2:
    case 0xC0:
        return 3;
    case 0xB3:
        return 6;
    case 0xB4:
    case 0xC1:
    case 0xC5:
        return 1;
    case 0xB6:
    case 0xC2:
    case 0xC3:
    case 0xC4:
    case 0xFC:
        return 2;
    case 0xE0:
    case 0xE1:
        return 16;
    case 0x36:
    case 0x3A:
        return 1;
    default:
        return 0;
    }
}

static void m5_panel_reset_window(M5SpiPanelState *s)
{
    s->cx = s->xs;
    s->cy = s->ys;
}

static void m5_panel_put_pixel(M5SpiPanelState *s, uint16_t px)
{
    static unsigned pixel_trace_count;
    int x = s->cx, y = s->cy;
    if (s->apply_madctl) {
        if (s->madctl & 0x20) { int t = x; x = y; y = t; }
        if (s->madctl & 0x40) { x = s->mem_w - 1 - x; }
        if (s->madctl & 0x80) { y = s->mem_h - 1 - y; }
    }
    if (getenv("M5SW_PANEL_PIXEL_TRACE") &&
        (px == 0xf800 || px == 0x001f || px == 0x07e0)
        && pixel_trace_count++ < 500) {
        fprintf(stderr, "[m5panel-pixel] (%d,%d)=%04x window=(%u,%u)-(%u,%u)\n",
                x, y, px, s->xs, s->ys, s->xe, s->ye);
    }
    if (x >= 0 && x < (int)s->mem_w && y >= 0 && y < (int)s->mem_h) {
        s->mem[y * s->mem_w + x] = px;
    }
    if (++s->cx > s->xe) {
        s->cx = s->xs;
        if (++s->cy > s->ye) {
            s->cy = s->ys;
        }
    }
}

void m5_spi_panel_write(M5SpiPanelState *s, const uint8_t *buf, uint32_t len,
                        bool command_phase)
{
    static unsigned stream_trace_count;
    static unsigned stream_trace_group;
    static unsigned dc_trace_count;
    if (!command_phase && s->infer_command && len == 1
        && s->infer_params_left == 0 && s->pending_pixel_bytes == 0
        && m5_panel_is_dcs_command(buf[0])) {
        command_phase = true;
    }
    if (getenv("M5SW_PANEL_DC_TRACE") && len && dc_trace_count++ < 1000) {
        fprintf(stderr, "[m5panel-dc] phase=%d len=%u first=%02x\n",
                command_phase, len, buf[0]);
    }
    if (getenv("M5SW_SPI_TRACE") && m5_panel_trace_count < 10000) {
        for (uint32_t i = 0; i < len && m5_panel_trace_count < 10000; i++) {
            fprintf(stderr, "[m5panel] %c %02x\n",
                    command_phase ? 'C' : 'D', buf[i]);
            m5_panel_trace_count++;
        }
    }
    if (!command_phase && s->cmd == 0x2c && getenv("M5SW_PANEL_STREAM_TRACE")
        && stream_trace_count < 6000) {
        for (uint32_t i = 0; i < len && stream_trace_count < 6000; i++) {
            fprintf(stderr, "[m5panel-stream] %02x\n", buf[i]);
            stream_trace_count++;
        }
    }
    for (uint32_t i = 0; i < len; i++) {
        uint8_t b = buf[i];
        if (command_phase) {
            s->infer_params_left = m5_panel_dcs_param_count(b);
            s->pending_pixel_bytes = 0;
            if (b == 0x2c) {
                stream_trace_count = 0;
                if (getenv("M5SW_PANEL_STREAM_TRACE")) {
                    fprintf(stderr, "[m5panel-stream-group] %u\n",
                            stream_trace_group++);
                }
            }
            if (getenv("M5SW_SPI_WINDOW_TRACE") && (b == 0x2A || b == 0x2B)) {
                fprintf(stderr, "[m5panel-window] cmd=%02x\n", b);
            }
            s->cmd = b;
            s->pidx = 0;
            s->pixel_mode = false;
            switch (b) {
            case 0x28: s->disp_on = false; s->dirty = true; break;
            case 0x29: s->disp_on = true; s->dirty = true; break;
            case 0x10: s->sleep = true; s->dirty = true; break;
            case 0x11: s->sleep = false; s->dirty = true; break;
            case 0x20: s->controller_invert = false; s->dirty = true; break;
            case 0x21: s->controller_invert = true; s->dirty = true; break;
            case 0x01:
                s->disp_on = false;
                s->sleep = true;
                s->madctl = 0;
                s->controller_invert = false;
                break;
            default:
                break;
            }
            continue;
        }

        switch (s->cmd) {
        case 0x2A:
            if (getenv("M5SW_SPI_WINDOW_TRACE")) {
                fprintf(stderr, "[m5panel-window] 2a[%u]=%02x\n", s->pidx, b);
            }
            if (s->pidx < 4) {
                s->params[s->pidx++] = b;
            }
            if (s->pidx == 4) {
                s->xs = (s->params[0] << 8) | s->params[1];
                s->xe = (s->params[2] << 8) | s->params[3];
            }
            break;
        case 0x2B:
            if (getenv("M5SW_SPI_WINDOW_TRACE")) {
                fprintf(stderr, "[m5panel-window] 2b[%u]=%02x\n", s->pidx, b);
            }
            if (s->pidx < 4) {
                s->params[s->pidx++] = b;
            }
            if (s->pidx == 4) {
                s->ys = (s->params[0] << 8) | s->params[1];
                s->ye = (s->params[2] << 8) | s->params[3];
            }
            break;
        case 0x2C:
        case 0x3C:
            if (!s->pixel_mode) {
                m5_panel_reset_window(s);
                s->pixel_mode = true;
                s->pix_half = false;
                    s->pending_pixel_bytes =
                        (uint32_t)(s->xe - s->xs + 1) *
                        (uint32_t)(s->ye - s->ys + 1) * 2;
            }
            if (!s->pix_half) {
                s->pix_hi = b;
                s->pix_half = true;
            } else {
                m5_panel_put_pixel(s, (s->pix_hi << 8) | b);
                s->pix_half = false;
                s->dirty = true;
            }
            break;
        case 0x36:
            s->madctl = b;
            s->dirty = true;
            break;
        case 0x3A:
            s->colmod = b;
            break;
        default:
            break;
        }
        if (s->infer_params_left) {
            s->infer_params_left--;
        }
        if (s->pending_pixel_bytes) {
            s->pending_pixel_bytes--;
        }
    }
    if (s->immediate_update && s->dirty) {
        qemu_bh_schedule(s->refresh_bh);
        qemu_clock_notify(QEMU_CLOCK_VIRTUAL);
    }
}

uint32_t m5_spi_panel_read_id(M5SpiPanelState *s)
{
    return s->read_id;
}

static void m5_panel_update(void *opaque)
{
    M5SpiPanelState *s = opaque;
    DisplaySurface *surf = qemu_console_surface(s->con);
    if (!surf || surface_bits_per_pixel(surf) != 32 ||
        surface_width(surf) != s->vis_w || surface_height(surf) != s->vis_h) {
        surf = qemu_create_displaysurface(s->vis_w, s->vis_h);
        dpy_gfx_replace_surface(s->con, surf);
        s->dirty = true;
    }
    if (!s->dirty) {
        return;
    }
    s->dirty = false;
    uint32_t *dst = (uint32_t *)surface_data(surf);
    int stride = surface_stride(surf) / 4;
    bool on = s->disp_on && !s->sleep;
    bool invert = s->physical_invert ^ s->controller_invert;
    for (uint32_t y = 0; y < s->vis_h; y++) {
        uint32_t *d = dst + y * stride;
        for (uint32_t x = 0; x < s->vis_w; x++) {
            uint32_t mx = x + s->off_x;
            uint32_t my = y + s->off_y;
            switch (s->glass_rotation & 3) {
            case 1:
                mx = s->off_x + y;
                my = s->off_y + s->vis_w - 1 - x;
                break;
            case 2:
                mx = s->off_x + s->vis_w - 1 - x;
                my = s->off_y + s->vis_h - 1 - y;
                break;
            case 3:
                mx = s->off_x + s->vis_h - 1 - y;
                my = s->off_y + x;
                break;
            default:
                break;
            }
            uint16_t p = s->mem[my * s->mem_w + mx];
            if (invert) {
                p = ~p;
            }
            uint32_t r = ((p >> 11) & 0x1f) * 255 / 31;
            uint32_t g = ((p >> 5) & 0x3f) * 255 / 63;
            uint32_t b = (p & 0x1f) * 255 / 31;
            if (!on) {
                r = g = b = 0;
            }
            if (getenv("M5SW_PANEL_REFRESH_TRACE") && x == 20 && y == 20) {
                fprintf(stderr,
                        "[m5panel-pixel-render] mx=%u my=%u p=%04x on=%d inv=%d\n",
                        mx, my, p, on, invert);
            }
            d[x] = 0xff000000u | (r << 16) | (g << 8) | b;
        }
    }
    if (getenv("M5SW_PANEL_REFRESH_TRACE")) {
        int stride_dbg = surface_stride(surf) / 4;
        uint32_t *dbg = (uint32_t *)surface_data(surf);
        fprintf(stderr, "[m5panel-render] surface=%p sample=%08x size=%ux%u\n",
                (void *)surf, dbg[20 * stride_dbg + 20],
                surface_width(surf), surface_height(surf));
    }
    dpy_gfx_update(s->con, 0, 0, s->vis_w, s->vis_h);
}

static void m5_panel_invalidate(void *opaque)
{
    ((M5SpiPanelState *)opaque)->dirty = true;
}

static const GraphicHwOps m5_panel_ops = {
    .invalidate = m5_panel_invalidate,
    .gfx_update = m5_panel_update,
};

static uint32_t m5_panel_pixel_rgb(M5SpiPanelState *s, uint32_t x, uint32_t y)
{
    uint32_t mx = x + s->off_x;
    uint32_t my = y + s->off_y;

    switch (s->glass_rotation & 3) {
    case 1:
        mx = s->off_x + y;
        my = s->off_y + s->vis_w - 1 - x;
        break;
    case 2:
        mx = s->off_x + s->vis_w - 1 - x;
        my = s->off_y + s->vis_h - 1 - y;
        break;
    case 3:
        mx = s->off_x + s->vis_h - 1 - y;
        my = s->off_y + x;
        break;
    default:
        break;
    }

    uint16_t p = s->mem[my * s->mem_w + mx];
    bool on = s->disp_on && !s->sleep;
    bool invert = s->physical_invert ^ s->controller_invert;
    if (invert) {
        p = ~p;
    }
    uint32_t r = ((p >> 11) & 0x1f) * 255 / 31;
    uint32_t g = ((p >> 5) & 0x3f) * 255 / 63;
    uint32_t b = (p & 0x1f) * 255 / 31;
    if (!on) {
        r = g = b = 0;
    }
    return (r << 16) | (g << 8) | b;
}

static void m5_panel_dump_ppm(M5SpiPanelState *s)
{
    if (!s->dump_path) {
        return;
    }

    FILE *f = fopen(s->dump_path, "wb");
    if (!f) {
        return;
    }
    fprintf(f, "P6\n%u %u\n255\n", s->vis_w, s->vis_h);
    for (uint32_t y = 0; y < s->vis_h; y++) {
        for (uint32_t x = 0; x < s->vis_w; x++) {
            uint32_t rgb = m5_panel_pixel_rgb(s, x, y);
            uint8_t bytes[3] = { rgb >> 16, rgb >> 8, rgb };
            fwrite(bytes, sizeof(bytes), 1, f);
        }
    }
    fclose(f);
}

static void m5_panel_refresh_tick(void *opaque)
{
    M5SpiPanelState *s = opaque;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (getenv("M5SW_PANEL_REFRESH_TRACE") && s->dirty) {
        fprintf(stderr, "[m5panel-refresh] dirty sample=%04x\n",
                s->mem[20 * s->mem_w + 20]);
    }
    m5_panel_update(s);
    timer_mod(s->refresh_timer, now + 16666667);
}

static void m5_panel_refresh_bh(void *opaque)
{
    m5_panel_update(opaque);
}

static char *m5_panel_get_dump_path(Object *obj, Error **errp)
{
    return g_strdup(((M5SpiPanelState *)obj)->dump_path);
}

static void m5_panel_set_dump_path(Object *obj, const char *value, Error **errp)
{
    M5SpiPanelState *s = (M5SpiPanelState *)obj;
    g_free(s->dump_path);
    s->dump_path = g_strdup(value);
}

static bool m5_panel_get_refresh_now(Object *obj, Error **errp)
{
    return false;
}

static void m5_panel_set_refresh_now(Object *obj, bool value, Error **errp)
{
    M5SpiPanelState *s = (M5SpiPanelState *)obj;
    if (value) {
        s->dirty = true;
        m5_panel_update(s);
        m5_panel_dump_ppm(s);
    }
}

static uint8_t tca8418_event(int row, int col, bool down)
{
    int raw_row = col / 2;
    int raw_col = row + ((col % 2) ? 4 : 0);
    int value = raw_row * 10 + raw_col + 1;

    return value | (down ? 0x80 : 0);
}

static bool tca8418_key_pos(int qcode, int *row, int *col)
{
    if (qcode >= Q_KEY_CODE_A && qcode <= Q_KEY_CODE_Z) {
        int index = qcode - Q_KEY_CODE_A;
        *row = index < 10 ? 2 : 3;
        *col = index < 10 ? 2 + index : 3 + index - 10;
        return true;
    }
    switch (qcode) {
    case Q_KEY_CODE_RET:
        *row = 2;
        *col = 13;
        return true;
    case Q_KEY_CODE_SPC:
        *row = 3;
        *col = 13;
        return true;
    case Q_KEY_CODE_TAB:
        *row = 1;
        *col = 0;
        return true;
    case Q_KEY_CODE_BACKSPACE:
        *row = 0;
        *col = 13;
        return true;
    default:
        return false;
    }
}

static void m5_panel_keyboard_event(int qcode, bool down)
{
    int row, col;

    if (qcode == Q_KEY_CODE_LEFT || qcode == Q_KEY_CODE_RIGHT ||
        qcode == Q_KEY_CODE_UP || qcode == Q_KEY_CODE_DOWN) {
        int fn_raw = tca8418_event(2, 0, down);
        int direction_raw;

        if (qcode == Q_KEY_CODE_LEFT) {
            direction_raw = tca8418_event(3, 10, down);
        } else if (qcode == Q_KEY_CODE_DOWN) {
            direction_raw = tca8418_event(3, 11, down);
        } else if (qcode == Q_KEY_CODE_RIGHT) {
            direction_raw = tca8418_event(3, 12, down);
        } else {
            direction_raw = tca8418_event(2, 11, down);
        }
        if (down) {
            m5sw_keyboard_event(fn_raw);
            m5sw_keyboard_event(direction_raw);
        } else {
            m5sw_keyboard_event(direction_raw);
            m5sw_keyboard_event(fn_raw);
        }
        return;
    }

    if (tca8418_key_pos(qcode, &row, &col)) {
        m5sw_keyboard_event(tca8418_event(row, col, down));
    }
}

static void m5_panel_input(DeviceState *dev, QemuConsole *src, InputEvent *evt)
{
    M5SpiPanelState *s = M5_SPI_PANEL(dev);
    if (getenv("M5SW_INPUT_TRACE")) {
        fprintf(stderr, "[m5panel-input] type=%d\n", evt->type);
    }
    switch (evt->type) {
    case INPUT_EVENT_KIND_KEY: {
        InputKeyEvent *key = evt->u.key.data;
        int q = qemu_input_key_value_to_qcode(key->key);
        int down = key->down;
        if (getenv("M5SW_INPUT_TRACE")) {
            fprintf(stderr, "[m5panel-input] qcode=%d down=%d\n", q, down);
        }
        if (s->keyboard) {
            m5_panel_keyboard_event(q, down);
            break;
        }
        if (s->plc_keys) {
            if (q == Q_KEY_CODE_A) {
                m5sw_plc_key_set(0, down);
            } else if (q == Q_KEY_CODE_B) {
                m5sw_plc_key_set(1, down);
            } else if (q == Q_KEY_CODE_C) {
                m5sw_plc_key_set(2, down);
            }
            break;
        }
        switch (q) {
        case Q_KEY_CODE_A: case Q_KEY_CODE_LEFT: case Q_KEY_CODE_1:
            esp32_gpio_set_input(s->key_a_pin, !down);
            break;
        case Q_KEY_CODE_B: case Q_KEY_CODE_RIGHT: case Q_KEY_CODE_2:
            esp32_gpio_set_input(s->key_b_pin, !down);
            break;
        case Q_KEY_CODE_P: case Q_KEY_CODE_3:
            m5sw_pwr_button(down);
            break;
        default:
            break;
        }
        break;
    }
    case INPUT_EVENT_KIND_ABS: {
        InputMoveEvent *m = evt->u.abs.data;
        int v = qemu_input_scale_axis(m->value, INPUT_EVENT_ABS_MIN,
                                      INPUT_EVENT_ABS_MAX, 0, s->vis_w - 1);
        if (m->axis == INPUT_AXIS_X) {
            s->mouse_x = v;
        } else if (m->axis == INPUT_AXIS_Y) {
            s->mouse_y = qemu_input_scale_axis(m->value, INPUT_EVENT_ABS_MIN,
                                               INPUT_EVENT_ABS_MAX, 0, s->vis_h - 1);
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

static void m5_panel_input_sync(DeviceState *dev)
{
    M5SpiPanelState *s = M5_SPI_PANEL(dev);
    if (s->touch) {
        m5sw_ft_touch_set_pin(s->mouse_btn, s->mouse_x, s->mouse_y,
                              s->touch_int_pin);
    }
}

static const QemuInputHandler m5_panel_input_handler = {
    .name = "M5Stack SPI panel keys",
    .mask = INPUT_EVENT_MASK_KEY | INPUT_EVENT_MASK_BTN | INPUT_EVENT_MASK_ABS,
    .event = m5_panel_input,
    .sync = m5_panel_input_sync,
};

static void m5_panel_realize(DeviceState *dev, Error **errp)
{
    M5SpiPanelState *s = M5_SPI_PANEL(dev);
    s->mem = g_new0(uint16_t, s->mem_w * s->mem_h);
    s->con = graphic_console_init(dev, 0, &m5_panel_ops, s);
    qemu_console_resize(s->con, s->vis_w, s->vis_h);
    s->dirty = true;
    s->sleep = true;
    s->xe = s->mem_w - 1;
    s->ye = s->mem_h - 1;
    m5_panel_reset_window(s);
    s->refresh_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                    m5_panel_refresh_tick, s);
    s->refresh_bh = qemu_bh_new(m5_panel_refresh_bh, s);
    timer_mod(s->refresh_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 16666667);
    QemuInputHandlerState *hs = qemu_input_handler_register(dev, &m5_panel_input_handler);
    qemu_input_handler_activate(hs);
    object_property_add_str(OBJECT(s), "dump-path",
                            m5_panel_get_dump_path, m5_panel_set_dump_path);
    object_property_add_bool(OBJECT(s), "refresh-now",
                             m5_panel_get_refresh_now, m5_panel_set_refresh_now);
}

static Property m5_panel_props[] = {
    DEFINE_PROP_UINT32("mem-width", M5SpiPanelState, mem_w, 240),
    DEFINE_PROP_UINT32("mem-height", M5SpiPanelState, mem_h, 320),
    DEFINE_PROP_UINT32("vis-width", M5SpiPanelState, vis_w, 135),
    DEFINE_PROP_UINT32("vis-height", M5SpiPanelState, vis_h, 240),
    DEFINE_PROP_UINT32("offset-x", M5SpiPanelState, off_x, 52),
    DEFINE_PROP_UINT32("offset-y", M5SpiPanelState, off_y, 40),
    DEFINE_PROP_UINT32("key-a-pin", M5SpiPanelState, key_a_pin, 10),
    DEFINE_PROP_UINT32("key-b-pin", M5SpiPanelState, key_b_pin, 9),
    DEFINE_PROP_UINT32("read-id", M5SpiPanelState, read_id, 0x00007683),
    DEFINE_PROP_UINT32("glass-rotation", M5SpiPanelState, glass_rotation, 0),
    DEFINE_PROP_BOOL("apply-madctl", M5SpiPanelState, apply_madctl, true),
    DEFINE_PROP_BOOL("touch", M5SpiPanelState, touch, false),
    DEFINE_PROP_UINT32("touch-int-pin", M5SpiPanelState, touch_int_pin, 21),
    DEFINE_PROP_BOOL("immediate-update", M5SpiPanelState, immediate_update, false),
    DEFINE_PROP_BOOL("keyboard", M5SpiPanelState, keyboard, false),
    DEFINE_PROP_BOOL("plc-keys", M5SpiPanelState, plc_keys, false),
    DEFINE_PROP_BOOL("infer-command", M5SpiPanelState, infer_command, false),
    DEFINE_PROP_BOOL("invert", M5SpiPanelState, physical_invert, true),
    DEFINE_PROP_END_OF_LIST(),
};

static void m5_panel_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    dc->realize = m5_panel_realize;
    device_class_set_props(dc, m5_panel_props);
}

static const TypeInfo m5_panel_info = {
    .name = TYPE_M5_SPI_PANEL,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(M5SpiPanelState),
    .class_init = m5_panel_class_init,
};

static void m5_panel_register(void)
{
    type_register_static(&m5_panel_info);
}
type_init(m5_panel_register)

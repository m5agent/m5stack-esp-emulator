/*
 * CO5300 466x466 AMOLED controller (QSPI command set as used by M5GFX Panel_AMOLED)
 * Frames are delimited by the software chip-select on GPIO39.
 *   [0x02, 0x00, cmd, 0x00, params...]      register write (1-line)
 *   [0x32|0x12, 0x00, 0x2C|0x3C, 0x00, px]  memory write (4-line), RGB565 big-endian
 * Also hosts the input handler: keyboard -> KEYA(G2)/KEYB(G1)/PWR, mouse -> CST820.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qapi/error.h"
#include "hw/qdev-core.h"
#include "ui/console.h"
#include "ui/input.h"
#include "qemu/timer.h"
#include "m5stopwatch.h"

#define MEM_W 480
#define MEM_H 480
#define VIS_W 466
#define VIS_H 466
#define VIS_X0 6
#define VIS_Y0 0
#define PIN_CS 39
#define PIN_KEYA 2
#define PIN_KEYB 1
#define PIN_TE 38

struct Co5300State {
    DeviceState parent_obj;
    QemuConsole *con;
    uint16_t mem[MEM_W * MEM_H];
    bool dirty;
    /* frame parser */
    bool selected;
    uint32_t nbytes;
    uint8_t hdr[4];
    uint8_t cmd;
    uint32_t pidx;
    uint8_t params[8];
    bool pixel_mode;
    uint8_t pix_hi;
    bool pix_half;
    /* registers */
    uint16_t xs, xe, ys, ye, cx, cy;
    uint8_t madctl, colmod, bright;
    bool disp_on, sleep, invert;
    uint64_t pixels_written;
    int mouse_x, mouse_y, mouse_btn;
    bool full;
    QEMUTimer *te_timer;
    bool te_level;
};

static void co_reset_window(Co5300State *s)
{
    s->cx = s->xs;
    s->cy = s->ys;
}

static void co_put_pixel(Co5300State *s, uint16_t px)
{
    int x = s->cx, y = s->cy;
    if (s->madctl & 0x20) { int t = x; x = y; y = t; }
    if (s->madctl & 0x40) { x = MEM_W - 1 - x; }
    if (s->madctl & 0x80) { y = MEM_H - 1 - y; }
    if (x >= 0 && x < MEM_W && y >= 0 && y < MEM_H) {
        s->mem[y * MEM_W + x] = px;
    }
    s->pixels_written++;
    if (++s->cx > s->xe) {
        s->cx = s->xs;
        if (++s->cy > s->ye) {
            s->cy = s->ys;
        }
    }
}

static void co_param(Co5300State *s, uint8_t b)
{
    if (s->pidx < sizeof(s->params)) {
        s->params[s->pidx] = b;
    }
    s->pidx++;
    switch (s->cmd) {
    case 0x2A:
        if (s->pidx == 4) {
            s->xs = (s->params[0] << 8) | s->params[1];
            s->xe = (s->params[2] << 8) | s->params[3];
        }
        break;
    case 0x2B:
        if (s->pidx == 4) {
            s->ys = (s->params[0] << 8) | s->params[1];
            s->ye = (s->params[2] << 8) | s->params[3];
        }
        break;
    case 0x36: s->madctl = b; break;
    case 0x3A: s->colmod = b; break;
    case 0x51: s->bright = b; s->dirty = true; break;
    default: break;
    }
}

static void co_command(Co5300State *s, uint8_t cmd)
{
    s->cmd = cmd;
    s->pidx = 0;
    switch (cmd) {
    case 0x28: s->disp_on = false; s->dirty = true; break;
    case 0x29: s->disp_on = true; s->dirty = true; break;
    case 0x10: s->sleep = true; s->dirty = true; break;
    case 0x11: s->sleep = false; s->dirty = true; break;
    case 0x20: s->invert = false; s->dirty = true; break;
    case 0x21: s->invert = true; s->dirty = true; break;
    case 0x01: /* SWRESET */
        s->disp_on = false; s->sleep = true; s->bright = 0; s->madctl = 0;
        break;
    default: break;
    }
}

static int co_trace = -1;

void co5300_cs(Co5300State *s, int level)
{
    if (co_trace < 0) {
        co_trace = getenv("M5SW_LCD_TRACE") != NULL;
    }
    if (co_trace && level && s->selected) {
        fprintf(stderr, "[co5300] frame op=%02x cmd=%02x bytes=%u params=%u win=%u,%u-%u,%u pos=%u,%u half=%d\n",
                s->hdr[0], s->hdr[2], s->nbytes, s->pidx, s->xs, s->ys, s->xe, s->ye, s->cx, s->cy, s->pix_half);
    }
    if (!level) {
        s->selected = true;
        s->nbytes = 0;
        s->pixel_mode = false;
        s->pix_half = false;
        s->cmd = 0;
        s->pidx = 0;
    } else {
        s->selected = false;
    }
}

void co5300_write(Co5300State *s, const uint8_t *buf, uint32_t len)
{
    /*
     * IDF's 32-bit command encoding uses [opcode, 0, command, 0] and the
     * QSPI device CS is controlled by the controller rather than the GPIO
     * model.  Treat a complete four-byte opcode header as a transaction
     * boundary so a preceding RAMWR burst cannot swallow the next command
     * as pixel data.
     */
    if (len == 4 && buf[1] == 0 && buf[3] == 0
        && (buf[0] == 0x02 || buf[0] == 0x12 || buf[0] == 0x32)) {
        s->nbytes = 0;
        s->pixel_mode = false;
        s->pix_half = false;
        s->cmd = 0;
        s->pidx = 0;
    }
    for (uint32_t i = 0; i < len; i++) {
        uint8_t b = buf[i];
        if (s->nbytes < 4) {
            s->hdr[s->nbytes++] = b;
            if (s->nbytes == 4) {
                uint8_t op = s->hdr[0], c = s->hdr[2];
                /*
                 * M5GFX releases differ in where the 8-bit CO5300 command
                 * sits inside the QSPI address phase: the validated UIFlow2
                 * path sends [op, 00, cmd, 00], while MotoNav sends
                 * [op, cmd, 00, 00].  Accept both wire forms.
                 */
                if (!c) {
                    c = s->hdr[1];
                }
                if (op == 0x02) {
                    co_command(s, c);
                } else if (op == 0x32 || op == 0x12) {
                    if (c == 0x2C) {
                        co_reset_window(s);
                        s->pixel_mode = true;
                    } else if (c == 0x3C) {
                        s->pixel_mode = true;
                    } else {
                        s->pixel_mode = false;
                    }
                    s->pix_half = false;
                    s->cmd = 0;
                }
            }
            continue;
        }
        s->nbytes++;
        if (s->pixel_mode) {
            if (!s->pix_half) {
                s->pix_hi = b;
                s->pix_half = true;
            } else {
                co_put_pixel(s, (s->pix_hi << 8) | b);
                s->pix_half = false;
                s->dirty = true;
            }
        } else if (s->hdr[0] == 0x02) {
            co_param(s, b);
        }
    }
}

static void co_cs_cb(void *opaque, int pin, int level)
{
    co5300_cs(opaque, level);
}

static void co_update(void *opaque)
{
    Co5300State *s = opaque;
    DisplaySurface *surf = qemu_console_surface(s->con);
    int want_w = s->full ? MEM_W : VIS_W, want_h = s->full ? MEM_H : VIS_H;
    if (!surf || surface_bits_per_pixel(surf) != 32 ||
        surface_width(surf) != want_w || surface_height(surf) != want_h) {
        surf = qemu_create_displaysurface(want_w, want_h);
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
    uint32_t br = s->bright;
    int vw = want_w, vh = want_h;
    int x0 = s->full ? 0 : VIS_X0, y0 = s->full ? 0 : VIS_Y0;
    /*
     * The CO5300 controller has a square 466x466 framebuffer, but the
     * StopWatch glass is circular.  Mask the corners in the QEMU console
     * output so screendumps show the same visible area as the real panel.
     * The memory dump itself remains untouched.
     */
    int cx = vw / 2, cy = vh / 2;
    int radius2 = (vw / 2) * (vw / 2);
    for (int y = 0; y < vh; y++) {
        const uint16_t *src = &s->mem[(y + y0) * MEM_W + x0];
        uint32_t *d = dst + y * stride;
        for (int x = 0; x < vw; x++) {
            int dx = x - cx, dy = y - cy;
            if (!s->full && dx * dx + dy * dy > radius2) {
                d[x] = 0xff000000u;
                continue;
            }
            uint16_t p = src[x];
            if (s->invert) {
                p = ~p;
            }
            uint32_t r = ((p >> 11) & 0x1f) * 255 / 31;
            uint32_t g = ((p >> 5) & 0x3f) * 255 / 63;
            uint32_t b = (p & 0x1f) * 255 / 31;
            if (!on) {
                r = g = b = 0;
            } else {
                r = r * br / 255; g = g * br / 255; b = b * br / 255;
            }
            d[x] = 0xff000000u | (r << 16) | (g << 8) | b;
        }
    }
    dpy_gfx_update(s->con, 0, 0, vw, vh);
}

static void co_invalidate(void *opaque)
{
    ((Co5300State *)opaque)->dirty = true;
}

static const GraphicHwOps co_ops = {
    .invalidate = co_invalidate,
    .gfx_update = co_update,
};

/* ---- input ---- */
static void co_input_event(DeviceState *dev, QemuConsole *src, InputEvent *evt)
{
    Co5300State *s = CO5300(dev);
    switch (evt->type) {
    case INPUT_EVENT_KIND_KEY: {
        InputKeyEvent *key = evt->u.key.data;
        int q = qemu_input_key_value_to_qcode(key->key);
        int down = key->down;
        switch (q) {
        case Q_KEY_CODE_A: case Q_KEY_CODE_LEFT: case Q_KEY_CODE_1:
            esp32_gpio_set_input(PIN_KEYA, !down);
            break;
        case Q_KEY_CODE_B: case Q_KEY_CODE_RIGHT: case Q_KEY_CODE_2:
            esp32_gpio_set_input(PIN_KEYB, !down);
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
        int v = qemu_input_scale_axis(m->value, INPUT_EVENT_ABS_MIN, INPUT_EVENT_ABS_MAX, 0, VIS_W - 1);
        if (m->axis == INPUT_AXIS_X) {
            s->mouse_x = v;
        } else if (m->axis == INPUT_AXIS_Y) {
            s->mouse_y = v;
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

static void co_input_sync(DeviceState *dev)
{
    Co5300State *s = CO5300(dev);
    m5sw_touch_set(s->mouse_btn, s->mouse_x, s->mouse_y);
}

static const QemuInputHandler co_input_handler = {
    .name = "M5StopWatch touch+keys",
    .mask = INPUT_EVENT_MASK_KEY | INPUT_EVENT_MASK_BTN | INPUT_EVENT_MASK_ABS,
    .event = co_input_event,
    .sync = co_input_sync,
};

/* Tearing-effect output: ~60 Hz, short high pulse (TE active high) */
static void co_te_tick(void *opaque)
{
    Co5300State *s = opaque;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    s->te_level = !s->te_level;
    esp32_gpio_set_input(PIN_TE, s->te_level);
    timer_mod(s->te_timer, now + (s->te_level ? 500000 : 16166667));
}

static void co_realize(DeviceState *dev, Error **errp)
{
    Co5300State *s = CO5300(dev);
    s->con = graphic_console_init(dev, 0, &co_ops, s);
    s->full = getenv("M5SW_LCD_FULL") != NULL;   /* debug: show whole 480x480 GRAM */
    qemu_console_resize(s->con, s->full ? MEM_W : VIS_W, s->full ? MEM_H : VIS_H);
    s->colmod = 0x55;
    s->sleep = true;
    s->xe = MEM_W - 1;
    s->ye = MEM_H - 1;
    esp32_gpio_add_out_listener(PIN_CS, co_cs_cb, s);
    esp32_gpio_set_input(PIN_TE, 0);
    s->te_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, co_te_tick, s);
    timer_mod(s->te_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 16666667);
    QemuInputHandlerState *hs = qemu_input_handler_register(dev, &co_input_handler);
    qemu_input_handler_activate(hs);
}

static void co_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    dc->realize = co_realize;
}

static const TypeInfo co_info = {
    .name = TYPE_CO5300,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(Co5300State),
    .class_init = co_class_init,
};

static void co_register(void)
{
    type_register_static(&co_info);
}
type_init(co_register)

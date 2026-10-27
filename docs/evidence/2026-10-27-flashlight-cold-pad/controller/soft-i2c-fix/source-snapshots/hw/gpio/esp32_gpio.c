/*
 * ESP32 GPIO emulation
 *
 * Copyright (c) 2019 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/hw.h"
#include "hw/sysbus.h"
#include "hw/registerfields.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "hw/gpio/esp32_gpio.h"
#include "hw/gpio/esp32s3_gpio_pad_aux.h"
#include "hw/misc/esp32_ledc.h"
#include "../m5stopwatch/m5stopwatch.h"



/*
 * Minimal functional GPIO model: register storage, OUT/ENABLE W1TS/W1TC,
 * IN/IN1 computed from outputs and externally driven inputs (default: pulled up).
 * Output-change listeners let board models observe e.g. software chip-selects.
 */
#define GPIO_NPINS 54
#define GPIO_MAX_LISTENERS 8
static uint64_t g_ext_in = ~0ULL;      /* externally driven input levels */
static uint32_t g_regs[0x200];         /* 0x000..0x7ff */
static Esp32GpioState *g_gpio_device;
static bool g_gpio_s3;
static void gpio_transition_irq(uint64_t before, uint64_t after);
static void gpio_update_irq(void);
static uint64_t g_open_drain;          /* pins whose output stage is open-drain */
static uint64_t g_force_mask;          /* passive board lines forced by a model */
static uint64_t g_force_level;
static struct {
    esp32_gpio_out_cb cb;
    void *opaque;
} g_listeners[GPIO_NPINS][GPIO_MAX_LISTENERS];
static uint8_t g_listener_count[GPIO_NPINS];
static int g_trace_last_level = -1;

static uint64_t gpio_line64(void);
static uint64_t gpio_out64(void);
static uint64_t gpio_en64(void);

/* Controller-local observer/bias state. The existing GPIO model is singleton. */
#define GPIO_PAD_OBSERVERS_PER_PIN 8
static uint64_t g_external_seen;
static uint32_t g_iomux_regs[49];
static bool g_iomux_pull_known[49];
static Esp32GpioOdOrigin g_od_origin[GPIO_NPINS];
static uint64_t g_pad_revision[GPIO_NPINS];
static uint64_t g_pad_epoch, g_pad_generation, g_pad_sequence;
static unsigned g_pad_dispatch_depth;

struct Esp32GpioPadObserver {
    Esp32GpioState *gpio;
    unsigned pin;
    Esp32GpioPadObserverFn cb;
    void *opaque;
    struct Esp32GpioPadObserver *next;
};
struct Esp32GpioBoardBias {
    Esp32GpioState *gpio;
    unsigned pin;
    Esp32GpioBias bias;
    const void *owner;
    struct Esp32GpioBoardBias *next;
};
static Esp32GpioPadObserver *g_pad_observers;
static Esp32GpioBoardBias *g_board_biases;
static uint64_t gpio_legacy_line64(void);

static bool gpio_pad_valid(Esp32GpioState *s, unsigned pin)
{
    return s && s == g_gpio_device && pin < (g_gpio_s3 ? 49 : 40) &&
           (!g_gpio_s3 || pin < 22 || pin > 25);
}

static bool gpio_iomux_alias(unsigned pin)
{
    return pin <= 21 || (pin >= 33 && pin <= 38) || pin == 45 || pin == 46;
}

static void gpio_iomux_reset(void)
{
    /* TRM v1.8 Table 6.12-1 RST codes; holes have no pad. UART RST4
     * describes its peripheral OE, not a GPIO_ENABLE bit to synthesize.
     */
    static const uint8_t rst[49] = {
        3, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0,
        0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 3, 3,
        3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 4, 3, 2, 2, 1, 1,
    };
    for (unsigned pin = 0; pin < 49; pin++) {
        unsigned code = rst[pin];
        g_iomux_regs[pin] = ((pin == 19 || pin == 20) ? 3u : 2u) << 10;
        if (code == 1 || code == 2 || code == 3) {
            g_iomux_regs[pin] |= 1u << 9;
        }
        if (code == 2) { g_iomux_regs[pin] |= 1u << 7; }
        if (code == 3 || code == 4) { g_iomux_regs[pin] |= 1u << 8; }
        /* GPIO39's reset pull depends on eFuse DIS_PAD_JTAG. An explicit
         * later IOMUX write supplies both pull bits without that ambiguity.
         */
        g_iomux_pull_known[pin] = pin != 39;
    }
}

static void gpio_snapshot_internal(Esp32GpioState *s, unsigned pin,
                                   Esp32GpioPadSnapshot *out)
{
    memset(out, 0, sizeof(*out));
    out->pin = pin;
    out->s3 = g_gpio_s3;
    out->controller_generation = g_pad_generation;
    out->epoch = g_pad_epoch;
    out->revision = pin < GPIO_NPINS ? g_pad_revision[pin] : 0;
    out->at_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (!gpio_pad_valid(s, pin)) { return; }
    uint64_t bit = 1ULL << pin;
    uint32_t route = g_regs[((g_gpio_s3 ? 0x554 : 0x530) + pin * 4) / 4];
    uint32_t pin_cfg = g_regs[((g_gpio_s3 ? 0x74 : 0x88) + pin * 4) / 4];
    out->level = !!(gpio_legacy_line64() & bit);
    out->out_latch = !!(gpio_out64() & bit);
    out->enable_reg = !!(gpio_en64() & bit);
    out->out_sel = route & 0x1ff;
    out->out_inv = !!(route & (1u << 9));
    out->oen_sel = !!(route & (1u << 10));
    out->oen_inv = !!(route & (1u << 11));
    out->open_drain = !!(g_open_drain & bit);
    out->pad_driver_reg = !!(pin_cfg & (1u << 2));
    out->od_origin = g_od_origin[pin];
    out->external_seen = !!(g_external_seen & bit);
    out->external_level = !!(g_ext_in & bit);
    out->force_enabled = !!(g_force_mask & bit);
    out->force_level = !!(g_force_level & bit);
    for (Esp32GpioBoardBias *b = g_board_biases; b; b = b->next) {
        if (b->gpio == s && b->pin == pin) {
            if (b->bias == ESP32_GPIO_BIAS_PULL_UP) { out->bias_up_count++; }
            else { out->bias_down_count++; }
        }
    }
    if (g_gpio_s3) {
        uint32_t mux = g_iomux_regs[pin];
        out->iomux_valid = true;
        out->mcu_sel = (mux >> 12) & 7;
        out->fun_pd = !!(mux & (1u << 7));
        out->fun_pu = !!(mux & (1u << 8));
        out->fun_ie = !!(mux & (1u << 9));
        out->slp_sel = !!(mux & (1u << 1));
        out->filter_en = !!(mux & (1u << 15));
        out->pull_config_known = g_iomux_pull_known[pin];
        out->override_mask = esp32s3_gpio_pad_aux_blockers(s, pin);
        if (out->mcu_sel == 1) {
            out->mux_path = ESP32_GPIO_MUX_GPIO_MATRIX;
        } else if (out->mcu_sel == 0 && gpio_iomux_alias(pin)) {
            out->mux_path = ESP32_GPIO_MUX_GPIO_ALIAS;
        } else {
            out->mux_path = ESP32_GPIO_MUX_OTHER_UNMODELED;
            out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_MUX;
        }
        /* The function table proves the unmodified GPIO alias. It does not
         * establish its coupling to peripheral routing or inversion bits.
         */
        if (out->mux_path == ESP32_GPIO_MUX_GPIO_ALIAS &&
            (out->out_sel != 256 || out->out_inv || out->oen_inv)) {
            out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_MUX;
        }
        if (out->override_mask) { out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_OVERRIDE; }
    } else {
        out->mux_path = ESP32_GPIO_MUX_UNRESOLVED;
        out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_MUX;
    }
    bool mux_ok = !(out->blocker_mask & (ESP32_GPIO_PAD_BLOCK_MUX |
                                       ESP32_GPIO_PAD_BLOCK_OVERRIDE));
    if (mux_ok) {
        out->oe_known = out->out_sel == 256 || out->oen_sel;
        if (out->oe_known) { out->oe = out->enable_reg ^ out->oen_inv; }
        else { out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_PERIPHERAL_OE; }
        out->drive_known = out->out_sel == 256;
        out->drive_level = out->out_latch ^ out->out_inv;
        if (out->oe_known && out->oe && !out->drive_known) {
            out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_PERIPHERAL_DATA;
        }
    }
    bool driven = mux_ok && out->oe_known && out->oe && out->drive_known &&
                  (!out->open_drain || !out->drive_level);
    bool released = mux_ok && out->oe_known &&
                    (!out->oe || (out->drive_known && out->open_drain &&
                                  out->drive_level));
    if (driven) {
        out->known = true;
        out->level = out->drive_level;
        out->source_mask = ESP32_GPIO_PAD_SOURCE_GPIO;
        /* The legacy external API cannot distinguish an actively driven
         * value from release/pull semantics at every call site. Never
         * certify an opposing explicit external value as a known pad.
         */
        if (out->external_seen && out->external_level != out->level) {
            out->source_mask |= ESP32_GPIO_PAD_SOURCE_EXTERNAL;
            out->conflict = true;
        }
        if (out->force_enabled) {
            out->source_mask |= ESP32_GPIO_PAD_SOURCE_FORCE;
            if (out->force_level != out->level) { out->conflict = true; }
        }
    } else if (released) {
        if (out->force_enabled) {
            out->known = true;
            out->level = out->force_level;
            out->source_mask = ESP32_GPIO_PAD_SOURCE_FORCE;
            if (out->external_seen && out->external_level != out->level) {
                out->conflict = true;
            }
        } else if (out->external_seen) {
            out->known = true;
            out->level = out->external_level;
            out->source_mask = ESP32_GPIO_PAD_SOURCE_EXTERNAL;
        } else {
            bool up = out->bias_up_count || out->fun_pu;
            bool down = out->bias_down_count || out->fun_pd;
            if (out->bias_up_count) { out->source_mask |= ESP32_GPIO_PAD_SOURCE_BOARD_UP; }
            if (out->bias_down_count) { out->source_mask |= ESP32_GPIO_PAD_SOURCE_BOARD_DOWN; }
            if (out->fun_pu) { out->source_mask |= ESP32_GPIO_PAD_SOURCE_IOMUX_UP; }
            if (out->fun_pd) { out->source_mask |= ESP32_GPIO_PAD_SOURCE_IOMUX_DOWN; }
            if (!out->pull_config_known) {
                out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_RESET_UNKNOWN;
            } else if (up && down) {
                out->conflict = true;
            } else if (up || down) {
                out->known = true;
                out->level = up;
            } else {
                out->source_mask |= ESP32_GPIO_PAD_SOURCE_LEGACY_FALLBACK;
                out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_FLOATING;
            }
        }
    }
    if (out->conflict) {
        out->known = false;
        out->blocker_mask |= ESP32_GPIO_PAD_BLOCK_CONFLICT;
    }
    if (!out->known) {
        /* Compatibility reads retain the previous resolver's value. It is
         * diagnostic only and must not confer a known Unit baseline.
         */
        out->level = !!(gpio_legacy_line64() & bit);
    }
    out->receiver_level = out->iomux_valid && !out->fun_ie ? false : out->level;
    out->receiver_known = out->iomux_valid && !out->fun_ie ? true :
                          out->known && !out->filter_en;
}

static uint32_t gpio_pad_changes(const Esp32GpioPadSnapshot *a,
                                 const Esp32GpioPadSnapshot *b)
{
    uint32_t changed = 0;
    if (a->level != b->level) { changed |= ESP32_GPIO_PAD_CHANGE_LEVEL; }
    if (a->known != b->known || a->conflict != b->conflict ||
        a->blocker_mask != b->blocker_mask || a->override_mask != b->override_mask) {
        changed |= ESP32_GPIO_PAD_CHANGE_KNOWN;
    }
    if (a->source_mask != b->source_mask) { changed |= ESP32_GPIO_PAD_CHANGE_SOURCE; }
    if (a->oe_known != b->oe_known || a->oe != b->oe ||
        a->drive_known != b->drive_known || a->drive_level != b->drive_level) {
        changed |= ESP32_GPIO_PAD_CHANGE_DRIVE;
    }
    if (a->out_sel != b->out_sel || a->out_inv != b->out_inv ||
        a->oen_sel != b->oen_sel || a->oen_inv != b->oen_inv) {
        changed |= ESP32_GPIO_PAD_CHANGE_ROUTE;
    }
    if (a->iomux_valid != b->iomux_valid || a->mcu_sel != b->mcu_sel ||
        a->mux_path != b->mux_path || a->fun_ie != b->fun_ie ||
        a->fun_pu != b->fun_pu || a->fun_pd != b->fun_pd ||
        a->slp_sel != b->slp_sel || a->filter_en != b->filter_en ||
        a->pull_config_known != b->pull_config_known) {
        changed |= ESP32_GPIO_PAD_CHANGE_IOMUX;
    }
    if (a->external_seen != b->external_seen || a->external_level != b->external_level) {
        changed |= ESP32_GPIO_PAD_CHANGE_EXTERNAL;
    }
    if (a->force_enabled != b->force_enabled || a->force_level != b->force_level) {
        changed |= ESP32_GPIO_PAD_CHANGE_FORCE;
    }
    if (a->open_drain != b->open_drain || a->pad_driver_reg != b->pad_driver_reg ||
        a->od_origin != b->od_origin) { changed |= ESP32_GPIO_PAD_CHANGE_OD; }
    if (a->bias_up_count != b->bias_up_count || a->bias_down_count != b->bias_down_count) {
        changed |= ESP32_GPIO_PAD_CHANGE_BIAS;
    }
    if (a->receiver_level != b->receiver_level || a->receiver_known != b->receiver_known) {
        changed |= ESP32_GPIO_PAD_CHANGE_RECEIVER;
    }
    if (a->out_latch != b->out_latch) { changed |= ESP32_GPIO_PAD_CHANGE_LATCH; }
    if (a->enable_reg != b->enable_reg) { changed |= ESP32_GPIO_PAD_CHANGE_ENABLE; }
    if (a->epoch != b->epoch || a->controller_generation != b->controller_generation) {
        changed |= ESP32_GPIO_PAD_CHANGE_RESET;
    }
    return changed;
}

Esp32GpioState *esp32_gpio_get_controller(bool s3)
{
    return g_gpio_device && g_gpio_s3 == s3 ? g_gpio_device : NULL;
}

bool esp32_gpio_pad_snapshot(Esp32GpioState *s, unsigned pin,
                             Esp32GpioPadSnapshot *snapshot)
{
    if (!snapshot || !gpio_pad_valid(s, pin)) { return false; }
    gpio_snapshot_internal(s, pin, snapshot);
    return true;
}

void esp32_gpio_capture_pads(Esp32GpioState *s,
                            Esp32GpioPadSnapshot before[54])
{
    for (unsigned pin = 0; pin < GPIO_NPINS; pin++) {
        gpio_snapshot_internal(s, pin, &before[pin]);
    }
}

void esp32_gpio_notify_pads(Esp32GpioState *s,
                           const Esp32GpioPadSnapshot before[54],
                           Esp32GpioPadCause cause)
{
    Esp32GpioPadEvent events[GPIO_NPINS];
    bool changed[GPIO_NPINS] = { false };
    assert(!g_pad_dispatch_depth);
    /* Commit all per-pin revisions before any consumer can query another
     * pin from a callback for this multi-pin register transaction.
     */
    for (unsigned pin = 0; pin < GPIO_NPINS; pin++) {
        if (!gpio_pad_valid(s, pin)) { continue; }
        Esp32GpioPadEvent *event = &events[pin];
        *event = (Esp32GpioPadEvent) { .cause = cause, .before = before[pin] };
        gpio_snapshot_internal(s, pin, &event->after);
        event->change_mask = gpio_pad_changes(&event->before, &event->after);
        if (!event->change_mask) { continue; }
        event->after.revision = ++g_pad_revision[pin];
        event->commit_sequence = ++g_pad_sequence;
        changed[pin] = true;
    }
    g_pad_dispatch_depth++;
    for (unsigned pin = 0; pin < GPIO_NPINS; pin++) {
        if (!changed[pin]) { continue; }
        for (Esp32GpioPadObserver *o = g_pad_observers; o; o = o->next) {
            if (o->gpio == s && o->pin == pin) { o->cb(o->opaque, &events[pin]); }
        }
    }
    g_pad_dispatch_depth--;
}

Esp32GpioPadObserver *esp32_gpio_observe_pad(
    Esp32GpioState *s, unsigned pin, Esp32GpioPadObserverFn cb, void *opaque,
    Esp32GpioPadSnapshot *initial_out, Error **errp)
{
    if (!gpio_pad_valid(s, pin) || !cb || !initial_out || g_pad_dispatch_depth) {
        error_setg(errp, "invalid GPIO pad observer registration");
        return NULL;
    }
    unsigned count = 0;
    for (Esp32GpioPadObserver *o = g_pad_observers; o; o = o->next) {
        if (o->gpio == s && o->pin == pin) { count++; }
    }
    if (count >= GPIO_PAD_OBSERVERS_PER_PIN) {
        error_setg(errp, "GPIO pad observer capacity exceeded for pin %u", pin);
        return NULL;
    }
    Esp32GpioPadObserver *o = g_new0(Esp32GpioPadObserver, 1);
    o->gpio = s; o->pin = pin; o->cb = cb; o->opaque = opaque;
    object_ref(OBJECT(s));
    o->next = g_pad_observers; g_pad_observers = o;
    gpio_snapshot_internal(s, pin, initial_out);
    return o;
}

void esp32_gpio_unobserve_pad(Esp32GpioPadObserver *observer)
{
    if (!observer) { return; }
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadObserver **link = &g_pad_observers;
    while (*link && *link != observer) { link = &(*link)->next; }
    if (!*link) { return; }
    *link = observer->next;
    Esp32GpioState *s = observer->gpio;
    g_free(observer);
    object_unref(OBJECT(s));
}

Esp32GpioBoardBias *esp32_gpio_add_board_bias(
    Esp32GpioState *s, unsigned pin, Esp32GpioBias bias,
    const void *owner, Error **errp)
{
    if (!gpio_pad_valid(s, pin) || !owner || g_pad_dispatch_depth ||
        (bias != ESP32_GPIO_BIAS_PULL_UP && bias != ESP32_GPIO_BIAS_PULL_DOWN)) {
        error_setg(errp, "invalid GPIO board bias registration");
        return NULL;
    }
    unsigned count = 0;
    for (Esp32GpioBoardBias *b = g_board_biases; b; b = b->next) {
        if (b->gpio == s && b->pin == pin) {
            if (b->owner == owner) {
                error_setg(errp, "GPIO board bias owner already registered on pin %u", pin);
                return NULL;
            }
            count++;
        }
    }
    if (count >= GPIO_PAD_OBSERVERS_PER_PIN) {
        error_setg(errp, "GPIO board bias capacity exceeded for pin %u", pin);
        return NULL;
    }
    Esp32GpioPadSnapshot before[GPIO_NPINS];
    esp32_gpio_capture_pads(s, before);
    Esp32GpioBoardBias *b = g_new0(Esp32GpioBoardBias, 1);
    b->gpio = s; b->pin = pin; b->bias = bias; b->owner = owner;
    object_ref(OBJECT(s));
    b->next = g_board_biases; g_board_biases = b;
    esp32_gpio_notify_pads(s, before, ESP32_GPIO_PAD_BIAS_ADD);
    return b;
}

void esp32_gpio_remove_board_bias(Esp32GpioBoardBias *bias)
{
    if (!bias) { return; }
    assert(!g_pad_dispatch_depth);
    Esp32GpioBoardBias **link = &g_board_biases;
    while (*link && *link != bias) { link = &(*link)->next; }
    if (!*link) { return; }
    Esp32GpioState *s = bias->gpio;
    Esp32GpioPadSnapshot before[GPIO_NPINS];
    esp32_gpio_capture_pads(s, before);
    *link = bias->next;
    g_free(bias);
    esp32_gpio_notify_pads(s, before, ESP32_GPIO_PAD_BIAS_REMOVE);
    object_unref(OBJECT(s));
}


static int gpio_trace_pin(void)
{
    const char *value = getenv("M5SW_GPIO_TRACE_PIN");
    int pin = value ? atoi(value) : 18;

    return pin >= 0 && pin < GPIO_NPINS ? pin : 18;
}


void esp32_gpio_set_input(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) { return; }
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadSnapshot observed[GPIO_NPINS];
    esp32_gpio_capture_pads(g_gpio_device, observed);
    uint64_t before = gpio_line64();
    g_external_seen |= 1ULL << pin;
    if (level) { g_ext_in |= 1ULL << pin; }
    else { g_ext_in &= ~(1ULL << pin); }
    esp32_gpio_notify_pads(g_gpio_device, observed, ESP32_GPIO_PAD_EXTERNAL);
    gpio_transition_irq(before, gpio_line64());
    if (getenv("M5SW_GPIO_TRACE") &&
        (pin == 11 || pin == 12 || pin == gpio_trace_pin())) {
        fprintf(stderr, "[gpio] ext input pin=%d level=%d line=%d\n",
                pin, level, esp32_gpio_get_line(pin));
    }
}

void esp32_gpio_add_out_listener(int pin, esp32_gpio_out_cb cb, void *opaque)
{
    if (pin < 0 || pin >= GPIO_NPINS || !cb) {
        return;
    }
    if (g_listener_count[pin] >= GPIO_MAX_LISTENERS) {
        fprintf(stderr, "[gpio] listener overflow pin=%d\n", pin);
        return;
    }
    unsigned slot = g_listener_count[pin]++;
    g_listeners[pin][slot].cb = cb;
    g_listeners[pin][slot].opaque = opaque;
}


void esp32_gpio_set_open_drain(int pin, bool enable)
{
    if (pin < 0 || pin >= GPIO_NPINS) { return; }
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadSnapshot observed[GPIO_NPINS];
    esp32_gpio_capture_pads(g_gpio_device, observed);
    if (enable) { g_open_drain |= 1ULL << pin; }
    else { g_open_drain &= ~(1ULL << pin); }
    g_od_origin[pin] = ESP32_GPIO_OD_DIRECT;
    esp32_gpio_notify_pads(g_gpio_device, observed, ESP32_GPIO_PAD_DIRECT_OD);
}


void esp32_gpio_force_line(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) { return; }
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadSnapshot observed[GPIO_NPINS];
    esp32_gpio_capture_pads(g_gpio_device, observed);
    g_force_mask |= 1ULL << pin;
    if (level) { g_force_level |= 1ULL << pin; }
    else { g_force_level &= ~(1ULL << pin); }
    esp32_gpio_notify_pads(g_gpio_device, observed, ESP32_GPIO_PAD_FORCE);
}

int esp32_gpio_get_line(int pin)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return 1;
    }
    int level = (gpio_line64() >> pin) & 1;
    if (getenv("M5SW_GPIO_TRACE") && pin == gpio_trace_pin()) {
        fprintf(stderr, "[gpio] get pin=%d level=%d force=%d\n",
                pin, level, !!(g_force_mask & (1ULL << pin)));
    }
    return level;
}

static uint64_t gpio_out64(void)
{
    return (uint64_t)g_regs[0x04 / 4] | ((uint64_t)g_regs[0x10 / 4] << 32);
}

static uint64_t gpio_en64(void)
{
    return (uint64_t)g_regs[0x20 / 4] | ((uint64_t)g_regs[0x2c / 4] << 32);
}

/*
 * Effective pin level: driven output when the pin is enabled, otherwise
 * the board's external pull-up.  Software-I2C listeners need this rather
 * than the raw OUT register, because switching a pin between output-low
 * and input is a real bus transition.
 */
static uint64_t gpio_legacy_line64(void)
{
    uint64_t out = gpio_out64();
    uint64_t en = gpio_en64();
    uint64_t driven = out & en;

    /*
     * An open-drain output can only pull low: when its latch is high the
     * actual line level is determined by the external pull-up/devices.
     * This is what makes software-I2C acknowledge bits visible to the
     * master while it is releasing SDA.
     */
    uint64_t line = (driven & ~g_open_drain)
                  | ((driven & g_ext_in) & g_open_drain)
                  | (~en & g_ext_in);
    return (line & ~g_force_mask) | (g_force_level & g_force_mask);
}


static uint64_t gpio_line64(void)
{
    uint64_t line = gpio_legacy_line64();
    if (!g_gpio_device || !g_gpio_s3) { return line; }
    for (unsigned pin = 0; pin < 49; pin++) {
        if (!gpio_pad_valid(g_gpio_device, pin)) { continue; }
        Esp32GpioPadSnapshot state;
        gpio_snapshot_internal(g_gpio_device, pin, &state);
        if (state.known) {
            uint64_t bit = 1ULL << pin;
            line = state.level ? line | bit : line & ~bit;
        }
    }
    return line;
}

static uint64_t gpio_input64(void)
{
    uint64_t line = gpio_line64();
    if (g_gpio_s3) {
        line &= (1ULL << 49) - 1;
        for (unsigned pin = 0; pin < 49; pin++) {
            if (!gpio_pad_valid(g_gpio_device, pin) ||
                !(g_iomux_regs[pin] & (1u << 9))) {
                line &= ~(1ULL << pin);
            }
        }
    }
    return line;
}

static void gpio_update_irq(void)
{
    if (!g_gpio_device) { return; }
    uint64_t line = gpio_line64();
    unsigned base = g_gpio_s3 ? 0x74 : 0x88;
    for (int pin = 0; pin < (g_gpio_s3 ? 49 : 40); pin++) {
        uint32_t cfg = g_regs[(base + pin * 4) / 4];
        unsigned type = (cfg >> 7) & 7;
        if (((cfg >> 13) & 0x1f) &&
            ((type == 4 && !(line & (1ULL << pin))) ||
             (type == 5 && (line & (1ULL << pin))))) {
            g_regs[(pin < 32 ? 0x44 : 0x50) / 4] |= 1u << (pin & 31);
        }
    }
    qemu_set_irq(g_gpio_device->irq,
        !!(g_regs[0x44 / 4] | g_regs[0x50 / 4]));
}

static void gpio_transition_irq(uint64_t before, uint64_t after)
{
    uint64_t diff = before ^ after;
    unsigned base = g_gpio_s3 ? 0x74 : 0x88;
    for (int pin = 0; pin < (g_gpio_s3 ? 49 : 40); pin++) {
        if (!(diff & (1ULL << pin))) { continue; }
        uint32_t cfg = g_regs[(base + pin * 4) / 4];
        unsigned type = (cfg >> 7) & 7;
        bool high = (after >> pin) & 1;
        if (((cfg >> 13) & 0x1f) &&
            ((type == 1 && high) || (type == 2 && !high) || type == 3)) {
            g_regs[(pin < 32 ? 0x44 : 0x50) / 4] |= 1u << (pin & 31);
        }
    }
    gpio_update_irq();
}

static void gpio_notify(uint64_t before, uint64_t after)
{
    uint64_t diff = before ^ after;
    for (int i = 0; diff && i < GPIO_NPINS; i++) {
        if ((diff >> i) & 1) {
            for (int j = 0; j < g_listener_count[i]; j++) {
                if (g_listeners[i][j].cb) {
                    g_listeners[i][j].cb(g_listeners[i][j].opaque, i,
                                         (after >> i) & 1);
                }
            }
        }
    }
}

static uint64_t esp32_gpio_read(void *opaque, hwaddr addr, unsigned int size)
{
    Esp32GpioState *s = ESP32_GPIO(opaque);
    uint64_t in = gpio_input64();
    switch (addr) {
    case A_GPIO_STRAP:
        return s->strap_mode;
    case 0x3c: {
        int trace_pin = gpio_trace_pin();
        int trace_level = (in >> trace_pin) & 1;

        if (getenv("M5SW_GPIO_TRACE") &&
            trace_level != g_trace_last_level) {
            fprintf(stderr, "[gpio] in0=0x%08x pin%d=%d\n",
                    (uint32_t)in, trace_pin, trace_level);
            g_trace_last_level = trace_level;
        }
        return (uint32_t)in;
    }
    case 0x40:
        return (uint32_t)(in >> 32) & 0x3fffff;
    case 0x08: case 0x0c: case 0x14: case 0x18:
    case 0x24: case 0x28: case 0x30: case 0x34:
        return 0;
    default:
        if (addr == (g_gpio_s3 ? 0x5c : 0x68)) { return g_regs[0x44 / 4]; }
        if (addr == (g_gpio_s3 ? 0x68 : 0x7c)) { return g_regs[0x50 / 4]; }
        if (addr < sizeof(g_regs)) {
            return g_regs[addr / 4];
        }
        return 0;
    }
}

static void esp32_gpio_write(void *opaque, hwaddr addr,
                       uint64_t value, unsigned int size)
{
    Esp32GpioState *s = ESP32_GPIO(opaque);
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadSnapshot observed[GPIO_NPINS];
    esp32_gpio_capture_pads(s, observed);
    uint64_t before = gpio_line64();
    bool route_refresh = false;
    Esp32GpioPadCause cause = ESP32_GPIO_PAD_OUT;
    if (addr >= 0x20 && addr <= 0x34) { cause = ESP32_GPIO_PAD_ENABLE; }
    if (getenv("M5SW_GPIO_REG_TRACE") && addr >= 0x100 && addr < 0x140) {
        fprintf(stderr, "[gpio] wr addr=0x%03" HWADDR_PRIx
                " value=0x%08" PRIx64 "\n", addr, value);
    }
    switch (addr) {
    case 0x08: g_regs[0x04 / 4] |= value; break;
    case 0x0c: g_regs[0x04 / 4] &= ~value; break;
    case 0x14: g_regs[0x10 / 4] |= value; break;
    case 0x18: g_regs[0x10 / 4] &= ~value; break;
    case 0x24: g_regs[0x20 / 4] |= value; break;
    case 0x28: g_regs[0x20 / 4] &= ~value; break;
    case 0x30: g_regs[0x2c / 4] |= value; break;
    case 0x34: g_regs[0x2c / 4] &= ~value; break;
    case 0x48: g_regs[0x44 / 4] |= value; break;
    case 0x4c: g_regs[0x44 / 4] &= ~value; break;
    case 0x54: g_regs[0x50 / 4] |= value; break;
    case 0x58: g_regs[0x50 / 4] &= ~value; break;
    case A_GPIO_STRAP: case 0x3c: case 0x40:
        break;
    default:
        if (addr < sizeof(g_regs)) {
            uint32_t previous = g_regs[addr / 4];
            unsigned output_base = g_gpio_s3 ? 0x554 : 0x530;
            g_regs[addr / 4] = value;
            if (addr >= output_base &&
                addr < output_base + (g_gpio_s3 ? 49 : 40) * 4 &&
                ((previous ^ (uint32_t)value) & 0x3ff)) {
                route_refresh = true;
            }
            /*
             * GPIO_PIN0_REG starts at 0x74 on ESP32-S3.  M5GFX's
             * pinMode(input*) uses gpio_ll_od_enable(), which leaves the
             * output enable set and relies on open-drain + latch-high
             * semantics so an external low can still pull the line down.
             */
            if (addr >= output_base &&
                addr < output_base + (g_gpio_s3 ? 49 : 40) * 4) {
                cause = ESP32_GPIO_PAD_ROUTE;
            }
            unsigned pin_base = g_gpio_s3 ? 0x74 : 0x88;
            if (addr >= pin_base && addr < pin_base + GPIO_NPINS * 4) {
                unsigned pin = (addr - pin_base) / 4;
                uint64_t pin_bit = 1ULL << pin;
                cause = ESP32_GPIO_PAD_DRIVER;
                g_od_origin[pin] = ESP32_GPIO_OD_PAD_DRIVER;
                if (value & (1u << 2)) {
                    g_open_drain |= pin_bit;
                } else {
                    g_open_drain &= ~pin_bit;
                }
            }
        }
        break;
    }
    esp32_gpio_notify_pads(s, observed, cause);
    if (route_refresh) { esp32_ledc_gpio_route_changed(g_gpio_s3); }
    gpio_notify(before, gpio_line64());
    gpio_transition_irq(before, gpio_line64());
}

static const MemoryRegionOps uart_ops = {
    .read =  esp32_gpio_read,
    .write = esp32_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};


static void esp32_gpio_reset_hold(Object *obj, ResetType type)
{
    Esp32GpioState *s = ESP32_GPIO(obj);
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadSnapshot observed[GPIO_NPINS];
    esp32_gpio_capture_pads(s, observed);
    memset(g_regs, 0, sizeof(g_regs));
    g_open_drain = 0;
    memset(g_od_origin, ESP32_GPIO_OD_RESET, sizeof(g_od_origin));
    if (g_gpio_s3) {
        for (unsigned pin = 0; pin < 49; pin++) {
            g_regs[(0x554 + pin * 4) / 4] = 256;
        }
        gpio_iomux_reset();
    }
    g_pad_epoch++;
    esp32_gpio_notify_pads(s, observed, ESP32_GPIO_PAD_RESET);
    gpio_update_irq();
}

static void esp32_gpio_realize(DeviceState *dev, Error **errp)
{
}


static int gpio_iomux_pin(hwaddr addr)
{
    if (addr < 4 || addr > 4 + 48 * 4 || (addr & 3)) { return -1; }
    unsigned pin = (addr - 4) / 4;
    return g_gpio_s3 && (pin < 22 || pin > 25) ? pin : -1;
}

static uint64_t esp32_gpio_iomux_read(void *opaque, hwaddr addr, unsigned size)
{
    int pin = gpio_iomux_pin(addr);
    return pin >= 0 ? g_iomux_regs[pin] : 0;
}

static void esp32_gpio_iomux_write(void *opaque, hwaddr addr,
                                   uint64_t value, unsigned size)
{
    Esp32GpioState *s = ESP32_GPIO(opaque);
    int pin = gpio_iomux_pin(addr);
    if (pin < 0) { return; }
    assert(!g_pad_dispatch_depth);
    Esp32GpioPadSnapshot observed[GPIO_NPINS];
    esp32_gpio_capture_pads(s, observed);
    uint64_t before = gpio_line64();
    g_iomux_regs[pin] = value;
    g_iomux_pull_known[pin] = true;
    esp32_gpio_notify_pads(s, observed, ESP32_GPIO_PAD_IOMUX);
    gpio_notify(before, gpio_line64());
    gpio_transition_irq(before, gpio_line64());
}

static const MemoryRegionOps iomux_ops = {
    .read = esp32_gpio_iomux_read,
    .write = esp32_gpio_iomux_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
};

static void esp32_gpio_init(Object *obj)
{
    Esp32GpioState *s = ESP32_GPIO(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    g_gpio_device = s;
    g_gpio_s3 = object_dynamic_cast(obj, "esp32s3.gpio") != NULL;
    g_pad_generation++;
    g_pad_epoch = g_pad_sequence = 0;
    memset(g_pad_revision, 0, sizeof(g_pad_revision));
    g_external_seen = 0;
    if (g_gpio_s3) {
        gpio_iomux_reset();
        for (unsigned pin = 0; pin < 49; pin++) {
            g_regs[(0x554 + pin * 4) / 4] = 256;
        }
    }

    /* Set the default value for the strap_mode property */
    object_property_set_int(obj, "strap_mode", ESP32_STRAP_MODE_FLASH_BOOT, &error_fatal);

    memory_region_init_io(&s->iomem, obj, &uart_ops, s,
                          TYPE_ESP32_GPIO, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    memory_region_init_io(&s->iomux, obj, &iomux_ops, s,
                          "esp32s3.iomux", 0x2000);
    sysbus_init_mmio(sbd, &s->iomux);
    sysbus_init_irq(sbd, &s->irq);
}


static void esp32_gpio_finalize(Object *obj)
{
    if (g_gpio_device == ESP32_GPIO(obj)) {
        g_gpio_device = NULL;
    }
}

static Property esp32_gpio_properties[] = {
    /* The strap_mode needs to be explicitly set in the instance init, thus, set
     * the default value to 0. */
    DEFINE_PROP_UINT32("strap_mode", Esp32GpioState, strap_mode, 0),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32_gpio_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    rc->phases.hold = esp32_gpio_reset_hold;
    dc->realize = esp32_gpio_realize;
    device_class_set_props(dc, esp32_gpio_properties);
}

static const TypeInfo esp32_gpio_info = {
    .name = TYPE_ESP32_GPIO,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32GpioState),
    .instance_init = esp32_gpio_init,
    .instance_finalize = esp32_gpio_finalize,
    .class_init = esp32_gpio_class_init,
    .class_size = sizeof(Esp32GpioClass),
};

static void esp32_gpio_register_types(void)
{
    type_register_static(&esp32_gpio_info);
}

type_init(esp32_gpio_register_types)

/* ESP-IDF GPIO matrix register/signal maps, v5.5: S3 I2C 89..92,
 * classic ESP32 29/30 and 95/96. Both input and output routes must match.
 */
bool esp32_gpio_matrix_i2c_pins(unsigned controller, bool s3, int *sda, int *scl)
{
    unsigned scl_signal = s3 ? 89 + controller * 2 : (controller ? 95 : 29);
    unsigned sda_signal = scl_signal + 1;
    unsigned input_base = s3 ? 0x154 : 0x130;
    unsigned output_base = s3 ? 0x554 : 0x530;
    uint32_t scl_input = g_regs[(input_base + scl_signal * 4) / 4];
    uint32_t sda_input = g_regs[(input_base + sda_signal * 4) / 4];
    *scl = scl_input & 0x3f;
    *sda = sda_input & 0x3f;
    return controller < 2 && (scl_input & 0xc0) == 0x80 &&
           (sda_input & 0xc0) == 0x80 && *scl < (s3 ? 49 : 40) &&
           *sda < (s3 ? 49 : 40) &&
           (g_regs[(output_base + *scl * 4) / 4] & 0x3ff) == scl_signal &&
           (g_regs[(output_base + *sda * 4) / 4] & 0x3ff) == sda_signal;
}

int esp32_gpio_matrix_out_signal(int pin, bool s3)
{
    if (pin < 0 || pin >= (s3 ? 49 : 40)) { return -1; }
    uint32_t value = g_regs[((s3 ? 0x554 : 0x530) + pin * 4) / 4];
    return (value & BIT(9)) ? -1 : value & 0x1ff;
}
int esp32_gpio_matrix_in_pin(unsigned signal, bool s3)
{
    if (signal > 190) { return -1; }
    uint32_t value = g_regs[((s3 ? 0x154 : 0x130) + signal * 4) / 4];
    return (value & 0xc0) == 0x80 ? value & 0x3f : -1;
}

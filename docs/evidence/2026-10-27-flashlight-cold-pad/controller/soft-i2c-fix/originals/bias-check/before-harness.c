
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
#include <stdarg.h>
#define BIT(n) (1ULL << (n))
#define QEMU_CLOCK_VIRTUAL 1
#define A_GPIO_STRAP 0x38
#define HWADDR_PRIx PRIx64
#define g_new0(t,n) ((t *)calloc((n),sizeof(t)))
#define g_free free
typedef uint64_t hwaddr;
typedef int ResetType;
typedef struct Error { int unused; } Error;
typedef struct Esp32GpioState { unsigned refs;int irq;uint32_t strap_mode; } Esp32GpioState;
typedef Esp32GpioState Object;
#define OBJECT(v) ((Object *)(v))
#define ESP32_GPIO(v) ((Esp32GpioState *)(v))
static void object_ref(Object *s) { s->refs++; }
static void object_unref(Object *s) { assert(s->refs);s->refs--; }
static Error error_record;
static void error_setg(Error **e,const char *fmt,...) { if(e)*e=&error_record; }
static int64_t virtual_now;
static int64_t qemu_clock_get_ns(int id) { assert(id==1);return virtual_now; }
static int irq_calls,last_irq;
static void qemu_set_irq(int irq,int value) { irq_calls++;last_irq=value; }
static unsigned ledc_refreshes;
static void esp32_ledc_gpio_route_changed(bool s3) { ledc_refreshes++; }
typedef void (*esp32_gpio_out_cb)(void *,int,int);
void esp32_gpio_set_input(int pin,int level);
int esp32_gpio_get_line(int pin);
static uint32_t overrides[54];
static uint32_t esp32s3_gpio_pad_aux_blockers(Esp32GpioState *s,unsigned pin) { return overrides[pin]; }

#define ESP32_GPIO_PAD_SOURCE_GPIO             (1u << 0)
#define ESP32_GPIO_PAD_SOURCE_EXTERNAL         (1u << 1)
#define ESP32_GPIO_PAD_SOURCE_FORCE            (1u << 2)
#define ESP32_GPIO_PAD_SOURCE_BOARD_UP         (1u << 3)
#define ESP32_GPIO_PAD_SOURCE_BOARD_DOWN       (1u << 4)
#define ESP32_GPIO_PAD_SOURCE_IOMUX_UP         (1u << 5)
#define ESP32_GPIO_PAD_SOURCE_IOMUX_DOWN       (1u << 6)
#define ESP32_GPIO_PAD_SOURCE_LEGACY_FALLBACK   (1u << 7)

#define ESP32_GPIO_PAD_BLOCK_MUX               (1u << 0)
#define ESP32_GPIO_PAD_BLOCK_PERIPHERAL_DATA   (1u << 1)
#define ESP32_GPIO_PAD_BLOCK_PERIPHERAL_OE     (1u << 2)
#define ESP32_GPIO_PAD_BLOCK_OVERRIDE          (1u << 3)
#define ESP32_GPIO_PAD_BLOCK_FLOATING          (1u << 4)
#define ESP32_GPIO_PAD_BLOCK_CONFLICT          (1u << 5)
#define ESP32_GPIO_PAD_BLOCK_RESET_UNKNOWN     (1u << 6)

#define ESP32_GPIO_PAD_CHANGE_LEVEL            (1u << 0)
#define ESP32_GPIO_PAD_CHANGE_KNOWN            (1u << 1)
#define ESP32_GPIO_PAD_CHANGE_SOURCE           (1u << 2)
#define ESP32_GPIO_PAD_CHANGE_DRIVE            (1u << 3)
#define ESP32_GPIO_PAD_CHANGE_ROUTE            (1u << 4)
#define ESP32_GPIO_PAD_CHANGE_IOMUX            (1u << 5)
#define ESP32_GPIO_PAD_CHANGE_EXTERNAL         (1u << 6)
#define ESP32_GPIO_PAD_CHANGE_FORCE            (1u << 7)
#define ESP32_GPIO_PAD_CHANGE_OD               (1u << 8)
#define ESP32_GPIO_PAD_CHANGE_BIAS             (1u << 9)
#define ESP32_GPIO_PAD_CHANGE_RESET            (1u << 10)
#define ESP32_GPIO_PAD_CHANGE_RECEIVER         (1u << 11)
#define ESP32_GPIO_PAD_CHANGE_LATCH            (1u << 12)
#define ESP32_GPIO_PAD_CHANGE_ENABLE           (1u << 13)

typedef struct Esp32GpioPadObserver Esp32GpioPadObserver;
typedef struct Esp32GpioBoardBias Esp32GpioBoardBias;

typedef enum Esp32GpioPadCause {
    ESP32_GPIO_PAD_OUT, ESP32_GPIO_PAD_ENABLE, ESP32_GPIO_PAD_DRIVER,
    ESP32_GPIO_PAD_ROUTE, ESP32_GPIO_PAD_EXTERNAL, ESP32_GPIO_PAD_FORCE,
    ESP32_GPIO_PAD_DIRECT_OD, ESP32_GPIO_PAD_RESET, ESP32_GPIO_PAD_IOMUX,
    ESP32_GPIO_PAD_BIAS_ADD, ESP32_GPIO_PAD_BIAS_REMOVE,
    ESP32_GPIO_PAD_OVERRIDE,
} Esp32GpioPadCause;

typedef enum Esp32GpioBias {
    ESP32_GPIO_BIAS_PULL_UP, ESP32_GPIO_BIAS_PULL_DOWN,
} Esp32GpioBias;

typedef enum Esp32GpioOdOrigin {
    ESP32_GPIO_OD_RESET, ESP32_GPIO_OD_PAD_DRIVER, ESP32_GPIO_OD_DIRECT,
} Esp32GpioOdOrigin;

/* source_mask: GPIO_DRIVE, EXTERNAL, FORCE, BOARD_UP, BOARD_DOWN,
 * IOMUX_UP, IOMUX_DOWN, LEGACY_FALLBACK. Compatible sources may coexist.
 * blocker_mask: MUX_UNSUPPORTED, PERIPHERAL_DATA, PERIPHERAL_OE,
 * SLEEP_OR_OVERRIDE_UNMODELED, FLOATING_DEFAULT, SOURCE_CONFLICT.
 * Named constants will be uint32_t bits in the implementation header.
 */
typedef enum Esp32GpioMuxPath {
    ESP32_GPIO_MUX_GPIO_MATRIX,
    ESP32_GPIO_MUX_GPIO_ALIAS,
    ESP32_GPIO_MUX_OTHER_UNMODELED,
    ESP32_GPIO_MUX_UNRESOLVED,
} Esp32GpioMuxPath;

typedef struct Esp32GpioPadSnapshot {
    unsigned pin;
    bool s3;
    uint64_t controller_generation; /* Lifetime identity, not a physical ID. */
    uint64_t epoch;                 /* Incremented only by controller reset. */
    uint64_t revision;              /* This pin's meaningful committed facts. */
    int64_t at_ns;                  /* QEMU_CLOCK_VIRTUAL commit time. */
    bool level, known, conflict;
    bool receiver_level, receiver_known; /* IN receiver; distinct from pad. */
    uint32_t source_mask, blocker_mask, override_mask;
    bool out_latch, enable_reg;
    uint16_t out_sel;
    bool out_inv, oen_sel, oen_inv;
    bool oe_known, oe, drive_known, drive_level;
    bool open_drain, pad_driver_reg;
    Esp32GpioOdOrigin od_origin;    /* Last actual effective-OD writer. */
    bool iomux_valid;              /* Implemented pin/register, not a guess. */
    uint8_t mcu_sel;
    Esp32GpioMuxPath mux_path;      /* Per-pin function map, not mcu_sel==1. */
    bool fun_ie, fun_pu, fun_pd, slp_sel, filter_en;
    bool pull_config_known;
    bool external_seen, external_level;
    bool force_enabled, force_level;
    unsigned bias_up_count, bias_down_count;
} Esp32GpioPadSnapshot;

typedef struct Esp32GpioPadEvent {
    Esp32GpioPadCause cause;
    uint32_t change_mask;           /* Actual changed facts, not a write mask. */
    uint64_t commit_sequence;       /* Total order, including nested commits. */
    Esp32GpioPadSnapshot before, after;
} Esp32GpioPadEvent;

typedef void (*Esp32GpioPadObserverFn)(void *opaque,
                                     const Esp32GpioPadEvent *event);

/* Borrowed current controller, matching the active singleton layout.
 * NULL on absent/mismatching controller; never aliases another SoC layout.
 */
Esp32GpioState *esp32_gpio_get_controller(bool s3);
/* Pure read. Invalid pin/controller returns false, not a fabricated low. */
bool esp32_gpio_pad_snapshot(Esp32GpioState *s, unsigned pin,
                             Esp32GpioPadSnapshot *snapshot);
/* Atomically register and return the current baseline in initial_out.
 * Registration makes NO callback and supplies NO synthetic pad edge.
 * Callback event memory is borrowed for the synchronous call only.
 */
Esp32GpioPadObserver *esp32_gpio_observe_pad(
    Esp32GpioState *s, unsigned pin, Esp32GpioPadObserverFn cb, void *opaque,
    Esp32GpioPadSnapshot *initial_out, Error **errp);
void esp32_gpio_unobserve_pad(Esp32GpioPadObserver *observer);
/* One separately owned passive board bias. Multiple conflicting passive
 * biases resolve unknown; do not silently overwrite external_input storage.
 * Owner identity is opaque, never dereferenced; caller removes on unrealize.
 */
Esp32GpioBoardBias *esp32_gpio_add_board_bias(
    Esp32GpioState *s, unsigned pin, Esp32GpioBias bias,
    const void *owner, Error **errp);
void esp32_gpio_remove_board_bias(Esp32GpioBoardBias *bias);

/* Internal bridges for controller-owned auxiliary MMIO writers only. */
void esp32_gpio_capture_pads(Esp32GpioState *s,
                            Esp32GpioPadSnapshot before[54]);
void esp32_gpio_notify_pads(Esp32GpioState *s,
                           const Esp32GpioPadSnapshot before[54],
                           Esp32GpioPadCause cause);

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



static Esp32GpioState controller;
static Esp32GpioPadEvent seen[8192];static unsigned seen_count,legacy_edges;
static void observe(void *opaque,const Esp32GpioPadEvent *e) { assert(seen_count<8192);seen[seen_count++]=*e; }
static void legacy(void *opaque,int pin,int value) { legacy_edges++; }
static void fresh(void) {
 assert(!g_pad_observers&&!g_board_biases);memset(&controller,0,sizeof(controller));controller.refs=1;
 g_gpio_device=&controller;g_gpio_s3=true;g_ext_in=~0ULL;g_external_seen=0;g_force_mask=g_force_level=0;
 memset(g_regs,0,sizeof(g_regs));g_open_drain=0;memset(overrides,0,sizeof(overrides));memset(g_listeners,0,sizeof(g_listeners));memset(g_listener_count,0,sizeof(g_listener_count));
 memset(g_pad_revision,0,sizeof(g_pad_revision));g_pad_generation++;g_pad_epoch=g_pad_sequence=0;g_pad_dispatch_depth=0;virtual_now=0;
 esp32_gpio_reset_hold(OBJECT(&controller),0);seen_count=legacy_edges=ledc_refreshes=0;
}
static Esp32GpioPadSnapshot snap(unsigned pin) { Esp32GpioPadSnapshot v;assert(esp32_gpio_pad_snapshot(&controller,pin,&v));return v; }
static Esp32GpioPadObserver *watch(unsigned pin) { Esp32GpioPadSnapshot init;Error *e=NULL;Esp32GpioPadObserver *o=esp32_gpio_observe_pad(&controller,pin,observe,NULL,&init,&e);assert(o&&!e);return o; }
static void mux(unsigned pin,uint32_t raw) { esp32_gpio_iomux_write(&controller,4+pin*4,raw,4); }
static void mmio(hwaddr addr,uint32_t raw) { esp32_gpio_write(&controller,addr,raw,4); }
static Esp32GpioBoardBias *down(unsigned pin,const void *owner) { Error *e=NULL;Esp32GpioBoardBias*b=esp32_gpio_add_board_bias(&controller,pin,ESP32_GPIO_BIAS_PULL_DOWN,owner,&e);assert(b&&!e);return b; }
static void basic(void) {
 fresh();Esp32GpioPadSnapshot v=snap(2);assert(!v.known&&v.external_seen==false&&v.out_sel==256&&v.fun_ie);assert(snap(0).fun_pu);assert(!snap(4).fun_ie);assert(snap(45).fun_pd);assert(!snap(39).pull_config_known);assert(((g_iomux_regs[19]>>10)&3)==3);assert(!(gpio_en64()&(1ULL<<43)));
 assert(esp32_gpio_get_controller(true)==&controller&&!esp32_gpio_get_controller(false));assert(!esp32_gpio_pad_snapshot(&controller,22,&v));assert(!esp32_gpio_pad_snapshot(&controller,25,&v));
 int owner=0;Esp32GpioBoardBias*b=down(2,&owner);v=snap(2);assert(v.known&&!v.level&&!v.external_seen&&esp32_gpio_get_line(2)==0);
 Esp32GpioPadObserver*o=watch(2);assert(seen_count==0);uint64_t rev=v.revision;v=snap(2);assert(v.revision==rev&&seen_count==0);
 esp32_gpio_add_out_listener(2,legacy,NULL);mux(2,(1u<<12)|(1u<<9)|(2u<<10));assert(seen_count==1&&legacy_edges==0);mmio(0x24,1u<<2);assert(snap(2).known&&!snap(2).level&&legacy_edges==0);
 mmio(0x08,1u<<2);assert(snap(2).known&&snap(2).level&&legacy_edges==1);unsigned n=seen_count;
 mmio(0x08,1u<<2);assert(seen_count==n&&legacy_edges==1);
 mmio(0x554+2*4,256|(1u<<10));assert(snap(2).known&&snap(2).level&&legacy_edges==1);assert(seen[seen_count-1].change_mask==ESP32_GPIO_PAD_CHANGE_ROUTE);assert(ledc_refreshes==0);
 mmio(0x554+2*4,256|(1u<<10)|(1u<<9));assert(snap(2).known&&!snap(2).level&&legacy_edges==2);
 uint64_t epoch=snap(2).epoch;esp32_gpio_reset_hold(OBJECT(&controller),0);assert(snap(2).epoch==epoch+1&&snap(2).known&&!snap(2).level&&legacy_edges==2);
 esp32_gpio_unobserve_pad(o);esp32_gpio_remove_board_bias(b);assert(controller.refs==1);
}
static void truth(void) {
 unsigned checks=0;
 for(unsigned os=0;os<2;os++)for(unsigned oi=0;oi<2;oi++)for(unsigned ei=0;ei<2;ei++)for(unsigned en=0;en<2;en++)for(unsigned latch=0;latch<2;latch++)for(unsigned od=0;od<2;od++){
  fresh();int owner=0;Esp32GpioBoardBias*b=down(2,&owner);mux(2,(1u<<12)|(1u<<9));mmio(0x04,latch<<2);mmio(0x20,en<<2);mmio(0x74+2*4,od<<2);mmio(0x554+2*4,256|(os<<10)|(oi<<9)|(ei<<11));
  Esp32GpioPadSnapshot v=snap(2);bool data=latch^oi,oe=en^ei;bool expected=oe&&(!od||!data)?data:false;
  assert(v.oe_known&&v.oe==oe&&v.drive_known&&v.drive_level==data&&v.known&&v.level==expected);assert(esp32_gpio_get_line(2)==expected);assert(!!(esp32_gpio_read(&controller,0x3c,4)&(1u<<2))==expected);
  mux(2,1u<<12);assert(snap(2).level==expected&&snap(2).receiver_level==0&&snap(2).receiver_known);assert(!(esp32_gpio_read(&controller,0x3c,4)&(1u<<2)));esp32_gpio_remove_board_bias(b);checks++;
 }
 assert(checks==64);
}
static void peripheral(void) {
 fresh();int owner=0;Esp32GpioBoardBias*b=down(2,&owner);mux(2,(1u<<12)|(1u<<9));
 mmio(0x554+2*4,73|(1u<<10));assert(snap(2).oe_known&&!snap(2).oe&&snap(2).known&&!snap(2).level);
 mmio(0x24,1u<<2);assert(!snap(2).known&&(snap(2).blocker_mask&ESP32_GPIO_PAD_BLOCK_PERIPHERAL_DATA));
 mmio(0x28,1u<<2);mmio(0x554+2*4,73);assert(!snap(2).oe_known&&!snap(2).known&&(snap(2).blocker_mask&ESP32_GPIO_PAD_BLOCK_PERIPHERAL_OE));
 mmio(0x554+2*4,256);mux(2,1u<<9);assert(snap(2).known&&snap(2).mux_path==ESP32_GPIO_MUX_GPIO_ALIAS);mmio(0x554+2*4,256|(1u<<9));assert(!snap(2).known);
 mux(2,(1u<<12)|(1u<<9));assert(snap(2).known);esp32_gpio_remove_board_bias(b);
}
static void helper_commits(void) {
 fresh();int owner=0;Esp32GpioBoardBias*b=down(2,&owner);Esp32GpioPadObserver*o=watch(2);esp32_gpio_add_out_listener(2,legacy,NULL);
 esp32_gpio_set_input(2,0);assert(seen_count==1&&seen[0].cause==ESP32_GPIO_PAD_EXTERNAL&&legacy_edges==0);unsigned n=seen_count;esp32_gpio_set_input(2,0);assert(seen_count==n);
 esp32_gpio_set_input(2,1);assert(snap(2).known&&snap(2).level&&legacy_edges==0);
 esp32_gpio_force_line(2,0);assert(!snap(2).known&&snap(2).conflict&&legacy_edges==0);n=seen_count;esp32_gpio_force_line(2,0);assert(seen_count==n);
 esp32_gpio_set_open_drain(2,true);assert(seen[seen_count-1].cause==ESP32_GPIO_PAD_DIRECT_OD&&legacy_edges==0);n=seen_count;esp32_gpio_set_open_drain(2,true);assert(seen_count==n);
 esp32_gpio_unobserve_pad(o);esp32_gpio_remove_board_bias(b);assert(controller.refs==1);
}
static void bias_conflict(void) {
 fresh();int a=0,b=0;Esp32GpioBoardBias*d=down(2,&a);Esp32GpioPadObserver*o=watch(2);Error*e=NULL;Esp32GpioBoardBias*u=esp32_gpio_add_board_bias(&controller,2,ESP32_GPIO_BIAS_PULL_UP,&b,&e);assert(u&&!e&&!snap(2).known&&snap(2).conflict);
 mux(2,(1u<<12)|(1u<<9));mmio(0x24,1u<<2);assert(snap(2).known&&!snap(2).level);mmio(0x28,1u<<2);assert(!snap(2).known);
 esp32_gpio_remove_board_bias(u);assert(snap(2).known&&!snap(2).level);esp32_gpio_unobserve_pad(o);esp32_gpio_remove_board_bias(d);assert(controller.refs==1);
}
static void overrides_and_isolation(void) {
 fresh();int owner=0;Esp32GpioBoardBias*b=down(2,&owner);Esp32GpioPadObserver*o=watch(2);uint64_t rev=snap(2).revision;
 mmio(0x08,1u<<3);assert(seen_count==0&&snap(2).revision==rev);mux(22,1u<<12);assert(seen_count==0);Esp32GpioPadSnapshot before[54];esp32_gpio_capture_pads(&controller,before);overrides[2]=1;esp32_gpio_notify_pads(&controller,before,ESP32_GPIO_PAD_OVERRIDE);assert(!snap(2).known&&snap(2).override_mask==1&&seen_count==1);
 esp32_gpio_capture_pads(&controller,before);overrides[2]=0;esp32_gpio_notify_pads(&controller,before,ESP32_GPIO_PAD_OVERRIDE);assert(snap(2).known&&!snap(2).level&&seen_count==2);
 esp32_gpio_unobserve_pad(o);esp32_gpio_remove_board_bias(b);
}
static void nested_legacy(void *opaque,int pin,int value) { esp32_gpio_set_input(3,0); }
static void ordering(void) {
 fresh();int owner=0;Esp32GpioBoardBias*b=down(2,&owner);Esp32GpioPadObserver*a=watch(2),*c=watch(3);mux(2,(1u<<12)|(1u<<9));mmio(0x24,1u<<2);seen_count=0;esp32_gpio_add_out_listener(2,nested_legacy,NULL);mmio(0x08,1u<<2);
 assert(seen_count==2&&seen[0].after.pin==2&&seen[1].after.pin==3&&seen[0].commit_sequence<seen[1].commit_sequence);assert(seen[0].after.revision>seen[0].before.revision);
 esp32_gpio_unobserve_pad(a);esp32_gpio_unobserve_pad(c);esp32_gpio_remove_board_bias(b);
}
static void capacity(void) {
 fresh();Esp32GpioPadObserver*observers[8];for(unsigned i=0;i<8;i++)observers[i]=watch(2);Esp32GpioPadSnapshot initial;Error*e=NULL;assert(!esp32_gpio_observe_pad(&controller,2,observe,NULL,&initial,&e)&&e);for(unsigned i=0;i<8;i++)esp32_gpio_unobserve_pad(observers[i]);assert(controller.refs==1);
}

static void external_conflict(void) {
 unsigned failures=0;
 for(unsigned test=0;test<3;test++) {
  fresh();mux(2,(1u<<12)|(1u<<9));mmio(0x04,(test==0?1u:0u)<<2);mmio(0x24,1u<<2);
  if(test==2)mmio(0x74+2*4,1u<<2);
  esp32_gpio_set_input(2,test==0?0:1);Esp32GpioPadSnapshot v=snap(2);
  printf("external-opposition case=%u known=%d conflict=%d pad=%d compat=%d\n",test,v.known,v.conflict,v.level,esp32_gpio_get_line(2));
  if(v.known||!v.conflict)failures++;
  esp32_gpio_set_input(2,test==0?1:0);v=snap(2);assert(v.known&&!v.conflict);
 }
 fflush(stdout);assert(failures==0);
}


typedef struct I2CBus { unsigned calls; } I2CBus;
static Error *error_fatal;
static int i2c_start_transfer(I2CBus *s,int addr,int read) { s->calls++;return 0; }
static void i2c_end_transfer(I2CBus *s) { s->calls++; }
static int i2c_send(I2CBus *s,int byte) { s->calls++;return 0; }
static int i2c_recv(I2CBus *s) { s->calls++;return 0xff; }
static void i2c_nack(I2CBus *s) { s->calls++; }
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
static void tested_pinmode(unsigned pin,int mode) {
 uint32_t val=g_iomux_regs[pin];val &= ~((1u<<8)|(1u<<7)|(1u<<3)|(1u<<2));
 if(mode==1)val|=(1u<<7)|(1u<<2);if(mode==2)val|=(1u<<8)|(1u<<3);
 val&=~(7u<<12);val|=(1u<<9)|(1u<<12);mux(pin,val);
 uint32_t cfg=g_regs[(0x74+pin*4)/4];mmio(0x74+pin*4,mode?cfg|(1u<<2):cfg&~(1u<<2));
 if(mode)mmio(pin<32?0x08:0x14,1u<<(pin&31));
 mmio(pin<32?0x24:0x30,1u<<(pin&31));mmio(0x554+pin*4,256);
}
static unsigned read_pin(unsigned pin) { return !!(gpio_input64()&(1ULL<<pin)); }
static void latch_low(unsigned pin) { mmio(pin<32?0x0c:0x18,1u<<(pin&31)); }
static void latch_high(unsigned pin) { mmio(pin<32?0x08:0x14,1u<<(pin&31)); }
static void dispose_for_host_test(M5StopwatchSoftI2C *s) {
 /* Only the host harness has reset the listener table. Product bridge has
  * process lifetime and no dynamic teardown API. Do not infer hot-unplug. */
 memset(g_listeners,0,sizeof(g_listeners));memset(g_listener_count,0,sizeof(g_listener_count));
#if WITH_PULLUPS
 esp32_gpio_remove_board_bias(s->sda_pullup);
 assert(snap(s->scl_pin).bias_up_count==1);
 esp32_gpio_remove_board_bias(s->scl_pullup);
#endif
 soft_i2c_instance=NULL;free(s);assert(controller.refs==1);
}
static void s3_case(unsigned sda,unsigned scl,const char *name) {
 fresh();I2CBus bus={0};m5stopwatch_soft_i2c_init_pins(&bus,sda,scl);
 M5StopwatchSoftI2C *s=soft_i2c_instance;assert(s&&s->bus==&bus&&!error_fatal);
#if WITH_PULLUPS
 assert(s->sda_pullup&&s->scl_pullup&&controller.refs==3);
 assert(snap(sda).bias_up_count==1&&snap(scl).bias_up_count==1);
 assert(!snap(scl).external_seen&&!snap(scl).force_enabled);
#endif
 tested_pinmode(scl,0);tested_pinmode(sda,0);
 for(unsigned i=0;i<8;i++) {
  latch_low(scl);latch_low(sda);latch_high(scl);latch_high(sda);
 }
 unsigned reads=0;latch_low(scl);reads=(reads<<1)|read_pin(scl);
 latch_low(sda);reads=(reads<<1)|read_pin(sda);
 tested_pinmode(scl,1);Esp32GpioPadSnapshot p=snap(scl);
 reads=(reads<<1)|read_pin(scl);tested_pinmode(scl,2);
 tested_pinmode(sda,1);reads=(reads<<1)|read_pin(sda);tested_pinmode(sda,2);
 printf("case=%s sda=%u scl=%u pullups=%u probe_reads=0x%x scl_known=%u conflict=%u board_up=%u external=%u ie=%u\n",name,sda,scl,WITH_PULLUPS,reads,p.known,p.conflict,p.bias_up_count,p.external_seen,p.fun_ie);
#if WITH_PULLUPS
 assert(reads==3&&!p.known&&p.conflict&&p.bias_up_count==1&&!p.external_seen&&p.fun_ie);
 m5stopwatch_soft_i2c_set_hardware_active_on_bus(&bus);
 assert(s->hardware_active&&snap(sda).bias_up_count==1&&snap(scl).bias_up_count==1);
 esp32_gpio_reset_hold(OBJECT(&controller),0);
 assert(snap(sda).bias_up_count==1&&snap(scl).bias_up_count==1);
#else
 assert(reads!=3&&p.known&&!p.level&&!p.bias_up_count&&p.fun_ie);
#endif
 dispose_for_host_test(s);
}
static void esp32_case(void) {
 fresh();g_gpio_s3=false;esp32_gpio_reset_hold(OBJECT(&controller),0);
 I2CBus bus={0};m5stopwatch_soft_i2c_init_pins(&bus,21,22);
 M5StopwatchSoftI2C *s=soft_i2c_instance;
 assert(!error_fatal&&esp32_gpio_get_line(21)==1&&esp32_gpio_get_line(22)==1);
 printf("case=core2 sda=21 scl=22 pullups=%u legacy_levels=%d,%d\n",WITH_PULLUPS,esp32_gpio_get_line(21),esp32_gpio_get_line(22));
 dispose_for_host_test(s);
}
int main(void) {
 s3_case(12,11,"cores3-stackchan");s3_case(47,48,"stopwatch-atoms3r-sticks3-papermono");
 s3_case(3,2,"papercolor");s3_case(2,1,"unit-bus");esp32_case();return 0;
}

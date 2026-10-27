/* External Grove GPIO/ADC/PWM/RMT/UART endpoints. GPL-2.0-or-later. */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "qapi/visitor.h"
#include "qapi/qmp/qlist.h"
#include "qapi/qmp/qnum.h"
#include "qapi/qmp/qstring.h"
#include "hw/char/esp32_uart.h"
#include "hw/gpio/esp32_gpio.h"
#include "m5stopwatch.h"
#include "m5_unit_runtime.h"
#include <math.h>

typedef struct AW3641State AW3641State;

typedef struct GPIOUnit {
    M5Unit *unit;
    AW3641State *flashlight;
    struct GPIOUnit *next;
    bool s3, red, blue, motion, digital;
    double voltage, duty, frequency;
    unsigned pwm_signal;
    QEMUTimer *hold_timer;
    int64_t hold_until;
    uint32_t rgb[3];
    unsigned leds;
    uint64_t frames, incomplete_frames, adc_samples;
    uint32_t rx_pulses[192], tx_pulses[192];
    unsigned rx_count, tx_count;
    uint8_t uart_tx[4096];
    size_t uart_tx_size;
    char *last_rx;
} GPIOUnit;
static GPIOUnit *gpio_units;

/* BEGIN AW3641 NOMINAL DIGITAL MODEL
 * U152 official schematic: yellow EN, white NC, EN 10K pull-down; S1 is
 * internal FLASH/TORCH, not a guest input. AW3641E Feb 2019 V1.3 pp12-14,
 * Table 1 and Fig 7: pulses 1..8 -> 100..30% / 220ms, 9..16 -> 1.3s.
 * Source SHA256 ff6ee09ea120f612f43c39af6318d98e86a778d9cb3ecf1e643d794a94c52a6e.
 * This PARTIAL model qualifies only the recommended 0.75..10us bitbang
 * envelope. Outside it means UNKNOWN, never a claim the chip rejects it.
 * Latch at last-rise+500us and deadline at first-rise+nominal timeout are
 * explicit model policies, not measured silicon timing. No optical, current,
 * charge-pump, thermal, protection, electrical or bit-exact simulation.
 * Observer, bias and timers follow Unit QOM ownership; no live hotplug.
 */
#define AW3641_MIN_PULSE_NS 750LL
#define AW3641_MAX_PULSE_NS 10000LL
#define AW3641_RESET_NS 500001LL
#define AW3641_SETTLE_NS 500000LL
#define AW3641_TRACE_MAX 256

typedef enum AW3641Phase {
    AW3641_RESET_PENDING, AW3641_READY_LOW, AW3641_PROGRAMMING,
    AW3641_FLASH_ACTIVE, AW3641_FLASH_EXPIRED, AW3641_TORCH_ACTIVE,
    AW3641_UNQUALIFIED,
} AW3641Phase;

typedef struct AW3641Edge {
    int64_t at_ns;
    bool level;
} AW3641Edge;

struct AW3641State {
    M5Unit *unit;
    Esp32GpioState *controller;
    Esp32GpioPadObserver *observer;
    Esp32GpioBoardBias *bias;
    Esp32GpioPadSnapshot pad;
    bool pad_observed;
    uint64_t commit_sequence;
    bool en, flash_mode, mode_frozen, known, active, qualified, ready;
    bool unqualified_reported, pulse_count_capped;
    AW3641Phase phase;
    const char *reason;
    unsigned pulses, last_program, flash_level_pct, timeout_ms;
    int64_t last_edge_ns, low_since_ns, first_rise_ns;
    int64_t reset_at_ns, settle_at_ns, timeout_at_ns;
    uint64_t epoch, reset_epoch, settle_epoch, timeout_epoch;
    uint64_t edge_count, rising_edges, decoded_programs;
    uint64_t unqualified_programs, reset_events, timeout_events, trace_overflows;
    AW3641Edge trace[AW3641_TRACE_MAX];
    unsigned trace_head, trace_count;
    QEMUTimer *reset_timer, *settle_timer, *timeout_timer;
};

static bool aw3641_gpio_route(AW3641State *s)
{
    /* Preserve the raw legacy route diagnostic, not an output-known gate.
     * The controller now resolves actual pad/OE/OUT inversion and passive R1.
     */
    return esp32_gpio_matrix_out_signal(s->unit->yellow, s->unit->s3) == 256;
}

static bool aw3641_pad_synchronized(AW3641State *s)
{
    Esp32GpioPadSnapshot pad;
    return s->pad_observed &&
        esp32_gpio_pad_snapshot(s->controller, s->unit->yellow, &pad) &&
        pad.known && !pad.conflict && pad.level == s->en &&
        pad.controller_generation == s->pad.controller_generation &&
        pad.epoch == s->pad.epoch && pad.revision == s->pad.revision;
}

static bool aw3641_output_known(AW3641State *s)
{
    return s->known && aw3641_pad_synchronized(s);
}

static void aw3641_output(AW3641State *s, bool known, bool active)
{
    if (s->active != active) {
        /* Nominal model state changes, not measured electrical edges. */
        s->unit->output_transitions++;
    }
    s->known = known;
    s->active = active;
}

static void aw3641_unqualified(AW3641State *s, const char *reason)
{
    if (!s->unqualified_reported) {
        s->unqualified_programs++;
        s->unqualified_reported = true;
    }
    s->qualified = s->ready = false;
    s->reason = reason;
    s->phase = AW3641_UNQUALIFIED;
    timer_del(s->settle_timer);
    timer_del(s->timeout_timer);
    s->settle_at_ns = s->timeout_at_ns = -1;
    aw3641_output(s, false, false);
}

/* Losing the observed pad is a lifecycle break, not a pad edge.
 * No previous low interval, pulse train or pending timer may qualify a later
 * restoration. Recovery starts a fresh, complete long-low observation at the
 * new known-low baseline; it need not invent a falling edge. Keep the edge
 * trace/counters and last-program value as history, never as qualification.
 */
static void aw3641_observation_lost(AW3641State *s, const char *reason)
{
    aw3641_unqualified(s, reason);
    timer_del(s->reset_timer);
    s->epoch++;
    s->reset_at_ns = s->settle_at_ns = s->timeout_at_ns = -1;
    s->low_since_ns = s->first_rise_ns = -1;
    s->pulses = s->flash_level_pct = s->timeout_ms = 0;
    s->pulse_count_capped = false;
}

static bool aw3641_timer_source(AW3641State *s)
{
    /* Pure validity read. The combined commit event owns invalidation, not a
     * later timer or GET which happens to notice a missing observation.
     */
    return aw3641_pad_synchronized(s);
}

static void aw3641_begin_low(AW3641State *s, int64_t now)
{
    s->low_since_ns = now;
    s->reset_at_ns = now + AW3641_RESET_NS;
    s->reset_epoch = s->epoch;
    timer_mod_ns(s->reset_timer, s->reset_at_ns);
}

static void aw3641_finish_reset(AW3641State *s)
{
    timer_del(s->reset_timer);
    timer_del(s->settle_timer);
    timer_del(s->timeout_timer);
    s->epoch++;
    s->reset_at_ns = s->settle_at_ns = s->timeout_at_ns = -1;
    s->pulses = s->flash_level_pct = s->timeout_ms = 0;
    s->pulse_count_capped = false;
    s->first_rise_ns = -1;
    s->qualified = s->ready = true;
    s->unqualified_reported = false;
    s->reason = "none";
    s->phase = AW3641_READY_LOW;
    s->reset_events++;
    aw3641_output(s, true, false);
}

static void aw3641_reset_expired(void *opaque)
{
    AW3641State *s = opaque;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (s->en || s->reset_at_ns < 0 || now < s->reset_at_ns ||
        s->reset_epoch != s->epoch || !aw3641_timer_source(s)) {
        return;
    }
    aw3641_finish_reset(s);
}

static void aw3641_timeout_expired(void *opaque)
{
    AW3641State *s = opaque;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (s->phase != AW3641_FLASH_ACTIVE || !s->en ||
        s->timeout_at_ns < 0 || now < s->timeout_at_ns ||
        s->timeout_epoch != s->epoch || !aw3641_timer_source(s)) {
        return;
    }
    s->phase = AW3641_FLASH_EXPIRED;
    s->timeout_at_ns = -1;
    s->timeout_events++;
    aw3641_output(s, true, false);
}

static void aw3641_settle_expired(void *opaque)
{
    AW3641State *s = opaque;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (s->phase != AW3641_PROGRAMMING || !s->en || !s->qualified ||
        s->settle_at_ns < 0 || now < s->settle_at_ns ||
        s->settle_epoch != s->epoch || !aw3641_timer_source(s)) {
        return;
    }
    s->settle_at_ns = -1;
    if (!s->flash_mode) {
        /* Stable Torch EN high only; no Flash percentage or Flash deadline. */
        s->phase = AW3641_TORCH_ACTIVE;
        s->last_program = s->flash_level_pct = s->timeout_ms = 0;
        s->decoded_programs++;
        aw3641_output(s, true, true);
        return;
    }
    if (s->pulses < 1 || s->pulses > 16) {
        aw3641_unqualified(s, "pulse-count-outside-documentation");
        return;
    }
    s->last_program = s->pulses;
    s->flash_level_pct = 100 - ((s->pulses - 1) % 8) * 10;
    s->timeout_ms = s->pulses <= 8 ? 220 : 1300;
    s->timeout_at_ns = s->first_rise_ns + (int64_t)s->timeout_ms * 1000000;
    s->timeout_epoch = s->epoch;
    s->decoded_programs++;
    if (now >= s->timeout_at_ns) {
        s->phase = AW3641_FLASH_EXPIRED;
        s->timeout_at_ns = -1;
        s->timeout_events++;
        aw3641_output(s, true, false);
    } else {
        s->phase = AW3641_FLASH_ACTIVE;
        aw3641_output(s, true, true);
        timer_mod_ns(s->timeout_timer, s->timeout_at_ns);
    }
}

static void aw3641_trace(AW3641State *s, bool level, int64_t now)
{
    unsigned slot;
    if (s->trace_count < AW3641_TRACE_MAX) {
        slot = (s->trace_head + s->trace_count++) % AW3641_TRACE_MAX;
    } else {
        slot = s->trace_head;
        s->trace_head = (s->trace_head + 1) % AW3641_TRACE_MAX;
        s->trace_overflows++;
    }
    s->trace[slot] = (AW3641Edge) { .at_ns = now, .level = level };
    s->edge_count++;
    if (level) { s->rising_edges++; }
}

static void aw3641_pad_edge(AW3641State *s, bool high, int64_t now)
{
    int64_t duration = s->last_edge_ns < 0 ? -1 : now - s->last_edge_ns;
    /* Only called for a contiguous pair of known pad snapshots. A real rise
     * can complete this fresh low if main-loop timer delivery was delayed.
     */
    if (high && !s->en && !s->ready && s->low_since_ns >= 0 &&
        now - s->low_since_ns >= AW3641_RESET_NS) {
        aw3641_finish_reset(s);
    }
    s->en = high;
    s->last_edge_ns = now;
    aw3641_trace(s, high, now);
    if (!high) {
        timer_del(s->settle_timer);
        timer_del(s->timeout_timer);
        s->settle_at_ns = s->timeout_at_ns = -1;
        if (s->phase == AW3641_PROGRAMMING && s->qualified) {
            if (duration < AW3641_MIN_PULSE_NS || duration > AW3641_MAX_PULSE_NS) {
                aw3641_unqualified(s, "pulse-width-outside-recommended-window");
            }
        } else if (s->phase != AW3641_UNQUALIFIED) {
            s->phase = AW3641_RESET_PENDING;
            s->qualified = s->ready = false;
        }
        aw3641_output(s, false, false);
        aw3641_begin_low(s, now);
        return;
    }
    timer_del(s->reset_timer);
    s->reset_at_ns = -1;
    s->low_since_ns = -1;
    if (s->pulses < 17) { s->pulses++; }
    else { s->pulse_count_capped = true; }
    if (s->phase == AW3641_READY_LOW && s->ready && s->qualified) {
        s->epoch++;
        s->ready = false;
        s->first_rise_ns = now;
        s->phase = AW3641_PROGRAMMING;
        aw3641_output(s, false, false);
    } else if (s->phase == AW3641_PROGRAMMING && s->qualified) {
        if (!s->flash_mode) {
            aw3641_unqualified(s, "torch-modulation-not-qualified");
        } else if (duration < AW3641_MIN_PULSE_NS || duration > AW3641_MAX_PULSE_NS) {
            aw3641_unqualified(s, "pulse-width-outside-recommended-window");
        }
    } else if (s->phase != AW3641_UNQUALIFIED) {
        aw3641_unqualified(s, "new-program-requires-long-low-reset");
    }
    if (s->pulses > 16) {
        aw3641_unqualified(s, "pulse-count-outside-documentation");
    }
    if (s->phase == AW3641_PROGRAMMING && s->qualified) {
        s->settle_at_ns = now + AW3641_SETTLE_NS;
        s->settle_epoch = s->epoch;
        timer_mod_ns(s->settle_timer, s->settle_at_ns);
    }
}

static bool aw3641_same_observation(const Esp32GpioPadSnapshot *a,
                                    const Esp32GpioPadSnapshot *b)
{
    return a->controller_generation == b->controller_generation &&
        a->epoch == b->epoch && a->revision == b->revision;
}

static void aw3641_pad_event(void *opaque, const Esp32GpioPadEvent *event)
{
    AW3641State *s = opaque;
    const Esp32GpioPadSnapshot *before = &event->before, *after = &event->after;
    if (after->pin != (unsigned)s->unit->yellow || after->s3 != s->unit->s3 ||
        event->commit_sequence <= s->commit_sequence) {
        return;
    }
    bool reset = event->cause == ESP32_GPIO_PAD_RESET ||
        (event->change_mask & ESP32_GPIO_PAD_CHANGE_RESET);
    bool before_known = before->known && !before->conflict;
    bool after_known = after->known && !after->conflict;
    bool continuous = !reset && s->pad_observed && before_known &&
        s->pad.known && !s->pad.conflict &&
        aw3641_same_observation(&s->pad, before) &&
        before->controller_generation == after->controller_generation &&
        before->epoch == after->epoch && before->level == s->en;
    bool edge = before_known && after_known &&
        before->controller_generation == after->controller_generation &&
        before->level != after->level;

    /* Invalidate synchronously, even if the new baseline has the same level.
     * No timer/GET may be required between an unknown/reset and restoration.
     */
    if (!continuous || !after_known) {
        aw3641_observation_lost(s, reset ? "gpio-controller-reset-observed" :
            after_known ? "pad-observation-discontinuity" : "pad-source-not-observed");
    }
    s->pad = *after;
    s->pad_observed = true;
    s->commit_sequence = event->commit_sequence;
    if (continuous && after_known) {
        if (edge) {
            aw3641_pad_edge(s, after->level, after->at_ns);
        }
        /* Same-value writes and equivalent OE/source changes retain t0. */
        return;
    }

    s->en = after->level;
    if (edge) {
        /* This known before/after edge is trace history only: reset or a lost
         * observation has already revoked its old pulse/low qualification.
         */
        s->last_edge_ns = after->at_ns;
        aw3641_trace(s, after->level, after->at_ns);
    }
    if (after_known && !after->level) {
        aw3641_begin_low(s, after->at_ns);
    }
}
/* END AW3641 CORE */

static void aw3641_bool_get(Object *o, Visitor *v, const char *name,
                           void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    bool value = false;
    if (!strcmp(name, "flash-mode")) { value = s->flash_mode; }
    else if (!strcmp(name, "mode-frozen")) { value = s->mode_frozen; }
    else if (!strcmp(name, "en-level") || !strcmp(name, "pad-known")) {
        Esp32GpioPadSnapshot pad;
        bool valid = esp32_gpio_pad_snapshot(s->controller, s->unit->yellow, &pad);
        value = !strcmp(name, "pad-known") ? valid && pad.known && !pad.conflict :
            valid ? pad.level : s->en;
    }
    else if (!strcmp(name, "pad-synchronized")) { value = aw3641_pad_synchronized(s); }
    else if (!strcmp(name, "gpio-route-supported")) { value = aw3641_gpio_route(s); }
    else if (!strcmp(name, "output-known")) { value = aw3641_output_known(s); }
    else if (!strcmp(name, "active")) { value = aw3641_output_known(s) && s->active; }
    else if (!strcmp(name, "waveform-qualified")) { value = s->qualified && aw3641_pad_synchronized(s); }
    else if (!strcmp(name, "pulse-count-capped")) { value = s->pulse_count_capped; }
    /* bit-exact-supported/live-mode-change-supported/reset-observation-supported
     * are deliberately false, including in an otherwise qualified interval. */
    visit_type_bool(v, name, &value, errp);
}

static void aw3641_mode_set(Object *o, Visitor *v, const char *name,
                           void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    bool value;
    if (!visit_type_bool(v, name, &value, errp)) { return; }
    if (s->mode_frozen) {
        error_setg(errp, "FlashLight S1 fixture is frozen after creation; create a new session to select mode");
        return;
    }
    if (s->flash_mode != value) { s->unit->input_events++; }
    s->flash_mode = value;
}

static void aw3641_uint_get(Object *o, Visitor *v, const char *name,
                           void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    uint64_t value = 0;
    if (!strcmp(name, "pulse-count")) { value = s->pulses; }
    else if (!strcmp(name, "last-program-count")) { value = s->last_program; }
    else if (!strcmp(name, "flash-level-pct")) { value = s->flash_level_pct; }
    else if (!strcmp(name, "timeout-ms")) { value = s->timeout_ms; }
    else if (!strcmp(name, "edge-count")) { value = s->edge_count; }
    else if (!strcmp(name, "rising-edges")) { value = s->rising_edges; }
    else if (!strcmp(name, "decoded-programs")) { value = s->decoded_programs; }
    else if (!strcmp(name, "unqualified-programs")) { value = s->unqualified_programs; }
    else if (!strcmp(name, "reset-events")) { value = s->reset_events; }
    else if (!strcmp(name, "timeout-events")) { value = s->timeout_events; }
    else if (!strcmp(name, "trace-overflows")) { value = s->trace_overflows; }
    else if (!strcmp(name, "observation-controller-generation")) { value = s->pad.controller_generation; }
    else if (!strcmp(name, "observation-epoch")) { value = s->pad.epoch; }
    else if (!strcmp(name, "observation-revision")) { value = s->pad.revision; }
    visit_type_uint64(v, name, &value, errp);
}

static void aw3641_time_get(Object *o, Visitor *v, const char *name,
                           void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    int64_t value = s->last_edge_ns;
    if (!strcmp(name, "first-rise-ns")) { value = s->first_rise_ns; }
    else if (!strcmp(name, "settle-at-ns")) { value = s->settle_at_ns; }
    else if (!strcmp(name, "timeout-at-ns")) { value = s->timeout_at_ns; }
    else if (!strcmp(name, "reset-at-ns")) { value = s->reset_at_ns; }
    else if (!strcmp(name, "low-observed-since-ns")) { value = s->low_since_ns; }
    visit_type_int64(v, name, &value, errp);
}

static void aw3641_string_get(Object *o, Visitor *v, const char *name,
                             void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    static const char *const phases[] = {"reset-pending", "ready-low", "programming",
        "flash-active", "flash-expired", "torch-active", "unqualified"};
    const char *source = s->reason;
    if (!strcmp(name, "program-state")) { source = phases[s->phase]; }
    else if (!strcmp(name, "timing-policy")) {
        source = "nominal-model: long-low>500us; qualified inter-pulse HI/LO=750..10000ns; "
                 "latch=last-rise+500us; Flash deadline=first-rise+220/1300ms; "
                 "latch/deadline origins are model policy, not measured silicon";
    }
    char *value = g_strdup(source);
    visit_type_str(v, name, &value, errp);
    g_free(value);
}

static void aw3641_trace_get(Object *o, Visitor *v, const char *name,
                            void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    QList *array = qlist_new();
    /* Bounded oldest-to-newest pairs [QEMU virtual nanoseconds, pad 0/1]. */
    for (unsigned i = 0; i < s->trace_count; i++) {
        AW3641Edge *edge = &s->trace[(s->trace_head + i) % AW3641_TRACE_MAX];
        QList *pair = qlist_new();
        qlist_append_int(pair, edge->at_ns);
        qlist_append_int(pair, edge->level);
        qlist_append_obj(array, QOBJECT(pair));
    }
    QObject *value = QOBJECT(array);
    visit_type_any(v, name, &value, errp);
    qobject_unref(value);
}

static void aw3641_free(AW3641State *s)
{
    /* Handles retain their controller; detach the observer before removing
     * the bias, since bias removal is itself a controller pad commit.
     */
    if (s->observer) {
        esp32_gpio_unobserve_pad(s->observer);
        s->observer = NULL;
    }
    if (s->bias) {
        esp32_gpio_remove_board_bias(s->bias);
        s->bias = NULL;
    }
    timer_del(s->reset_timer);
    timer_del(s->settle_timer);
    timer_del(s->timeout_timer);
    timer_free(s->reset_timer);
    timer_free(s->settle_timer);
    timer_free(s->timeout_timer);
    g_free(s);
}

static void aw3641_release(Object *o, const char *name, void *opaque)
{
    AW3641State *s = opaque;
    for (GPIOUnit **link = &gpio_units; *link; link = &(*link)->next) {
        GPIOUnit *g = *link;
        if (g->flashlight == s) {
            *link = g->next;
            g_free(g);
            break;
        }
    }
    aw3641_free(s);
}

static AW3641State *aw3641_new(M5Unit *unit, Error **errp)
{
    AW3641State *s = g_new0(AW3641State, 1);
    s->unit = unit;
    s->flash_mode = true; /* Explicit synthetic creation fixture, not measured default. */
    s->reason = "awaiting-long-low-reset";
    s->phase = AW3641_RESET_PENDING;
    s->last_edge_ns = s->first_rise_ns = -1;
    s->reset_at_ns = s->settle_at_ns = s->timeout_at_ns = -1;
    s->low_since_ns = -1;
    s->reset_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, aw3641_reset_expired, s);
    s->settle_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, aw3641_settle_expired, s);
    s->timeout_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, aw3641_timeout_expired, s);
    s->controller = esp32_gpio_get_controller(unit->s3);
    if (!s->controller) {
        error_setg(errp, "FlashLight requires the matching GPIO controller");
        aw3641_free(s);
        return NULL;
    }
    /* Schematic EN R1=10K pull-down: an independent nominal passive bias,
     * never a write to the controller's external-input source storage.
     */
    s->bias = esp32_gpio_add_board_bias(s->controller, unit->yellow,
        ESP32_GPIO_BIAS_PULL_DOWN, s, errp);
    if (!s->bias) {
        aw3641_free(s);
        return NULL;
    }
    s->observer = esp32_gpio_observe_pad(s->controller, unit->yellow,
        aw3641_pad_event, s, &s->pad, errp);
    if (!s->observer) {
        aw3641_free(s);
        return NULL;
    }
    s->pad_observed = true;
    s->en = s->pad.level;
    if (s->pad.known && !s->pad.conflict && !s->en) {
        /* Registration samples at current virtual time, not the last write.
         * There is no edge, pulse or low history before this fresh t0.
         */
        aw3641_begin_low(s, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    } else if (!s->pad.known || s->pad.conflict) {
        s->reason = "pad-source-not-observed";
    }
    Object *o = OBJECT(unit);
    const char *const bools[] = {"flash-mode", "mode-frozen", "en-level",
        "pad-known", "pad-synchronized", "gpio-route-supported", "output-known", "active",
        "waveform-qualified", "pulse-count-capped", "bit-exact-supported",
        "live-mode-change-supported", "reset-observation-supported"};
    const char *const uints[] = {"pulse-count", "last-program-count", "flash-level-pct",
        "timeout-ms", "edge-count", "rising-edges", "decoded-programs",
        "unqualified-programs", "reset-events", "timeout-events", "trace-overflows",
        "observation-controller-generation", "observation-epoch", "observation-revision"};
    const char *const times[] = {"last-edge-ns", "first-rise-ns", "settle-at-ns", "timeout-at-ns",
        "reset-at-ns", "low-observed-since-ns"};
    for (unsigned i = 0; i < ARRAY_SIZE(bools); i++) {
        object_property_add(o, bools[i], "bool", aw3641_bool_get,
                            i == 0 ? aw3641_mode_set : NULL, NULL, s);
    }
    for (unsigned i = 0; i < ARRAY_SIZE(uints); i++) {
        object_property_add(o, uints[i], "uint64", aw3641_uint_get, NULL, NULL, s);
    }
    for (unsigned i = 0; i < ARRAY_SIZE(times); i++) {
        object_property_add(o, times[i], "int64", aw3641_time_get, NULL, NULL, s);
    }
    object_property_add(o, "program-state", "str", aw3641_string_get, NULL, NULL, s);
    object_property_add(o, "unknown-reason", "str", aw3641_string_get, NULL, NULL, s);
    object_property_add(o, "timing-policy", "str", aw3641_string_get, NULL, NULL, s);
    object_property_add(o, "edge-trace-ns", "any", aw3641_trace_get, NULL, aw3641_release, s);
    return s;
}
/* END AW3641 NOMINAL DIGITAL MODEL */


bool m5_unit_gpio_supported(const char *id)
{
    static const char *ids[] = {"pir", "dual-button", "limit", "key", "rgb",
        "angle", "light", "buzzer", "fan", "ir", "rs485", "hub", "flashlight"};
    for (unsigned i = 0; i < ARRAY_SIZE(ids); i++) {
        if (!strcmp(id, ids[i])) { return true; }
    }
    return false;
}

static void bool_get(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    bool value;
    if (!strcmp(name, "red-pressed")) { value = g->red; }
    else if (!strcmp(name, "blue-pressed") || !strcmp(name, "pressed")) { value = g->blue; }
    else if (!strcmp(name, "motion")) { value = g->motion; }
    else if (!strcmp(name, "digital-level")) { value = g->digital; }
    else { value = esp32_gpio_get_line(g->unit->white); }
    visit_type_bool(v, name, &value, errp);
}

static void motion_off(void *opaque)
{
    GPIOUnit *g = opaque;
    if (g->motion) {
        g->hold_until = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 2000000000LL;
        timer_mod_ns(g->hold_timer, g->hold_until);
    } else { esp32_gpio_set_input(g->unit->white, 0); }
}

static void bool_set(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    bool value;
    if (!visit_type_bool(v, name, &value, errp)) { return; }
    g->unit->input_events++;
    if (!strcmp(name, "red-pressed")) {
        g->red = value; esp32_gpio_set_input(g->unit->yellow, !value);
    } else if (!strcmp(name, "motion")) {
        g->motion = value;
        int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        if (value) {
            esp32_gpio_set_input(g->unit->white, 1);
            g->hold_until = now + 2000000000LL;
            timer_mod_ns(g->hold_timer, g->hold_until);
        } else if (now >= g->hold_until) { esp32_gpio_set_input(g->unit->white, 0); }
    } else if (!strcmp(name, "digital-level")) {
        g->digital = value; esp32_gpio_set_input(g->unit->yellow, value);
    } else {
        g->blue = value; esp32_gpio_set_input(g->unit->white, !value);
    }
}

static void num_get(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    double value = !strcmp(name, "frequency-hz") ? g->frequency :
                   !strcmp(name, "duty-pct") ? g->duty : g->voltage;
    if ((!strcmp(name, "frequency-hz") || !strcmp(name, "duty-pct")) &&
        esp32_gpio_matrix_out_signal(g->unit->yellow, g->s3) != g->pwm_signal) { value = 0; }
    visit_type_number(v, name, &value, errp);
}

static void num_set(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    double value;
    if (!visit_type_number(v, name, &value, errp)) { return; }
    double maximum = !strcmp(g->unit->unit_id, "angle") ? 2500 : 3300;
    if (!isfinite(value) || value < 0 || value > maximum) {
        error_setg(errp, "%s requires 0..%g mV", name, maximum); return;
    }
    g->voltage = value; g->unit->input_events++;
}

static void count_get(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    uint64_t value = *(uint64_t *)op;
    visit_type_uint64(v, name, &value, errp);
}

static void led_get(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    if (g->leds == 1) {
        uint32_t value = g->rgb[0]; visit_type_uint32(v, name, &value, errp); return;
    }
    QList *array = qlist_new();
    for (unsigned i = 0; i < g->leds; i++) { qlist_append_int(array, g->rgb[i]); }
    QObject *value = QOBJECT(array);
    visit_type_any(v, name, &value, errp); qobject_unref(value);
}

static void pulses_get(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    bool tx = !strcmp(name, "tx-pulses-us");
    QList *array = qlist_new();
    for (unsigned i = 0; i < (tx ? g->tx_count : g->rx_count); i++) {
        qlist_append_int(array, tx ? g->tx_pulses[i] : g->rx_pulses[i]);
    }
    QObject *value = QOBJECT(array);
    visit_type_any(v, name, &value, errp); qobject_unref(value);
}

static void pulses_set(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    QObject *value = NULL;
    if (!visit_type_any(v, name, &value, errp)) { return; }
    QList *array = qobject_to(QList, value);
    if (!array || qlist_size(array) > ARRAY_SIZE(g->rx_pulses)) {
        error_setg(errp, "IR pulse list exceeds 192 durations"); qobject_unref(value); return;
    }
    uint32_t pulses[192]; unsigned count = 0;
    const QListEntry *e;
    QLIST_FOREACH_ENTRY(array, e) {
        QNum *n = qobject_to(QNum, qlist_entry_obj(e));
        int64_t duration;
        if (!n || !qnum_get_try_int(n, &duration) || duration < 1 || duration > 1000000) {
            error_setg(errp, "IR duration must be 1..1000000 us"); qobject_unref(value); return;
        }
        pulses[count++] = duration;
    }
    memcpy(g->rx_pulses, pulses, count * sizeof(pulses[0]));
    g->rx_count = count; g->unit->input_events++;
    m5_unit_rmt_rx_arrived();
    qobject_unref(value);
}

uint16_t m5_unit_adc_sample(unsigned adc, unsigned channel, unsigned atten,
                            bool s3, uint16_t fallback)
{
    static const int classic1[] = {36, 37, 38, 39, 32, 33, 34, 35};
    static const int classic2[] = {4, 0, 2, 15, 13, 12, 14, 27, 25, 26};
    int pin = s3 ? (adc ? 11 : 1) + channel :
        adc ? (channel < 10 ? classic2[channel] : -1) :
        (channel < 8 ? classic1[channel] : -1);
    static const double ideal_fullscale_mv[] = {950, 1250, 1750, 3100};
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (g->unit->white == pin && (!strcmp(g->unit->unit_id, "angle") ||
                                    !strcmp(g->unit->unit_id, "light"))) {
            g->adc_samples++;
            return MIN(4095, llround(g->voltage * 4095 / ideal_fullscale_mv[atten & 3]));
        }
    }
    return fallback;
}

void m5_unit_pwm_observe(bool s3, unsigned channel, uint32_t timer,
                          uint32_t duty, uint32_t conf)
{
    unsigned signal = s3 ? 73 + channel : channel < 8 ? 71 + channel : 79 + channel - 8;
    unsigned resolution = timer & 15, divider = (timer >> 4) & 0x3ffff;
    double frequency = resolution && divider ?
        80000000.0 * 256 / divider / (1u << resolution) : 0;
    double percent = resolution ? MIN(100, (duty >> 4) * 100.0 / (1u << resolution)) : 0;
    if (!(conf & BIT(2)) || (timer & (BIT(22) | BIT(23)))) { percent = 0; }
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (g->s3 == s3 &&
            (!strcmp(g->unit->unit_id, "fan") || !strcmp(g->unit->unit_id, "buzzer")) &&
            esp32_gpio_matrix_out_signal(g->unit->yellow, s3) == signal) {
            if (g->frequency != frequency || g->duty != percent) { g->unit->output_transitions++; }
            g->frequency = frequency; g->duty = percent; g->pwm_signal = signal;
        }
    }
}

void m5_unit_rmt_tx(unsigned channel, const uint32_t *symbols,
                     unsigned count, double tick_hz)
{
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (esp32_gpio_matrix_out_signal(g->unit->yellow, true) != 81 + channel) { continue; }
        if (!strcmp(g->unit->unit_id, "ir")) {
            g->tx_count = 0;
            for (unsigned i = 0; i < count && g->tx_count + 1 < 192; i++) {
                g->tx_pulses[g->tx_count++] = llround((symbols[i] & 0x7fff) * 1000000.0 / tick_hz);
                g->tx_pulses[g->tx_count++] = llround(((symbols[i] >> 16) & 0x7fff) * 1000000.0 / tick_hz);
            }
            g->unit->output_transitions++;
        } else if (g->leds) {
            if (count < g->leds * 24) { g->incomplete_frames++; continue; }
            for (unsigned led = 0; led < g->leds; led++) {
                uint32_t grb = 0;
                for (unsigned bit = 0; bit < 24; bit++) {
                    uint32_t symbol = symbols[led * 24 + bit];
                    unsigned a = symbol & 0x7fff, b = (symbol >> 16) & 0x7fff;
                    bool high_first = symbol & BIT(15);
                    grb = (grb << 1) | (high_first ? a > b : b > a);
                }
                g->rgb[led] = ((grb >> 8) & 0xff00) | ((grb & 0xff00) << 8) | (grb & 0xff);
            }
            g->frames++; g->unit->output_transitions++;
        }
    }
}

unsigned m5_unit_rmt_rx(unsigned channel, uint32_t *symbols,
                         unsigned capacity, double tick_hz)
{
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (strcmp(g->unit->unit_id, "ir") || !g->rx_count ||
            esp32_gpio_matrix_in_pin(81 + channel, true) != g->unit->white) { continue; }
        unsigned count = (g->rx_count + 1) / 2;
        if (count > capacity) { return 0; }
        for (unsigned i = 0; i < count; i++) {
            uint32_t a = llround(g->rx_pulses[i * 2] * tick_hz / 1000000);
            uint32_t b = i * 2 + 1 < g->rx_count ? llround(g->rx_pulses[i * 2 + 1] * tick_hz / 1000000) : 0;
            if (a > 0x7fff || b > 0x7fff) { return 0; }
            symbols[i] = a | (b << 16) | BIT(31); /* demodulator active-low */
        }
        g->rx_count = 0;
        return count;
    }
    return 0;
}

static const unsigned uart_signal[] = {12, 15, 18};
void m5_unit_uart_tx(ESP32UARTState *uart, uint8_t byte)
{
    for (unsigned n = 0; n < 3; n++) {
        if (m5soc_get_uart_device(n) != DEVICE(uart)) { continue; }
        for (GPIOUnit *g = gpio_units; g; g = g->next) {
            if (!strcmp(g->unit->unit_id, "rs485") &&
                esp32_gpio_matrix_out_signal(g->unit->yellow, true) == uart_signal[n]) {
                if (g->uart_tx_size < sizeof(g->uart_tx)) { g->uart_tx[g->uart_tx_size++] = byte; }
                g->unit->written_bytes++;
            }
        }
    }
}

static void hex_get(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op;
    char *value;
    if (!strcmp(name, "rx-hex")) { value = g_strdup(g->last_rx ? g->last_rx : ""); }
    else {
        value = g_malloc(g->uart_tx_size * 2 + 1);
        for (size_t i = 0; i < g->uart_tx_size; i++) { sprintf(value + i * 2, "%02x", g->uart_tx[i]); }
        value[g->uart_tx_size * 2] = 0;
    }
    visit_type_str(v, name, &value, errp); g_free(value);
}

static void hex_set(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    GPIOUnit *g = op; char *value = NULL;
    if (!visit_type_str(v, name, &value, errp)) { return; }
    size_t size = strlen(value);
    if (size > 8192 || size % 2 || strspn(value, "0123456789abcdefABCDEF") != size) {
        error_setg(errp, "RX requires at most 4096 hex bytes"); g_free(value); return;
    }
    uint8_t data[4096];
    for (size_t i = 0; i < size / 2; i++) {
        char byte[] = {value[i * 2], value[i * 2 + 1], 0}; data[i] = strtoul(byte, NULL, 16);
    }
    for (unsigned n = 0; n < 3; n++) {
        if (esp32_gpio_matrix_in_pin(uart_signal[n], true) == g->unit->white) {
            DeviceState *uart = m5soc_get_uart_device(n);
            if (uart) {
                if (size / 2 > fifo8_num_free(&ESP32_UART(uart)->rx_fifo)) {
                    error_setg(errp, "Unit RX exceeds the UART FIFO's current free capacity");
                    g_free(value); return;
                }
                esp32_uart_inject_rx(ESP32_UART(uart), data, size / 2);
                g->unit->read_bytes += size / 2;
                g->unit->input_events++;
                g_free(g->last_rx); g->last_rx = value; return;
            }
        }
    }
    error_setg(errp, "no UART receiver is routed to the Unit white pin"); g_free(value);
}

void m5_unit_gpio_realize(M5Unit *unit, bool s3, Error **errp)
{
    if (!s3 && (!strcmp(unit->unit_id, "rgb") || !strcmp(unit->unit_id, "key") ||
                !strcmp(unit->unit_id, "ir") || !strcmp(unit->unit_id, "rs485"))) {
        error_setg(errp, "this Unit requires the S3 RMT/UART controller path"); return;
    }
    GPIOUnit *g = g_new0(GPIOUnit, 1);
    g->unit = unit; g->s3 = s3; g->voltage = 1250;
    g->next = gpio_units; gpio_units = g;
    Object *o = OBJECT(unit); const char *id = unit->unit_id;
    if (!strcmp(id, "flashlight")) {
        g->flashlight = aw3641_new(unit, errp);
        if (!g->flashlight) {
            gpio_units = g->next;
            g_free(g);
        }
        return;
    } else if (!strcmp(id, "pir")) {
        g->hold_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, motion_off, g);
        esp32_gpio_set_input(unit->white, 0);
        object_property_add(o, "motion", "bool", bool_get, bool_set, NULL, g);
        object_property_add(o, "input-level", "bool", bool_get, NULL, NULL, g);
    } else if (!strcmp(id, "dual-button") || !strcmp(id, "limit") || !strcmp(id, "key")) {
        esp32_gpio_set_input(unit->white, 1);
        if (!strcmp(id, "dual-button")) {
            esp32_gpio_set_input(unit->yellow, 1);
            object_property_add(o, "red-pressed", "bool", bool_get, bool_set, NULL, g);
            object_property_add(o, "blue-pressed", "bool", bool_get, bool_set, NULL, g);
        } else { object_property_add(o, "pressed", "bool", bool_get, bool_set, NULL, g); }
        object_property_add(o, "input-level", "bool", bool_get, NULL, NULL, g);
    } else if (!strcmp(id, "angle") || !strcmp(id, "light")) {
        object_property_add(o, !strcmp(id, "angle") ? "voltage-mv" : "analog-mv", "number", num_get, num_set, NULL, g);
        object_property_add(o, "adc-samples", "uint64", count_get, NULL, NULL, &g->adc_samples);
        if (!strcmp(id, "light")) {
            esp32_gpio_set_input(unit->yellow, 0);
            object_property_add(o, "digital-level", "bool", bool_get, bool_set, NULL, g);
        }
    } else if (!strcmp(id, "fan") || !strcmp(id, "buzzer")) {
        object_property_add(o, "frequency-hz", "number", num_get, NULL, NULL, g);
        object_property_add(o, "duty-pct", "number", num_get, NULL, NULL, g);
    } else if (!strcmp(id, "ir")) {
        object_property_add(o, "rx-pulses-us", "any", pulses_get, pulses_set, NULL, g);
        object_property_add(o, "tx-pulses-us", "any", pulses_get, NULL, NULL, g);
    } else if (!strcmp(id, "rs485")) {
        object_property_add(o, "rx-hex", "str", hex_get, hex_set, NULL, g);
        object_property_add(o, "tx-hex", "str", hex_get, NULL, NULL, g);
    }
    if (!strcmp(id, "rgb") || !strcmp(id, "key")) {
        g->leds = !strcmp(id, "key") ? 1 : 3;
        object_property_add(o, "led-rgb", g->leds == 1 ? "uint32" : "any", led_get, NULL, NULL, g);
        object_property_add(o, "led-frames", "uint64", count_get, NULL, NULL, &g->frames);
        object_property_add(o, "incomplete-frames", "uint64", count_get, NULL, NULL, &g->incomplete_frames);
    }
}

/* Called once after every creation initial property, including an empty set. */
void m5_unit_gpio_initial_complete(M5Unit *unit)
{
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (g->unit == unit && g->flashlight) {
            g->flashlight->mode_frozen = true;
            return;
        }
    }
}

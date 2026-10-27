/* Whole-source GPIO + AW3641 integration; only QEMU host facilities are shimmed.
 * No guest, silicon, electrical or runtime-service claim. */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "qom/object.h"
#include "hw/sysbus.h"
#include "exec/memory.h"
#undef type_init
#define type_init(fn)
#include GPIO_SOURCE
#include AW_SOURCE
#if !OLD_RUNTIME
#include AUX_SOURCE
#endif

/* QEMU environment shims: no GPIO/AW decisions live in this section. */
static int64_t host_now_ns;
static QEMUTimer *host_timers[32];
static unsigned host_timer_count;
static bool host_s3 = true;
static int host_object_refs;
typedef struct HostRegion {
    MemoryRegion *mr;
    const MemoryRegionOps *ops;
    void *opaque;
    uint64_t size, base;
    const char *name;
    bool mapped;
} HostRegion;
static HostRegion host_regions[16];
static unsigned host_region_count;
Error *error_fatal;

int64_t qemu_clock_get_ns(QEMUClockType type)
{
    assert(type == QEMU_CLOCK_VIRTUAL);
    return host_now_ns;
}
void timer_init_full(QEMUTimer *timer, QEMUTimerListGroup *group,
                     QEMUClockType type, int scale, int attrs,
                     QEMUTimerCB *cb, void *opaque)
{
    assert(type == QEMU_CLOCK_VIRTUAL && scale == SCALE_NS);
    assert(host_timer_count < G_N_ELEMENTS(host_timers));
    *timer = (QEMUTimer){ .expire_time = -1, .cb = cb, .opaque = opaque,
                          .scale = scale, .attributes = attrs };
    host_timers[host_timer_count++] = timer;
}
void timer_del(QEMUTimer *timer) { timer->expire_time = -1; }
void timer_mod_ns(QEMUTimer *timer, int64_t at)
{
    assert(at >= host_now_ns);
    timer->expire_time = at;
}
static void advance(int64_t target)
{
    assert(target >= host_now_ns);
    for (unsigned iterations = 0; ; iterations++) {
        assert(iterations < 10000);
        QEMUTimer *next = NULL;
        for (unsigned i = 0; i < host_timer_count; i++) {
            QEMUTimer *timer = host_timers[i];
            if (timer->expire_time >= 0 && timer->expire_time <= target &&
                (!next || timer->expire_time < next->expire_time)) { next = timer; }
        }
        if (!next) { break; }
        host_now_ns = next->expire_time;
        timer_del(next);
        next->cb(next->opaque);
    }
    host_now_ns = target;
}
Object *object_ref(void *obj) { host_object_refs++; return obj; }
void object_unref(void *obj) { host_object_refs--; assert(host_object_refs >= 0); }
Object *object_dynamic_cast_assert(Object *obj, const char *type,
                                   const char *file, int line, const char *func)
{ return obj; }
Object *object_dynamic_cast(Object *obj, const char *type)
{ return !strcmp(type, "esp32s3.gpio") ? host_s3 ? obj : NULL : obj; }
bool object_property_set_int(Object *obj, const char *name, int64_t value, Error **errp)
{ return true; }
ObjectProperty *object_property_add(Object *obj, const char *name, const char *type,
    ObjectPropertyAccessor *get, ObjectPropertyAccessor *set,
    ObjectPropertyRelease *release, void *opaque)
{ return NULL; }
void qemu_set_irq(qemu_irq irq, int level) { }
void sysbus_init_mmio(SysBusDevice *dev, MemoryRegion *mr) { }
void sysbus_init_irq(SysBusDevice *dev, qemu_irq *irq) { *irq = NULL; }
void memory_region_init_io(MemoryRegion *mr, Object *owner,
    const MemoryRegionOps *ops, void *opaque, const char *name, uint64_t size)
{
    assert(host_region_count < G_N_ELEMENTS(host_regions));
    host_regions[host_region_count++] = (HostRegion){
        .mr = mr, .ops = ops, .opaque = opaque, .size = size, .name = name };
}
void memory_region_add_subregion_overlap(MemoryRegion *mem, hwaddr addr,
                                         MemoryRegion *mr, int priority)
{
    for (unsigned i = 0; i < host_region_count; i++) {
        if (host_regions[i].mr == mr) {
            host_regions[i].base = addr;
            host_regions[i].mapped = true;
            return;
        }
    }
    abort();
}
void esp32_ledc_gpio_route_changed(bool s3) { }
void error_setg_internal(Error **errp, const char *file, int line,
                         const char *func, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "HARNESS_UNEXPECTED_ERROR %s:%d %s: ", file, line, func);
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    abort();
}

/* Fixtures invoke actual source init/MMIO and actual AW consumer functions. */
static Esp32GpioState controller;
static MemoryRegion system_mem;
static M5Unit unit;
static AW3641State *aw;
static unsigned pin = 2;
static void gpio_write(uint32_t addr, uint32_t value)
{ esp32_gpio_write(&controller, addr, value, 4); }
static uint32_t route_addr(unsigned n) { return (host_s3 ? 0x554 : 0x530) + n * 4; }
static void route(uint32_t value) { gpio_write(route_addr(pin), value); }
static void latch(bool high)
{ gpio_write((pin < 32 ? 0x08 : 0x14) + (high ? 0 : 4), 1u << (pin & 31)); }
static void output_enable(bool enable)
{ gpio_write((pin < 32 ? 0x24 : 0x30) + (enable ? 0 : 4), 1u << (pin & 31)); }
static void iomux(unsigned function, uint32_t flags)
{
#if !OLD_RUNTIME
    esp32_gpio_iomux_write(&controller, 4 + pin * 4, (function << 12) | flags, 4);
#endif
}
static void init_controller(void)
{
    esp32_gpio_init(OBJECT(&controller));
#if !OLD_RUNTIME
    esp32s3_gpio_pad_aux_init(&controller, &system_mem, 0x60008400);
#endif
}
static void create_unit(bool flash)
{
    unit = (M5Unit){ .unit_id = "flashlight", .yellow = pin, .white = pin + 1, .s3 = true };
    Error *err = NULL;
    m5_unit_gpio_realize(&unit, true, &err);
    assert(!err && gpio_units && gpio_units->unit == &unit);
    aw = gpio_units->flashlight;
    assert(aw);
    aw->flash_mode = flash; /* Creation-only S1 fixture; not a runtime input. */
    m5_unit_gpio_initial_complete(&unit);
    assert(aw->mode_frozen);
}
static void guest_pin_init(void)
{
    route(256);
    output_enable(true);
    iomux(1, 1u << 9);
    latch(false);
}
static void start(bool flash, bool unsupported)
{
    init_controller();
    if (unsupported) {
        route(73);
        iomux(7, 1u << 9);
    }
    create_unit(flash);
    guest_pin_init();
}
static void diagnostic(const char *stage)
{
    printf("stage=%s at=%"PRId64" known=%d active=%d phase=%d en=%d low=%"PRId64
           " reset_at=%"PRId64" edges=%"PRIu64" rising=%"PRIu64" resets=%"PRIu64"\n",
           stage, host_now_ns, aw3641_output_known(aw), aw->active, aw->phase,
           aw->en, aw->low_since_ns, aw->reset_at_ns, aw->edge_count,
           aw->rising_edges, aw->reset_events);
    fflush(stdout);
}
static void assert_off(void)
{ assert(aw3641_output_known(aw) && !aw->active && aw->phase == AW3641_READY_LOW); }
static void cold(void)
{
    start(true, true);
    diagnostic("after-original-cold-MMIO-path");
    assert(aw->edge_count == 0 && aw->rising_edges == 0 && aw->decoded_programs == 0);
    advance(500000);
    diagnostic("at-500000ns");
    assert(!aw3641_output_known(aw));
    advance(500001);
    diagnostic("at-500001ns");
    assert_off();
    assert(aw->reset_events == 1 && aw->edge_count == 0);
    latch(true);
    advance(host_now_ns + 500000);
    assert(aw3641_output_known(aw) && aw->active && aw->pulses == 1);
}
#if !OLD_RUNTIME
static Esp32GpioPadSnapshot snapshot(void)
{
    Esp32GpioPadSnapshot pad;
    assert(esp32_gpio_pad_snapshot(&controller, pin, &pad));
    return pad;
}
static void cntl_write(uint32_t offset, uint32_t value)
{
    assert(esp32s3_gpio_pad_aux_cntl_write(offset, value));
}
static uint32_t cntl_read(uint32_t offset)
{
    uint32_t value;
    assert(esp32s3_gpio_pad_aux_cntl_read(offset, &value));
    return value;
}
static void rtcio_mmio_write(uint32_t offset, uint32_t value)
{
    uint64_t addr = 0x60008400ULL + offset;
    for (unsigned i = 0; i < host_region_count; i++) {
        HostRegion *r = &host_regions[i];
        if (r->mapped && addr >= r->base && addr < r->base + r->size) {
            r->ops->write(r->opaque, addr - r->base, value, 4);
            assert(r->ops->read(r->opaque, addr - r->base, 4) == value);
            return;
        }
    }
    abort();
}
static void assert_lost(void)
{
    /* Inspect raw state before any QOM/getter/timer can mask a missing event. */
    assert(!aw->known && !aw->active && !aw->qualified && !aw->ready);
    assert(aw->reset_at_ns == -1 && aw->settle_at_ns == -1 && aw->timeout_at_ns == -1);
    assert(aw->low_since_ns == -1 && aw->first_rise_ns == -1);
    assert(aw->reset_timer->expire_time == -1 && aw->settle_timer->expire_time == -1 &&
           aw->timeout_timer->expire_time == -1);
}
static void recovery_boundary(int64_t t0, int64_t old_deadline)
{
    assert(!aw->known && !aw->active && !aw->qualified && !aw->ready);
    assert(aw->low_since_ns == t0 && aw->reset_at_ns == t0 + 500001);
    uint64_t epoch = aw->epoch, edges = aw->edge_count, resets = aw->reset_events;
    if (old_deadline >= host_now_ns && old_deadline < t0 + 500001) {
        advance(old_deadline);
        /* Deliver all old callback entry points late. No old timestamp/token
         * is forged into the current model; old scheduled timer was canceled. */
        aw3641_reset_expired(aw);
        aw3641_settle_expired(aw);
        aw3641_timeout_expired(aw);
        assert(!aw->known && !aw->active && aw->epoch == epoch);
    }
    advance(t0 + 500000);
    assert(!aw3641_output_known(aw) && aw->reset_events == resets);
    advance(t0 + 500001);
    assert_off();
    assert(aw->reset_events == resets + 1 && aw->edge_count == edges);
}
static void one_driver_pulse(void)
{
    uint64_t edges = aw->edge_count, rising = aw->rising_edges;
    latch(false);
    advance(host_now_ns + 2000);
    latch(true);
    assert(aw->edge_count == edges + 1 && aw->rising_edges == rising + 1);
    assert(!aw->known && !aw->active);
    advance(host_now_ns + 500000);
    assert(aw->known && aw->active && aw3641_output_known(aw));
    assert(aw->flash_level_pct == 100 && aw->timeout_ms == 220);
}
static void known_low_baseline(void)
{
    init_controller();
    advance(7000000000LL);
    create_unit(true);
    int64_t t0 = host_now_ns;
    assert(aw->low_since_ns == t0 && aw->edge_count == 0);
    guest_pin_init();
    recovery_boundary(t0, -1);
    one_driver_pulse();
}
static void same_low(void)
{
    start(true, false);
    assert(aw->low_since_ns == 0);
    advance(200000);
    uint64_t revision = snapshot().revision;
    latch(false); output_enable(true); route(256); iomux(1, 1u << 9);
    assert(snapshot().revision == revision);
    Esp32GpioPadSnapshot unused;
    assert(!esp32_gpio_get_controller(false));
    assert(!esp32_gpio_pad_snapshot(NULL, pin, &unused));
    assert(!esp32_gpio_pad_snapshot(&controller, 23, &unused));
    assert(!esp32_gpio_pad_snapshot(&controller, 55, &unused));
    /* The raw legacy route reader accepts an explicit register layout; its
     * numeric return is not the new typed controller's validity contract. */
    (void)esp32_gpio_matrix_out_signal(pin, false);
    assert(snapshot().revision == revision);
    gpio_write(route_addr(pin + 1), 73);
    gpio_write(0x08, 1u << (pin + 1));
    /* IE is an internal receiver gate, not external AW pad ownership. */
    iomux(1, 0);
    assert(snapshot().known && !snapshot().fun_ie && !snapshot().receiver_level);
    iomux(1, (1u << 9) | (1u << 15) | (1u << 1));
    assert(snapshot().known && !snapshot().receiver_known);
    iomux(1, 1u << 9);
    esp32_gpio_set_open_drain(pin, true);
    esp32_gpio_set_open_drain(pin, false);
    gpio_write(0x74 + pin * 4, 1u << 2);
    gpio_write(0x74 + pin * 4, 0);
    assert(aw->low_since_ns == 0 && aw->reset_at_ns == 500001 && aw->edge_count == 0);
    advance(500000); assert(!aw->known);
    advance(500001); assert_off();
}
static void equivalent_oe(void)
{
    start(true, false);
    advance(499999);
    uint64_t revision = snapshot().revision;
    route(256 | (1u << 10));
    assert(snapshot().revision > revision && snapshot().known && !snapshot().level);
    assert(aw->low_since_ns == 0 && aw->reset_at_ns == 500001 && aw->edge_count == 0);
    route(256);
    advance(500000); assert(!aw->known);
    advance(500001); assert_off();
    one_driver_pulse();
    uint64_t epoch = aw->epoch, events = aw->decoded_programs;
    int64_t timeout = aw->timeout_at_ns;
    route(256 | (1u << 10));
    route(256);
    assert(aw->known && aw->active && aw->epoch == epoch &&
           aw->timeout_at_ns == timeout && aw->decoded_programs == events);
}
static void inverted_edges(void)
{
    start(true, false);
    advance(500001); assert_off();
    /* OUT_INV is a real resolved low->high edge, without writing OUT. */
    route(256 | (1u << 9));
    assert(aw->edge_count == 1 && aw->rising_edges == 1 && snapshot().level);
    advance(host_now_ns + 500000);
    assert(aw->known && aw->active && aw3641_output_known(aw));
    assert(!aw3641_gpio_route(aw)); /* Legacy diagnostic does not gate actual pad. */
    /* OEN_INV disables this output; passive R1 makes the actual fall. */
    route(256 | (1u << 9) | (1u << 11));
    assert(aw->edge_count == 2 && aw->rising_edges == 1 && !snapshot().level);
    advance(host_now_ns + 500001); assert_off();
    route(256 | (1u << 9));
    assert(aw->edge_count == 3 && aw->rising_edges == 2);
    advance(host_now_ns + 500000);
    assert(aw->known && aw->active);
}

typedef enum Writer {
    WR_ROUTE, WR_OE_SOURCE, WR_IOMUX, WR_PULL_CONFLICT, WR_EXTERNAL,
    WR_FORCE, WR_BIAS, WR_RTC_MUX, WR_RTC_HOLD, WR_DIG_HOLD,
    WR_RTC_FORCE_HOLD, WR_DIG_FORCE_HOLD, WR_RTC_ISO, WR_DIG_ISO,
    WR_WRAPPER_ISO,
} Writer;
static Esp32GpioBoardBias *extra_bias;
static char bias_owner;
static uint32_t saved_rtcio, saved_cntl;
static void writer_prepare(Writer writer)
{
    if (writer == WR_DIG_HOLD || writer == WR_DIG_FORCE_HOLD || writer == WR_DIG_ISO) { pin = 39; }
    start(true, false);
    if (writer == WR_OE_SOURCE || writer == WR_PULL_CONFLICT || writer == WR_BIAS) {
        output_enable(false);
        if (writer == WR_OE_SOURCE) { route(73 | (1u << 10)); }
    }
    if (writer == WR_RTC_MUX) { saved_rtcio = rtcio_read(pad_aux, 0x84 + pin * 4, 4); }
    if (writer == WR_RTC_FORCE_HOLD || writer == WR_RTC_ISO) { saved_cntl = cntl_read(0x88); }
    if (writer == WR_DIG_FORCE_HOLD || writer == WR_DIG_ISO || writer == WR_WRAPPER_ISO) { saved_cntl = cntl_read(0x94); }
    assert(snapshot().known && !snapshot().level && aw->low_since_ns == 0);
}
static void writer_change(Writer writer, bool lose)
{
    switch (writer) {
    case WR_ROUTE: route(lose ? 73 : 256); break;
    case WR_OE_SOURCE: route(73 | (lose ? 0 : (1u << 10))); break;
    case WR_IOMUX: iomux(lose ? 7 : 1, 1u << 9); break;
    case WR_PULL_CONFLICT: iomux(1, (1u << 9) | (lose ? 1u << 8 : 0)); break;
    case WR_EXTERNAL: esp32_gpio_set_input(pin, lose); break;
    case WR_FORCE: esp32_gpio_force_line(pin, lose); break;
    case WR_BIAS:
        if (lose) { extra_bias = esp32_gpio_add_board_bias(&controller, pin, ESP32_GPIO_BIAS_PULL_UP, &bias_owner, NULL); assert(extra_bias); }
        else { esp32_gpio_remove_board_bias(extra_bias); extra_bias = NULL; }
        break;
    case WR_RTC_MUX: rtcio_mmio_write(0x84 + pin * 4, saved_rtcio | (lose ? 1u << 19 : 0)); break;
    case WR_RTC_HOLD: cntl_write(0xd8, lose ? 1u << pin : 0); break;
    case WR_DIG_HOLD: cntl_write(0xdc, lose ? 1u << (pin - 21) : 0); break;
    case WR_RTC_FORCE_HOLD: cntl_write(0x88, saved_cntl | (lose ? 1u << 21 : 0)); break;
    case WR_DIG_FORCE_HOLD: cntl_write(0x94, saved_cntl | (lose ? 1u << 15 : 0)); break;
    case WR_RTC_ISO: cntl_write(0x88, saved_cntl | (lose ? 1u << 4 : 0)); break;
    case WR_DIG_ISO: cntl_write(0x94, saved_cntl | (lose ? 1u << 13 : 0)); break;
    case WR_WRAPPER_ISO: cntl_write(0x94, saved_cntl | (lose ? 1u << 30 : 0)); break;
    }
}
static void source_writer(Writer writer)
{
    writer_prepare(writer);
    advance(499999);
    int64_t old_deadline = aw->reset_at_ns;
    uint64_t edges = aw->edge_count;
    writer_change(writer, true);
    assert_lost();
    assert(!snapshot().known && aw->edge_count == edges);
    advance(500000);
    writer_change(writer, false);
    assert(snapshot().known && !snapshot().level && aw->edge_count == edges);
    diagnostic("source-restored-new-low");
    recovery_boundary(host_now_ns, old_deadline);
    /* Forced/external source cannot be released by this API. Do not pretend
     * a guest's opposing push-pull level can defeat that explicit source. */
    if (writer != WR_FORCE && writer != WR_EXTERNAL) {
        route(256); output_enable(true); one_driver_pulse();
    }
}
static void pad_writer(const char *writer)
{
    start(true, false);
    advance(100000);
    if (!strcmp(writer, "enable")) {
        output_enable(false); latch(true);
        assert(!snapshot().level && aw->low_since_ns == 0);
        advance(200000); output_enable(true);
        assert(aw->edge_count == 1 && snapshot().level);
        advance(202000); output_enable(false);
    } else if (!strcmp(writer, "external")) {
        output_enable(false);
        esp32_gpio_set_input(pin, 1);
        advance(102000); esp32_gpio_set_input(pin, 0);
    } else {
        latch(true);
        advance(102000); latch(false);
    }
    assert(aw->edge_count == 2 && aw->rising_edges == 1 && !snapshot().level);
    recovery_boundary(host_now_ns, 500001);
}
static void open_drain_writer(bool mmio)
{
    start(true, false);
    advance(500001); assert_off(); one_driver_pulse();
    iomux(1, (1u << 9) | (1u << 8)); /* driven high ignores a passive pull */
    assert(aw->known && aw->active);
    uint64_t edges = aw->edge_count;
    if (mmio) { gpio_write(0x74 + pin * 4, 1u << 2); }
    else { esp32_gpio_set_open_drain(pin, true); }
    assert_lost(); assert(!snapshot().known && aw->edge_count == edges);
    if (mmio) { gpio_write(0x74 + pin * 4, 0); }
    else { esp32_gpio_set_open_drain(pin, false); }
    assert(snapshot().known && snapshot().level && !aw->known && !aw->active &&
           aw->low_since_ns == -1 && aw->reset_at_ns == -1);
    advance(host_now_ns + 500000000);
    assert(!aw->known && !aw->active);
    latch(false);
    recovery_boundary(host_now_ns, -1);
    one_driver_pulse();
}
static void high_roundtrip(bool flash)
{
    start(flash, false);
    advance(500001); assert_off();
    latch(true); advance(host_now_ns + 500000);
    assert(aw->known && aw->active);
    uint64_t resets = aw->reset_events, decoded = aw->decoded_programs;
    int64_t old_deadline = aw->timeout_at_ns;
    route(73); assert_lost();
    route(256);
    assert(snapshot().known && snapshot().level && !aw->known && !aw->active &&
           aw->low_since_ns == -1 && aw->first_rise_ns == -1);
    advance(host_now_ns + 2000000000LL);
    aw3641_reset_expired(aw); aw3641_settle_expired(aw); aw3641_timeout_expired(aw);
    assert(!aw->known && !aw->active && aw->reset_events == resets &&
           aw->decoded_programs == decoded);
    if (flash) { assert(old_deadline > 0 && aw->timeout_events == 0); }
    latch(false); recovery_boundary(host_now_ns, -1);
    latch(true); advance(host_now_ns + 500000);
    assert(aw->known && aw->active && aw->decoded_programs == decoded + 1);
}
static void unsupported_low(void)
{
    start(true, false);
    advance(500001); assert_off(); one_driver_pulse();
    uint64_t decoded = aw->decoded_programs;
    route(73); assert_lost();
    latch(false); advance(host_now_ns + 3000000000LL);
    assert(!aw->known && aw->low_since_ns == -1);
    route(256);
    recovery_boundary(host_now_ns, -1);
    assert(aw->decoded_programs == decoded && !aw->active);
    one_driver_pulse();
}
static void late_reset(bool enough)
{
    start(true, true);
    /* Deliberately hold back main-loop timers while the actual rise commits. */
    host_now_ns = enough ? 500001 : 500000;
    latch(true);
    assert(aw->edge_count == 1 && aw->rising_edges == 1);
    if (enough) {
        assert(aw->reset_events == 1 && aw->qualified && aw->phase == AW3641_PROGRAMMING);
        aw3641_reset_expired(aw);
        assert(aw->reset_events == 1);
        advance(host_now_ns + 500000);
        assert(aw->known && aw->active && aw->reset_events == 1);
    } else {
        assert(aw->reset_events == 0 && !aw->qualified && !aw->known);
        advance(host_now_ns + 500000);
        assert(!aw->known && !aw->active);
    }
}
static void gpio_reset_case(bool retained_hold, bool retained_mux)
{
    start(true, false);
    advance(499999);
    int64_t old_deadline = aw->reset_at_ns;
    uint64_t old_epoch = snapshot().epoch;
    uint32_t mux_word = rtcio_read(pad_aux, 0x84 + pin * 4, 4);
    if (retained_hold) { cntl_write(0xd8, 1u << pin); assert_lost(); }
    if (retained_mux) { rtcio_mmio_write(0x84 + pin * 4, mux_word | (1u << 19)); assert_lost(); }
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert(snapshot().epoch == old_epoch + 1 && !aw->known && !aw->active);
    if (retained_hold || retained_mux) {
        assert_lost();
        assert(!snapshot().known);
        if (retained_hold) { assert(cntl_read(0xd8) == 1u << pin); }
        if (retained_mux) { assert(rtcio_read(pad_aux, 0x84 + pin * 4, 4) & (1u << 19)); }
        advance(10000000);
        assert_lost();
        if (retained_hold) { cntl_write(0xd8, 0); }
        if (retained_mux) { rtcio_mmio_write(0x84 + pin * 4, mux_word); }
    }
    recovery_boundary(host_now_ns, old_deadline);
    guest_pin_init(); one_driver_pulse();
}
static void active_reset(void)
{
    start(true, false); advance(500001); assert_off(); one_driver_pulse();
    int64_t old_timeout = aw->timeout_at_ns;
    uint64_t resets = aw->reset_events;
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    int64_t t0 = host_now_ns;
    assert(!aw->known && !aw->active && aw->settle_at_ns == -1 && aw->timeout_at_ns == -1);
    recovery_boundary(t0, -1);
    assert(aw->reset_events == resets + 1);
    guest_pin_init(); one_driver_pulse();
    int64_t new_timeout = aw->timeout_at_ns;
    assert(new_timeout > old_timeout);
    advance(old_timeout); aw3641_timeout_expired(aw);
    assert(aw->known && aw->active && aw->timeout_events == 0);
    advance(new_timeout); assert(aw->known && !aw->active && aw->timeout_events == 1);
}
static void sticky_power(bool force_pd)
{
    start(true, false); advance(499999);
    uint32_t saved = cntl_read(force_pd ? 0x88 : 0x18);
    cntl_write(force_pd ? 0x88 : 0x18, saved | (force_pd ? 1u << 18 : 1u << 31));
    assert_lost(); assert(snapshot().override_mask & ESP32S3_PAD_AUX_POWER_REQUEST);
    cntl_write(force_pd ? 0x88 : 0x18, saved);
    assert_lost();
    guest_pin_init(); advance(9000000000LL);
    assert_lost();
    esp32_gpio_reset_hold(OBJECT(&controller), RESET_TYPE_COLD);
    assert_lost();
    assert(!snapshot().known && (snapshot().override_mask & ESP32S3_PAD_AUX_POWER_REQUEST));
}
static void release_owner(void)
{
    start(true, false);
    assert(host_object_refs == 2 && g_pad_observers && g_board_biases);
    aw3641_release(OBJECT(&unit), "edge-trace-ns", aw);
    assert(host_object_refs == 0 && !gpio_units && !g_pad_observers && !g_board_biases);
}
#endif
int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "cold")) { cold(); }
#if !OLD_RUNTIME
    else if (!strcmp(argv[1], "cold-pin9")) { pin = 9; cold(); }
    else if (!strcmp(argv[1], "cold-pin10")) { pin = 10; cold(); }
    else if (!strcmp(argv[1], "cold-pin39")) { pin = 39; cold(); }
    else if (!strcmp(argv[1], "known-low-baseline")) { known_low_baseline(); }
    else if (!strcmp(argv[1], "same-low")) { same_low(); }
    else if (!strcmp(argv[1], "equivalent-oe")) { equivalent_oe(); }
    else if (!strcmp(argv[1], "inverted-edges")) { inverted_edges(); }
    else if (!strcmp(argv[1], "writer-route")) { source_writer(WR_ROUTE); }
    else if (!strcmp(argv[1], "writer-oe-source")) { source_writer(WR_OE_SOURCE); }
    else if (!strcmp(argv[1], "writer-iomux")) { source_writer(WR_IOMUX); }
    else if (!strcmp(argv[1], "writer-pull-conflict")) { source_writer(WR_PULL_CONFLICT); }
    else if (!strcmp(argv[1], "writer-external")) { source_writer(WR_EXTERNAL); }
    else if (!strcmp(argv[1], "writer-force")) { source_writer(WR_FORCE); }
    else if (!strcmp(argv[1], "writer-bias")) { source_writer(WR_BIAS); }
    else if (!strcmp(argv[1], "writer-rtc-mux")) { source_writer(WR_RTC_MUX); }
    else if (!strcmp(argv[1], "writer-rtc-hold")) { source_writer(WR_RTC_HOLD); }
    else if (!strcmp(argv[1], "writer-digital-hold")) { source_writer(WR_DIG_HOLD); }
    else if (!strcmp(argv[1], "writer-rtc-force-hold")) { source_writer(WR_RTC_FORCE_HOLD); }
    else if (!strcmp(argv[1], "writer-digital-force-hold")) { source_writer(WR_DIG_FORCE_HOLD); }
    else if (!strcmp(argv[1], "writer-rtc-isolation")) { source_writer(WR_RTC_ISO); }
    else if (!strcmp(argv[1], "writer-digital-isolation")) { source_writer(WR_DIG_ISO); }
    else if (!strcmp(argv[1], "writer-wrapper-isolation")) { source_writer(WR_WRAPPER_ISO); }
    else if (!strcmp(argv[1], "pad-out")) { pad_writer("out"); }
    else if (!strcmp(argv[1], "pad-enable")) { pad_writer("enable"); }
    else if (!strcmp(argv[1], "pad-external")) { pad_writer("external"); }
    else if (!strcmp(argv[1], "open-drain-direct")) { open_drain_writer(false); }
    else if (!strcmp(argv[1], "open-drain-mmio")) { open_drain_writer(true); }
    else if (!strcmp(argv[1], "high-roundtrip-flash")) { high_roundtrip(true); }
    else if (!strcmp(argv[1], "high-roundtrip-torch")) { high_roundtrip(false); }
    else if (!strcmp(argv[1], "unsupported-low")) { unsupported_low(); }
    else if (!strcmp(argv[1], "late-reset-500000")) { late_reset(false); }
    else if (!strcmp(argv[1], "late-reset-500001")) { late_reset(true); }
    else if (!strcmp(argv[1], "gpio-reset-low")) { gpio_reset_case(false, false); }
    else if (!strcmp(argv[1], "gpio-reset-retains-hold")) { gpio_reset_case(true, false); }
    else if (!strcmp(argv[1], "gpio-reset-retains-mux")) { gpio_reset_case(false, true); }
    else if (!strcmp(argv[1], "gpio-reset-active")) { active_reset(); }
    else if (!strcmp(argv[1], "sticky-sleep")) { sticky_power(false); }
    else if (!strcmp(argv[1], "sticky-force-pd")) { sticky_power(true); }
    else if (!strcmp(argv[1], "release-owner")) { release_owner(); }
#endif
    else { abort(); }
    printf("PASS %s (%s actual-source C logic; no guest/hardware claim)\n",
           argv[1], OLD_RUNTIME ? "OLD" : "CANDIDATE");
    return 0;
}

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
int main(int argc, char **argv)
{
    assert(argc == 2);
    if (!strcmp(argv[1], "cold")) { cold(); }
    else { abort(); }
    printf("PASS %s (%s actual-source C logic; no guest/hardware claim)\n",
           argv[1], OLD_RUNTIME ? "OLD" : "CANDIDATE");
    return 0;
}

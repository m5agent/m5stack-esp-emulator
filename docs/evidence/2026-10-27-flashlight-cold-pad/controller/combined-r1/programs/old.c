/* Standard-C QEMU environment shims only. All GPIO/MMIO/AW/aux logic below
 * is inserted unchanged from the bootstrap patch replay by the Python test. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <inttypes.h>
#define G_N_ELEMENTS(a) (sizeof(a)/sizeof((a)[0]))
#define ARRAY_SIZE(a) G_N_ELEMENTS(a)
#define BIT(n) (UINT64_C(1) << (n))
#define g_new0(type,n) ((type *)calloc((n),sizeof(type)))
#define g_free free
static char *g_strdup(const char *text) { size_t size=strlen(text)+1;char *copy=malloc(size);memcpy(copy,text,size);return copy; }
typedef uint64_t hwaddr;
#define HWADDR_PRIx PRIx64
#define DEVICE_LITTLE_ENDIAN 0
#define A_GPIO_STRAP 0x38
#define ESP32_STRAP_MODE_FLASH_BOOT 0x12
#define TYPE_ESP32_GPIO "esp32.gpio"
#define TYPE_SYS_BUS_DEVICE "sys-bus-device"
typedef struct Object { int unused; } Object;
typedef struct DeviceState { Object parent_obj; } DeviceState;
typedef struct SysBusDevice { DeviceState parent_obj; } SysBusDevice;
typedef struct Error { int unused; } Error;
typedef enum ResetType { RESET_TYPE_COLD } ResetType;
typedef void *qemu_irq;
typedef struct MemoryRegion { int unused; } MemoryRegion;
typedef struct MemoryRegionOps {
 uint64_t (*read)(void *,hwaddr,unsigned);
 void (*write)(void *,hwaddr,uint64_t,unsigned);
 int endianness;
 struct { unsigned min_access_size,max_access_size; } valid;
} MemoryRegionOps;
typedef struct Esp32GpioState {
 SysBusDevice parent_obj;MemoryRegion iomem,iomux;qemu_irq irq;uint32_t strap_mode;
} Esp32GpioState;
#define OBJECT(obj) ((Object *)(obj))
#define ESP32_GPIO(obj) ((Esp32GpioState *)(obj))
#define SYS_BUS_DEVICE(obj) ((SysBusDevice *)(obj))
typedef int QEMUClockType;
#define QEMU_CLOCK_VIRTUAL 1
#define SCALE_NS 1
typedef struct QEMUTimerListGroup { int unused; } QEMUTimerListGroup;
typedef void QEMUTimerCB(void *);
typedef struct QEMUTimer {
 int64_t expire_time;QEMUTimerCB *cb;void *opaque;int scale,attributes;
} QEMUTimer;
int64_t qemu_clock_get_ns(QEMUClockType);
void timer_init_full(QEMUTimer *,QEMUTimerListGroup *,QEMUClockType,int,int,QEMUTimerCB *,void *);
void timer_del(QEMUTimer *);
void timer_mod_ns(QEMUTimer *,int64_t);
static QEMUTimer *timer_new_ns(QEMUClockType type,QEMUTimerCB *cb,void *opaque) {
 QEMUTimer *timer=calloc(1,sizeof(*timer));timer_init_full(timer,NULL,type,SCALE_NS,0,cb,opaque);return timer;
}
static void timer_free(QEMUTimer *timer) { if(timer){timer_del(timer);free(timer);} }
typedef struct Visitor { int unused; } Visitor;
typedef struct QObject { int unused; } QObject;
typedef struct QList { QObject parent; } QList;
#define QOBJECT(obj) ((QObject *)(obj))
static bool visit_type_bool(Visitor *v,const char *n,bool *p,Error **e) { return true; }
static bool visit_type_uint64(Visitor *v,const char *n,uint64_t *p,Error **e) { return true; }
static bool visit_type_int64(Visitor *v,const char *n,int64_t *p,Error **e) { return true; }
static bool visit_type_str(Visitor *v,const char *n,char **p,Error **e) { return true; }
static bool visit_type_any(Visitor *v,const char *n,QObject **p,Error **e) { return true; }
static QList *qlist_new(void) { return calloc(1,sizeof(QList)); }
static void qlist_append_int(QList *list,int64_t value) { }
static void qlist_append_obj(QList *list,QObject *value) { free(value); }
static void qobject_unref(QObject *obj) { free(obj); }
typedef void ObjectPropertyAccessor(Object *,Visitor *,const char *,void *,Error **);
typedef void ObjectPropertyRelease(Object *,const char *,void *);
typedef struct ObjectProperty { int unused; } ObjectProperty;
Object *object_ref(void *);
void object_unref(void *);
Object *object_dynamic_cast(Object *,const char *);
Object *object_dynamic_cast_assert(Object *,const char *,const char *,int,const char *);
bool object_property_set_int(Object *,const char *,int64_t,Error **);
ObjectProperty *object_property_add(Object *,const char *,const char *,ObjectPropertyAccessor *,ObjectPropertyAccessor *,ObjectPropertyRelease *,void *);
void qemu_set_irq(qemu_irq,int);
void sysbus_init_mmio(SysBusDevice *,MemoryRegion *);
void sysbus_init_irq(SysBusDevice *,qemu_irq *);
void memory_region_init_io(MemoryRegion *,Object *,const MemoryRegionOps *,void *,const char *,uint64_t);
void memory_region_add_subregion_overlap(MemoryRegion *,hwaddr,MemoryRegion *,int);
void error_setg_internal(Error **,const char *,int,const char *,const char *,...);
#define error_setg(errp,...) error_setg_internal(errp,__FILE__,__LINE__,__func__,__VA_ARGS__)
extern Error *error_fatal;
typedef void (*esp32_gpio_out_cb)(void *,int,int);
int esp32_gpio_get_line(int);
void esp32_gpio_set_input(int,int);
void esp32_gpio_set_open_drain(int,bool);
void esp32_gpio_force_line(int,int);
void esp32_gpio_add_out_listener(int,esp32_gpio_out_cb,void *);
void esp32_ledc_gpio_route_changed(bool);
void m5_unit_gpio_route_changed(bool,unsigned);
int esp32_gpio_matrix_out_signal(int,bool);
int esp32_gpio_matrix_in_pin(unsigned,bool);
typedef struct M5Unit {
 DeviceState parent_obj;char *unit_id;int yellow,white;bool s3;
 uint64_t input_events,output_transitions;
} M5Unit;

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

static int gpio_trace_pin(void)
{
    const char *value = getenv("M5SW_GPIO_TRACE_PIN");
    int pin = value ? atoi(value) : 18;

    return pin >= 0 && pin < GPIO_NPINS ? pin : 18;
}

void esp32_gpio_set_input(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    uint64_t before = gpio_line64();
    if (level) {
        g_ext_in |= 1ULL << pin;
    } else {
        g_ext_in &= ~(1ULL << pin);
    }
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
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    if (enable) {
        g_open_drain |= 1ULL << pin;
    } else {
        g_open_drain &= ~(1ULL << pin);
    }
}

void esp32_gpio_force_line(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    g_force_mask |= 1ULL << pin;
    if (level) {
        g_force_level |= 1ULL << pin;
    } else {
        g_force_level &= ~(1ULL << pin);
    }
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
static uint64_t gpio_line64(void)
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
    uint64_t in = gpio_line64();
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
    uint64_t before = gpio_line64();
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
                esp32_ledc_gpio_route_changed(g_gpio_s3);
                m5_unit_gpio_route_changed(g_gpio_s3,
                                           (addr - output_base) / 4);
            }
            /*
             * GPIO_PIN0_REG starts at 0x74 on ESP32-S3.  M5GFX's
             * pinMode(input*) uses gpio_ll_od_enable(), which leaves the
             * output enable set and relies on open-drain + latch-high
             * semantics so an external low can still pull the line down.
             */
            unsigned pin_base = g_gpio_s3 ? 0x74 : 0x88;
            if (addr >= pin_base && addr < pin_base + GPIO_NPINS * 4) {
                uint64_t pin_bit = 1ULL << ((addr - pin_base) / 4);
                if (value & (1u << 2)) {
                    g_open_drain |= pin_bit;
                } else {
                    g_open_drain &= ~pin_bit;
                }
            }
        }
        break;
    }
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
    memset(g_regs, 0, sizeof(g_regs));
    g_open_drain = 0;
    gpio_update_irq();
}

static void esp32_gpio_realize(DeviceState *dev, Error **errp)
{
}

static void esp32_gpio_init(Object *obj)
{
    Esp32GpioState *s = ESP32_GPIO(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    g_gpio_device = s;
    g_gpio_s3 = object_dynamic_cast(obj, "esp32s3.gpio") != NULL;

    /* Set the default value for the strap_mode property */
    object_property_set_int(obj, "strap_mode", ESP32_STRAP_MODE_FLASH_BOOT, &error_fatal);

    memory_region_init_io(&s->iomem, obj, &uart_ops, s,
                          TYPE_ESP32_GPIO, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
}


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

extern int esp32_gpio_matrix_out_signal(int pin, bool s3);
extern int esp32_gpio_matrix_in_pin(unsigned signal, bool s3);


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
 * State/timers follow existing GPIOUnit VM-process ownership; no hotplug.
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
    /* Existing API returns -1 for its observed GPIO-matrix OUT inversion bit.
     * No claim about inversion/electrical paths beyond that API is made.
     * LEDC/RMT/UART routes do not supply pad waveforms in this backend.
     */
    return esp32_gpio_matrix_out_signal(s->unit->yellow, s->unit->s3) == 256;
}

static bool aw3641_pad_synchronized(AW3641State *s)
{
    return !!esp32_gpio_get_line(s->unit->yellow) == s->en;
}

static bool aw3641_output_known(AW3641State *s)
{
    /* In particular, do not conceal UNIT-HOST-36's missing reset callback. */
    return s->known && aw3641_gpio_route(s) && aw3641_pad_synchronized(s);
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

/* Losing the observed route/pad is a lifecycle break, not a pad edge.
 * No previous low interval, pulse train or pending timer may qualify a later
 * GPIO restoration.  Recovery requires a new observed GPIO falling edge and
 * the complete documented long-low interval.  Keep the edge trace/counters
 * and last-program value as history; never infer an LEDC/RMT waveform here.
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
    if (!aw3641_pad_synchronized(s)) {
        aw3641_observation_lost(s, "pad-callback-not-synchronized");
        return false;
    }
    if (!aw3641_gpio_route(s)) {
        aw3641_observation_lost(s, "gpio-route-not-observed");
        return false;
    }
    return true;
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

static void aw3641_pad_changed(void *opaque, int pin, int value)
{
    AW3641State *s = opaque;
    bool high = !!value;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    int64_t duration = s->last_edge_ns < 0 ? -1 : now - s->last_edge_ns;
    if (pin != s->unit->yellow || high == s->en) { return; }
    /* A real rising callback also proves the preceding continuously observed
     * low interval if timer delivery was delayed by the main event loop.
     */
    if (high && !s->en && !s->ready && s->low_since_ns >= 0 &&
        now - s->low_since_ns >= AW3641_RESET_NS && aw3641_gpio_route(s)) {
        aw3641_finish_reset(s);
    }
    s->en = high;
    s->last_edge_ns = now;
    aw3641_trace(s, high, now);
    if (!aw3641_gpio_route(s)) {
        aw3641_observation_lost(s, "gpio-route-not-observed");
        return;
    }
    if (!aw3641_pad_synchronized(s)) {
        aw3641_observation_lost(s, "pad-callback-not-synchronized");
        return;
    }
    if (!high) {
        s->low_since_ns = now;
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
        s->reset_at_ns = now + AW3641_RESET_NS;
        s->reset_epoch = s->epoch;
        timer_mod_ns(s->reset_timer, s->reset_at_ns);
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
/* END AW3641 CORE */

static void aw3641_bool_get(Object *o, Visitor *v, const char *name,
                           void *opaque, Error **errp)
{
    AW3641State *s = opaque;
    bool value = false;
    if (!strcmp(name, "flash-mode")) { value = s->flash_mode; }
    else if (!strcmp(name, "mode-frozen")) { value = s->mode_frozen; }
    else if (!strcmp(name, "en-level")) { value = !!esp32_gpio_get_line(s->unit->yellow); }
    else if (!strcmp(name, "pad-synchronized")) { value = aw3641_pad_synchronized(s); }
    else if (!strcmp(name, "gpio-route-supported")) { value = aw3641_gpio_route(s); }
    else if (!strcmp(name, "output-known")) { value = aw3641_output_known(s); }
    else if (!strcmp(name, "active")) { value = aw3641_output_known(s) && s->active; }
    else if (!strcmp(name, "waveform-qualified")) { value = s->qualified && aw3641_gpio_route(s) && aw3641_pad_synchronized(s); }
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

static AW3641State *aw3641_new(M5Unit *unit)
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
    esp32_gpio_set_input(unit->yellow, 0); /* Schematic EN 10K pull-down, digital bias only. */
    s->en = !!esp32_gpio_get_line(unit->yellow);
    if (!s->en) {
        s->low_since_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        s->reset_at_ns = s->low_since_ns + AW3641_RESET_NS;
        s->reset_epoch = s->epoch;
        timer_mod_ns(s->reset_timer, s->reset_at_ns);
    }
    Object *o = OBJECT(unit);
    const char *const bools[] = {"flash-mode", "mode-frozen", "en-level",
        "pad-synchronized", "gpio-route-supported", "output-known", "active",
        "waveform-qualified", "pulse-count-capped", "bit-exact-supported",
        "live-mode-change-supported", "reset-observation-supported"};
    const char *const uints[] = {"pulse-count", "last-program-count", "flash-level-pct",
        "timeout-ms", "edge-count", "rising-edges", "decoded-programs",
        "unqualified-programs", "reset-events", "timeout-events", "trace-overflows"};
    const char *const times[] = {"last-edge-ns", "first-rise-ns", "settle-at-ns", "timeout-at-ns"};
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
    object_property_add(o, "edge-trace-ns", "any", aw3641_trace_get, NULL, NULL, s);
    esp32_gpio_add_out_listener(unit->yellow, aw3641_pad_changed, s);
    return s;
}
/* END AW3641 NOMINAL DIGITAL MODEL */
void m5_unit_gpio_initial_complete(M5Unit *unit)
{
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (g->unit == unit && g->flashlight) {
            g->flashlight->mode_frozen = true;
            return;
        }
    }
}
void m5_unit_gpio_route_changed(bool s3, unsigned pin)
{
    for (GPIOUnit *g = gpio_units; g; g = g->next) {
        if (g->s3 == s3 && g->unit->yellow == (int)pin && g->flashlight) {
            /* Restoring GPIO also discards any unsupported/cold low interval;
             * route changes never supply a new pad edge or reset baseline.
             */
            aw3641_observation_lost(g->flashlight,
                aw3641_gpio_route(g->flashlight) ?
                "awaiting-long-low-after-route-change" : "gpio-route-not-observed");
        }
    }
}
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
    /* Fixture wiring only; actual AW construction and lifecycle are replayed. */
    GPIOUnit *g = g_new0(GPIOUnit, 1);
    g->unit = &unit; g->s3 = true; g->next = gpio_units; gpio_units = g;
#if OLD_RUNTIME
    aw = aw3641_new(&unit);
#else
    aw = aw3641_new(&unit, &err);
#endif
    assert(!err && aw);
    g->flashlight = aw;
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

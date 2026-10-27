
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define QEMU_CLOCK_VIRTUAL 1
#define g_new0(type,n) ((type *)calloc((n),sizeof(type)))
#define g_free free
static char *g_strdup(const char *v) { size_t n=strlen(v)+1; char *p=malloc(n); memcpy(p,v,n); return p; }
typedef struct Object { int unused; } Object;
#define OBJECT(o) ((Object *)(o))
typedef struct M5Unit { int white,yellow; bool s3; uint64_t input_events,output_transitions; } M5Unit;
typedef struct Error { const char *message; } Error;
static Error last_error;
static void error_setg(Error **e,const char *message,...) { if(e) { last_error.message=message; *e=&last_error; } }
typedef struct QObject { unsigned kind; } QObject;
typedef struct QInt { QObject base; int64_t value; } QInt;
typedef struct QList { QObject base; size_t count; QObject *items[1024]; } QList;
#define QOBJECT(o) ((QObject *)(o))
static QList *qlist_new(void) { QList *q=calloc(1,sizeof(*q)); q->base.kind=1; return q; }
static void qlist_append_obj(QList *q,QObject *value) { assert(q->count<ARRAY_SIZE(q->items)); q->items[q->count++]=value; }
static void qlist_append_int(QList *q,int64_t value) { QInt *n=calloc(1,sizeof(*n));n->base.kind=2;n->value=value;qlist_append_obj(q,QOBJECT(n)); }
static void qobject_unref(QObject *q) { if(q->kind==1) { QList *a=(QList *)q;for(size_t i=0;i<a->count;i++)qobject_unref(a->items[i]); }free(q); }
typedef struct Visitor { bool input,boolean; uint64_t u64; int64_t i64; size_t pairs; char text[1024]; } Visitor;
static bool visit_type_bool(Visitor *v,const char *n,bool *p,Error **e) { if(v->input)*p=v->boolean;else v->boolean=*p;return true; }
static bool visit_type_uint64(Visitor *v,const char *n,uint64_t *p,Error **e) { v->u64=*p;return true; }
static bool visit_type_int64(Visitor *v,const char *n,int64_t *p,Error **e) { v->i64=*p;return true; }
static bool visit_type_str(Visitor *v,const char *n,char **p,Error **e) { snprintf(v->text,sizeof(v->text),"%s",*p);return true; }
static bool visit_type_any(Visitor *v,const char *n,QObject **p,Error **e) {
 QList *a=(QList *)*p;v->pairs=a->count;
 for(size_t i=0;i<a->count;i++) { QList *pair=(QList *)a->items[i]; assert(pair->count==2);assert(((QInt *)pair->items[1])->value==0||((QInt *)pair->items[1])->value==1); }
 return true;
}
typedef void (*PropertyFn)(Object *,Visitor *,const char *,void *,Error **);
typedef struct Property { const char *name,*type;PropertyFn get,set;void *opaque; } Property;
static Property properties[1024];static unsigned property_count;
static void object_property_add(Object *o,const char *name,const char *type,PropertyFn get,PropertyFn set,void *release,void *opaque) {
 assert(property_count<ARRAY_SIZE(properties));
 properties[property_count++]=(Property){name,type,get,set,opaque};
}
typedef struct QEMUTimer { bool pending;int64_t at;void (*cb)(void *);void *opaque; } QEMUTimer;
static QEMUTimer *timers[128];static unsigned timer_count;static int64_t now_ns;
static int64_t qemu_clock_get_ns(int clock) { assert(clock==QEMU_CLOCK_VIRTUAL);return now_ns; }
static QEMUTimer *timer_new_ns(int clock,void (*cb)(void *),void *opaque) { assert(clock==QEMU_CLOCK_VIRTUAL);assert(timer_count<ARRAY_SIZE(timers));QEMUTimer *t=calloc(1,sizeof(*t));t->cb=cb;t->opaque=opaque;timers[timer_count++]=t;return t; }
static void timer_mod_ns(QEMUTimer *t,int64_t at) { assert(at>=now_ns);t->at=at;t->pending=true; }
static void timer_del(QEMUTimer *t) { t->pending=false; }
static void advance(int64_t target) {
 assert(target>=now_ns);unsigned count=0;
 for(;;) { QEMUTimer *next=NULL;for(unsigned i=0;i<timer_count;i++)if(timers[i]->pending&&timers[i]->at<=target&&(!next||timers[i]->at<next->at))next=timers[i];
  if(!next)break;assert(++count<10000);now_ns=next->at;next->pending=false;next->cb(next->opaque);
 }now_ns=target;
}

#include <inttypes.h>
#define BIT(x) (1ULL << (x))
#define HWADDR_PRIx PRIx64
#define A_GPIO_STRAP 0x38
typedef uint64_t hwaddr;
typedef struct Esp32GpioState { unsigned strap_mode; int irq; } Esp32GpioState;
#define ESP32_GPIO(p) ((Esp32GpioState *)(p))
typedef void (*esp32_gpio_out_cb)(void *,int,int);
int esp32_gpio_get_line(int pin);
static unsigned ledc_route_notifications;
static void qemu_set_irq(int irq,int level) { (void)irq; (void)level; }
static void esp32_ledc_gpio_route_changed(bool s3) { ledc_route_notifications++; }
void m5_unit_gpio_route_changed(bool s3,unsigned pin);

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


int esp32_gpio_matrix_out_signal(int pin, bool s3)
{
    if (pin < 0 || pin >= (s3 ? 49 : 40)) { return -1; }
    uint32_t value = g_regs[((s3 ? 0x554 : 0x530) + pin * 4) / 4];
    return (value & BIT(9)) ? -1 : value & 0x1ff;
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

static bool aw3641_timer_source(AW3641State *s)
{
    if (!aw3641_pad_synchronized(s)) {
        aw3641_unqualified(s, "pad-callback-not-synchronized");
        return false;
    }
    if (!aw3641_gpio_route(s)) {
        aw3641_unqualified(s, "gpio-route-not-observed");
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
        aw3641_unqualified(s, "gpio-route-not-observed");
    }
    if (!aw3641_pad_synchronized(s)) {
        aw3641_unqualified(s, "pad-callback-not-synchronized");
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
/* Tests are independent of the candidate helper: all route changes enter the
 * extracted real esp32_gpio_write MMIO path, all edges use OUT W1TS/W1TC. */
static M5Unit fixture_units[8];
static GPIOUnit fixture_links[8];
static AW3641State *fixture_states[8];
static unsigned fixture_count, checks, failures, cases;
static const char *case_name;
static bool get_state_bool(AW3641State *s,const char *name) {
    Visitor v={0}; aw3641_bool_get(NULL,&v,name,s,NULL); return v.boolean;
}
static void check(bool ok,const char *expr,int line,AW3641State *s) {
    checks++; if(ok)return; failures++;
    printf("{\"event\":\"FAIL\",\"case\":\"%s\",\"line\":%d,\"assertion\":\"%s\",\"known_internal\":%d,\"active_internal\":%d,\"known_getter\":%d,\"phase\":%d,\"edges\":%" PRIu64 ",\"rising_edges\":%" PRIu64 ",\"decoded\":%" PRIu64 ",\"low_since_ns\":%" PRId64 ",\"reset_at_ns\":%" PRId64 ",\"settle_at_ns\":%" PRId64 ",\"timeout_at_ns\":%" PRId64 "}\n",
           case_name,line,expr,s->known,s->active,get_state_bool(s,"output-known"),s->phase,
           s->edge_count,s->rising_edges,s->decoded_programs,s->low_since_ns,s->reset_at_ns,s->settle_at_ns,s->timeout_at_ns);
}
#define CHECK(s,x) check(!!(x),#x,__LINE__,s)
static void mmio(hwaddr address,uint32_t value) { esp32_gpio_write(NULL,address,value,4); }
static void route(bool s3,unsigned pin,uint32_t signal) {
    bool previous_layout=g_gpio_s3; g_gpio_s3=s3;
    mmio((s3?0x554:0x530)+pin*4,signal); g_gpio_s3=previous_layout;
}
static void pad_at(unsigned pin,bool value) {
    mmio(pin<32?(value?0x08:0x0c):(value?0x14:0x18),1u<<(pin&31));
}
static void pad(AW3641State *s,bool value) { pad_at(s->unit->yellow,value); }
static void fresh(const char *name) {
    for(unsigned i=0;i<timer_count;i++)free(timers[i]);
    for(unsigned i=0;i<fixture_count;i++)free(fixture_states[i]);
    fixture_count=timer_count=property_count=0; gpio_units=NULL; now_ns=0;
    memset(g_regs,0,sizeof(g_regs)); memset(g_listeners,0,sizeof(g_listeners));
    memset(g_listener_count,0,sizeof(g_listener_count));
    memset(fixture_units,0,sizeof(fixture_units)); memset(fixture_links,0,sizeof(fixture_links));
    g_ext_in=g_open_drain=g_force_mask=g_force_level=0; g_gpio_device=NULL;
    ledc_route_notifications=0;g_gpio_s3=true;case_name=name;cases++;
    mmio(0x24,(1u<<2)|(1u<<3));
    route(true,2,256);route(true,3,256);route(false,2,256);route(false,3,256);
}
static AW3641State *create(bool flash,bool s3,unsigned pin) {
    assert(fixture_count<ARRAY_SIZE(fixture_states));unsigned i=fixture_count++;
    M5Unit *u=&fixture_units[i];*u=(M5Unit){.white=1,.yellow=pin,.s3=s3};
    AW3641State *s=aw3641_new(u);fixture_states[i]=s;
    GPIOUnit *g=&fixture_links[i];g->unit=u;g->flashlight=s;g->s3=s3;g->next=gpio_units;gpio_units=g;
    Visitor v={.input=true,.boolean=flash};Error *e=NULL;aw3641_mode_set(NULL,&v,"flash-mode",s,&e);assert(!e);
    m5_unit_gpio_initial_complete(u);assert(s->mode_frozen);
    return s;
}
static AW3641State *active(bool flash) {
    AW3641State *s=create(flash,true,2);advance(now_ns+600000);
    CHECK(s,s->phase==AW3641_READY_LOW&&s->known&&!s->active);
    pad(s,true);advance(now_ns+500000);
    CHECK(s,s->known&&s->active&&s->qualified&&get_state_bool(s,"output-known"));
    return s;
}
static void no_output(AW3641State *s) {
    CHECK(s,!s->known&&!s->active&&!s->qualified&&!s->ready);
    CHECK(s,!get_state_bool(s,"output-known")&&!get_state_bool(s,"active")&&!get_state_bool(s,"waveform-qualified"));
}
static void no_timers(AW3641State *s) {
    CHECK(s,!s->reset_timer->pending&&!s->settle_timer->pending&&!s->timeout_timer->pending);
    CHECK(s,s->reset_at_ns==-1&&s->settle_at_ns==-1&&s->timeout_at_ns==-1);
}
static void recover(AW3641State *s) {
    pad(s,true);pad(s,false);advance(now_ns+500000);no_output(s);
    advance(now_ns+1);CHECK(s,s->known&&!s->active&&s->ready&&s->qualified);
    pad(s,true);advance(now_ns+500000);CHECK(s,s->known&&s->active&&s->qualified);
}
static void roundtrip(bool flash,unsigned unsupported,const char *name) {
    fresh(name);AW3641State *s=active(flash);
    uint64_t edges=s->edge_count,rises=s->rising_edges,decoded=s->decoded_programs,epoch=s->epoch;
    int64_t original_timeout=s->timeout_at_ns;
    route(true,2,unsupported);
    /* Internal assertions happen before any read of a QOM getter. */
    CHECK(s,!s->known&&!s->active&&!s->qualified&&!s->ready);
    CHECK(s,s->epoch>epoch);no_timers(s);
    CHECK(s,s->low_since_ns==-1&&s->first_rise_ns==-1);
    route(true,2,256);no_output(s);no_timers(s);
    CHECK(s,s->edge_count==edges&&s->rising_edges==rises&&s->decoded_programs==decoded);
    CHECK(s,!flash||now_ns<original_timeout);
    advance(now_ns+2000000000LL);no_output(s);
    CHECK(s,s->edge_count==edges&&s->rising_edges==rises&&s->decoded_programs==decoded);
    recover(s);
}
static void phase_loss(unsigned phase,const char *name) {
    fresh(name);AW3641State *s=create(true,true,2);
    if(phase>=1)advance(now_ns+600000);
    if(phase>=2)pad(s,true);
    if(phase>=3)advance(now_ns+500000);
    if(phase==4)pad(s,false);
    uint64_t edges=s->edge_count,decoded=s->decoded_programs;
    route(true,2,73);no_timers(s);route(true,2,256);no_output(s);
    advance(now_ns+2000000000LL);no_output(s);
    CHECK(s,s->edge_count==edges&&s->decoded_programs==decoded);
    recover(s);
}
static void stale_low(unsigned kind,const char *name) {
    fresh(name);AW3641State *s=active(true);uint64_t resets=s->reset_events;
    if(kind==0) { pad(s,false);advance(now_ns+200000);route(true,2,73); }
    else { route(true,2,73);pad(s,false); }
    if(kind==1) { advance(now_ns+200000);route(true,2,256);advance(now_ns+600000); }
    else {
        /* Delayed dispatch is deliberate: edge shortcut must not borrow the
         * invalid interval even when reset callback was never delivered. */
        now_ns+=600000;route(true,2,256);pad(s,true);advance(now_ns+500000);
    }
    no_output(s);CHECK(s,s->reset_events==resets);
    if(!s->en) { pad(s,true);advance(now_ns+500000);no_output(s); }
    recover(s);
}
static void stale_callbacks(unsigned kind,const char *name) {
    fresh(name);AW3641State *s=create(true,true,2);
    if(kind>0){advance(now_ns+600000);pad(s,true);}
    if(kind>1)advance(now_ns+500000);
    route(true,2,73);route(true,2,256);uint64_t decoded=s->decoded_programs,reset=s->reset_events,timeout=s->timeout_events;
    now_ns+=2000000000LL;
    /* Invoke real saved callback entrypoints despite timer_del, then invoke
     * the scheduler. They must not revive state or increment decoder counts. */
    aw3641_reset_expired(s);aw3641_settle_expired(s);aw3641_timeout_expired(s);
    advance(now_ns);no_output(s);no_timers(s);
    CHECK(s,s->decoded_programs==decoded&&s->reset_events==reset&&s->timeout_events==timeout);
}
static void repeated_and_ignored(void) {
    fresh("repeated-and-ignored-register-writes");AW3641State *s=active(false);
    uint64_t edges=s->edge_count,decoded=s->decoded_programs,epoch=s->epoch;
    unsigned notices=ledc_route_notifications;
    route(true,2,256);route(true,2,256|BIT(10));
    CHECK(s,s->known&&s->active&&s->epoch==epoch);
    CHECK(s,ledc_route_notifications==notices);
    route(true,2,73);uint64_t unqualified=s->unqualified_programs;
    CHECK(s,unqualified==1);route(true,2,73);route(true,2,81);route(true,2,256|BIT(9));
    no_output(s);CHECK(s,s->unqualified_programs==unqualified);
    route(true,2,256);no_output(s);CHECK(s,s->edge_count==edges&&s->decoded_programs==decoded);
}
static void instance_isolation(void) {
    fresh("other-pin-and-layout-isolation");
    AW3641State *s=create(false,true,2),*other=create(false,true,3),*classic=create(false,false,2);
    advance(now_ns+600000);pad(s,true);pad(other,true);advance(now_ns+500000);
    CHECK(s,s->known&&s->active);CHECK(other,other->known&&other->active);CHECK(classic,classic->known&&classic->active);
    uint64_t s_edges=s->edge_count,other_edges=other->edge_count,classic_edges=classic->edge_count;
    route(false,2,73);CHECK(s,s->known&&s->active);CHECK(other,other->known&&other->active);no_output(classic);
    route(true,3,73);CHECK(s,s->known&&s->active);no_output(other);no_output(classic);
    route(true,2,73);no_output(s);
    CHECK(s,s->edge_count==s_edges&&other->edge_count==other_edges&&classic->edge_count==classic_edges);
}
static void short_low(void) {
    fresh("new-supported-short-low-does-not-requalify");AW3641State *s=active(true);
    route(true,2,73);route(true,2,256);pad(s,false);advance(now_ns+500000);pad(s,true);
    advance(now_ns+500000);no_output(s);recover(s);
}
static void unsupported_constructor(bool delayed,const char *name) {
    fresh(name);route(true,2,73);AW3641State *s=create(true,true,2);
    uint64_t edges=s->edge_count,decoded=s->decoded_programs;
    if(delayed) now_ns+=600000; else advance(now_ns+200000);
    route(true,2,256);no_output(s);no_timers(s);
    if(delayed) { pad(s,true);advance(now_ns+500000); }
    else advance(now_ns+600000);
    no_output(s);CHECK(s,s->decoded_programs==decoded);
    CHECK(s,s->edge_count==edges+(delayed?1:0));recover(s);
}
int main(void) {
    const unsigned unsupported[]={73,81,0,511,256|BIT(9)};
    const char *torch_names[]={"torch-ledc-roundtrip-before-any-getter","torch-rmt-roundtrip","torch-zero-roundtrip","torch-signal511-roundtrip","torch-out-inv-roundtrip"};
    const char *flash_names[]={"flash-ledc-roundtrip-before-deadline","flash-rmt-roundtrip-before-deadline","flash-zero-roundtrip-before-deadline","flash-signal511-roundtrip-before-deadline","flash-out-inv-roundtrip-before-deadline"};
    for(unsigned i=0;i<ARRAY_SIZE(unsupported);i++){roundtrip(false,unsupported[i],torch_names[i]);roundtrip(true,unsupported[i],flash_names[i]);}
    phase_loss(0,"reset-pending-loss");phase_loss(1,"ready-low-loss");phase_loss(2,"programming-settle-pending-loss");phase_loss(3,"flash-timeout-pending-loss");phase_loss(4,"falling-reset-pending-loss");
    stale_low(0,"pre-loss-low-cannot-cross-unsupported-with-delayed-timer");
    stale_low(1,"unsupported-fall-return-low-before-timer");
    stale_low(2,"unsupported-fall-return-rise-delayed-timer");
    stale_callbacks(0,"cancel-reset-and-stale-callback");stale_callbacks(1,"cancel-settle-and-stale-callback");stale_callbacks(2,"cancel-timeout-and-stale-callback");
    repeated_and_ignored();instance_isolation();short_low();
    unsupported_constructor(false,"unsupported-constructor-return-low-before-deadline");
    unsupported_constructor(true,"unsupported-constructor-return-rise-after-delayed-deadline");
    printf("{\"event\":\"SUMMARY\",\"cases\":%u,\"checks\":%u,\"failures\":%u,\"result\":\"%s\",\"api_contacted\":false,\"guest_execution\":\"NOT RUN\",\"hardware_execution\":\"NOT RUN\"}\n",cases,checks,failures,failures?"FAIL":"PASS");
    return failures?1:0;
}

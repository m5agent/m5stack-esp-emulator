/* Actual source fragments; GPL-2.0-or-later. Host-only test stubs. */
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include "queue.h"
#define BIT(n) (1u << (n))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define HWADDR_PRIx PRIx64
#define A_GPIO_STRAP 0x38
#define GPIO_NPINS 54
#define ESP32_LEDC_CHANNEL_CNT 16
typedef uint64_t hwaddr;
typedef void Object; typedef void Error;
typedef struct { double number; } Visitor;
typedef struct { unsigned value; } LEDState;
typedef struct Esp32LEDCState {
    uint32_t duty_res[8], timer_conf_reg[8], timer_value_reg[8];
    uint32_t channel_conf0_reg[16], channel_duty_reg[16], conf_reg;
    bool esp32s3_layout;
    LEDState led[16];
    QLIST_ENTRY(Esp32LEDCState) route_observer_next;
} Esp32LEDCState;
typedef Esp32LEDCState DeviceState;
#define ESP32_LEDC(x) ((Esp32LEDCState *)(x))
#define DEVICE(x) (x)
static void *error_fatal;
static unsigned led_writes;
static void qdev_realize(void *dev, void *bus, void *error) {}
static void led_set_intensity(LEDState *led, unsigned value) { led->value=value; led_writes++; }
static QLIST_HEAD(, Esp32LEDCState) ledc_devices = QLIST_HEAD_INITIALIZER(ledc_devices);
static uint32_t g_regs[512];
static bool g_gpio_s3 = true;
static uint64_t g_open_drain;
static uint64_t gpio_line64(void) { return 0; }
static void gpio_notify(uint64_t a, uint64_t b) {}
static void gpio_transition_irq(uint64_t a, uint64_t b) {}
static bool visit_type_number(Visitor *v, const char *name, double *n, Error **e) {v->number=*n;return true;}
typedef struct { const char *unit_id; int yellow; uint64_t output_transitions; } M5Unit;
typedef struct GPIOUnit {
    M5Unit *unit; struct GPIOUnit *next; bool s3;
    double voltage, duty, frequency; unsigned pwm_signal;
} GPIOUnit;
static GPIOUnit *gpio_units;
void esp32_ledc_gpio_route_changed(bool s3);
#define REG32(n,a) enum { A_##n = a };
REG32(LEDC_CONF_REG, 0x190)

#define LEDC_REG_GROUP(name, base) \
    REG32(name ## _CONF0_REG, (base)) \
    REG32(name ## _CONF1_REG, ((base) + 0x00C)) \
    REG32(name ## _DUTY_REG, ((base) + 0x008)) \
    REG32(name ## _DUTY_R_REG, ((base) + 0x010))

#define LEDC_TIMER_REG_GROUP(name, base) \
    REG32(name ## _CONF_REG, (base)) \
    REG32(name ## _VALUE_REG, ((base) + 0x004))

LEDC_REG_GROUP(LEDC_HSCH0, 0x000)
LEDC_REG_GROUP(LEDC_HSCH1, 0x014)
LEDC_REG_GROUP(LEDC_HSCH2, 0x028)
LEDC_REG_GROUP(LEDC_HSCH3, 0x03C)
LEDC_REG_GROUP(LEDC_HSCH4, 0x050)
LEDC_REG_GROUP(LEDC_HSCH5, 0x064)
LEDC_REG_GROUP(LEDC_HSCH6, 0x078)
LEDC_REG_GROUP(LEDC_HSCH7, 0x08C)

LEDC_REG_GROUP(LEDC_LSCH0, 0x0A0)
LEDC_REG_GROUP(LEDC_LSCH1, 0x0B4)
LEDC_REG_GROUP(LEDC_LSCH2, 0x0C8)
LEDC_REG_GROUP(LEDC_LSCH3, 0x0DC)
LEDC_REG_GROUP(LEDC_LSCH4, 0x0F0)
LEDC_REG_GROUP(LEDC_LSCH5, 0x104)
LEDC_REG_GROUP(LEDC_LSCH6, 0x118)
LEDC_REG_GROUP(LEDC_LSCH7, 0x12C)

LEDC_TIMER_REG_GROUP(LEDC_HSTIMER0, 0x140)
LEDC_TIMER_REG_GROUP(LEDC_HSTIMER1, 0x148)
LEDC_TIMER_REG_GROUP(LEDC_HSTIMER2, 0x150)
LEDC_TIMER_REG_GROUP(LEDC_HSTIMER3, 0x158)

LEDC_TIMER_REG_GROUP(LEDC_LSTIMER0, 0x160)
LEDC_TIMER_REG_GROUP(LEDC_LSTIMER1, 0x168)
LEDC_TIMER_REG_GROUP(LEDC_LSTIMER2, 0x170)
LEDC_TIMER_REG_GROUP(LEDC_LSTIMER3, 0x178)

REG32(LEDC_INT_RAW_REG, 0x180)
REG32(LEDC_INT_ST_REG, 0x184)
REG32(LEDC_INT_ENA_REG, 0x188)
REG32(LEDC_INT_CLR_REG, 0x18C)

int esp32_gpio_matrix_out_signal(int pin, bool s3)
{
    if (pin < 0 || pin >= (s3 ? 49 : 40)) { return -1; }
    uint32_t value = g_regs[((s3 ? 0x554 : 0x530) + pin * 4) / 4];
    return (value & BIT(9)) ? -1 : value & 0x1ff;
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
            g_regs[addr / 4] = value;
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
        if ((!strcmp(g->unit->unit_id, "fan") || !strcmp(g->unit->unit_id, "buzzer")) &&
            esp32_gpio_matrix_out_signal(g->unit->yellow, s3) == signal) {
            if (g->frequency != frequency || g->duty != percent) { g->unit->output_transitions++; }
            g->frequency = frequency; g->duty = percent; g->pwm_signal = signal;
        }
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

static void ledc_observe(Esp32LEDCState *s)
{
    for (unsigned channel = 0; channel < (s->esp32s3_layout ? 8 : 16); channel++) {
        unsigned timer = (s->channel_conf0_reg[channel] & 3) +
                         (!s->esp32s3_layout && channel >= 8 ? 4 : 0);
        m5_unit_pwm_observe(s->esp32s3_layout, channel,
            s->timer_conf_reg[timer], s->channel_duty_reg[channel],
            s->channel_conf0_reg[channel]);
    }
}

static uint64_t esp32_ledc_read(void *opaque, hwaddr addr, unsigned int size)
{
    Esp32LEDCState *s = ESP32_LEDC(opaque);
    uint64_t r = 0;
    if (s->esp32s3_layout && addr < 0xa0) {
        unsigned offset = addr % 0x14;
        if (offset == 8 || offset == 16) {
            /* The existing model applies duty writes immediately. Expose
             * that settled set+update state, without claiming pending/current
             * cycle, fade or active-latch timing semantics. */
            return s->channel_duty_reg[addr / 0x14] & 0x7ffff;
        }
    }
    if (s->esp32s3_layout && addr >= 0xa0 && addr < 0xc0) {
        unsigned index = (addr - 0xa0) / 8;
        r = (addr & 4) ? s->timer_value_reg[index]
                       : s->timer_conf_reg[index];
        return r;
    }
    if (s->esp32s3_layout && addr == 0xd0) {
        r = s->conf_reg;
        return r;
    }
    switch (addr) {
    case A_LEDC_HSTIMER0_CONF_REG ... A_LEDC_LSTIMER3_CONF_REG:
        r = s->timer_conf_reg[(addr - A_LEDC_HSTIMER0_CONF_REG) / 0x8];
        break;

    case A_LEDC_HSCH0_CONF0_REG:
    case A_LEDC_HSCH1_CONF0_REG:
    case A_LEDC_HSCH2_CONF0_REG:
    case A_LEDC_HSCH3_CONF0_REG:
    case A_LEDC_HSCH4_CONF0_REG:
    case A_LEDC_HSCH5_CONF0_REG:
    case A_LEDC_HSCH6_CONF0_REG:
    case A_LEDC_HSCH7_CONF0_REG:
    case A_LEDC_LSCH0_CONF0_REG:
    case A_LEDC_LSCH1_CONF0_REG:
    case A_LEDC_LSCH2_CONF0_REG:
    case A_LEDC_LSCH3_CONF0_REG:
    case A_LEDC_LSCH4_CONF0_REG:
    case A_LEDC_LSCH5_CONF0_REG:
    case A_LEDC_LSCH6_CONF0_REG:
    case A_LEDC_LSCH7_CONF0_REG:
        r = s->channel_conf0_reg[(addr - A_LEDC_HSCH0_CONF0_REG) / 0x14];
        break;
    }
    return r;
}

static uint32_t esp32_ledc_get_percent(Esp32LEDCState *s, uint32_t value, hwaddr addr)
{
    uint32_t duty_val =  (value >> 4) & ((1 << 20) - 1);
    uint32_t duty_res;
    if (((addr - A_LEDC_HSCH0_DUTY_REG) / 0x14) < 8) {
        /* get duty res for the high speed channel from high speed timer */
        duty_res = s->duty_res[(s->channel_conf0_reg[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14] & ((1 << 2) - 1))];
    } else {
        /* get duty res for the low speed channel from low speed timer */
        duty_res = s->duty_res[((s->channel_conf0_reg[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14]) & ((1 << 2) - 1)) + 4];
    }
    return duty_res ? (100 * duty_val / ((2 << (duty_res - 1)) - 1)) : 0;
}

static void esp32_ledc_write(void *opaque, hwaddr addr,
                            uint64_t value, unsigned int size)
{
    Esp32LEDCState *s = ESP32_LEDC(opaque);
    if (s->esp32s3_layout && addr >= 0xa0 && addr < 0xc0) {
        unsigned index = (addr - 0xa0) / 8;
        if (addr & 4) {
            s->timer_value_reg[index] = value;
        } else {
            s->timer_conf_reg[index] = value;
            if ((value & 0xf) != 0) {
                s->duty_res[index] = value & 0xf;
            }
        }
        ledc_observe(s);
        return;
    }
    if (s->esp32s3_layout && addr == 0xd0) {
        s->conf_reg = value;
        ledc_observe(s);
        return;
    }
    switch (addr) {
    case A_LEDC_HSTIMER0_CONF_REG ... A_LEDC_LSTIMER3_CONF_REG:
        /* get duty resolution from timer config */
        if (((uint32_t)value & ((1 << 4) - 1)) != 0) {
            s->duty_res[(addr - A_LEDC_HSTIMER0_CONF_REG) / 0x8] = (uint32_t)value & ((1 << 4) - 1);
        }
        s->timer_conf_reg[(addr - A_LEDC_HSTIMER0_CONF_REG) / 0x8] = value;
        break;

    case A_LEDC_HSCH0_CONF0_REG:
    case A_LEDC_HSCH1_CONF0_REG:
    case A_LEDC_HSCH2_CONF0_REG:
    case A_LEDC_HSCH3_CONF0_REG:
    case A_LEDC_HSCH4_CONF0_REG:
    case A_LEDC_HSCH5_CONF0_REG:
    case A_LEDC_HSCH6_CONF0_REG:
    case A_LEDC_HSCH7_CONF0_REG:
    case A_LEDC_LSCH0_CONF0_REG:
    case A_LEDC_LSCH1_CONF0_REG:
    case A_LEDC_LSCH2_CONF0_REG:
    case A_LEDC_LSCH3_CONF0_REG:
    case A_LEDC_LSCH4_CONF0_REG:
    case A_LEDC_LSCH5_CONF0_REG:
    case A_LEDC_LSCH6_CONF0_REG:
    case A_LEDC_LSCH7_CONF0_REG:
        s->channel_conf0_reg[(addr - A_LEDC_HSCH0_CONF0_REG) / 0x14] = value;
        break;

    case A_LEDC_HSCH0_DUTY_REG:
    case A_LEDC_HSCH1_DUTY_REG:
    case A_LEDC_HSCH2_DUTY_REG:
    case A_LEDC_HSCH3_DUTY_REG:
    case A_LEDC_HSCH4_DUTY_REG:
    case A_LEDC_HSCH5_DUTY_REG:
    case A_LEDC_HSCH6_DUTY_REG:
    case A_LEDC_HSCH7_DUTY_REG:
    case A_LEDC_LSCH0_DUTY_REG:
    case A_LEDC_LSCH1_DUTY_REG:
    case A_LEDC_LSCH2_DUTY_REG:
    case A_LEDC_LSCH3_DUTY_REG:
    case A_LEDC_LSCH4_DUTY_REG:
    case A_LEDC_LSCH5_DUTY_REG:
    case A_LEDC_LSCH6_DUTY_REG:
    case A_LEDC_LSCH7_DUTY_REG:
        s->channel_duty_reg[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14] = value;
        led_set_intensity(&s->led[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14], esp32_ledc_get_percent(s, value, addr));
        break;
    }
    ledc_observe(s);
}

static void esp32_ledc_realize(DeviceState *dev, Error **errp)
{
    Esp32LEDCState *s = ESP32_LEDC(dev);
    for (int i = 0; i < ESP32_LEDC_CHANNEL_CNT; i++) {
        qdev_realize(DEVICE(&s->led[i]), NULL, &error_fatal);
    }
}
void esp32_ledc_gpio_route_changed(bool s3) { (void)s3; }

static double get(GPIOUnit *g, const char *name) {
    Visitor v={0}; num_get(NULL,&v,name,g,NULL); return v.number;
}
static void route(bool s3, unsigned pin, unsigned signal) {
    g_gpio_s3=s3;
    esp32_gpio_write(NULL,(s3?0x554:0x530)+4*pin,signal,4);
}
static void check(GPIOUnit *g, double frequency, double duty) {
    assert(get(g,"frequency-hz")==frequency);
    assert(get(g,"duty-pct")==duty);
}
int main(void) {
    Esp32LEDCState s={.esp32s3_layout=true}, c={0};
    M5Unit units[]={{.unit_id="buzzer",.yellow=2},{.unit_id="fan",.yellow=3},
                    {.unit_id="buzzer",.yellow=2},{.unit_id="fan",.yellow=3}};
    GPIOUnit gs={.unit=&units[0],.s3=true}, fs={.unit=&units[1],.s3=true},
             gc={.unit=&units[2],.s3=false}, fc={.unit=&units[3],.s3=false};
    gs.next=&fs; fs.next=&gc; gc.next=&fc; gpio_units=&gs;
    esp32_ledc_realize(&s,NULL); esp32_ledc_realize(&c,NULL);
#if BASELINE
    QLIST_INSERT_HEAD(&ledc_devices,&s,route_observer_next);
    QLIST_INSERT_HEAD(&ledc_devices,&c,route_observer_next);
#endif
    /* Exact original initialization order: LEDC timer/config/duty, then route. */
    esp32_ledc_write(&s,0xa0,(1250<<4)|13,4);
    esp32_ledc_write(&s,0,4,4);
    esp32_ledc_write(&s,8,0,4);
    unsigned writes=led_writes;
    route(true,2,73);
    assert(led_writes==writes);
#if BASELINE
    double route_hz=get(&gs,"frequency-hz");
    ledc_observe(&s);
    printf("{\"baseline_route_hz\":%g,\"manual_observer_hz\":%g,\"baseline_cross_layout_frequency\":%g}\n",route_hz,get(&gs,"frequency-hz"),gc.frequency);
    return !(route_hz==0 && get(&gs,"frequency-hz")==2000 && gc.frequency==2000);
#else
    check(&gs,2000,0); assert(gc.frequency==0 && gc.duty==0);
    assert(esp32_ledc_read(&s,8,4)==0 && esp32_ledc_read(&s,16,4)==0);
    /* A second endpoint sees the same current controller state. */
    route(true,3,73); check(&fs,2000,0);
    uint64_t transitions=gs.unit->output_transitions;
    route(true,2,73); assert(gs.unit->output_transitions==transitions);
    route(true,2,73|BIT(10)); assert(gs.unit->output_transitions==transitions);
    /* Unroute; mutate real registers while disconnected; restore new state. */
    route(true,2,256); check(&gs,0,0);
    esp32_ledc_write(&s,0xa0,(2500<<4)|13,4);
    esp32_ledc_write(&s,8,2048<<4,4);
    check(&gs,0,0); check(&fs,1000,25);
    writes=led_writes; route(true,2,73); check(&gs,1000,25); assert(led_writes==writes);
    /* Move to another channel/timer, then reuse channel zero after changes. */
    esp32_ledc_write(&s,0xa8,(5000<<4)|13,4);
    esp32_ledc_write(&s,0x14,5,4); esp32_ledc_write(&s,0x1c,4096<<4,4);
    writes=led_writes; route(true,2,74); check(&gs,500,50); assert(led_writes==writes);
    esp32_ledc_write(&s,8,1024<<4,4); check(&gs,500,50);
    route(true,2,73); check(&gs,1000,12.5);
    /* Existing bit9 route gate and invalid/non-LEDC routes remain zero. */
    route(true,2,73|BIT(9)); check(&gs,0,0);
    route(true,2,81); check(&gs,0,0);
    route(true,2,73); check(&gs,1000,12.5);
    /* Output enable/pause/reset mask observed duty, never register readback. */
    esp32_ledc_write(&s,0,0,4); route(true,2,256); route(true,2,73); check(&gs,1000,0);
    assert(esp32_ledc_read(&s,8,4)==(1024<<4) && esp32_ledc_read(&s,16,4)==(1024<<4));
    esp32_ledc_write(&s,0,4,4);
    for (unsigned flag=22;flag<=23;flag++) {
        esp32_ledc_write(&s,0xa0,(2500<<4)|13|BIT(flag),4);
        route(true,2,256); route(true,2,73); check(&gs,1000,0);
        assert(esp32_ledc_read(&s,16,4)==(1024<<4));
    }
    esp32_ledc_write(&s,0xa0,(2500<<4)|13,4); check(&gs,1000,12.5);
    esp32_ledc_write(&s,8,0,4); route(true,2,256); route(true,2,73); check(&gs,1000,0);
    /* Last S3 channel and low-19-bit readback remain independent of route. */
    esp32_ledc_write(&s,7*20,4,4); esp32_ledc_write(&s,7*20+8,4096<<4,4);
    route(true,2,80); check(&gs,1000,50);
    esp32_ledc_write(&s,7*20+8,0xffffffff,4);
    assert(esp32_ledc_read(&s,7*20+8,4)==0x7ffff);
    assert(esp32_ledc_read(&s,7*20+16,4)==0x7ffff);
    /* Classic uses its own live register arrays, 16 channels and timer bank. */
    esp32_ledc_write(&c,A_LEDC_HSTIMER0_CONF_REG,(1250<<4)|13,4);
    esp32_ledc_write(&c,A_LEDC_HSCH0_CONF0_REG,4,4);
    esp32_ledc_write(&c,A_LEDC_HSCH0_DUTY_REG,4096<<4,4);
    writes=led_writes; route(false,2,71); check(&gc,2000,50); assert(led_writes==writes);
    double old_s3_duty=gs.duty,old_s3_freq=gs.frequency;
    esp32_ledc_write(&c,A_LEDC_LSTIMER0_CONF_REG,(5000<<4)|13,4);
    esp32_ledc_write(&c,A_LEDC_LSCH7_CONF0_REG,4,4);
    esp32_ledc_write(&c,A_LEDC_LSCH7_DUTY_REG,2048<<4,4);
    route(false,2,86); check(&gc,500,25);
    assert(gs.duty==old_s3_duty && gs.frequency==old_s3_freq);
    assert(esp32_ledc_read(&c,A_LEDC_HSCH0_DUTY_REG,4)==0);
    assert(esp32_ledc_read(&c,A_LEDC_HSCH0_DUTY_R_REG,4)==0);
    /* SoC filter: a classic mutation must not refresh a deliberately changed S3 bank. */
    s.timer_conf_reg[0]=(1250<<4)|13; s.channel_duty_reg[7]=0;
    route(false,2,71); assert(gs.duty==old_s3_duty && gs.frequency==old_s3_freq);
    writes=led_writes; route(true,2,73); check(&gs,2000,0); assert(led_writes==writes);
    /* Lifecycle removal makes further route notification a harmless no-op. */
    esp32_ledc_unrealize(&s); esp32_ledc_unrealize(&c); assert(QLIST_EMPTY(&ledc_devices));
    route(true,2,256); route(true,2,73); assert(led_writes==writes);
    puts("{\"status\":\"PASS\",\"scope\":\"actual C fragments, host stubs, no firmware execution\",\"route_write_side_effects\":0,\"cross_layout_endpoint_writes\":0,\"cases\":18}");
    return 0;
#endif
}

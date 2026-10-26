/* Actual QEMU C-fragment diagnostic. SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#define BIT(n) (1u<<(n))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define HWADDR_PRIx PRIx64
#define A_GPIO_STRAP 0x38
#define GPIO_NPINS 49
typedef uint64_t hwaddr;
typedef void Object; typedef void Error; typedef struct { double number; } Visitor;
static uint32_t g_regs[1024]; static bool g_gpio_s3=true; static uint64_t g_open_drain;
static uint64_t gpio_line64(void) {return 0;}
static void gpio_notify(uint64_t a,uint64_t b) {}
static void gpio_transition_irq(uint64_t a,uint64_t b) {}
static bool visit_type_number(Visitor *v,const char *name,double *number,Error **error) {v->number=*number;return true;}
typedef struct {const char *unit_id; int yellow; uint64_t output_transitions;} M5Unit;
typedef struct GPIOUnit { M5Unit *unit; struct GPIOUnit *next; bool s3; double voltage,duty,frequency;unsigned pwm_signal;} GPIOUnit;
static GPIOUnit *gpio_units;
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
int main(void) {
 M5Unit unit={.unit_id="buzzer",.yellow=2}; GPIOUnit gpio={.unit=&unit,.s3=true}; gpio_units=&gpio; Visitor v={0};
 m5_unit_pwm_observe(true,0,(1250<<4)|13,0,4);
 esp32_gpio_write(NULL,0x554+2*4,73,4);
 num_get(NULL,&v,"frequency-hz",&gpio,NULL); double after_route=v.number;
 m5_unit_pwm_observe(true,0,(1250<<4)|13,0,4);
 num_get(NULL,&v,"frequency-hz",&gpio,NULL);
 printf("{\"after_actual_route_write_hz\":%g,\"after_identical_ledc_observer_hz\":%g,\"duty_pct\":%g}\n",after_route,v.number,gpio.duty);
 return !(after_route==0 && v.number==2000 && gpio.duty==0);
}

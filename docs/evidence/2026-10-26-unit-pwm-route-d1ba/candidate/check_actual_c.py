#!/usr/bin/env python3
"""Compile exact candidate/baseline C functions with host-only stubs, no guest."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SHA = lambda b: hashlib.sha256(b).hexdigest()


def function(text, name):
    start = text.index('\n' + name + '(') + 1 if '\n' + name + '(' in text else -1
    if start < 0:
        import re
        match = re.search(r'^.*\b' + name + r'\([^;]*?\)\n\{', text, re.M)
        assert match, name
        start = match.start()
    opened = text.index('{', start)
    depth = 1
    end = opened + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


PREAMBLE = r'''/* Actual source fragments; GPL-2.0-or-later. Host-only test stubs. */
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
'''

MAIN = r'''
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
'''


def build(source, baseline):
    names = {
        'hw/gpio/esp32_gpio.c': ('esp32_gpio_matrix_out_signal', 'esp32_gpio_write'),
        'hw/m5stopwatch/m5_unit_gpio.c': ('m5_unit_pwm_observe', 'num_get'),
        'hw/misc/esp32_ledc.c': ('ledc_observe', 'esp32_ledc_read', 'esp32_ledc_get_percent',
                               'esp32_ledc_write', 'esp32_ledc_realize'),
    }
    if not baseline:
        names['hw/misc/esp32_ledc.c'] += ('esp32_ledc_gpio_route_changed', 'esp32_ledc_unrealize')
    funcs = [(name, function((source / path).read_text(), name))
             for path, functions in names.items() for name in functions]
    header = (source / 'include/hw/misc/esp32_ledc.h').read_text()
    constants = header[header.index('REG32(LEDC_CONF_REG'):]
    c = PREAMBLE + constants + '\n' + '\n'.join(body for _, body in funcs)
    if baseline:
        c += 'void esp32_ledc_gpio_route_changed(bool s3) { (void)s3; }\n'
    c += MAIN
    label = 'baseline' if baseline else 'candidate'
    path = OUT / (label + '.c')
    path.write_text(c)
    command = [shutil.which('clang'), '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-parameter',
               '-Wno-unused-function', '-Wno-sign-compare', '-Werror', '-DBASELINE=' + str(int(baseline)), str(path), '-o', str(path.with_suffix(''))]
    subprocess.run(command, check=True, capture_output=True)
    result = subprocess.run([str(path.with_suffix(''))], check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    (OUT / (label + '-result.json')).write_text(json.dumps(data, indent=2) + '\n')
    return {'source_kind': label, 'function_sha256': {n: SHA(body.encode()) for n, body in funcs},
            'source_file_sha256': {p: SHA((source / p).read_bytes()) for p in names},
            'harness_sha256': SHA(path.read_bytes()), 'compile_command': command, 'result': data}


def main():
    source = ROOT / '.work/unit-runtime-source-pwm-route/qemu'
    (OUT / 'queue.h').write_bytes((source / 'include/qemu/queue.h').read_bytes())
    candidate = build(source, False)
    baseline = build(ROOT / '.work/unit-runtime-source-ledc-readback/qemu', True)
    unchanged = ('esp32_ledc_read', 'esp32_ledc_write', 'esp32_ledc_get_percent',
                 'num_get', 'esp32_gpio_matrix_out_signal', 'ledc_observe')
    assert all(candidate['function_sha256'][n] == baseline['function_sha256'][n] for n in unchanged)
    (OUT / 'actual-c-fragments.json').write_text(json.dumps({'status': 'PASS', 'candidate': candidate,
        'baseline': baseline, 'unchanged_actual_functions': unchanged,
        'api_browser_guest_calls': 0, 'hardware': 'NOT RUN'}, indent=2) + '\n')
    print(json.dumps({'candidate': candidate['result'], 'baseline': baseline['result']}))


if __name__ == '__main__':
    main()

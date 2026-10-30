"""Compile actual shipped classic RMT and WS2812 C paths, without a guest/cache."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/qemu-m5stack-peripherals/0099-classic-atom-rmt-boards.patch'


def added_file(name):
    text = PATCH.read_text().split('+++ b/' + name + '\n', 1)[1].split('\n--- ', 1)[0]
    return '\n'.join(line[1:] for line in text.splitlines() if line.startswith('+')) + '\n'


STUBS = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#define BIT(n) (1U << (n))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
typedef int SysBusDevice;
typedef int MemoryRegion;
typedef int QEMUTimer;
typedef int qemu_irq;
typedef uint64_t hwaddr;
#define OBJECT_DECLARE_SIMPLE_TYPE(a,b)
#define QEMU_CLOCK_VIRTUAL 0
static int irq;
static void qemu_set_irq(qemu_irq unused, int value) {(void)unused;irq=value;}
static int64_t qemu_clock_get_ms(int unused) {(void)unused;return 0;}
static void timer_mod(QEMUTimer *unused, int64_t value) {(void)unused;(void)value;}
static unsigned captured_count, calls;
static uint32_t captured[4096];
static void m5_unit_rmt_tx_routed(unsigned channel, const uint32_t *symbols,
    unsigned count, double tick_hz, bool s3) {
    assert(channel==0 && tick_hz==80000000.0 && !s3);
    captured_count=count;calls++;memcpy(captured,symbols,count*sizeof(*symbols));
}
'''

CONTROLS = r'''
static uint32_t item(unsigned i, unsigned total) {return i<total ? (1U + i%32000) | ((3U + i%30000)<<16) : 0;}
static void init(M5ClassicRmtState *s) {
    memset(s,0,sizeof(*s)); captured_count=calls=0;irq=0;
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF0,(1U<<24)|1,4);
    classic_rmt_write(s,RMT_CLASSIC_APB_CONF,BIT(1),4);
    classic_rmt_write(s,RMT_CLASSIC_TX_LIM_CH0,32,4);
    classic_rmt_write(s,RMT_CLASSIC_INT_ENA,BIT(24)|BIT(0)|BIT(2),4);
}
static void transaction(unsigned total, bool error) {
    M5ClassicRmtState *s=calloc(1,sizeof(*s));init(s);
    for(unsigned i=0;i<64;i++)s->symbols[i]=item(i,total);
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF1,BIT(17)|BIT(0),4);
    unsigned next=64, loops=0;
    while(s->active_mask) {
        assert(++loops<200);
        classic_rmt_tx_timer(s);
        if(s->tx_wait_mask) {
            unsigned count=s->tx_count[0],cursor=s->tx_cursor[0];
            assert(classic_rmt_read(s,RMT_CLASSIC_INT_ST,4)&BIT(24));
            assert(irq==1);
            classic_rmt_tx_timer(s);assert(s->tx_count[0]==count && s->tx_cursor[0]==cursor);
            unsigned half=(cursor-32)%64;
            for(unsigned i=0;i<32;i++)s->symbols[half+i]=item(next++,total);
            classic_rmt_write(s,RMT_CLASSIC_INT_CLR,BIT(24),4);
        }
    }
    assert(s->tx_errors==(unsigned)error);
    if(error){assert(calls==0 && s->tx_count[0]==4096 && (s->int_raw&BIT(2)));}
    else {
        assert(calls==1 && captured_count==total && s->tx_completions==1);
        for(unsigned i=0;i<total;i++)assert(captured[i]==item(i,total));
    }
    printf("transaction-%u-%s PASS thresholds=%llu\n",total,error?"bounded-error":"complete",(unsigned long long)s->tx_thresholds);
    free(s);
}
int main(void) {
    transaction(24,false); transaction(72,false); transaction(600,false);
    transaction(4096,false); transaction(4097,true);
    M5ClassicRmtState *s=calloc(1,sizeof(*s));init(s);
    classic_rmt_write(s,RMT_CLASSIC_APB_CONF,0,4);
    classic_rmt_write(s,RMT_CLASSIC_TX_LIM_CH0,0,4);
    for(unsigned i=0;i<64;i++)s->symbols[i]=item(i,64);
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF1,BIT(17)|BIT(0),4);
    classic_rmt_tx_timer(s); assert(captured_count==64 && calls==1 && !s->active_mask);
    classic_rmt_write(s,RMT_CLASSIC_INT_CLR,BIT(0),4);assert(irq==0);
    assert(classic_rmt_read(s,RMT_CLASSIC_DATE,4)==0x16042000);
    free(s); puts("nonwrapping-memory-and-w1c PASS");return 0;
}
'''

ROUTE_STUBS = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#include <stdio.h>
#define BIT(n) (1U << (n))
typedef struct {const char *unit_id;unsigned yellow;unsigned output_transitions;} M5Unit;
typedef struct GPIOUnit {struct GPIOUnit *next;bool s3;M5Unit *unit;unsigned leds;uint32_t rgb[25];uint64_t frames,incomplete_frames;unsigned tx_count,tx_pulses[192];} GPIOUnit;
static GPIOUnit *gpio_units;
static unsigned classic_route=87,s3_route=81;
static unsigned esp32_gpio_matrix_out_signal(unsigned pin,bool s3){(void)pin;return s3?s3_route:classic_route;}
'''
ROUTE_CONTROLS = r'''
static void fill(uint32_t *symbols,unsigned n,uint32_t rgb) {
    uint32_t grb=((rgb&0xff00)<<8)|((rgb>>8)&0xff00)|(rgb&0xff);
    for(unsigned led=0;led<n;led++)for(unsigned bit=0;bit<24;bit++){
        bool one=grb&(1U<<(23-bit));symbols[led*24+bit]=(one?8:3)|BIT(15)|((one?3:8)<<16);
    }
}
int main(void){
    M5Unit cu={"key",27,0},su={"rgb",35,0};
    GPIOUnit classic={.s3=false,.unit=&cu,.leds=25},s3={.s3=true,.unit=&su,.leds=3};
    classic.next=&s3;gpio_units=&classic;uint32_t symbols[600];fill(symbols,25,0x123456);
    m5_unit_rmt_tx_routed(0,symbols,600,40000000,false);
    assert(classic.frames==1 && s3.frames==0);for(unsigned i=0;i<25;i++)assert(classic.rgb[i]==0x123456);
    m5_unit_rmt_tx(0,symbols,72,40000000);assert(s3.frames==1 && classic.frames==1);
    for(unsigned i=0;i<3;i++)assert(s3.rgb[i]==0x123456);
    fill(symbols,25,0xabcdef);
    m5_unit_rmt_tx_routed(0,symbols,599,40000000,false);
    assert(classic.frames==1 && classic.incomplete_frames==1 && classic.rgb[24]==0x123456);
    classic_route=81;m5_unit_rmt_tx_routed(0,symbols,600,40000000,false);assert(classic.frames==1);
    classic_route=87;classic.leds=1;m5_unit_rmt_tx_routed(0,symbols,24,40000000,false);
    assert(classic.frames==2 && classic.rgb[0]==0xabcdef && m5_unit_gpio_rgb_value(&cu,0)==0xabcdef);
    s3_route=87;m5_unit_rmt_tx(0,symbols,72,40000000);assert(s3.frames==1);
    puts("classic-25-and-1-led-s3-3-led-route-and-short-negative PASS");return 0;
}
'''


@unittest.skipUnless(shutil.which('cc'), 'requires a C compiler')
class ClassicAtomRmtTests(unittest.TestCase):
    def compile_run(self, text):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'control.c';binary=Path(directory)/'control'
            source.write_text(text)
            result=subprocess.run([shutil.which('cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter',str(source),'-lm','-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            return result.stdout

    def test_fifo_threshold_ack_wrap_full_600_and_bounded_4096_symbols(self):
        source=added_file('hw/m5stopwatch/m5_rmt_classic.c')
        lock=json.loads((ROOT/'scripts/qemu-wasm-build/sources.lock.json').read_text())
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),
                         lock['patched_files']['hw/m5stopwatch/m5_rmt_classic.c'])
        source='\n'.join(x for x in source.splitlines() if not x.startswith('#include'))
        source=source.split('static const MemoryRegionOps classic_rmt_ops',1)[0]
        result=self.compile_run(STUBS+source+CONTROLS)
        self.assertIn('transaction-600-complete PASS',result)
        self.assertIn('transaction-4097-bounded-error PASS',result)
        self.assertIn('nonwrapping-memory-and-w1c PASS',result)

    def test_actual_ws2812_s3_and_classic_routes_and_led_counts(self):
        fixture=json.loads((ROOT/'platform/tests/fixtures/classic_atom_rmt_route.json').read_text())
        fragment=fixture['fragment']
        self.assertEqual(hashlib.sha256(fragment.encode()).hexdigest(),fixture['fragment_sha256'])
        lock=json.loads((ROOT/'scripts/qemu-wasm-build/sources.lock.json').read_text())
        self.assertEqual(lock['patched_files'][fixture['source']['path']],fixture['source']['sha256'])
        self.assertIn('+    unsigned signal = (s3 ? 81 : 87) + channel;',PATCH.read_text())
        self.assertIn('+        if (g->s3 != s3 || esp32_gpio_matrix_out_signal(',PATCH.read_text())
        self.assertIn('GPL-2.0-or-later',fixture['source']['license'])
        self.assertIn('short-negative PASS',self.compile_run(ROUTE_STUBS+fragment+ROUTE_CONTROLS))

if __name__=='__main__':unittest.main()

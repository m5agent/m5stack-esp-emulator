"""Execute the native classic RMT C model with a deterministic virtual clock."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_bootstrap_unit_runtime_recipe import new_file, recipe


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "hw/m5stopwatch/m5_rmt_classic.c"
SEED = "patches/qemu-m5stack-peripherals/0066-esp32-classic-rmt-legacy.patch"
LAYERS = (
    "patches/qemu-unit-runtime/0013-native-expanded-atom-rmt-delta.patch",
    "patches/qemu-m5stack-peripherals/0189-classic-rmt-symbol-timing.patch",
)


def replay(directory, layers):
    target = Path(directory) / SOURCE
    target.parent.mkdir(parents=True)
    target.write_text(new_file(SEED, SOURCE))
    for layer in layers:
        for flags in (("--check",), ()):
            subprocess.run(["git", "apply", "--include=" + SOURCE, *flags,
                            str(ROOT / layer)], cwd=directory, check=True,
                           capture_output=True, text=True)
    return target.read_text()


STUBS = r'''
#include <assert.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define BIT(n) (1U << (n))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define OBJECT_DECLARE_SIMPLE_TYPE(a,b)
#define M5_RMT_CLASSIC(x) ((M5ClassicRmtState *)(x))
#define QEMU_CLOCK_VIRTUAL 0
typedef int SysBusDevice;
typedef int MemoryRegion;
typedef int QEMUTimer;
typedef int qemu_irq;
typedef int ResetType;
typedef void Object;
typedef uint64_t hwaddr;
static int irq;
static int64_t now_ns, due_ns;
static bool timer_active;
static void qemu_set_irq(qemu_irq unused, int value) {irq=value;}
static void qemu_irq_lower(qemu_irq unused) {irq=0;}
static int64_t qemu_clock_get_ns(int unused) {return now_ns;}
static int64_t qemu_clock_get_ms(int unused) {return now_ns/1000000;}
static void timer_mod(QEMUTimer *unused, int64_t value) {
    due_ns=value*(OLD_MODEL ? 1000000 : 1);timer_active=true;
}
static void timer_del(QEMUTimer *unused) {timer_active=false;}
static unsigned counts[8], calls[8];
static double rates[8];
static uint32_t captured[8][4096];
static void m5_unit_rmt_tx_routed(unsigned channel, const uint32_t *symbols,
    unsigned count, double tick_hz, bool s3) {
    assert(channel<8 && !s3);counts[channel]=count;rates[channel]=tick_hz;
    calls[channel]++;memcpy(captured[channel],symbols,count*sizeof(*symbols));
}
'''


COMMON = r'''
static M5ClassicRmtState *fresh(unsigned blocks, unsigned divider,
                                 unsigned threshold, bool apb, bool wrap) {
    M5ClassicRmtState *s=calloc(1,sizeof(*s));assert(s);
    memset(counts,0,sizeof(counts));memset(calls,0,sizeof(calls));
    irq=0;now_ns=1000000000;timer_active=false;
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF0,(blocks<<24)|divider,4);
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF1,apb?BIT(17):0,4);
    classic_rmt_write(s,RMT_CLASSIC_APB_CONF,wrap?BIT(1):0,4);
    classic_rmt_write(s,RMT_CLASSIC_TX_LIM_CH0,threshold,4);
    classic_rmt_write(s,RMT_CLASSIC_INT_ENA,BIT(24)|BIT(0)|BIT(2),4);
    return s;
}
static void start(M5ClassicRmtState *s,unsigned channel) {
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF1+channel*8,
                      classic_rmt_conf1(s,channel)|BIT(0),4);
}
static void step(M5ClassicRmtState *s) {
    assert(timer_active && due_ns>=now_ns);now_ns=due_ns;
    classic_rmt_tx_timer(s);
}
/* Original AtomMatrix BIN: T1/T2/T3=72/72/144 cycles at 240 MHz,
 * APB divider 2. Both pulse words total 48 RMT ticks (1.2 us).
 * Fill exactly eight pixel bytes at each 64-symbol threshold. */
static uint32_t pixel_symbol(unsigned n) {
    return ((n/8*37+11) & (1U<<(7-n%8))) ? 0x00188018 : 0x0024800c;
}
static unsigned pixel_cursor,fill_half,fill_pos,late_fills;
static uint32_t last_fill;
static void fill(M5ClassicRmtState *s,unsigned total,bool timed) {
    uint32_t ccount=(uint32_t)(now_ns*240/1000);
    if(timed && last_fill && (int32_t)(ccount-last_fill)>27648) {
        pixel_cursor=total;late_fills++;
    }
    last_fill=ccount;
    for(unsigned byte=0;byte<8;byte++) {
        if(pixel_cursor<total) {
            for(unsigned bit=0;bit<8;bit++)
                s->symbols[fill_pos++]=pixel_symbol(pixel_cursor++);
        } else {
            s->symbols[fill_pos++]=0;
        }
    }
    fill_half^=1;
    if(!fill_half)fill_pos=0;
}
static void original_guard_transaction(unsigned total) {
    M5ClassicRmtState *s=fresh(2,2,64,true,true);
    pixel_cursor=fill_half=fill_pos=late_fills=last_fill=0;
    fill(s,total,false);fill(s,total,false);start(s,0);
    last_fill=(uint32_t)(now_ns*240/1000);
    unsigned loops=0;
    while(s->active_mask) {
        assert(++loops<5000);step(s);
        if(s->int_raw&BIT(24)) {
            fill(s,total,true);
            classic_rmt_write(s,RMT_CLASSIC_INT_CLR,BIT(24),4);
        }
    }
    assert(calls[0]==1 && s->tx_completions==1 && rates[0]==40000000);
    if(OLD_MODEL) {
        assert(counts[0]==128 && late_fills==2 && s->tx_thresholds==2);
        puts("original-CCOUNT-guard-1ms-negative-128-symbols PASS");
    } else {
        assert(counts[0]==total && late_fills==0);
        assert(now_ns==1000000000+(int64_t)total*1200);
        for(unsigned i=0;i<total;i++)assert(captured[0][i]==pixel_symbol(i));
        puts("original-CCOUNT-guard-600-symbols-720us PASS");
    }
    free(s);
}
'''


CONTROLS = r'''
static void clock_durations(void) {
    M5ClassicRmtState *s=fresh(1,3,0,true,false);
    s->symbols[0]=s->symbols[1]=2|(3U<<16);start(s,0);
    assert(due_ns==1000000188);
    now_ns=due_ns-1;classic_rmt_tx_timer(s);assert(s->tx_count[0]==0);
    step(s);assert(s->tx_count[0]==1 && due_ns==1000000375);
    step(s);assert(counts[0]==2 && now_ns==1000000375);free(s);
    s=fresh(1,2,0,false,false);s->symbols[0]=2|(3U<<16);start(s,0);
    assert(due_ns==1000010000);step(s);
    assert(counts[0]==1 && rates[0]==500000);free(s);
    s=fresh(1,0,0,true,false);s->symbols[0]=2|(3U<<16);start(s,0);
    assert(due_ns==1000016000);step(s);assert(counts[0]==1);free(s);
    s=fresh(1,2,0,true,false);s->symbols[0]=10|BIT(15);start(s,0);
    assert(due_ns==1000000250 && calls[0]==0);step(s);
    assert(counts[0]==1 && !s->active_mask);free(s);
    s=fresh(1,2,0,true,false);start(s,0);
    assert(calls[0]==1 && counts[0]==0 && !timer_active);free(s);
    puts("APB-REF-divider-zero-half-ns-zero-terminators PASS");
}
static void independent_threshold(void) {
    M5ClassicRmtState *s=fresh(2,2,64,true,true);
    for(unsigned i=0;i<128;i++)s->symbols[i]=pixel_symbol(i);
    start(s,0);while(s->tx_count[0]<64)step(s);
    assert(now_ns==1000076800 && s->tx_thresholds==1 && irq==1);
    /* The transmitter must not pause for an ISR or its W1C acknowledgement. */
    while(s->tx_count[0]<128)step(s);
    assert(now_ns==1000153600 && s->tx_thresholds==2 && irq==1);
    classic_rmt_write(s,RMT_CLASSIC_INT_CLR,BIT(24),4);assert(irq==0);
    /* The first wrapped symbol is already in flight. The next unread symbol
     * remains live RAM, so a write before its fetch must take effect. */
    s->symbols[1]=0;step(s);
    assert(counts[0]==129 && !s->active_mask && s->tx_completions==1);
    assert(captured[0][128]==pixel_symbol(0));free(s);
    puts("76.8us-threshold-no-ACK-stall-live-wrap-refill PASS");
}
static void late_timer_does_not_shift_wire_time(void) {
    M5ClassicRmtState *s=fresh(2,2,64,true,true);
    for(unsigned i=0;i<128;i++)s->symbols[i]=pixel_symbol(i);
    start(s,0);now_ns+=80000;classic_rmt_tx_timer(s);
    assert(s->tx_count[0]==66 && s->tx_thresholds==1);
    assert(due_ns==1000080400);free(s);
    puts("late-callback-keeps-absolute-symbol-deadlines PASS");
}
static void late_isr_remains_a_failure(void) {
    M5ClassicRmtState *s=fresh(2,2,64,true,true);
    pixel_cursor=fill_half=fill_pos=late_fills=last_fill=0;
    fill(s,600,false);fill(s,600,false);start(s,0);
    last_fill=(uint32_t)(now_ns*240/1000);
    while(s->tx_count[0]<64)step(s);
    now_ns+=50000;classic_rmt_tx_timer(s);
    fill(s,600,true);assert(late_fills==1);
    classic_rmt_write(s,RMT_CLASSIC_INT_CLR,BIT(24),4);
    while(s->active_mask)step(s);
    assert(counts[0]==128 && counts[0]!=600);
    free(s);puts("late-guest-ISR-still-truncates-negative PASS");
}
static void memory_boundaries(void) {
    M5ClassicRmtState *s=fresh(1,2,0,true,false);
    for(unsigned i=0;i<64;i++)s->symbols[i]=pixel_symbol(i);
    start(s,0);while(s->active_mask)step(s);
    assert(counts[0]==64 && now_ns==1000076800);free(s);
    s=fresh(1,2,0,true,true);
    for(unsigned i=0;i<64;i++)s->symbols[i]=pixel_symbol(i);
    start(s,0);while(s->active_mask)step(s);
    assert(calls[0]==0 && s->tx_errors==1 && s->tx_count[0]==4096);
    assert(s->int_raw&BIT(2));free(s);
    puts("nonwrapping-capacity-and-4096-capture-bound PASS");
}
static void channels_and_reset(void) {
    M5ClassicRmtState *s=fresh(1,2,0,true,false);
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF0+16,(1U<<24)|2,4);
    classic_rmt_write(s,RMT_CLASSIC_CH0CONF1+16,0,4);
    s->symbols[0]=pixel_symbol(0);s->symbols[128]=2|(3U<<16);
    start(s,0);start(s,2);assert(due_ns==1000001200);
    step(s);assert(calls[0]==1 && calls[2]==0 && due_ns==1000010000);
    step(s);assert(calls[2]==1 && rates[2]==500000 && !timer_active);
    start(s,0);classic_rmt_reset_hold((Object *)s,0);
    assert(!timer_active && !s->active_mask && !irq);
    assert(!s->tx_symbols && !s->tx_thresholds && !s->tx_completions);
    now_ns+=1000000;classic_rmt_tx_timer(s);assert(calls[0]==1);
    assert(!s->tx_current[0] && !s->tx_deadline_ns[0] && !s->tx_half_ns[0]);
    free(s);puts("independent-channel-deadlines-and-reset-cancellation PASS");
}
int main(void) {
    original_guard_transaction(600);clock_durations();independent_threshold();
    late_timer_does_not_shift_wire_time();late_isr_remains_a_failure();
    memory_boundaries();channels_and_reset();
    return 0;
}
'''


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and Git required")
class ClassicRmtTimingTests(unittest.TestCase):
    def compile_run(self, source, old=False):
        source = "\n".join(line for line in source.splitlines()
                           if not line.startswith("#include"))
        reset = source.split("static void classic_rmt_reset_hold", 1)[1].split(
            "static void classic_rmt_count_get", 1)[0]
        source = source.split("static const MemoryRegionOps", 1)[0]
        body = (f"#define OLD_MODEL {int(old)}\n" + STUBS + source
                + "static void classic_rmt_reset_hold" + reset + COMMON)
        body += ("int main(void){original_guard_transaction(600);return 0;}"
                 if old else CONTROLS)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control.c"
            path.write_text(body)
            binary = Path(directory) / "control"
            result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall",
                                     "-Wextra", "-Werror", "-Wno-unused-function",
                                     "-Wno-unused-parameter", str(path), "-o", str(binary)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_native_replay_timing_controls_and_reverse(self):
        self.assertIn(LAYERS[-1], recipe())
        with tempfile.TemporaryDirectory() as directory:
            source = replay(directory, LAYERS)
            output = self.compile_run(source)
            self.assertEqual(output.count(" PASS"), 7, output)
            for layer in reversed(LAYERS):
                for flags in (("--reverse", "--check"), ("--reverse",)):
                    subprocess.run(["git", "apply", "--include=" + SOURCE,
                                    *flags, str(ROOT / layer)], cwd=directory,
                                   check=True, capture_output=True, text=True)
            self.assertEqual((Path(directory) / SOURCE).read_text(), new_file(SEED, SOURCE))

    def test_original_1ms_model_triggers_firmware_guard_and_truncates(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.compile_run(replay(directory, LAYERS[:1]), old=True)
        self.assertIn("original-CCOUNT-guard-1ms-negative-128-symbols PASS", output)


if __name__ == "__main__":
    unittest.main()

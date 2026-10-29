"""Compile shipped QEMU timer functions; no guest, cache or network is required."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0017-wasm-systimer-periodic-deadline.patch"
FIXTURE = ROOT / "platform/tests/fixtures/systimer_periodic_40edccac.json"


def function(source, name):
    match = re.search(r"^(?:static\s+)?(?:inline\s+)?(?:bool|void|int64_t)\s+"
                      + name + r"\s*\([^;]*?\)\s*\{", source, re.M)
    if match is None:
        raise AssertionError("Missing actual source function: " + name)
    at, depth = match.end(), 1
    while depth:
        if source[at] == "{":
            depth += 1
        elif source[at] == "}":
            depth -= 1
        at += 1
    return source[match.start():at]


def patched_notify(postimage):
    lines, in_hunk = [], False
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line[:1] in (" ", "+" if postimage else "-"):
            lines.append(line[1:])
    return function("\n".join(lines), "esp_systimer_notify")

C_STUBS = r"""
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#define ESP_SYSTIMER_CNT_PER_US 16
#define ESP_SYSTIMER_CNT_CLK 16000000
#define ESP_SYSTIMER_52BIT_MASK ((1ULL<<52)-1)
#define ESP_SYSTIMER_COMP_COUNT 3
#define TICKS_TO_NS(ticks) (((ticks) / ESP_SYSTIMER_CNT_PER_US) * 1000)
#define SYSTIMER_DEBUG 0
#define QEMU_CLOCK_REALTIME 0
#define QEMU_CLOCK_VIRTUAL 1
#define QEMU_CLOCK_HOST 2
#define QEMU_CLOCK_VIRTUAL_RT 3
#define REPLAY_MODE_NONE 0
#define CHECKPOINT_CLOCK_HOST 0
#define CHECKPOINT_CLOCK_VIRTUAL_RT 1
#define CHECKPOINT_CLOCK_VIRTUAL 2
#define QEMU_TIMER_ATTR_EXTERNAL 1
#define qatomic_read(p) (*(p))
typedef void QEMUTimerCB(void *);
typedef struct QEMUTimer QEMUTimer;
typedef struct {bool enabled; int type;} QEMUClock;
typedef struct {QEMUTimer *active_timers;QEMUClock *clock;int timers_done_ev,active_timers_lock;} QEMUTimerList;
struct QEMUTimer {int64_t expire_time;QEMUTimer *next;QEMUTimerCB *cb;void *opaque;int attributes;QEMUTimerList *list;};
typedef struct {int64_t base;uint64_t value;bool enabled;} ESPSysTimerCounter;
typedef struct ESPSysTimerState ESPSysTimerState;
typedef struct {int counter;bool period_mode,int_enabled,enabled;int raw_st,cur_irq_level,irq;uint64_t period;int64_t expire_time;QEMUTimer qtimer;ESPSysTimerState *systimer;} ESPSysTimerComp;
struct ESPSysTimerState {ESPSysTimerCounter counter[2];ESPSysTimerComp comparators[3];};
static int replay_mode=0,irq_raises=0,notify_calls=0;
static int64_t fake_now=0;
static int64_t qemu_clock_get_ns(int type){(void)type;return fake_now;}
static void qemu_event_reset(int*p){*p=0;}static void qemu_event_set(int*p){*p=1;}
static void qemu_mutex_lock(int*p){(void)p;}static void qemu_mutex_unlock(int*p){(void)p;}
static bool replay_checkpoint(int x){(void)x;return true;}
static void qemu_set_irq(int irq,int level){(void)irq;if(level)irq_raises++;}
static void timer_mod_ns(QEMUTimer*t,int64_t at){
    QEMUTimer **p=&t->list->active_timers;
    while(*p && *p!=t)p=&(*p)->next;
    if(*p==t)*p=t->next;
    t->expire_time=at;p=&t->list->active_timers;
    while(*p && (*p)->expire_time<=at)p=&(*p)->next;
    t->next=*p;*p=t;
}
"""

C_CONTROLS = r"""static void callback(void *p) {
    if (++notify_calls > 10000) { fputs("unbounded callback sequence\n",stderr); exit(2); }
    esp_systimer_notify(p);
}
static void sample(const char *name, int64_t late_ns, uint64_t period,
                   int count, bool periodic, bool enabled, bool raw, bool direct,
                   uint64_t initial_counter) {
    ESPSysTimerState s = {0};
    QEMUClock clock = {true,QEMU_CLOCK_VIRTUAL};
    QEMUTimerList list = {.clock=&clock};
    const int64_t expire = 1000000000;
    fake_now = expire+late_ns; irq_raises = notify_calls = 0;
    s.counter[0].enabled = enabled; s.counter[0].base = expire-500000;
    s.counter[0].value = initial_counter;
    for (int i=0; i<count; i++) {
        ESPSysTimerComp *c = &s.comparators[i];
        c->systimer=&s; c->period=period; c->period_mode=periodic;
        c->int_enabled=true; c->raw_st=raw; c->cur_irq_level=raw;
        c->expire_time=expire; c->qtimer.cb=callback; c->qtimer.opaque=c;
        c->qtimer.list=&list; timer_mod_ns(&c->qtimer,expire);
    }
    if (direct) callback(&s.comparators[0]); else timerlist_run_timers(&list);
    const int64_t next = s.comparators[0].expire_time;
    const int64_t period_ns = TICKS_TO_NS(period);
    const uint64_t elapsed_ticks = ((fake_now-(expire-500000))*16)/1000;
    const uint64_t expected = enabled ? (initial_counter+elapsed_ticks)&ESP_SYSTIMER_52BIT_MASK : initial_counter;
    printf("{\"case\":\"%s\",\"callbacks\":%d,\"irq_raises\":%d,\"next\":%"PRId64",\"now\":%"PRId64",\"phase\":%s,\"counter\":%"PRIu64",\"expected_counter\":%"PRIu64",\"raw\":%d,\"timer_pending\":%s}\n",
           name,notify_calls,irq_raises,next,fake_now,
           period_ns==0 || (next-expire)%period_ns==0 ? "true":"false",
           s.counter[0].value,expected,s.comparators[0].raw_st,list.active_timers?"true":"false");
}
int main(void) {
    sample("early",-250000,16000,1,true,true,false,true,1000);
    sample("exact",0,16000,1,true,true,false,false,1000);
    sample("late_one_period",1000000,16000,1,true,true,false,false,1000);
    sample("late_50ms",50000000,16000,1,true,true,false,false,1000);
    sample("late_1s",1000000000,16000,1,true,true,false,false,1000);
    sample("two_comparators",50000000,16000,2,true,true,false,false,1000);
    sample("raw_pending",50000000,16000,2,true,true,true,false,1000);
    sample("one_shot",50000000,16000,1,false,true,false,false,1000);
    sample("disabled_counter",50000000,16000,1,true,false,false,false,1000);
    /* A zero period is intentionally called once, preserving the old semantics
     * without running its known immediately-rearmed host timer loop forever. */
    sample("zero_period",50000000,0,1,true,true,false,true,1000);
    sample("sub_us_period",50000000,15,1,true,true,false,true,1000);
    sample("counter_wrap",50000000,16000,1,true,true,false,false,ESP_SYSTIMER_52BIT_MASK-4000);
    return 0;
}
"""

class SystimerPeriodicPatchTests(unittest.TestCase):
    def test_fixed_upstream_and_function_identity(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["source"]["commit"], "40edccac415693c5130f91c01d84176ae6008566")
        self.assertIn("GNU General Public License", fixture["source_headers"]["systimer"])
        self.assertIn("Permission is hereby granted, free of charge", fixture["source_headers"]["timerlist"])
        for name, source in fixture["functions"].items():
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), fixture["function_sha256"][name])
        self.assertEqual(hashlib.sha256(patched_notify(False).encode()).hexdigest(),
                         fixture["source"]["notify_preimage_sha256"])
        lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
        self.assertEqual(lock["patched_files"]["hw/timer/esp_systimer.c"], fixture["source"]["postimage_file_sha256"])
        row = next(p for p in lock["patches"] if p["path"] == str(PATCH.relative_to(ROOT)))
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), row["sha256"])

    @unittest.skipUnless(shutil.which("cc"), "A host C compiler is required for the actual-function control")
    def test_actual_functions_before_after_and_native(self):
        fixture = json.loads(FIXTURE.read_text())
        helper = "\n".join(fixture["functions"][name] for name in
                           ["esp_systimer_update_counter", "esp_systimer_set_irqs"])
        timerloop = "\n".join(fixture["functions"][name] for name in
                              ["timer_expired_ns", "timerlist_run_timers"])
        headers = "\n".join(fixture["source_headers"].values())
        results = {}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name, postimage, flags in [("old", False, []), ("wasm", True, ["-D__EMSCRIPTEN__"]),
                                          ("native", True, [])]:
                source = folder / (name + ".c")
                source.write_text(headers + C_STUBS + helper + patched_notify(postimage) + timerloop + C_CONTROLS)
                executable = folder / name
                subprocess.run([shutil.which("cc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                *flags, str(source), "-o", str(executable)], check=True, capture_output=True, text=True)
                output = subprocess.check_output([str(executable)], text=True, timeout=10)
                results[name] = {row["case"]: row for row in map(json.loads, output.splitlines())}
        self.assertEqual(results["native"], results["old"], "Native bootstrap behavior must remain byte-for-byte equivalent")
        old, fixed = results["old"], results["wasm"]
        self.assertEqual(old["late_50ms"]["callbacks"], 51)
        self.assertEqual(old["late_1s"]["callbacks"], 1001)
        self.assertEqual(old["two_comparators"]["callbacks"], 102)
        self.assertEqual(old["raw_pending"]["callbacks"], 102)
        self.assertEqual(old["raw_pending"]["irq_raises"], 0)
        self.assertEqual(fixed["late_50ms"]["callbacks"], 1)
        self.assertEqual(fixed["late_1s"]["callbacks"], 1)
        self.assertEqual(fixed["two_comparators"]["callbacks"], 2)
        self.assertEqual(fixed["raw_pending"]["callbacks"], 2)
        for case in ["early", "exact", "zero_period", "sub_us_period", "one_shot", "disabled_counter"]:
            self.assertEqual(fixed[case], old[case], case)
        for case, row in fixed.items():
            self.assertEqual(row["counter"], row["expected_counter"], case)
            self.assertEqual(old[case]["counter"], row["counter"], case)
            self.assertEqual(old[case]["irq_raises"], row["irq_raises"], case)
            self.assertEqual(old[case]["raw"], row["raw"], case)
            self.assertTrue(row["phase"], case)
        for case in ["late_one_period", "late_50ms", "late_1s", "two_comparators", "raw_pending", "counter_wrap"]:
            self.assertGreater(fixed[case]["next"], fixed[case]["now"], case)
        self.assertFalse(fixed["one_shot"]["timer_pending"])
        self.assertFalse(fixed["disabled_counter"]["timer_pending"])


if __name__ == "__main__":
    unittest.main()

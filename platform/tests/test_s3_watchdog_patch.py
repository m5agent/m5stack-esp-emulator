"""Replay the S3 watchdog patch and execute its actual register/timer C logic.

Pinned upstream GPL source seeds live beside the harness. Only host QOM, IRQ
and virtual-clock plumbing is shimmed; this is separate from guest evidence.
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "platform/tests/fixtures/s3_timg_upstream"
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0053-s3-watchdog-immediate-config.patch"


def function(source, name):
    match = re.search(r"^static [^\n]*\b" + re.escape(name) + r"\(", source, re.M)
    if not match:
        raise AssertionError(name + " missing from actual controller")
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated C function")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef struct { int64_t deadline; bool pending; } QEMUTimer;
typedef int *qemu_irq;
typedef int SysBusDevice;
typedef int SysBusDeviceClass;
typedef int MemoryRegion;
#define REG32(name, offset) enum { A_##name = offset };
#define FIELD(reg, name, shift, bits) enum { R_##reg##_##name##_SHIFT = shift, R_##reg##_##name##_MASK = ((1ULL << bits)-1) << shift };
#define FIELD_EX32(value, reg, name) (((value) & R_##reg##_##name##_MASK) >> R_##reg##_##name##_SHIFT)
#define container_of(ptr, type, field) ((type *)((char *)(ptr)-offsetof(type,field)))
#define OBJECT_CHECK(type, obj, name) ((type *)(obj))
#define OBJECT_GET_CLASS(type, obj, name) ((void)(obj), &controller_class)
#define OBJECT_CLASS_CHECK(type, obj, name) ((type *)(obj))
#define QEMU_CLOCK_VIRTUAL 0
static int64_t now_ns;
static int64_t qemu_clock_get_ns(int clock) { (void)clock; return now_ns; }
static void timer_mod_ns(QEMUTimer *timer, int64_t deadline) { timer->deadline=deadline; timer->pending=true; }
static void timer_del(QEMUTimer *timer) { timer->pending=false; }
static void qemu_irq_raise(qemu_irq irq) { (*irq)++; }
'''

MAIN = r'''
static void initialize(ESPTimgState *s, bool immediate, int *interrupt, int *reset) {
    memset(s,0,sizeof(*s));
    controller_class.m_wdt_config_immediate=immediate;
    s->wdt.wkey=ESP_WDT_DEFAULT_WKEY;
    s->wdt.interrupt_irq=interrupt; s->wdt.reset_irq=reset;
    s->wdt.counter.frequency=ESP_APB_CLK;
    s->wdt.prescaler=1;
}
int main(void) {
    ESPTimgState s; int interrupt=0, reset=0;
    initialize(&s,true,&interrupt,&reset);
    write_wdt(&s,A_TIMG_WDTCONFIG1,40000U<<16);
    write_wdt(&s,A_TIMG_WDTCONFIG2,4000);
    write_wdt(&s,A_TIMG_WDTCONFIG3,8000);
    uint32_t config=(1U<<31)|(ESP_WDT_INTERRUPT<<29)|(ESP_WDT_RESET_SYS<<27);
    write_wdt(&s,A_TIMG_WDTCONFIG0,config); /* S3 never writes CONF_UPDATE_EN. */
    assert(s.wdt.counter.frequency==2000 && s.wdt.stage_conf[0]==ESP_WDT_INTERRUPT);
    assert(s.wdt.stage[0]==4000 && s.wdt.counter.timer.deadline==2000000000LL);
    for (int n=0;n<12;n++) { now_ns+=250000000; esp_wdt_feed(&s.wdt); }
    assert(s.wdt.current_stage==0 && s.wdt.counter.timer.deadline==now_ns+2000000000LL);
    s.wdt.int_enabled=true;
    now_ns=s.wdt.counter.timer.deadline; esp_wdt_cb(&s.wdt);
    assert(interrupt==1 && s.wdt.raw_st==1 && s.wdt.current_stage==1);
    now_ns=s.wdt.counter.timer.deadline; esp_wdt_cb(&s.wdt);
    assert(reset==1);
    s.wdt.wkey=0; uint32_t saved=s.wdt.stage[0];
    write_wdt(&s,A_TIMG_WDTCONFIG2,2); write_wdt(&s,A_TIMG_WDTCONFIG1,1U<<16);
    assert(s.wdt.stage[0]==saved && s.wdt.prescaler==40000);
    s.wdt.wkey=ESP_WDT_DEFAULT_WKEY;
    write_wdt(&s,A_TIMG_WDTCONFIG1,0x20); /* Reserved bits cannot divide by zero. */
    assert(s.wdt.prescaler==1 && s.wdt.counter.frequency==ESP_APB_CLK);
    now_ns=0; initialize(&s,false,&interrupt,&reset);
    write_wdt(&s,A_TIMG_WDTCONFIG1,40000U<<16); write_wdt(&s,A_TIMG_WDTCONFIG2,4000);
    write_wdt(&s,A_TIMG_WDTCONFIG0,config);
    assert(s.wdt.stage_conf[0]==ESP_WDT_OFF && s.wdt.prescaler==1);
    write_wdt(&s,A_TIMG_WDTCONFIG0,config|(1U<<22));
    assert(s.wdt.stage_conf[0]==ESP_WDT_INTERRUPT && s.wdt.prescaler==40000);
    assert(s.wdt.counter.timer.deadline==2000000000LL);
    puts("PASS S3 immediate MWDT, feed, IRQ, reset, protection and generic latch");
}
'''


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class S3WatchdogPatchTests(unittest.TestCase):
    def test_actual_wdt_register_logic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("hw/timer/esp_timg.c", "include/hw/timer/esp_timg.h", "hw/timer/esp32s3_timg.c"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                checksums = {"esp_timg.c": "7003cdc57bf17a80615106bede8291241d6c2b164d46d2836ae20fd76d26e2b0",
                             "esp_timg.h": "8d415c04fac0be34278de2bd1fcb97f7f5804f9c00465a8ec1764ffbb353df41",
                             "esp32s3_timg.c": "e451781d4994a6b4b98dee479d98f0b0363657815d7a4af7453463b85ef9df05"}
                self.assertEqual(hashlib.sha256((FIXTURES / path.name).read_bytes()).hexdigest(), checksums[path.name])
                shutil.copyfile(FIXTURES / path.name, path)
            subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True, capture_output=True)
            source = (root / "hw/timer/esp_timg.c").read_text()
            header = (root / "include/hw/timer/esp_timg.h").read_text()
            header = "\n".join(line for line in header.splitlines() if not line.startswith(("#include", "#pragma")))
            subclass = (root / "hw/timer/esp32s3_timg.c").read_text()
            self.assertIn("esp->m_wdt_config_immediate = true;", subclass)
            names = ["esp_virtual_counter_update", "esp_virtual_counter_alarm_in_ticks",
                     "esp_wdt_ext_clk_frequency", "esp_wdt_is_writable", "esp_wdt_enabled",
                     "esp_wdt_cb", "esp_wdt_update_prescaler", "esp_wdt_update_stage",
                     "esp_wdt_feed", "esp_wdt_update_config"]
            write = function(source, "esp_timg_write")
            start = write.index("case A_TIMG_WDTCONFIG0:")
            end = write.index("case A_TIMG_INT_ENA_TIMG:", start)
            cases = write[start:end]
            program = (STUBS + header + "\nstatic ESPTimgClass controller_class;\n"
                       + "\n".join(function(source, name) for name in names)
                       + "\nstatic void write_wdt(ESPTimgState *s, uint32_t addr, uint32_t value) {\n"
                       + "ESPTimgClass *klass=&controller_class; switch(addr) {\n"
                       + cases + "default: assert(0); } }\n" + MAIN)
            c = root / "test.c"
            c.write_text(program)
            binary = root / "test"
            result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)

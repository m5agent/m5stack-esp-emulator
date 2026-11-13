"""Exercise the actual C6 TSF MMIO functions, with their preceding model."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "c6_wifi_tsf"
PATCH = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0018-c6-wifi-tsf-counter.patch"
STUB = r"""
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef void Object;
typedef int SysBusDevice;
typedef int MemoryRegion;
typedef int QEMUTimer;
typedef int NICConf;
typedef int NICState;
typedef int MemReentrancyGuard;
typedef int qemu_irq;
typedef int ResetType;
typedef uint64_t hwaddr;
#define OBJECT_CHECK(t,p,n) ((t *)(p))
#define BIT(n) (UINT32_C(1) << (n))
#define QEMU_CLOCK_VIRTUAL 0
static int64_t now;
#define qemu_clock_get_ns(clock) (now)
static int64_t qemu_clock_get_us(int clock) { return now / 1000; }
static void qemu_irq_lower(qemu_irq irq) {}
static bool wifi_trace_enabled(void) { return false; }
"""
MAIN = r"""
static Esp32C6WifiState s;
static void wr(unsigned a, uint32_t v) {esp32c6_wifi_write(&s,a,v,4);}
static uint32_t rd(unsigned a) {return esp32c6_wifi_read(&s,a,4);}
static void enable(unsigned i, bool on) {wr(0x50+8*i,on?BIT(31):0);}
static void load(unsigned i, uint64_t value) {
 wr(0x18,value);wr(0x1c,value>>32);wr(0x14,rd(0x14)|BIT(4+i));
}
static uint64_t capture(unsigned i) {
 wr(0x14,rd(0x14)|BIT(i));
 uint64_t value=(uint64_t)rd(0x24)<<32|rd(0x20);
 wr(0x14,rd(0x14)&~BIT(i));return value;
}
int main(int argc, char **argv) {
 assert(argc==2);unsigned test=atoi(argv[1]);esp32c6_wifi_reset_hold(&s,0);
 switch(test) {
 case 0:wr(0x100,0xaabbccdd);now=2345678;assert(rd(0x100)==0xaabbccdd&&rd(0)==2345);break;
 case 1:now=123456789;assert(capture(0)==0);break;
 case 2:enable(0,true);now=1000000;assert(capture(0)==1000);break;
 case 3:load(0,0x123456789abcdef0ULL);assert(capture(0)==0x123456789abcdef0ULL);break;
 case 4:load(0,0xffffffffULL);enable(0,true);wr(0x14,1);now=2000;
  assert(rd(0x24)==0&&rd(0x20)==0xffffffffu);wr(0x14,0);assert(capture(0)==0x100000001ULL);break;
 case 5:enable(0,true);now=1500;enable(0,false);now=1001500;assert(capture(0)==1);
  enable(0,true);now=1002000;assert(capture(0)==2);break;
 case 6:load(0,42);assert(!(rd(0x14)&0xf0));enable(0,true);now=10000;
  assert(capture(0)==52);now=20000;assert(capture(0)==62);load(0,42);assert(capture(0)==42);break;
 case 7:load(0,UINT64_MAX-1);enable(0,true);now=3000;assert(capture(0)==1);break;
 case 8:for(unsigned i=0;i<4;i++){load(i,100*i);enable(i,i%2==0);}now=2000;
  for(unsigned i=0;i<4;i++)assert(capture(i)==100*i+(i%2==0?2:0));break;
 case 9:load(0,123);enable(0,true);now=2345;esp32c6_wifi_reset_hold(&s,0);
  now=900000;assert(capture(0)==0&&!(rd(0x50)&BIT(31)));break;
 case 10:load(0,42);enable(0,true);wr(0x14,1);now=100000;wr(0x14,1);
  assert(rd(0x20)==42);wr(0x14,0);assert(capture(0)==142);break;
 case 11:enable(0,true);for(int i=1;i<=20;i++){now=i*100;enable(0,true);}
  assert(capture(0)==2);break;
 default:abort();
 }
 printf("PASS actual TSF MMIO %u\n",test);return 0;
}
"""


def function(text, name):
    match = re.search(r"static[\w *]+\b" + name + r"\([^;]*?\)\n\{", text)
    assert match, name
    depth = 0
    for index in range(text.index("{", match.start()), len(text)):
        depth += (text[index] == "{") - (text[index] == "}")
        if depth == 0:
            return text[match.start():index + 1] + "\n"
    raise AssertionError(name)


def build(source, output):
    text = (source / "hw/misc/esp32c6_wifi.c").read_text()
    header = (source / "include/hw/misc/esp32c6_wifi.h").read_text()
    code = STUB + re.sub(r"^#(?:include|pragma).*\n", "", header, flags=re.M)
    if "static void esp32c6_wifi_tsf_update" in text:
        code += function(text, "esp32c6_wifi_tsf_update")
    for name in ("esp32c6_wifi_read", "esp32c6_wifi_write", "esp32c6_wifi_reset_hold"):
        code += function(text, name)
    output.with_suffix(".c").write_text(code + MAIN)
    subprocess.run([
        "cc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-parameter", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        str(output.with_suffix(".c")), "-o", str(output),
    ], check=True, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class C6WifiTsfTests(unittest.TestCase):
    def test_actual_mmio_before_after(self):
        with tempfile.TemporaryDirectory(prefix="m5-c6-tsf-") as temp:
            out = Path(temp)
            for mode in ("before", "after"):
                source = out / mode
                shutil.copytree(FIXTURE, source)
                if mode == "after":
                    for args in (["--check"], [], ["--reverse", "--check"]):
                        subprocess.run(["git", "apply", *args, str(PATCH)], cwd=source,
                                       check=True, capture_output=True)
                binary = out / (mode + "-test")
                try:
                    build(source, binary)
                except subprocess.CalledProcessError as error:
                    self.fail(error.stderr)
                for case in range(12):
                    with self.subTest(mode=mode, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True,
                                                text=True, timeout=10, env=dict(os.environ,
                                                ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1"))
                        if mode == "after" or case in (0, 1, 9):
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertIn("PASS actual TSF MMIO", result.stdout)
                        else:
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn("assert", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()

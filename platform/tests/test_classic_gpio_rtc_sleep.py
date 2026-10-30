"""Compile real controller handlers; guest/hardware acceptance is separate."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "patches/qemu-m5stack-peripherals"


def patched(name, path):
    result, active = [], False
    for line in (PATCHES / name).read_text().splitlines():
        if line.startswith("diff --git "):
            active = line.endswith(" b/" + path)
        elif active and not line.startswith(("+++", "---", "@@")):
            if line.startswith(("+", " ")):
                result.append(line[1:])
    return "\n".join(result)


def function(source, name):
    match = re.search(r"(?m)^(?:static\s+)?(?:void|bool|int|uint32_t|uint64_t)\s+"
                      + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", source)
    if not match:
        raise AssertionError("complete C handler missing: " + name)
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                    lambda m: " " * len(m.group()), source, flags=re.S)
    depth = 0
    for end in range(masked.index("{", match.start()), len(masked)):
        depth += (masked[end] == "{") - (masked[end] == "}")
        if depth == 0:
            return source[match.start():end + 1]
    raise AssertionError(name)


COMMON = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#define G_N_ELEMENTS(a) (sizeof(a)/sizeof((a)[0]))
#define QEMU_CLOCK_VIRTUAL 0
static int64_t qemu_clock_get_ns(int clock) { (void)clock; return 1234; }
typedef struct Esp32GpioState { int unused; } Esp32GpioState;
typedef uint64_t hwaddr;
typedef void (*esp32_gpio_out_cb)(void *, int, int);
typedef void (*esp32_gpio_reset_cb)(void *, int);
"""


class ClassicGpioRtcSleepTests(unittest.TestCase):
    def compile_run(self, source, extra_args=()):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("C compiler unavailable")
        with tempfile.TemporaryDirectory() as directory:
            cfile, binary = Path(directory) / "test.c", Path(directory) / "test"
            cfile.write_text(source)
            built = subprocess.run([compiler, "-std=c11", "-Werror=implicit-function-declaration",
                                    *extra_args,
                                    str(cfile), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_rtc_header_supplies_its_own_controller_dimensions(self):
        header = patched("0104-classic-gpio-rtc-sleep.patch",
                         "include/hw/misc/esp32_rtc_cntl.h")
        # QEMU transport types are irrelevant here. Keep the dimensions in a
        # separate dependency so the original include-order failure reproduces.
        stubs = {
            "hw/hw.h": "#include <stdint.h>\n#include <stdbool.h>\n"
                       "typedef int qemu_irq;\ntypedef struct {int x;} MemoryRegion;\n",
            "hw/sysbus.h": "typedef struct {int x;} SysBusDevice;\n",
            "hw/registerfields.h": "#define REG32(name, value)\n"
                                   "#define FIELD(name, field, shift, width)\n",
            "hw/misc/esp32_reg.h": "#define ESP32_CPU_COUNT 2\n"
                                    "#define ESP32_RTC_CNTL_SCRATCH_REG_COUNT 8\n",
            "qemu/notify.h": "typedef struct {int x;} Notifier;\n",
            "qemu/main-loop.h": "typedef struct QEMUBH QEMUBH;\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in stubs.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            (root / "rtc.h").write_text(header)
            self.compile_run('#include <assert.h>\n#include "rtc.h"\n'
                             'int main(void) { Esp32RtcCntlState s={0};'
                             'assert(sizeof(s.reset_cause)/sizeof(s.reset_cause[0])==2);'
                             'assert(sizeof(s.scratch_reg)/sizeof(s.scratch_reg[0])==8);'
                             'return 0;}\n', ("-I", str(root)))

    def test_classic_matrix_pad_drives_real_hold_observer(self):
        gpio = patched("0104-classic-gpio-rtc-sleep.patch", "hw/gpio/esp32_gpio.c")
        header = patched("0047-unit-flashlight-cold-pad-observation.patch",
                         "include/hw/gpio/esp32_gpio.h")
        types = header[header.index("#define ESP32_GPIO_PAD_SOURCE_GPIO"):
                       header.index("/* Borrowed current controller")]
        globals_ = gpio[gpio.index("#define GPIO_NPINS"):
                        gpio.index("static bool gpio_pad_valid")]
        power = patched("0102-board-power-lifecycle.patch", "hw/m5stopwatch/m5stickcplus2.c")
        helpers = r"""
static uint64_t gpio_legacy_line64(void) { return g_ext_in; }
static uint32_t rtc_override;
static uint32_t esp32_rtc_gpio_pad_blockers(unsigned pin) { (void)pin; return rtc_override; }
static uint32_t esp32s3_gpio_pad_aux_blockers(Esp32GpioState *s, unsigned p) {
 (void)s; (void)p; return 0;
}
typedef struct M5StickCPlus2Hold {
 bool usb_present, armed, known, high, low_driven, powered; int64_t shutdown_requests;
} M5StickCPlus2Hold;
static unsigned shutdowns;
#define SHUTDOWN_CAUSE_GUEST_SHUTDOWN 1
static void qemu_system_shutdown_request(int reason) { assert(reason==1); shutdowns++; }
"""
        names = ["gpio_pad_valid", "gpio_iomux_alias", "gpio_iomux_reset", "gpio_out64",
                 "gpio_en64", "gpio_snapshot_internal", "gpio_iomux_pin"]
        main = r"""
int main(void) {
 Esp32GpioState controller={0}; g_gpio_device=&controller; g_gpio_s3=false;
 gpio_iomux_reset(); assert(gpio_iomux_pin(0x48)==4 && gpio_iomux_pin(0x18)==35);
 assert(gpio_iomux_pin(0x40)==2 && gpio_iomux_pin(0x25)==-1);
 assert(!gpio_pad_valid(&controller,24) && !gpio_pad_valid(&controller,28));
 g_regs[0x04/4]=1u<<4; g_regs[0x20/4]=1u<<4;
 g_regs[(0x530+4*4)/4]=256;
 Esp32GpioPadEvent event={0}; gpio_snapshot_internal(&controller,4,&event.after);
 assert(!event.after.known); /* cold unknown is never a power command */
 g_iomux_written[4]=true; g_iomux_pull_known[4]=true;
 g_iomux_regs[4]=(2u<<12)|(1u<<9);
 gpio_snapshot_internal(&controller,4,&event.after);
 assert(event.after.known && event.after.drive_known && event.after.oe && event.after.level);
 M5StickCPlus2Hold hold={.usb_present=true,.powered=true};
 plus2_hold_observe(&hold,&event); assert(hold.armed && hold.powered);
 g_iomux_regs[4]=(1u<<12); gpio_snapshot_internal(&controller,4,&event.after);
 assert(!event.after.known); /* S3's function number is wrong on classic */
 g_iomux_regs[4]=(2u<<12); rtc_override=1;
 gpio_snapshot_internal(&controller,4,&event.after); assert(!event.after.known);
 plus2_hold_observe(&hold,&event); assert(hold.powered && !shutdowns);
 rtc_override=0; g_regs[0x04/4]=0; gpio_snapshot_internal(&controller,4,&event.after);
 assert(event.after.known && !event.after.level);
 plus2_hold_observe(&hold,&event); assert(hold.powered && !shutdowns);
 hold.usb_present=false; plus2_hold_update(&hold);
 assert(!hold.powered && shutdowns==1);
 /* Peripheral route, input-only and released OD cannot impersonate GPIO high. */
 g_regs[(0x530+4*4)/4]=1; gpio_snapshot_internal(&controller,4,&event.after);
 assert(!event.after.drive_known && !event.after.known);
 g_regs[(0x530+4*4)/4]=256; g_regs[0x20/4]=0;
 gpio_snapshot_internal(&controller,4,&event.after); assert(!event.after.known);
 g_regs[0x20/4]=1u<<4; g_regs[0x04/4]=1u<<4; g_open_drain=1u<<4;
 gpio_snapshot_internal(&controller,4,&event.after); assert(!event.after.known);
 g_iomux_regs[4]|=1u<<8; gpio_snapshot_internal(&controller,4,&event.after);
 assert(event.after.known && event.after.level);
 return 0;
}
"""
        self.compile_run(COMMON + types + globals_ + helpers
                         + "\n".join(function(gpio, name) for name in names)
                         + function(power, "plus2_hold_update")
                         + function(power, "plus2_hold_observe") + main)

    def test_sleep_and_ext0_wake_require_controller_configuration(self):
        rtc = patched("0104-classic-gpio-rtc-sleep.patch", "hw/misc/esp32_rtc_cntl.c")
        table = rtc[rtc.index("typedef struct ClassicRtcPad"):
                    rtc.index("static void rtc_notify_pads")]
        prefix = r"""
typedef struct Esp32GpioPadSnapshot { int unused; } Esp32GpioPadSnapshot;
typedef struct Esp32RtcCntlState {
 uint32_t sleep_regs[0x140/4], rtcio_regs[0x400/4];
 uint64_t external_seen, external_levels;
 bool sleeping, deep_sleep, wake_reset_pending;
 int64_t sleep_requests, wakeup_requests;
 int irq,dig_reset_req,reset_cause[2];
} Esp32RtcCntlState;
static int state, suspends, wakes, resets;
#define RUN_STATE_SUSPENDED 1
#define QEMU_WAKEUP_REASON_OTHER 3
#define ESP32_DEEPSLEEP_RESET 5
static void *error_abort;
static bool runstate_check(int s) { return state==s; }
static void qemu_system_suspend_request(void) { state=1; suspends++; }
static void qemu_system_wakeup_request(int reason, void *error) {
 (void)error; assert(reason==3 && state==1); state=0; wakes++;
}
static void qemu_set_irq(int irq,int level) { (void)irq; (void)level; }
static void qemu_irq_pulse(int irq) { (void)irq; resets++; }
static Esp32GpioState controller;
static Esp32GpioState *esp32_gpio_get_controller(bool s3) { assert(!s3); return &controller; }
static void esp32_gpio_capture_pads(Esp32GpioState *g,Esp32GpioPadSnapshot *p) { (void)g;(void)p; }
static void rtc_notify_pads(Esp32RtcCntlState *s,Esp32GpioPadSnapshot *p) { (void)s;(void)p; }
"""
        main = r"""
int main(void) {
 Esp32RtcCntlState s={0}; classic_rtc=&s;
 s.sleep_regs[RTC_DIG_PWC/4]=1u<<31;
 s.sleep_regs[RTC_WAKEUP/4]=1u<<11; /* only EXT0 */
 s.rtcio_regs[RTC_EXT0_SEL/4]=5u<<27; /* RTCIO5 == GPIO35 */
 s.rtcio_regs[0x80/4]=(1u<<28)|(1u<<18); /* real mux + input receiver */
 esp32_rtc_gpio_input_changed(35,1); esp32_rtc_sleep_enter(&s);
 assert(state==1 && suspends==1 && s.deep_sleep && s.sleeping && !resets);
 assert(esp32_rtc_gpio_pad_blockers(4));
 esp32_rtc_gpio_input_changed(37,0); assert(!wakes); /* wrong ordinary button */
 esp32_rtc_gpio_input_changed(35,1); assert(!wakes); /* inactive level */
 s.rtcio_regs[0x80/4]&=~(1u<<18);
 esp32_rtc_gpio_input_changed(35,0); assert(!wakes); /* disabled RTC receiver */
 s.rtcio_regs[0x80/4]|=1u<<18; s.sleep_regs[RTC_WAKEUP/4]=0;
 esp32_rtc_gpio_input_changed(35,0); assert(!wakes); /* disabled EXT0 */
 s.sleep_regs[RTC_WAKEUP/4]=1u<<11; s.rtcio_regs[RTC_EXT0_SEL/4]=31u<<27;
 esp32_rtc_gpio_input_changed(35,0); assert(!wakes); /* invalid channel */
 s.rtcio_regs[RTC_EXT0_SEL/4]=5u<<27;
 esp32_rtc_gpio_input_changed(35,0);
 assert(wakes==1 && resets==1 && !s.sleeping && s.wakeup_requests==1);
 assert(s.reset_cause[0]==5 && (s.sleep_regs[RTC_WAKEUP/4]&0x7ff)==1);
 esp32_rtc_gpio_input_changed(35,0); assert(wakes==1 && resets==1);
 /* Light sleep resumes its caller instead of manufacturing a reset. */
 s.sleep_regs[RTC_DIG_PWC/4]=0; esp32_rtc_gpio_input_changed(35,1);
 esp32_rtc_sleep_enter(&s); esp32_rtc_gpio_input_changed(35,0);
 assert(wakes==2 && resets==1 && !s.deep_sleep && s.sleep_requests==2);
 return 0;
}
"""
        names = ["esp32_rtc_gpio_pad_blockers", "esp32_rtc_try_ext0_wake",
                 "esp32_rtc_gpio_input_changed", "esp32_rtc_sleep_enter"]
        self.compile_run(COMMON + prefix + table
                         + "\n".join(function(rtc, name) for name in names) + main)


if __name__ == "__main__":
    unittest.main()

"""Replay the shipped C power state machines with a deterministic clock.

This is a controller contract test, not guest or physical-device validation.
The code under test is extracted from the source patch; no local QEMU checkout
or .work cache is required. Only QEMU time, reset/shutdown delivery and pad-event
transport are stubbed. Assertions cover independent datasheet boundaries.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0102-board-power-lifecycle.patch"


def new_side(path):
    lines = []
    active = False
    for line in PATCH.read_text().splitlines():
        if line.startswith("diff --git "):
            active = line.endswith(" b/" + path)
        elif active and not line.startswith(("+++", "---", "@@")):
            if line.startswith(("+", " ")):
                lines.append(line[1:])
    return "\n".join(lines)


def c_function(source, name):
    match = re.search(
        r"(?m)^(?:static\s+)?(?:void|bool|int64_t)\s+" + re.escape(name)
        + r"\s*\([^;{}]*\)\s*\{", source,
    )
    if not match:
        raise AssertionError("complete patched C function missing: " + name)
    # Ignore strings and comments while matching braces; preserve source bytes.
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                    lambda m: " " * len(m.group()), source, flags=re.S)
    level = 0
    for end in range(masked.index("{", match.start()), len(masked)):
        level += (masked[end] == "{") - (masked[end] == "}")
        if level == 0:
            return source[match.start():end + 1]
    raise AssertionError("unclosed patched C function: " + name)


PREFIX = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#define BIT(n) (1u << (n))
#define SCALE_MS 1000000LL
#define NANOSECONDS_PER_SECOND 1000000000LL
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define QEMU_CLOCK_VIRTUAL 0
#define SHUTDOWN_CAUSE_GUEST_SHUTDOWN 1
#define SHUTDOWN_CAUSE_GUEST_RESET 2
enum { M_PM1, M_AXP192, M_AXP2101 };
typedef struct QEMUTimer {
    int64_t deadline;
    bool pending;
    void (*callback)(void *);
    void *opaque;
} QEMUTimer;
typedef struct M5swI2CDev {
    const char *model_name;
    int model;
    uint8_t regs[256];
    QEMUTimer *power_key_timer;
    int64_t power_key_down_ns, power_key_release_ns;
    int64_t shutdown_requests, reset_requests, download_requests;
    bool power_enabled, power_key_down, power_key_long, download_requested;
    bool pm1_pa_enabled;
    unsigned pm1_clicks;
} M5swI2CDev;
static M5swI2CDev *g_stackchan_ioe1;
static int64_t clock_ns;
static unsigned shutdowns, resets;
static QEMUTimer timer;
static bool rail_events[16];
static unsigned rail_event_count;
static int64_t qemu_clock_get_ns(int id) { (void)id; return clock_ns; }
static void timer_del(QEMUTimer *t) { t->pending = false; }
static void timer_mod(QEMUTimer *t, int64_t when) {
    t->pending = true; t->deadline = when;
}
static void qemu_system_shutdown_request(int cause) {
    assert(cause == SHUTDOWN_CAUSE_GUEST_SHUTDOWN); shutdowns++;
}
static void qemu_system_reset_request(int cause) {
    assert(cause == SHUTDOWN_CAUSE_GUEST_RESET); resets++;
}
static void m5_scs_servo_power_changed(bool high) {
    assert(rail_event_count < 16); rail_events[rail_event_count++] = high;
}
typedef struct Esp32GpioPadSnapshot {
    bool known, conflict, drive_known, oe_known, oe, level, drive_level;
} Esp32GpioPadSnapshot;
typedef struct Esp32GpioPadEvent { Esp32GpioPadSnapshot after; } Esp32GpioPadEvent;
typedef struct M5StickCPlus2Hold {
    bool usb_present, armed, known, high, low_driven, powered;
    int64_t shutdown_requests;
} M5StickCPlus2Hold;
"""


SCENARIOS = r"""
static void init(M5swI2CDev *s, int model) {
    memset(s, 0, sizeof(*s)); memset(&timer, 0, sizeof(timer));
    clock_ns = 0; shutdowns = resets = 0;
    s->model = model; s->model_name = "contract-fixture";
    s->power_enabled = true; s->power_key_timer = &timer;
    timer.callback = pmic_key_tick; timer.opaque = s;
    if (model == M_PM1) { s->regs[6] = 0x17; s->regs[0x13] = 0x1f; s->regs[0x49] = 0x2a; }
    if (model == M_AXP192) s->regs[0x36] = 0x0c;
    if (model == M_AXP2101) s->regs[0x22] = 2;
}
static void advance_ms(int64_t target) {
    target *= SCALE_MS; assert(target >= clock_ns);
    unsigned steps = 0;
    while (timer.pending && timer.deadline <= target) {
        assert(++steps < 32); clock_ns = timer.deadline; timer.pending = false;
        timer.callback(timer.opaque);
    }
    clock_ns = target;
}
static void write_reg(M5swI2CDev *s, uint8_t reg, uint8_t value) {
    if (!pmic_write_power_register(s, reg, value)) s->regs[reg] = value;
}
static void click(M5swI2CDev *s, int64_t down, int64_t up) {
    advance_ms(down); pmic_key_event(s, true);
    advance_ms(up); pmic_key_event(s, false);
}
static void axp2101(void) {
    M5swI2CDev s;
    init(&s, M_AXP2101); click(&s, 0, 500);
    assert(s.regs[0x49] == 8 && !shutdowns && !resets);
    write_reg(&s, 0x49, 8); assert(s.regs[0x49] == 0);
    init(&s, M_AXP2101); pmic_key_event(&s, true); advance_ms(1000);
    assert(s.regs[0x49] == 4); pmic_key_event(&s, true); /* autorepeat */
    advance_ms(3999); assert(!shutdowns); advance_ms(4000);
    assert(shutdowns == 1 && s.shutdown_requests == 1 && !s.power_enabled);
    init(&s, M_AXP2101); write_reg(&s, 0x27, 0x04); /* bits3:2 = six seconds */
    pmic_key_event(&s, true); advance_ms(5999); assert(!shutdowns);
    advance_ms(6000); assert(shutdowns == 1);
    init(&s, M_AXP2101); write_reg(&s, 0x22, 0); pmic_key_event(&s, true);
    advance_ms(12000); assert(!shutdowns && !resets && s.power_key_long);
    write_reg(&s, 0x22, 2); advance_ms(12000); assert(shutdowns == 1);
    init(&s, M_AXP2101); write_reg(&s, 0x22, 3); pmic_key_event(&s, true);
    advance_ms(4000); assert(resets == 1 && !shutdowns && s.power_enabled);
    init(&s, M_AXP2101); write_reg(&s, 0x22, 0); write_reg(&s, 0x10, 4);
    pmic_key_event(&s, true); advance_ms(15999); assert(!shutdowns);
    advance_ms(16000); assert(shutdowns == 1);
    init(&s, M_AXP2101); write_reg(&s, 0x32, 0x80); assert(!shutdowns);
    write_reg(&s, 0x10, 0x30); assert(!shutdowns && !resets);
    write_reg(&s, 0x10, 0x31); assert(shutdowns == 1 && s.regs[0x10] == 0x30);
    init(&s, M_AXP2101); write_reg(&s, 0x10, 0x32);
    assert(resets == 1 && !shutdowns && s.regs[0x10] == 0x30);
}
static void axp192(void) {
    M5swI2CDev s;
    init(&s, M_AXP192); click(&s, 0, 250);
    assert(s.regs[0x46] == 2 && !shutdowns);
    write_reg(&s, 0x46, 2); assert(s.regs[0x46] == 0);
    init(&s, M_AXP192); write_reg(&s, 0x36, 0);
    pmic_key_event(&s, true); advance_ms(11000);
    assert(s.regs[0x46] == 1 && !shutdowns);
    pmic_key_event(&s, false); assert(s.regs[0x46] == 1);
    init(&s, M_AXP192); write_reg(&s, 0x36, 0x0f);
    pmic_key_event(&s, true); advance_ms(9999); assert(!shutdowns);
    advance_ms(10000); assert(shutdowns == 1);
    init(&s, M_AXP192); write_reg(&s, 0x10, 1); assert(!shutdowns);
    write_reg(&s, 0x32, 0x42); assert(!shutdowns);
    write_reg(&s, 0x32, 0xc2); assert(shutdowns == 1 && s.regs[0x32] == 0x42);
}
static void pm1(void) {
    M5swI2CDev s;
    init(&s, M_PM1); click(&s, 0, 100); advance_ms(349); assert(!resets);
    advance_ms(350); assert(resets == 1 && !shutdowns);
    init(&s, M_PM1); write_reg(&s, 0x49, 0xab); write_reg(&s, 0x4a, 1);
    click(&s, 0, 100); advance_ms(350);
    assert(s.regs[0x42] == 1 && !resets && !shutdowns);
    init(&s, M_PM1); write_reg(&s, 0x49, 0xab); write_reg(&s, 0x4a, 1);
    click(&s, 0, 50); click(&s, 150, 200);
    assert(s.regs[0x42] == 4 && !resets && !shutdowns);
    init(&s, M_PM1); write_reg(&s, 0x49, 0xab);
    click(&s, 0, 50); click(&s, 150, 200); assert(shutdowns == 1);
    init(&s, M_PM1); write_reg(&s, 0x49, 0xab);
    pmic_key_event(&s, true); advance_ms(3000);
    assert(!shutdowns && !resets && !s.download_requests);
    init(&s, M_PM1); pmic_key_event(&s, true); advance_ms(2000);
    assert(s.download_requested && s.download_requests == 1 && !resets && !shutdowns);
    init(&s, M_PM1); write_reg(&s, 0x0c, 1); write_reg(&s, 0x0c, 0xa0);
    assert(!shutdowns && !resets); write_reg(&s, 0x0c, 0xa3);
    assert(s.download_requests == 1 && !resets && !shutdowns);
    write_reg(&s, 0x0c, 0xa2); assert(resets == 1 && !s.download_requested);
    init(&s, M_PM1); s.regs[6] = 0x1f; s.regs[7] = BIT(2) | BIT(5) | BIT(6);
    s.regs[0x10] = s.regs[0x11] = 0x1f;
    write_reg(&s, 0x0c, 0xa1);
    assert(shutdowns == 1 && s.regs[6] == 0x0d);
    assert(s.regs[0x10] == BIT(2) && s.regs[0x11] == BIT(2));
    init(&s, M_PM1); write_reg(&s, 6, 0x15); assert(shutdowns == 1);
}
static void pad(M5StickCPlus2Hold *s, bool known, bool drive, bool high) {
    Esp32GpioPadEvent e = {.after={.known=known, .drive_known=drive,
        .oe_known=drive, .oe=drive, .level=high, .drive_level=high}};
    plus2_hold_observe(s, &e);
}
static void plus2(void) {
    M5StickCPlus2Hold s = {.usb_present=true, .powered=true}; shutdowns = 0;
    pad(&s, true, true, true); pad(&s, true, true, false);
    assert(s.armed && !s.high && s.powered && !shutdowns);
    s.usb_present=false; plus2_hold_update(&s); assert(shutdowns == 1);
    s=(M5StickCPlus2Hold){.powered=true}; shutdowns = 0;
    pad(&s, true, true, false); assert(!s.armed && !shutdowns);
    pad(&s, true, true, true); pad(&s, false, false, false); assert(!shutdowns);
    pad(&s, true, false, false); assert(!shutdowns); /* input is not off */
    pad(&s, true, true, false); assert(shutdowns == 1);
    pad(&s, true, true, false); assert(shutdowns == 1);
}
static void servo_rail(void) {
    M5swI2CDev s = {0}; assert(!m5sw_stackchan_servo_power_enabled());
    g_stackchan_ioe1=&s; assert(!m5sw_stackchan_servo_power_enabled());
    s.regs[5]=1; assert(!m5sw_stackchan_servo_power_enabled()); /* input default high */
    s.regs[3]=1; assert(m5sw_stackchan_servo_power_enabled()); /* push-pull */
    s.regs[0x13]=1; assert(!m5sw_stackchan_servo_power_enabled()); /* OD released */
    s.regs[9]=1; assert(m5sw_stackchan_servo_power_enabled());
    s.regs[0x0b]=1; assert(!m5sw_stackchan_servo_power_enabled()); /* opposed pulls */
    s.regs[0x13]=0; assert(m5sw_stackchan_servo_power_enabled()); /* strong output */
    s.regs[3]=0; s.regs[0x0b]=0; assert(m5sw_stackchan_servo_power_enabled());
    s.regs[9]=0; assert(!m5sw_stackchan_servo_power_enabled());
    rail_event_count=0; stackchan_power_update(&s); s.regs[3]=1;
    stackchan_power_update(&s); s.regs[5]=0; stackchan_power_update(&s);
    assert(rail_event_count==3 && !rail_events[0] && rail_events[1] && !rail_events[2]);
}
int main(int argc, char **argv) {
    assert(argc==2);
    if (!strcmp(argv[1],"axp2101")) axp2101();
    else if (!strcmp(argv[1],"axp192")) axp192();
    else if (!strcmp(argv[1],"pm1")) pm1();
    else if (!strcmp(argv[1],"plus2")) plus2();
    else if (!strcmp(argv[1],"servo")) servo_rail();
    else return 2;
    puts("C controller contract PASS; no firmware or hardware executed"); return 0;
}
"""


class BoardPowerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if not compiler:
            raise unittest.SkipTest("a C compiler is needed for controller replay")
        cls.temporary = tempfile.TemporaryDirectory(prefix="m5-power-contract-")
        cls.addClassCleanup(cls.temporary.cleanup)
        i2c = new_side("hw/m5stopwatch/m5sw_i2c_devs.c")
        hold = new_side("hw/m5stopwatch/m5stickcplus2.c")
        names = ["m5sw_stackchan_servo_power_enabled", "stackchan_power_update",
                 "pm1_release_gpio", "pmic_power_off", "pmic_reset_request",
                 "pmic_key_long_ns", "pmic_key_off_enabled", "pmic_key_off_ns",
                 "pm1_double_ns", "pmic_key_rearm", "pmic_download_request",
                 "pmic_key_tick", "pmic_key_event", "pmic_write_power_register"]
        functions = [c_function(i2c, name) for name in names]
        functions += [c_function(hold, name) for name in
                      ("plus2_hold_update", "plus2_hold_observe")]
        directory = Path(cls.temporary.name)
        source = directory / "power.c"
        source.write_text(PREFIX + "\n\n".join(functions) + SCENARIOS)
        cls.binary = directory / "power"
        result = subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra",
                                 "-Werror=implicit-function-declaration", str(source),
                                 "-o", str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError("patched controller C did not compile:\n" + result.stderr)

    def replay(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("C controller contract PASS", result.stdout)

    def test_axp2101_key_classification_thresholds_and_commands(self):
        self.replay("axp2101")

    def test_axp192_disable_w1c_and_chip_specific_off(self):
        self.replay("axp192")

    def test_pm1_click_policy_commands_and_retention(self):
        self.replay("pm1")

    def test_plus2_usb_unknown_and_input_negative_controls(self):
        self.replay("plus2")

    def test_stackchan_output_open_drain_and_pull_resolution(self):
        self.replay("servo")


if __name__ == "__main__":
    unittest.main()

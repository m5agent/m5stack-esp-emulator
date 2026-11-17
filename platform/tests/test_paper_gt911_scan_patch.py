"""Replay Paper GT911 scan and ACK bodies against deterministic virtual time."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_high_priority_irq_cooperative import extract_function
from test_xtensa_inactive_irq_yield_guard_patch import fragment


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0225-paper-gt911-scan-phase.patch"
MODEL = "hw/m5stopwatch/m5paper_et047.c"

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>

#define SCALE_MS 1000000LL
#define QEMU_CLOCK_VIRTUAL 1
static int64_t now;
static bool int_high = true;

typedef struct { int64_t expiry; } QEMUTimer;
typedef struct { int unused; } I2CSlave;
static int64_t qemu_clock_get_ns(int clock)
{
    assert(clock == QEMU_CLOCK_VIRTUAL);
    return now;
}
static bool timer_pending(QEMUTimer *timer) { return timer->expiry != 0; }
static void timer_mod_ns(QEMUTimer *timer, int64_t deadline)
{
    assert(deadline > now);
    timer->expiry = deadline;
}
static void esp32_gpio_force_line(unsigned pin, bool level)
{
    assert(pin == 48);
    int_high = level;
}
"""

SCENARIOS = r"""
static void advance_to(M5Gt911 *touch, int64_t time)
{
    assert(time > now);
    now = time;
    if (touch->timer->expiry && touch->timer->expiry <= now) {
        touch->timer->expiry = 0;
        gt911_scan(touch);
    }
}

int main(void)
{
    QEMUTimer timer = {0};
    M5Gt911 touch = {.timer = &timer, .down = true, .x = 113, .y = 347};

    now = 400000;
    gt911_schedule_scan(&touch);
    assert(timer.expiry == 5400000);
    advance_to(&touch, 5600000); /* Delayed callback keeps its original phase. */
    assert(!int_high && touch.ready && touch.report_down);
    assert(touch.report_x == 113 && touch.report_y == 347);

    touch.x = 170;
    touch.y = 380;
    advance_to(&touch, 14100000);
    gt911_schedule_scan(&touch);
    assert(!timer_pending(&timer) && touch.report_x == 113);
    gt911_acknowledge(&touch);
    assert(int_high && !touch.ready && timer.expiry == 15400000);
    advance_to(&touch, 15400000);
    assert(!int_high && touch.ready && touch.report_down);
    assert(touch.report_x == 170 && touch.report_y == 380);

    touch.down = false;
    advance_to(&touch, 17500000);
    gt911_acknowledge(&touch);
    assert(timer.expiry == 20400000);
    advance_to(&touch, 20400000);
    assert(!int_high && touch.ready && !touch.report_down);
    gt911_acknowledge(&touch);
    assert(int_high && !touch.ready && !timer_pending(&timer));

    touch.config[GT911_REFRESH_RATE - GT911_CONFIG] = 0x23;
    touch.down = true;
    gt911_schedule_scan(&touch);
    assert(timer.expiry == 28400000); /* Report rate uses the low nibble. */
    advance_to(&touch, 28400000);
    advance_to(&touch, 35000000);
    gt911_acknowledge(&touch);
    assert(timer.expiry == 36400000);
    return 0;
}
"""


class PaperGT911ScanPatchTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C toolchain unavailable")
    def test_ack_preserves_scan_phase_and_report_latch(self):
        model = fragment(PATCH, MODEL)
        constants = [line for line in model.splitlines() if line.startswith((
            "#define GT911_INT ", "#define GT911_CONFIG ", "#define GT911_CONFIG_SIZE ",
            "#define GT911_REFRESH_RATE ",
        ))]
        touch = model[model.index("struct M5Gt911 {"):model.index("struct M5PaperET047 {")]
        functions = [extract_function(model, f"static void {name}(") for name in (
            "gt911_scan", "gt911_schedule_scan", "gt911_acknowledge",
        )]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "gt911.c"
            binary = source.with_suffix("")
            source.write_text("\n".join((STUBS, *constants, "typedef " + touch.rstrip()[:-1] +
                                         " M5Gt911;", *functions, SCENARIOS)))
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(source),
                            "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

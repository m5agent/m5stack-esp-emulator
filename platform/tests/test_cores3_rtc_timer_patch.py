"""Exercise the locked CoreS3 RTC countdown without starting QEMU."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0042-cores3-rtc-pmic-wakeup.patch"

SHIM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define BIT(n) (1u << (n))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define NANOSECONDS_PER_SECOND INT64_C(1000000000)
#define QEMU_CLOCK_HOST 1

typedef struct {
    int64_t deadline;
    bool pending;
    void (*callback)(void *);
    void *opaque;
} QEMUTimer;

typedef int *qemu_irq;
typedef struct {
    uint8_t regs[256];
    QEMUTimer *rtc_countdown;
    int64_t rtc_countdown_start;
    qemu_irq rtc_irq;
} M5swI2CDev;

static int64_t host_ns;

static int64_t qemu_clock_get_ns(int clock) {
    assert(clock == QEMU_CLOCK_HOST);
    return host_ns;
}

static void timer_mod_ns(QEMUTimer *timer, int64_t deadline) {
    assert(deadline > host_ns);
    timer->pending = true;
    timer->deadline = deadline;
}

static void timer_del(QEMUTimer *timer) {
    timer->pending = false;
}

static void qemu_set_irq(qemu_irq irq, int level) {
    *irq = level;
}

static void advance_to(QEMUTimer *timer, int64_t target) {
    assert(target >= host_ns);
    while (timer->pending && timer->deadline <= target) {
        host_ns = timer->deadline;
        timer->pending = false;
        timer->callback(timer->opaque);
    }
    host_ns = target;
}
'''

CONTROL = r'''
static void check_five_second_wakeup(void) {
    int irq = 1;
    M5swI2CDev rtc = { .rtc_irq = &irq };
    QEMUTimer timer = { .callback = pcf8563_countdown_expired, .opaque = &rtc };
    rtc.rtc_countdown = &timer;
    host_ns = 12 * NANOSECONDS_PER_SECOND;
    const int64_t start = host_ns;

    /* M5Unified stops the previous timer, loads 5 ticks, then enables TIE. */
    pcf8563_write_timer(&rtc, 0x0e, 0x03);
    pcf8563_write_timer(&rtc, 0x01, 0x08);
    pcf8563_write_timer(&rtc, 0x0f, 0x05);
    pcf8563_write_timer(&rtc, 0x0e, 0x82);
    pcf8563_write_timer(&rtc, 0x01, 0x09);
    assert(rtc.regs[0x01] == 0x01 && irq == 1);
    assert(timer.pending && timer.deadline == start + 5 * NANOSECONDS_PER_SECOND);
    assert(pcf8563_countdown_read(&rtc) == 5);
    advance_to(&timer, start + NANOSECONDS_PER_SECOND);
    assert(pcf8563_countdown_read(&rtc) == 4);
    advance_to(&timer, start + 5 * NANOSECONDS_PER_SECOND - 1);
    assert(pcf8563_countdown_read(&rtc) == 1);
    assert(rtc.regs[0x01] == 0x01 && irq == 1);
    advance_to(&timer, start + 5 * NANOSECONDS_PER_SECOND);
    assert(rtc.regs[0x01] == 0x05 && irq == 0);
    assert(pcf8563_countdown_read(&rtc) == 5);

    /* Writing one preserves TF and leaves the cleared AF unset. */
    pcf8563_write_timer(&rtc, 0x01, 0x0d);
    assert(rtc.regs[0x01] == 0x05 && irq == 0);
    pcf8563_write_timer(&rtc, 0x01, 0x09);
    assert(rtc.regs[0x01] == 0x01 && irq == 1);
    assert(timer.pending && timer.deadline == start + 10 * NANOSECONDS_PER_SECOND);
    advance_to(&timer, start + 10 * NANOSECONDS_PER_SECOND);
    assert(rtc.regs[0x01] == 0x05 && irq == 0);
    pcf8563_write_timer(&rtc, 0x01, 0x04);
    assert(rtc.regs[0x01] == 0x04 && irq == 1);
}

static void check_unarmed_and_disabled_irq(void) {
    int irq = 1;
    M5swI2CDev rtc = { .rtc_irq = &irq };
    QEMUTimer timer = { .callback = pcf8563_countdown_expired, .opaque = &rtc };
    rtc.rtc_countdown = &timer;
    host_ns = 0;

    pcf8563_write_timer(&rtc, 0x01, 0x01);
    pcf8563_write_timer(&rtc, 0x0e, 0x82);
    assert(!timer.pending && irq == 1);
    pcf8563_write_timer(&rtc, 0x0f, 0x05);
    assert(timer.pending);
    pcf8563_write_timer(&rtc, 0x0e, 0x03);
    assert(!timer.pending);
    advance_to(&timer, 6 * NANOSECONDS_PER_SECOND);
    assert(rtc.regs[0x01] == 0x01 && irq == 1);
    assert(pcf8563_countdown_read(&rtc) == 5);

    pcf8563_write_timer(&rtc, 0x01, 0x00);
    pcf8563_write_timer(&rtc, 0x0e, 0x82);
    advance_to(&timer, 11 * NANOSECONDS_PER_SECOND);
    assert(rtc.regs[0x01] == 0x04 && irq == 1);
    pcf8563_write_timer(&rtc, 0x01, 0x05);
    assert(rtc.regs[0x01] == 0x05 && irq == 0);
}

int main(void) {
    check_five_second_wakeup();
    check_unarmed_and_disabled_irq();
}
'''


class CoreS3RtcTimerPatch(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler is required")
    def test_countdown_and_active_low_irq(self):
        patch = PATCH.read_text(encoding="utf-8")
        device = patch.split("diff --git a/hw/m5stopwatch/m5sw_i2c_devs.c ", 1)[1]
        postimage = "\n".join(
            row[1:] for row in device.splitlines()
            if row.startswith((" ", "+")) and not row.startswith("+++")
        )
        macros = "\n".join(re.findall(r"^#define RTC_\w+\s+.+$", postimage, re.MULTILINE))
        functions = []
        for name in (
            "pcf8563_countdown_enabled",
            "pcf8563_level_irq_enabled",
            "pcf8563_tick_ns",
            "pcf8563_next_expiry",
            "pcf8563_countdown_read",
            "pcf8563_update_irq",
            "pcf8563_schedule_countdown",
            "pcf8563_countdown_expired",
            "pcf8563_write_timer",
        ):
            body = re.search(
                rf"^static \w+ {name}\(.+?^\}}$", postimage, re.MULTILINE | re.DOTALL
            )
            self.assertIsNotNone(body, name)
            functions.append(body.group(0))

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rtc_timer.c"
            binary = source.with_suffix("")
            source.write_text("\n".join((SHIM, macros, *functions, CONTROL)), encoding="utf-8")
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Werror", source, "-o", binary], check=True
            )
            subprocess.run([binary], check=True)

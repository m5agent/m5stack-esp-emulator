"""Run patched adaptive icount policy and state-load checks as actual C."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_high_priority_irq_cooperative import extract_function
from test_xtensa_inactive_irq_yield_guard_patch import fragment


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0202-icount-adaptive-max-shift.patch"

PREAMBLE = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NANOSECONDS_PER_SECOND 1000000000L
#define MAX_ICOUNT_SHIFT 10
#define QEMU_CLOCK_VIRTUAL 1
#define QEMU_CLOCK_VIRTUAL_RT 2
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define qatomic_set(target, value) (*(target) = (value))
#define qatomic_set_i64(target, value) qatomic_set(target, value)
#define REPLAY_CLOCK_LOCKED(type, expression) (expression)

typedef struct { int unused; } Error;
typedef struct { int unused; } QEMUTimer;
typedef struct { uint8_t bytes[2]; size_t size; int error; } QEMUFile;
typedef struct { int unused; } VMStateField;
typedef struct { int unused; } JSONWriter;
typedef struct {
    const char *name;
    int (*get)(QEMUFile *, void *, size_t, const VMStateField *);
    int (*put)(QEMUFile *, void *, size_t, const VMStateField *, JSONWriter *);
} VMStateInfo;

static int get_int16(QEMUFile *f, void *pv, size_t size, const VMStateField *field)
{
    if (f->size != 2) {
        f->error = -EIO;
        *(int16_t *)pv = 0;
        return 0;
    }
    *(int16_t *)pv = (uint16_t)((f->bytes[0] << 8) | f->bytes[1]);
    return 0;
}

static int put_int16(QEMUFile *f, void *pv, size_t size,
                     const VMStateField *field, JSONWriter *vmdesc)
{
    uint16_t value = *(int16_t *)pv;
    f->bytes[0] = value >> 8;
    f->bytes[1] = value;
    f->size = 2;
    return 0;
}

static const VMStateInfo vmstate_info_int16 = {
    .name = "int16", .get = get_int16, .put = put_int16,
};
static int qemu_file_get_error(QEMUFile *f) { return f->error; }
typedef struct {
    const char *shift, *max_shift, *rr;
    bool align, sleep;
} QemuOpts;
typedef struct {
    int16_t icount_time_shift, icount_max_shift;
    bool icount_shift_limited;
    int vm_clock_seqlock, vm_clock_lock;
    int64_t qemu_icount_bias, qemu_icount, last_delta, vm_clock_warp_start;
    QEMUTimer *icount_warp_timer, *icount_rt_timer, *icount_vm_timer;
} TimersState;
static TimersState timers_state;
static bool icount_sleep = true;
static bool icount_align_option;
static int64_t icount_max_percpu_ns;
static int64_t host_clock;
static bool running = true;
static unsigned diagnostics;

static const char *qemu_opt_get(QemuOpts *opts, const char *name)
{
    if (!strcmp(name, "shift")) {
        return opts->shift;
    }
    if (!strcmp(name, "max-shift")) {
        return opts->max_shift;
    }
    assert(!strcmp(name, "rr"));
    return opts->rr;
}

static bool qemu_opt_get_bool(QemuOpts *opts, const char *name, bool fallback)
{
    return !strcmp(name, "align") ? opts->align : opts->sleep;
}

static int qemu_strtol(const char *text, const char **end, int base, long *out)
{
    char *tail;
    errno = 0;
    *out = strtol(text, &tail, base);
    return errno || tail == text || *tail ? -EINVAL : 0;
}

static int qemu_strtoul(const char *text, const char **end, int base,
                       unsigned long *out)
{
    char *tail;
    errno = 0;
    *out = strtoul(text, &tail, base);
    return errno || tail == text || *tail ? -EINVAL : 0;
}

static void error_report(const char *message, ...) { diagnostics++; }
static void error_setg(Error **error, const char *message, ...) { diagnostics++; }
static void icount_enable_precise(void) { }
static void icount_enable_adaptive(void) { }
static bool runstate_is_running(void) { return running; }
static int64_t cpu_get_clock_locked(void) { return host_clock; }
static void seqlock_write_lock(void *a, void *b) { }
static void seqlock_write_unlock(void *a, void *b) { }
static void icount_timer_cb(void *unused) { }
static void icount_adjust_rt(void *unused) { }
static void icount_adjust_vm(void *unused) { }
static QEMUTimer *timer_new_ns(int c, void (*cb)(void *), void *x) { return NULL; }
static QEMUTimer *timer_new_ms(int c, void (*cb)(void *), void *x) { return NULL; }
static void timer_mod(QEMUTimer *timer, int64_t deadline) { }
static int64_t qemu_clock_get_ms(int clock) { return 0; }
static int64_t qemu_clock_get_ns(int clock) { return 0; }

static int64_t icount_get_locked(void)
{
    return timers_state.qemu_icount_bias +
           (timers_state.qemu_icount << timers_state.icount_time_shift);
}
"""

ORACLE = r"""
static void configure(const char *shift, const char *cap, bool align, bool sleep,
                      const char *rr, bool expected)
{
    QemuOpts opts = {.shift = shift, .max_shift = cap, .rr = rr,
                    .align = align, .sleep = sleep};
    timers_state = (TimersState){0};
    icount_sleep = true;
    icount_align_option = false;
    unsigned prior = diagnostics;
    assert(icount_configure(&opts, NULL) == expected);
    assert(diagnostics == prior + !expected);
}

static void adjust(bool behind)
{
    int64_t previous = icount_get_locked();
    int64_t delta = 200000000;
    host_clock = previous + (behind ? delta : -delta);
    timers_state.last_delta = 0;
    icount_adjust();
    assert(icount_get_locked() == previous);
}

static void load_shift(uint8_t high, uint8_t low, size_t bytes, int expected,
                       int16_t expected_current)
{
    QEMUFile input = {.bytes = {high, low}, .size = bytes};
    assert(icount_shift_get(&input, &timers_state.icount_time_shift,
                            sizeof(timers_state.icount_time_shift), NULL) == expected);
    assert(timers_state.icount_time_shift == expected_current);
}

int main(void)
{
    configure("5", NULL, false, false, NULL, true);
    assert(timers_state.icount_time_shift == 5);
    configure("10", NULL, false, false, NULL, true);
    assert(timers_state.icount_time_shift == 10);
    configure("5", "5", false, true, NULL, false);
    configure(NULL, "5", false, true, NULL, false);
    configure("auto", "-1", false, true, NULL, false);
    configure("auto", "11", false, true, NULL, false);
    configure("auto", "1.5", false, true, NULL, false);
    configure("auto", "0x5", false, true, NULL, false);
    configure("auto", "", false, true, NULL, false);
    configure("auto", "5", true, true, NULL, false);
    configure("auto", "5", false, false, NULL, false);
    configure("auto", "5", false, true, "record", false);
    configure("auto", "5", false, true, "replay", false);

    configure("auto", NULL, false, true, NULL, true);
    assert(!timers_state.icount_shift_limited);
    assert(timers_state.icount_time_shift == 3);
    timers_state.qemu_icount = 10000;
    for (int i = 0; i < 10; i++) {
        adjust(true);
    }
    assert(timers_state.icount_time_shift == 10);
    load_shift(0, 8, 2, 0, 8);

    configure("auto", "5", false, true, NULL, true);
    assert(timers_state.icount_shift_limited && timers_state.icount_max_shift == 5);
    assert(timers_state.icount_time_shift == 3);
    timers_state.qemu_icount = 10000;
    adjust(true);
    assert(timers_state.icount_time_shift == 4);
    adjust(true);
    adjust(true);
    assert(timers_state.icount_time_shift == 5);
    load_shift(0, 5, 2, 0, 5);
    adjust(false);
    assert(timers_state.icount_time_shift == 4);
    load_shift(0, 6, 2, -EINVAL, 4);
    load_shift(0, 11, 2, -EINVAL, 4);
    load_shift(0xff, 0xff, 2, -EINVAL, 4);
    load_shift(0, 0, 1, -EIO, 4);
    load_shift(0, 0, 0, -EIO, 4);
    QEMUFile output = {0};
    assert(icount_shift_put(&output, &timers_state.icount_time_shift,
                            sizeof(timers_state.icount_time_shift), NULL, NULL) == 0);
    assert(output.size == 2 && output.bytes[0] == 0 && output.bytes[1] == 4);
    load_shift(0, 0, 2, 0, 0);

    configure("auto", "0", false, true, NULL, true);
    assert(timers_state.icount_time_shift == 0);
    adjust(true);
    adjust(false);
    assert(timers_state.icount_time_shift == 0);
    configure("auto", "2", false, true, NULL, true);
    assert(timers_state.icount_time_shift == 2);
    configure("auto", "10", false, true, NULL, true);
    assert(timers_state.icount_max_shift == 10);
    return 0;
}
"""


class AdaptiveMaxShiftPatchTests(unittest.TestCase):
    def test_actual_configuration_adjustment_and_shift_wire_codec(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        icount = fragment(PATCH, "accel/tcg/icount-common.c")
        state = fragment(PATCH, "system/cpu-timers.c")
        actual = [
            "#define ICOUNT_WOBBLE (NANOSECONDS_PER_SECOND / 10)",
            extract_function(icount, "static void icount_adjust(void)"),
            extract_function(icount, "bool icount_configure("),
            extract_function(state, "static int icount_shift_get("),
            extract_function(state, "static int icount_shift_put("),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "icount.c"
            binary = source.with_suffix("")
            source.write_text(PREAMBLE + "\n".join(actual) + ORACLE)
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", str(source), "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_cli_and_existing_vmstate_registration(self):
        cli = fragment(PATCH, "system/vl.c")
        self.assertIn('.name = "max-shift"', cli)
        replay_guard = cli.index('qemu_opt_get(icount_opts, "max-shift")')
        replay_config = cli.index("replay_configure(icount_opts);")
        self.assertLess(replay_guard, replay_config)
        self.assertIn('qemu_opt_get(icount_opts, "rr")', cli[replay_guard:replay_config])
        self.assertIn("exit(1);", cli[replay_guard:replay_config])
        state = fragment(PATCH, "system/cpu-timers.c")
        self.assertIn('    .name = "int16",', state)
        self.assertIn("VMSTATE_SINGLE(icount_time_shift, TimersState, 0,", state)
        self.assertIn("vmstate_info_icount_shift, int16_t)", state)
        self.assertNotIn("VMSTATE_SINGLE(icount_max_shift", state)

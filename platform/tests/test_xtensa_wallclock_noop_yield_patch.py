"""Replay real memw/retw translator bodies; no QEMU guest is executed."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0024-xtensa-skip-disabled-icount-yield.patch"


def patch_image(*, postimage: bool) -> str:
    """Read complete function context directly from the replayable patch."""
    lines = []
    in_hunk = False
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line.startswith(" "):
            lines.append(line[1:])
        elif in_hunk and line.startswith("+" if postimage else "-"):
            lines.append(line[1:])
    return "\n".join(lines)


def function(text: str, name: str) -> str:
    start = text.index(f"static void {name}(")
    opening = text.index("{", start)
    depth = 0
    for at in range(opening, len(text)):
        depth += (text[at] == "{") - (text[at] == "}")
        if depth == 0:
            return text[start:at + 1]
    raise AssertionError(f"Patch lacks complete {name} function context")


HARNESS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { ICOUNT_DISABLED, ICOUNT_PRECISE, ICOUNT_ADAPTATIVE };
static int use_icount;
#ifdef TEST_USER_ONLY
#define icount_enabled() ICOUNT_DISABLED
#else
#define icount_enabled() use_icount
#endif
typedef int TCGv_i32;
typedef struct { uint32_t pc; int tb_cf_use_icount; } DisasContext;
typedef struct { int unused; } OpcodeArg;
enum { WINDOW_BASE, WINDOW_START };
static int cpu_SR[] = {101, 102}, cpu_R[] = {201}, tcg_env = 301;
enum { TCG_BAR_SC = 16, TCG_MO_ALL = 15 };
enum { YIELD, BARRIER, SHL, ANDC, MOVI, DEPOSIT, RETW, JUMP };
typedef struct { int kind, args[5]; } Event;
static Event events[32];
static unsigned event_count;
static int next_temp;
static void emit(int kind, int a, int b, int c, int d, int e)
{
    assert(event_count < 32);
    events[event_count++] = (Event){kind, {a, b, c, d, e}};
}
static int tcg_temp_new(void) { return ++next_temp; }
static int tcg_constant_i32(uint32_t value) { return (int)value; }
static void gen_helper_high_priority_irq_yield(int env, int handler_only)
{ emit(YIELD, env, handler_only, 0, 0, 0); }
static void tcg_gen_mb(int flags) { emit(BARRIER, flags, 0, 0, 0, 0); }
static void tcg_gen_shl_i32(int out, int a, int b)
{ emit(SHL, out, a, b, 0, 0); }
static void tcg_gen_andc_i32(int out, int a, int b)
{ emit(ANDC, out, a, b, 0, 0); }
static void tcg_gen_movi_i32(int out, int value)
{ emit(MOVI, out, value, 0, 0, 0); }
static void tcg_gen_deposit_i32(int out, int a, int b, int first, int count)
{ emit(DEPOSIT, out, a, b, first, count); }
static void gen_helper_retw(int env, int value)
{ emit(RETW, env, value, 0, 0, 0); }
static void gen_jump(DisasContext *dc, int target)
{ emit(JUMP, (int)dc->pc, target, 0, 0, 0); }
"""

MAIN = r"""
typedef void (*Translator)(DisasContext *, const OpcodeArg [], const uint32_t []);
static unsigned run(Translator translate, int tb_flag, Event *result)
{
    DisasContext dc = { .pc = 0x12345678u, .tb_cf_use_icount = tb_flag };
    OpcodeArg args[1] = {{0}};
    uint32_t params[1] = {0};
    event_count = 0; next_temp = 1000; memset(events, 0, sizeof events);
    translate(&dc, args, params);
    memcpy(result, events, event_count * sizeof(Event));
    return event_count;
}
static void compare(Translator before, Translator after, int tb_flag,
                    int handler_only, int required_tail)
{
    Event control[32] = {0}, candidate[32] = {0};
    unsigned ncontrol = run(before, tb_flag, control);
    unsigned ncandidate = run(after, tb_flag, candidate);
    unsigned seen_yield = 0, seen_tail = 0, expected = 0;
    for (unsigned i = 0; i < ncontrol; ++i) {
        if (control[i].kind == YIELD) {
            seen_yield++;
            assert(control[i].args[0] == tcg_env);
            assert(control[i].args[1] == handler_only);
            if (!icount_enabled()) continue;
        }
        assert(expected < ncandidate);
        assert(memcmp(&control[i], &candidate[expected], sizeof(Event)) == 0);
        if (candidate[expected].kind == required_tail) seen_tail++;
        expected++;
    }
    assert(seen_yield == 1 && seen_tail == 1 && expected == ncandidate);
    assert(ncandidate == ncontrol - (icount_enabled() ? 0 : 1));
    if (handler_only) {
        assert(candidate[ncandidate - 1].kind == BARRIER);
        assert(candidate[ncandidate - 1].args[0] == (TCG_BAR_SC | TCG_MO_ALL));
    } else {
        assert(candidate[ncandidate - 2].kind == RETW);
        assert(candidate[ncandidate - 1].kind == JUMP);
    }
}
int main(void)
{
    for (use_icount = ICOUNT_DISABLED; use_icount <= ICOUNT_ADAPTATIVE; use_icount++) {
        /* Replay can clear CF_USE_ICOUNT while global icount remains enabled. */
        for (int tb_flag = 0; tb_flag <= 1; tb_flag++) {
            compare(before_memw, after_memw, tb_flag, 1, BARRIER);
            compare(before_retw, after_retw, tb_flag, 0, RETW);
        }
    }
    puts("PASS: real translator bodies preserve barriers, retw and icount sequences");
    return 0;
}
"""


class XtensaWallclockNoopYieldTests(unittest.TestCase):
    def test_patch_is_pinned_and_uses_global_mode(self):
        lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
        row = next(row for row in lock["patches"] if row["path"] == PATCH.relative_to(ROOT).as_posix())
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), row["sha256"])
        post = patch_image(postimage=True)
        self.assertIn('#include "sysemu/cpu-timers.h"', post)
        for name in ("translate_memw", "translate_retw"):
            body = function(post, name)
            self.assertEqual(body.count("if (icount_enabled())"), 1)
            self.assertNotIn("tb_cflags", body)
            self.assertNotIn("CF_USE_ICOUNT", body)

    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_actual_preimage_postimage_translator_sequences(self):
        bodies = []
        for postimage, prefix in ((False, "before"), (True, "after")):
            image = patch_image(postimage=postimage)
            for name in ("memw", "retw"):
                body = function(image, "translate_" + name)
                bodies.append(body.replace("translate_" + name, prefix + "_" + name, 1))
        with tempfile.TemporaryDirectory(prefix="m5-xtensa-yield-") as directory:
            path = Path(directory)
            source = path / "translator.c"
            source.write_text(HARNESS + "\n".join(bodies) + MAIN)
            for user_only in (False, True):
                with self.subTest(user_only=user_only):
                    binary = path / ("user-only" if user_only else "system")
                    command = [shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter"]
                    if user_only:
                        command.append("-DTEST_USER_ONLY")
                    subprocess.run(command + [str(source), "-o", str(binary)], check=True, capture_output=True, text=True, timeout=20)
                    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=5)
                    self.assertIn("PASS: real translator bodies", result.stdout)


if __name__ == "__main__":
    unittest.main()

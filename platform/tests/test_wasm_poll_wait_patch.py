"""Compile the actual WASM poll branch with deterministic host I/O controls."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0015-wasm-poll-host-wait.patch"


def actual_wasm_poll() -> str:
    """Read the shipped branch, never an independently copied algorithm."""
    sections = PATCH.read_text().split("\n@@ ")[1:]
    hunk = next(section.split("\n", 1)[1] for section in sections
                if "int qemu_poll_ns(" in section)
    postimage = "\n".join(line[1:] for line in hunk.splitlines()
                          if line[:1] in {" ", "+"})
    start = postimage.index("int qemu_poll_ns(")
    end = postimage.index("#elif defined(CONFIG_PPOLL)", start)
    return postimage[start:end].replace("#ifdef __EMSCRIPTEN__\n", "", 1) + "\n}\n"


STUBS = r"""
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#define MIN(a,b) ((a) < (b) ? (a) : (b))
typedef unsigned guint;
typedef struct { int fd; short events, revents; } GPollFD;
static double now_ms, ready_at, error_at, largest_sleep;
static int polls, sleeps;
static double emscripten_get_now(void) { return now_ms; }
static void emscripten_thread_sleep(double milliseconds) {
    assert(milliseconds > 0 && milliseconds <= 5.0);
    largest_sleep = fmax(largest_sleep, milliseconds);
    now_ms += milliseconds;
    sleeps++;
    assert(sleeps < 100);
}
static int g_poll(GPollFD *fds, guint nfds, int timeout) {
    assert(timeout == 0);
    polls++;
    if (now_ms >= error_at) { errno = EINTR; return -1; }
    if (nfds) {
        fds[0].revents = now_ms >= ready_at ? 1 : 0;
        return fds[0].revents != 0;
    }
    return 0;
}
static void reset(void) {
    now_ms = 1000; ready_at = error_at = INFINITY;
    largest_sleep = 0; polls = sleeps = 0; errno = 0;
}
"""

CONTROLS = r"""
int main(void) {
    GPollFD fd = { .fd = 0, .events = 1 };
    reset(); ready_at = now_ms;
    assert(qemu_poll_ns(&fd, 1, 1000000000) == 1 && fd.revents == 1);
    assert(sleeps == 0 && polls == 1);
    reset();
    assert(qemu_poll_ns(&fd, 1, 0) == 0 && sleeps == 0 && polls == 1);
    reset();
    assert(qemu_poll_ns(&fd, 1, 30000000) == 0);
    assert(now_ms == 1030 && polls == 7 && sleeps == 6 && largest_sleep == 5);
    reset();
    assert(qemu_poll_ns(&fd, 1, 125000) == 0);
    assert(now_ms == 1000.125 && sleeps == 1 && polls == 2);
    reset(); ready_at = now_ms + 12;
    assert(qemu_poll_ns(&fd, 1, -1) == 1);
    assert(now_ms == 1015 && sleeps == 3 && polls == 4);
    reset(); ready_at = now_ms + 3;
    assert(qemu_poll_ns(&fd, 1, INT64_MAX) == 1);
    assert(now_ms == 1005 && sleeps == 1);
    reset(); error_at = now_ms;
    assert(qemu_poll_ns(&fd, 1, -1) == -1 && errno == EINTR && sleeps == 0);
    reset(); error_at = now_ms + 10;
    assert(qemu_poll_ns(&fd, 1, 20000000) == -1 && errno == EINTR);
    assert(now_ms == 1010 && sleeps == 2);
    reset(); ready_at = now_ms + 5;
    assert(qemu_poll_ns(&fd, 1, 5000000) == 1 && now_ms == 1005);
    reset();
    assert(qemu_poll_ns(NULL, 0, 2500000) == 0 && now_ms == 1002.5);
    puts("10 actual WASM poll host-time, readiness, timeout and error controls passed");
    return 0;
}
"""


class WasmPollWaitTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "requires C compiler")
    def test_actual_branch_waits_only_when_no_event_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "poll.c"
            target = Path(directory) / "poll"
            source.write_text(STUBS + actual_wasm_poll() + CONTROLS)
            subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Werror",
                            str(source), "-lm", "-o", str(target)], check=True,
                           capture_output=True, text=True)
            result = subprocess.run([str(target)], check=True, capture_output=True, text=True)
            self.assertIn("10 actual WASM poll", result.stdout)

    def test_patch_preserves_native_poll_branch(self):
        removed = [line[1:] for line in PATCH.read_text().splitlines()
                   if line.startswith("-") and not line.startswith("---")]
        self.assertEqual(removed, ["#ifdef CONFIG_PPOLL"])
        self.assertIn("#elif defined(CONFIG_PPOLL)", PATCH.read_text())


if __name__ == "__main__":
    unittest.main()

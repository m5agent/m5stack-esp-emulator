"""Compile the protected-feed contract from the actual TIMG patch hunk."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0069-esp32-timg-wdt-feed-unprotected.patch"
)


def hunk_postimage(marker: str) -> str:
    text = PATCH.read_text()
    section = text[text.index("--- a/hw/timer/esp32_timg.c"):]
    at = section.index(marker)
    start = section.rfind("\n@@ ", 0, at)
    if start < 0:
        raise AssertionError("TIMG patch hunk header is missing")
    end = section.find("\n@@ ", at)
    lines = section[start:end if end >= 0 else None].splitlines()[1:]
    return "\n".join(
        line[1:] for line in lines if line[:1] in {" ", "+"}
    )


STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define QEMU_CLOCK_VIRTUAL 0
enum { A_TIMG_WDTFEED = 0x60 };
typedef uint64_t hwaddr;
typedef uint64_t uint64;
typedef struct {
    int id;
    struct {
        int protect_reg;
        int cur_stage;
        int en;
        int flashboot_en;
        uint64_t last_feed_ns;
        uint64_t feed_count;
    } wdt;
} Esp32TimgState;

static int feeds;
static bool esp32_handoff_trace_enabled(void) { return true; }
static bool esp32_timg_trace_enabled(void) { return false; }
static uint64_t qemu_clock_get_ns(int clock) { (void)clock; return 11; }
static void esp32_timg_handoff_trace(
    Esp32TimgState *s, const char *event, uint64_t a, uint64_t b,
    uint64_t c, uint64_t d
) {
    (void)s; (void)event; (void)a; (void)b; (void)c; (void)d;
}
static void esp32_timg_wdt_feed(void *wdt) {
    (void)wdt;
    ++feeds;
}
"""

MAIN = r"""
int main(void) {
    Esp32TimgState state = {
        .id = 0,
        .wdt = {
            .protect_reg = 0,
            .cur_stage = 2,
            .en = 1,
            .flashboot_en = 1,
        },
    };
    hwaddr addr = 0x60;
    void *opaque = &state;
    Esp32TimgState *s = (Esp32TimgState *)opaque;
    switch (addr) {
__BRANCH__
    }
    assert(feeds == 1);
    assert(state.wdt.last_feed_ns == 11);
    assert(state.wdt.feed_count == 1);
    return 0;
}
"""


class Esp32TimgWdtFeedPatchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_protected_wdtfeed_is_still_delivered(self):
        postimage = hunk_postimage("case A_TIMG_WDTFEED:")
        start = postimage.index("case A_TIMG_WDTFEED:")
        branch = postimage[start:]
        source = STUBS + MAIN.replace("__BRANCH__", branch)
        with tempfile.TemporaryDirectory() as directory:
            c_path = Path(directory) / "protected_feed.c"
            binary = Path(directory) / "protected_feed"
            c_path.write_text(source)
            result = subprocess.run(
                [
                    shutil.which("cc"),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(c_path),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_patch_keeps_configuration_protection(self):
        text = PATCH.read_text()
        self.assertIn("case A_TIMG_WDTFEED:", text)
        self.assertIn("esp32_timg_wdt_feed(&s->wdt);", text)
        self.assertNotIn("if (!esp32_timg_wdt_protected", hunk_postimage("case A_TIMG_WDTFEED:"))


if __name__ == "__main__":
    unittest.main()

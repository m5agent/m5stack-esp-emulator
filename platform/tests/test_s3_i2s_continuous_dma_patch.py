"""Compile the actual S3 I2S TX timer across the capture-window lifecycle."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack


PATCH = "patches/qemu-m5stack-peripherals/0062-esp32s3-i2s-continuous-dma-completion.patch"
SOURCE = "hw/m5stopwatch/m5_i2s.c"


def function(source, name):
    match = re.search(
        r"static void " + name + r"\(void \*opaque\)",
        source,
    )
    if match is None:
        raise AssertionError("actual I2S callback is missing: " + name)
    start = source.index("{", match.start())
    depth = 0
    for index in range(start, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated actual I2S callback")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define QEMU_CLOCK_REALTIME 1
#define g_autofree
#define g_malloc malloc
#define GDMA_I2S0 0
#define GDMA_I2S1 1
#define ESP_GDMA_OUT_IDX 1
typedef int GdmaPeripheral;
typedef struct {
    bool tx_started, dma_irq, dma_active, trace;
    void *tx_timer, *gdma;
    uint64_t pcm_bytes, pcm_limit;
    int64_t capture_until_ms, dma_due_ms;
    uint32_t dma_channel, dma_events, port, pcm_writes;
} M5I2SState;
static int64_t now;
static unsigned timer_updates, completions, snapshots;
static bool channel_available;
static int64_t qemu_clock_get_ms(int clock) { assert(clock == 1); return now; }
static void timer_mod(void *timer, int64_t deadline) {
    assert(timer && deadline >= now);
    timer_updates++;
}
static bool esp_gdma_get_channel_periph(void *gdma, GdmaPeripheral periph,
                                        int dir, uint32_t *channel) {
    (void)gdma;
    if (!channel_available) return false;
    assert(dir == ESP_GDMA_OUT_IDX);
    *channel = periph == GDMA_I2S1 ? 1 : 0;
    return true;
}
static void i2s_complete_dma(M5I2SState *s, uint32_t channel) {
    assert(channel == 1);
    s->dma_events++;
    completions++;
}
static uint32_t esp_gdma_snapshot_out_channel(void *gdma, uint32_t channel,
                                              uint8_t *buffer, uint32_t size) {
    (void)gdma;
    (void)channel;
    (void)buffer;
    (void)size;
    snapshots++;
    return 0;
}
static bool i2s_store_pcm(M5I2SState *s, const uint8_t *buffer, uint32_t bytes) {
    (void)s;
    (void)buffer;
    (void)bytes;
    return true;
}
'''


MAIN = r'''
static void tick(M5I2SState *s, int64_t delta) {
    now += delta;
    i2s_tx_timer(s);
}
int main(int argc, char **argv) {
    assert(argc == 2);
    M5I2SState s = {
        .tx_started = true,
        .dma_irq = true,
        .tx_timer = &s,
        .gdma = &s,
        .port = 1,
        .capture_until_ms = 0,
        .pcm_limit = 1,
        .pcm_bytes = 1,
    };
    channel_available = true;
    switch (atoi(argv[1])) {
    case 0:
        s.tx_started = false;
        tick(&s, 1);
        assert(timer_updates == 0 && completions == 0);
        break;
    case 1:
        tick(&s, 1);
        assert(timer_updates == 1 && s.dma_active && completions == 0);
        for (unsigned index = 0; index < 140; index++) tick(&s, 21);
        assert(completions == 140 && timer_updates == 141);
        break;
    case 2:
        s.dma_irq = false;
        s.capture_until_ms = 0;
        tick(&s, 1);
        assert(snapshots == 0 && completions == 0);
        break;
    case 3:
        channel_available = false;
        tick(&s, 1);
        assert(!s.dma_active && completions == 0);
        break;
    default:
        return 2;
    }
    puts("PASS actual S3 I2S TX timer separates completion from capture window");
    return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class S3I2SContinuousDmaPatchTests(unittest.TestCase):
    def test_completion_survives_capture_window_and_128_descriptors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                subprocess.run(
                    ["git", "apply", "--include=" + SOURCE, str(ROOT / patch)],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
            before = (root / SOURCE).read_text()
            subprocess.run(
                ["git", "apply", str(ROOT / PATCH)],
                cwd=root,
                check=True,
                capture_output=True,
            )
            after = (root / SOURCE).read_text()
            subprocess.run(
                ["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                cwd=root,
                check=True,
                capture_output=True,
            )
            for label, source in (("baseline", before), ("fixed", after)):
                program = root / (label + ".c")
                program.write_text(STUBS + function(source, "i2s_tx_timer") + MAIN)
                binary = root / label
                result = subprocess.run(
                    [
                        shutil.which("cc"),
                        "-std=c11",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        str(program),
                        "-o",
                        str(binary),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for case in range(4):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run(
                            [str(binary), str(case)],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if label == "fixed" or case in {0, 2, 3}:
                            self.assertEqual(
                                result.returncode,
                                0,
                                result.stdout + result.stderr,
                            )
                        else:
                            self.assertNotEqual(
                                result.returncode,
                                0,
                                "pre-fix callback must stop after the capture window",
                            )


if __name__ == "__main__":
    unittest.main()

"""Compile actual patched I2S RX callback with a bounded DMA transport shim.

The shim supplies descriptor capacity and accepts exactly that many bytes;
stream selection/cursor/EOF/timer behavior comes from the replayed C source.
This is C-logic evidence, separate from the visible guest microphone oracle.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0054-i2s-rx-consume-transferred-pcm.patch"
SOURCE = "hw/m5stopwatch/m5_i2s.c"


def callback(source):
    match = re.search(r"static void i2s_rx_timer\(void \*opaque\)", source)
    if match is None:
        raise AssertionError("actual I2S callback is missing")
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
typedef struct {
    bool rx_started, rx_dma_active, trace;
    void *gdma, *rx_timer;
    uint8_t *rx_pcm;
    uint32_t rx_pcm_size, rx_pcm_pos, rx_dma_channel, port;
    int64_t rx_dma_due_ms;
} M5I2SState;
static int64_t now;
static unsigned capacity, output_size;
static uint8_t input[6000], output[20000];
static int64_t qemu_clock_get_ms(int clock) { assert(clock==1); return now; }
static void timer_mod(void *timer,int64_t deadline) { assert(timer && deadline>=now); }
static uint32_t esp_gdma_complete_in_descriptor(void *gdma,unsigned channel,const uint8_t *buffer,unsigned size) {
    assert(gdma && channel==2);
    unsigned accepted=MIN(size,capacity);
    assert(output_size+accepted<=sizeof(output));
    memcpy(output+output_size,buffer,accepted);
    output_size+=accepted;
    return accepted;
}
'''


MAIN = r'''
static void step(M5I2SState *s) { now+=25; i2s_rx_timer(s); }
static void compare_stream(void) {
    for (unsigned n=0;n<output_size;n++) assert(output[n]==input[n%sizeof(input)]);
}
int main(int argc,char **argv) {
    assert(argc==2);
    for (unsigned n=0;n<sizeof(input);n++) input[n]=(uint8_t)((n*37)^(n>>8));
    M5I2SState s={.rx_started=true,.rx_dma_active=true,.gdma=&s,.rx_timer=&s,
        .rx_pcm=input,.rx_pcm_size=sizeof(input),.rx_dma_channel=2};
    switch(atoi(argv[1])) {
    case 0: /* Typical 512-byte descriptor is smaller than 4096 staging. */
        capacity=512; step(&s); step(&s);
        assert(output_size==1024 && s.rx_pcm_pos==1024); compare_stream(); break;
    case 1: /* Short source tail, then the next descriptor wraps without loss. */
        capacity=1024;
        for(unsigned n=0;n<9;n++) step(&s);
        assert(output_size==9072 && s.rx_pcm_pos==3072); compare_stream(); break;
    case 2: /* No descriptor progress must leave the source untouched. */
        capacity=0; step(&s); assert(output_size==0 && s.rx_pcm_pos==0);
        capacity=512; step(&s); assert(output_size==512 && s.rx_pcm_pos==512);
        compare_stream(); break;
    case 3: /* Idle/not-due guards must not consume any source bytes. */
        capacity=512; s.rx_started=false; step(&s); assert(s.rx_pcm_pos==0);
        s.rx_started=true; s.rx_dma_due_ms=now+100; step(&s);
        assert(output_size==0 && s.rx_pcm_pos==0);
        s.rx_dma_due_ms=0; step(&s); compare_stream(); break;
    default: return 2;
    }
    puts("PASS actual I2S RX descriptor consumption and EOF continuity");
    return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class I2SRxPcmCursorPatchTests(unittest.TestCase):
    def test_actual_callback_consumes_only_transferred_descriptor_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    continue
                subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / patch)],
                               cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                           cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                c_path = root / (label + ".c")
                c_path.write_text(STUBS + callback(source) + MAIN)
                binary = root / label
                result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                                         str(c_path), "-o", str(binary)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                for case in range(4):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed" or case == 3:
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0, "old cursor must fail this byte-stream oracle")


if __name__ == "__main__":
    unittest.main()

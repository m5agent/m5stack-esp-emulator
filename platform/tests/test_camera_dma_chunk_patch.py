"""Actual LCD_CAM C callback regression for multi-node half-buffer transfers.

DMA node capacity/acknowledgement are transport boundaries. Pixel generation,
source consumption, half-buffer completion and VSYNC behavior use the replayed
controller source. Visible guest/QEMU validation is a separate evidence layer.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0055-lcd-cam-frame-dma-chunks.patch"
SOURCE = "hw/m5stopwatch/m5_lcd_cam.c"


def function(source, name):
    match = re.search(r"static (?:void|uint16_t) " + re.escape(name) + r"\(", source)
    if match is None:
        raise AssertionError("actual camera function missing: " + name)
    start = source.index("{", match.start())
    depth = 0
    for index in range(start, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated actual camera function")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define g_autofree
#define g_malloc0(n) calloc(1,(n))
#define QEMU_CLOCK_VIRTUAL 1
#define GDMA_LCDCAM 5
#define ESP_GDMA_IN_IDX 0
#define GDMA_INT_ST_REG 1
#define R_GDMA_INTERRUPT_IN_SUC_EOF_MASK 2
#define CAM_VSYNC_INT 4
typedef struct M5LcdCamState {
    void *gdma, *capture_timer;
    uint32_t width,height,frame_seed,frame_offset,frame_bytes,chunk_len,chunks_left;
    uint8_t *frame_data;
    uint32_t frame_data_size,int_ena,int_raw;
    bool frame_auto_increment,started,dma_armed;
} M5LcdCamState;
static bool channel_ready=true,pending=false;
static unsigned capacity=3840,output_size,descriptor_calls,fail_after=~0u,vsyncs;
static uint8_t output[200000];
static int64_t now,scheduled;
static void lcd_cam_update_irq(M5LcdCamState *s) { if(s->int_raw&s->int_ena&CAM_VSYNC_INT)vsyncs++; }
static int64_t qemu_clock_get_ms(int clock) { assert(clock==1);return now; }
static void timer_mod(void *timer,int64_t deadline) { assert(timer && deadline>=now);scheduled=deadline; }
static bool esp_gdma_get_channel_periph(void *gdma,unsigned periph,unsigned direction,uint32_t *channel) {
    assert(gdma && periph==5 && direction==0);*channel=1;return channel_ready;
}
static uint32_t esp_gdma_complete_in_descriptor(void *gdma,unsigned channel,const uint8_t *data,unsigned size) {
    assert(gdma && channel==1);
    if(descriptor_calls>=fail_after)return 0;
    descriptor_calls++;
    unsigned accepted=MIN(size,capacity);
    assert(output_size+accepted<=sizeof(output));
    memcpy(output+output_size,data,accepted);output_size+=accepted;pending=true;
    return accepted;
}
static uint64_t esp_gdma_read_chan_register(void *gdma,unsigned direction,unsigned channel,unsigned reg) {
    assert(gdma && direction==0 && channel==1 && reg==GDMA_INT_ST_REG);
    return pending?R_GDMA_INTERRUPT_IN_SUC_EOF_MASK:0;
}
static void esp_gdma_set_chan_interrupt(void *gdma,unsigned direction,unsigned channel,unsigned mask) {
    assert(gdma && direction==0 && channel==1 && mask==2);pending=true;
}
'''


MAIN = r'''
static void step(M5LcdCamState *s) {now+=2;lcd_cam_capture(s);}
int main(int argc,char **argv) {
    assert(argc==2);
    M5LcdCamState s={.gdma=&s,.capture_timer=&s,.width=320,.height=240,
        .frame_bytes=153600,.chunk_len=15360,.chunks_left=10,
        .int_ena=CAM_VSYNC_INT,.started=true};
    switch(atoi(argv[1])) {
    case 0: /* Real CoreS3 trace: one half-buffer spans four 3840-byte nodes. */
        step(&s);assert(output_size==15360 && descriptor_calls==4 && s.chunks_left==9);break;
    case 1: /* Full framebuffer, ten EOF boundaries, then VSYNC after final ack. */
        for(unsigned n=0;n<10;n++){pending=false;step(&s);assert(output_size==(n+1)*15360);}
        assert(vsyncs==0);pending=false;step(&s);
        assert(vsyncs==1 && output_size==153600 && descriptor_calls==40);
        for(unsigned n=0;n<output_size;n+=2){
            uint16_t pixel=camera_pattern_pixel(&s,n/2);
            assert(output[n]==(uint8_t)pixel && output[n+1]==(pixel>>8));
        }
        break;
    case 2: /* Initial VSYNC with no configured DMA must not consume source. */
        channel_ready=false;step(&s);assert(output_size==0 && s.frame_offset==0);break;
    case 3: /* A stopped capture must not write another cyclic descriptor. */
        s.started=false;step(&s);assert(output_size==0 && s.frame_offset==0);break;
    case 4: /* Pending EOF must not coalesce another buffer completion or VSYNC. */
        pending=true;step(&s);assert(output_size==0 && s.chunks_left==10 && !vsyncs);break;
    case 5: /* Real descriptor error preserves transferred bytes, not a full frame. */
        fail_after=1;step(&s);assert(output_size==3840 && s.frame_offset==3840 && s.chunks_left==10 && !vsyncs);break;
    case 6: /* A borrowed framebuffer must not permanently stop sensor VSYNC. */
        s.chunks_left=0;step(&s);
        assert(vsyncs==1 && scheduled>now && output_size==0 && s.frame_offset==0);
        s.int_raw=0;step(&s);
        assert(vsyncs==2 && scheduled>now && output_size==0 && s.frame_offset==0);break;
    default:return 2;
    }
    puts("PASS LCD_CAM actual half-buffer descriptor, source and EOF sequencing");return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class CameraDmaChunkPatchTests(unittest.TestCase):
    def test_actual_camera_half_buffer_and_frame_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    # Freeze this historical 0055 transfer-order boundary;
                    # later data-format patches have independent regressions.
                    break
                subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + "\n".join(function(source, name) for name in ("camera_pattern_pixel", "lcd_cam_fill_frame", "lcd_cam_capture")) + MAIN)
                result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                for case in range(7):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed":
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0, "old capture must fail this transfer boundary oracle")


if __name__ == "__main__":
    unittest.main()

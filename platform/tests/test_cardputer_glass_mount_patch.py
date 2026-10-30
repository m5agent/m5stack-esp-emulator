"""Replay actual panel address/write/read functions for the ADV glass mount.

The oracle follows fixed M5GFX Panel_LCD::setRotation and the official
Cardputer default rotation1; it is independent of the QEMU output under test.
Host controller proof is not guest or physical-hardware validation.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PANEL = "hw/m5stopwatch/m5_spi_panel.c"
BOARD = "hw/m5stopwatch/m5cardputeradv.c"
PATCH = "patches/qemu-wasm-probe/0023-cardputer-adv-glass-mount.patch"


def function(source, name):
    start = source.index(name)
    start = source.rfind("static ", 0, start)
    opening = source.index("{", start)
    level, position = 1, opening + 1
    while level:
        level += (source[position] == "{") - (source[position] == "}")
        position += 1
    return source[start:position]


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "git/C compiler required")
class CardputerGlassMountTests(unittest.TestCase):
    def test_real_memory_and_glass_paths_all_pixels_four_rotations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
            for row in lock["patches"]:
                if row["path"] == PATCH:
                    break
                subprocess.run(["git", "apply", "--include=" + PANEL, "--include=" + BOARD,
                                str(ROOT / row["path"])], cwd=root, check=True, capture_output=True)
            old_board = (root / BOARD).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root,
                           check=True, capture_output=True)
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                           cwd=root, check=True, capture_output=True)
            new_board = (root / BOARD).read_text()
            source = (root / PANEL).read_text()
            old_rotation = re.search(r'"glass-rotation", (\d+)', old_board).group(1)
            new_rotation = re.search(r'"glass-rotation", (\d+)', new_board).group(1)
            self.assertEqual((old_rotation, new_rotation), ("1", "3"))
            common = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
typedef struct {
    uint16_t *mem, xs, xe, ys, ye, cx, cy;
    uint32_t mem_w, mem_h, vis_w, vis_h, off_x, off_y, glass_rotation;
    uint8_t madctl;
    bool apply_madctl, disp_on, sleep, physical_invert, controller_invert;
} M5SpiPanelState;
'''+function(source, "m5_panel_put_pixel(")+"\n"+function(source, "m5_panel_pixel_rgb(")+r'''
static uint32_t rgb(uint16_t c) {
    return ((c >> 11 & 31) * 255 / 31 << 16) |
           ((c >> 5 & 63) * 255 / 63 << 8) | ((c & 31) * 255 / 31);
}
int main(void) {
    uint16_t memory[240*320]={0}, expected[240*135];
    M5SpiPanelState s={.mem=memory,.mem_w=240,.mem_h=320,.vis_w=240,.vis_h=135,
                      .off_x=52,.off_y=40,.apply_madctl=true,.disp_on=true,
                      .glass_rotation=GLASS_ROTATION};
    /* Fixed M5GFX9bcedf4/0.2.35 Panel_LCD::setRotation for135x240,
     * offsets52/40, native memory240x320; these are driver address writes.
     * Rotation1 is the M5Cardputer default upright landscape orientation. */
    const unsigned windows[][4]={{52,40,135,240},{40,53,240,135},
                                 {53,40,135,240},{40,52,240,135}};
    const uint8_t madctl[]={0x00,0x64,0xd4,0xb0};
    unsigned total_bad=0;
    for(unsigned rotation=0;rotation<4;rotation++) {
        unsigned w=windows[rotation][2],h=windows[rotation][3];
        s.xs=windows[rotation][0];s.ys=windows[rotation][1];
        s.xe=s.xs+w-1;s.ye=s.ys+h-1;s.cx=s.xs;s.cy=s.ys;s.madctl=madctl[rotation];
        for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++) {
            uint16_t color=((x&31)<<11)|((y&63)<<5)|((x^y)&31);
            unsigned px=x,py=y;
            switch(rotation) {
            case 0:px=y;py=134-x;break;
            case 2:px=239-y;py=x;break;
            case 3:px=239-x;py=134-y;break;
            }
            expected[py*240+px]=color;
            m5_panel_put_pixel(&s,color);
        }
        unsigned bad=0;
        for(unsigned y=0;y<135;y++)for(unsigned x=0;x<240;x++)
            bad+=m5_panel_pixel_rgb(&s,x,y)!=rgb(expected[y*240+x]);
        printf("rotation%u pixels32400 mismatches%u\n",rotation,bad);total_bad+=bad;
    }
    return total_bad ? 1 : 0;
}
'''
            for rotation, should_pass in [(old_rotation, False), (new_rotation, True)]:
                path = root / "glass.c"
                path.write_text(common)
                binary = root / "glass"
                compiled = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Werror",
                    "-Wno-unused-parameter", "-DGLASS_ROTATION=" + rotation, str(path), "-o", str(binary)],
                    text=True, capture_output=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode == 0, should_pass, result.stdout + result.stderr)
                if should_pass:
                    for index in range(4):
                        self.assertIn(f"rotation{index} pixels32400 mismatches0", result.stdout)


if __name__ == "__main__":
    unittest.main()

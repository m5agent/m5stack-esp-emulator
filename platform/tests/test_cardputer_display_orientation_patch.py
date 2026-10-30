"""Replay the real panel getter and its old partial-window regression in C.

This checks the controller source, not a browser, firmware or physical LCD.
"""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
UNIT = "hw/m5stopwatch/m5_spi_panel.c"
PATCH = "patches/qemu-wasm-probe/0022-panel-madctl-orientation.patch"


def getter(source):
    start = source.index("static char *m5_panel_logical_orientation_get")
    opening = source.index("{", start)
    depth = 1
    position = opening + 1
    while depth:
        depth += (source[position] == "{") - (source[position] == "}")
        position += 1
    return source[start:position]


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git/C compiler required")
class CardputerDisplayOrientationTests(unittest.TestCase):
    def test_madctl_orientation_survives_partial_window_and_old_source_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            subprocess.run(["git", "init", "-q", str(directory)], check=True, capture_output=True)
            lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
            for row in lock["patches"]:
                if row["path"] == PATCH:
                    break
                subprocess.run(["git", "apply", "--include=" + UNIT, str(ROOT / row["path"])],
                               cwd=directory, check=True, capture_output=True)
            before = (directory / UNIT).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=directory,
                           check=True, capture_output=True)
            after = (directory / UNIT).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                           cwd=directory, check=True, capture_output=True)
            old_getter = getter(before).replace("m5_panel_logical_orientation_get", "old_getter")
            code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct {
    uint32_t vis_w, vis_h, glass_rotation;
    uint16_t xs, xe, ys, ye;
    uint8_t madctl;
    bool apply_madctl;
} M5SpiPanelState;
typedef M5SpiPanelState Object;
typedef void Error;
static char *g_strdup(const char *text) { return (char *)text; }
'''+old_getter+"\n"+getter(after)+r'''
int main(void) {
    M5SpiPanelState s = {.vis_w=240,.vis_h=135,.glass_rotation=1,.apply_madctl=true};
    s.xe=134;s.ye=239;
    assert(!strcmp(old_getter(&s, NULL), "portrait"));
    assert(!strcmp(m5_panel_logical_orientation_get(&s, NULL), "portrait"));
    s.xe=7;s.ye=7;
    assert(!strcmp(old_getter(&s, NULL), "unknown"));
    assert(!strcmp(m5_panel_logical_orientation_get(&s, NULL), "portrait"));
    /* M5GFX Panel_LCD's rotations0..3: MV=0,1,0,1. Other MADCTL bits,
     * CASET/RASET dimensions and even transient invalid windows do not
     * change the logical axes selected by MADCTL.MV. */
    const uint8_t rotations[]={0x00,0x64,0xd4,0xb0};
    const unsigned windows[][2]={{1,1},{8,8},{135,240},{240,135},{17,211}};
    for (unsigned rotation=0;rotation<4;rotation++) {
        s.madctl=rotations[rotation];
        for (unsigned window=0;window<5;window++) {
            s.xs=11;s.ys=9;s.xe=s.xs+windows[window][0]-1;s.ye=s.ys+windows[window][1]-1;
            assert(!strcmp(m5_panel_logical_orientation_get(&s,NULL),
                           rotation&1 ? "landscape" : "portrait"));
        }
    }
    s.glass_rotation=0;s.madctl=0x20;
    assert(!strcmp(m5_panel_logical_orientation_get(&s,NULL),"portrait"));
    s.madctl=0;
    assert(!strcmp(m5_panel_logical_orientation_get(&s,NULL),"landscape"));
    s.apply_madctl=false;s.madctl=0x20;
    assert(!strcmp(m5_panel_logical_orientation_get(&s,NULL),"landscape"));
    s.apply_madctl=true;s.vis_h=s.vis_w;
    assert(!strcmp(m5_panel_logical_orientation_get(&s,NULL),"landscape"));
    puts("PASS actual panel getter: old portrait-to-unknown reproduced; four MADCTL rotations and partial windows stable");
    return 0;
}
'''
            source = directory / "orientation.c"
            source.write_text(code)
            binary = directory / "orientation"
            compile_result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Werror",
                "-Wno-unused-parameter", str(source), "-o", str(binary)], capture_output=True,
                text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("old portrait-to-unknown reproduced", result.stdout)


if __name__ == "__main__":
    unittest.main()

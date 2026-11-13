"""Compile the actual panel command handler and read-only QOM observer.

Host controller/replay evidence only; original BIN guest runs are separate.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_unit_flashlight_cold_pad_patch import bootstrap_stack, ROOT

PANEL = "hw/m5stopwatch/m5_spi_panel.c"
PATCH = "patches/qemu-m5stack-peripherals/0187-spi-panel-frame-presentation.patch"


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git/C compiler required")
class PanelPresentationPatchTests(unittest.TestCase):
    def test_actual_madctl_reset_generation_and_read_only_observer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack(full=True):
                if patch == PATCH:
                    break
                subprocess.run(["git", "apply", "--include=" + PANEL, str(ROOT / patch)], cwd=root,
                               check=True, capture_output=True)
            before = (root / PANEL).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root,
                           check=True, capture_output=True)
            after = (root / PANEL).read_text()
            for signature in ("static void m5_panel_put_pixel(", "static uint32_t m5_panel_pixel_rgb("):
                self.assertEqual(function(before, signature), function(after, signature))
            code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
    uint32_t mem_w,mem_h,vis_w,vis_h,off_x,off_y,glass_rotation;
    uint64_t presentation_generation;
    uint8_t madctl,cmd,colmod,params[4],pix_hi;
    uint16_t xs,xe,ys,ye,cx,cy;
    unsigned read_offset,pidx,infer_params_left,pending_pixel_bytes;
    bool mono_sh1107,apply_madctl,infer_command,disp_on,sleep,controller_invert;
    bool dirty,pixel_mode,pix_half,immediate_update;
    void *refresh_bh;
} M5SpiPanelState;
typedef M5SpiPanelState Object;
typedef void Error;
#define M5_SPI_PANEL(obj) ((M5SpiPanelState *)(obj))
#define QEMU_CLOCK_VIRTUAL 0
static unsigned m5_panel_trace_count;
static void qemu_bh_schedule(void *p) {(void)p;}
static void qemu_clock_notify(int clock) {(void)clock;}
static void m5_sh1107_write(M5SpiPanelState *s,const uint8_t *b,uint32_t n,bool c) {(void)s;(void)b;(void)n;(void)c;}
static void m5_panel_put_pixel(M5SpiPanelState *s,uint16_t px) {(void)s;(void)px;}
static char *g_strdup_printf(const char *format,...) {
    static char text[2048]; va_list args;va_start(args,format);
    vsnprintf(text,sizeof(text),format,args);va_end(args);return text;
}
'''
            for signature in ("static bool m5_panel_is_dcs_command(", "static uint32_t m5_panel_dcs_param_count(",
                              "static void m5_panel_reset_window(", "void m5_spi_panel_write(",
                              "static char *m5_panel_presentation_get("):
                code += "\n" + function(after, signature)
            code += r'''
static void command(M5SpiPanelState *s,uint8_t value) {m5_spi_panel_write(s,&value,1,true);}
static void madctl(M5SpiPanelState *s,uint8_t value) {command(s,0x36);m5_spi_panel_write(s,&value,1,false);}
int main(void) {
    M5SpiPanelState s={.mem_w=240,.mem_h=320,.vis_w=135,.vis_h=240,
       .off_x=52,.off_y=40,.apply_madctl=true,.presentation_generation=1};
    madctl(&s,0xa0);assert(s.presentation_generation==2);
    madctl(&s,0xa0);assert(s.presentation_generation==2);
    madctl(&s,0x60);madctl(&s,0xa0);assert(s.presentation_generation==4);
    const uint8_t window[]={0,3,0,8};
    command(&s,0x2a);m5_spi_panel_write(&s,window,4,false);
    command(&s,0x2b);m5_spi_panel_write(&s,window,4,false);
    assert(s.presentation_generation==4);
    M5SpiPanelState before=s;
    puts(m5_panel_presentation_get(&s,NULL));
    assert(!memcmp(&s,&before,sizeof(s)));
    command(&s,1);assert(s.madctl==0);assert(s.presentation_generation==5);
    command(&s,1);assert(s.presentation_generation==6);
    puts(m5_panel_presentation_get(&s,NULL));
    s.mono_sh1107=true;puts(m5_panel_presentation_get(&s,NULL));
    return 0;
}
'''
            (root / "test.c").write_text(code)
            compiled = subprocess.run(["cc", "-std=c11", "-Wall", "-Werror", "-Wno-unused-parameter",
                                       str(root / "test.c"), "-o", str(root / "test")], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(root / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual((values[0]["generation"], values[0]["madctl"]), (4, 0xa0))
            self.assertEqual((values[1]["generation"], values[1]["madctl"]), (6, 0))
            self.assertFalse(values[2]["supported"])


if __name__ == "__main__":
    unittest.main()

"""Compare real panel blitters and trace side effects from patch images."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_wallclock_noop_yield_patch import function


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0026-panel-trace-predicate-order.patch"


def image(postimage):
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


HARNESS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

typedef struct { uint32_t w, h; uint32_t *pixels; } DisplaySurface;
typedef struct { DisplaySurface *surface; } QemuConsole;
typedef struct {
    QemuConsole *con;
    uint16_t *mem;
    uint32_t mem_w, mem_h, vis_w, vis_h, off_x, off_y;
    bool physical_invert, controller_invert, dirty, disp_on, sleep;
    uint8_t madctl;
    uint16_t xs, xe, ys, ye, cx, cy;
    uint32_t glass_rotation;
    bool apply_madctl;
} M5SpiPanelState;
static unsigned refresh_lookups, pixel_lookups, updates;
static bool refresh_enabled, pixel_enabled;
static char output[4096];
static size_t output_length;
static char *trace_getenv(const char *name)
{
    if (!strcmp(name, "M5SW_PANEL_REFRESH_TRACE")) {
        refresh_lookups++; return refresh_enabled ? "1" : NULL;
    }
    assert(!strcmp(name, "M5SW_PANEL_PIXEL_TRACE"));
    pixel_lookups++; return pixel_enabled ? "1" : NULL;
}
static int trace_fprintf(FILE *stream, const char *format, ...)
{
    (void)stream;
    va_list ap; va_start(ap, format);
    int n = vsnprintf(output + output_length, sizeof output - output_length, format, ap);
    va_end(ap);
    assert(n >= 0 && (size_t)n < sizeof output - output_length);
    output_length += (size_t)n; return n;
}
static DisplaySurface *qemu_console_surface(QemuConsole *con) { return con->surface; }
static int surface_bits_per_pixel(DisplaySurface *s) { (void)s; return 32; }
static uint32_t surface_width(DisplaySurface *s) { return s->w; }
static uint32_t surface_height(DisplaySurface *s) { return s->h; }
static void *surface_data(DisplaySurface *s) { return s->pixels; }
static uint32_t surface_stride(DisplaySurface *s) { return s->w * 4; }
static DisplaySurface *qemu_create_displaysurface(uint32_t w, uint32_t h)
{ (void)w; (void)h; assert(!"unexpected surface replacement"); return NULL; }
static void dpy_gfx_replace_surface(QemuConsole *con, DisplaySurface *surface)
{ (void)con; (void)surface; assert(!"unexpected surface replacement"); }
static void dpy_gfx_update(QemuConsole *con, int x, int y, uint32_t w, uint32_t h)
{ assert(x == 0 && y == 0 && w == con->surface->w && h == con->surface->h); updates++; }
static void reset_observation(void)
{ refresh_lookups = pixel_lookups = updates = 0; output_length = 0; output[0] = 0; }
#define getenv trace_getenv
#define fprintf trace_fprintf
"""

MAIN = r"""
enum { WIDTH = 320, HEIGHT = 240, MEM_SIDE = 384 };
static uint16_t panel_memory[MEM_SIDE * MEM_SIDE];
static uint32_t before_pixels[WIDTH * HEIGHT], after_pixels[WIDTH * HEIGHT];
static DisplaySurface surface = {WIDTH, HEIGHT, NULL};
static QemuConsole console = {&surface};
static void compare_updates(void)
{
    for (unsigned i = 0; i < MEM_SIDE * MEM_SIDE; i++) panel_memory[i] = (uint16_t)((i * 17u) ^ 0x5aa5u);
    for (unsigned rotation = 0; rotation < 4; rotation++)
    for (unsigned on = 0; on < 2; on++)
    for (unsigned sleep = 0; sleep < 2; sleep++)
    for (unsigned physical = 0; physical < 2; physical++)
    for (unsigned controller = 0; controller < 2; controller++)
    for (unsigned trace = 0; trace < 2; trace++) {
        M5SpiPanelState control = {.con = &console, .mem = panel_memory,
            .mem_w = MEM_SIDE, .mem_h = MEM_SIDE, .vis_w = WIDTH, .vis_h = HEIGHT,
            .off_x = 3, .off_y = 4, .physical_invert = physical, .controller_invert = controller,
            .dirty = true, .disp_on = on, .sleep = sleep, .glass_rotation = rotation};
        M5SpiPanelState candidate = control;
        char original_log[sizeof output];
        refresh_enabled = trace;
        surface.pixels = before_pixels; reset_observation(); before_update(&control);
        assert(refresh_lookups == WIDTH * HEIGHT + 1 && updates == 1);
        strcpy(original_log, output);
        surface.pixels = after_pixels; reset_observation(); after_update(&candidate);
        assert(refresh_lookups == 2 && updates == 1);
        assert(!strcmp(original_log, output));
        assert(!memcmp(before_pixels, after_pixels, sizeof before_pixels));
        assert(!control.dirty && !candidate.dirty);
        if (!on || sleep) {
            for (unsigned i = 0; i < WIDTH * HEIGHT; i++) assert(after_pixels[i] == 0xff000000u);
        }
        /* A clean panel still returns before any trace query or notification. */
        reset_observation(); before_update(&control); assert(!refresh_lookups && !updates);
        reset_observation(); after_update(&candidate); assert(!refresh_lookups && !updates);
    }
}
static void compare_pixel_writes(void)
{
    const uint16_t colors[] = {0x1234, 0xf800, 0x07e0, 0x001f};
    const uint8_t madctls[] = {0, 0x20, 0x40, 0x80, 0xe0};
    unsigned control_messages = 0, candidate_messages = 0;
    for (unsigned apply = 0; apply < 2; apply++)
    for (unsigned m = 0; m < sizeof madctls; m++)
    for (unsigned trace = 0; trace < 2; trace++) {
        uint16_t control_mem[64] = {0}, candidate_mem[64] = {0};
        M5SpiPanelState control = {.mem = control_mem, .mem_w = 8, .mem_h = 8,
            .xs = 1, .xe = 3, .ys = 2, .ye = 4, .cx = 1, .cy = 2,
            .apply_madctl = apply, .madctl = madctls[m]};
        M5SpiPanelState candidate = control; candidate.mem = candidate_mem;
        for (unsigned i = 0; i < 604; i++) {
            uint16_t px = colors[i % 4]; char original_log[sizeof output];
            pixel_enabled = trace;
            reset_observation(); before_put_pixel(&control, px);
            assert(pixel_lookups == 1); strcpy(original_log, output);
            control_messages += output_length > 0;
            reset_observation(); after_put_pixel(&candidate, px);
            assert(pixel_lookups == (px != 0x1234 ? 1u : 0u));
            candidate_messages += output_length > 0;
            assert(!strcmp(original_log, output));
            assert(!memcmp(control_mem, candidate_mem, sizeof control_mem));
            assert(control.cx == candidate.cx && control.cy == candidate.cy);
            if (!trace || px == 0x1234) assert(!output_length);
        }
    }
    /* Both real function-local counters saturate at the same 500 log lines. */
    assert(control_messages == 500 && candidate_messages == 500);
}
int main(void)
{
    compare_updates(); compare_pixel_writes();
    puts("PASS: actual panel outputs/traces unchanged; dirty-frame getenv 76801 to 2");
    return 0;
}
"""


class PanelTracePredicateTests(unittest.TestCase):
    def test_patch_identity_and_only_predicate_reordering(self):
        lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
        row = next(row for row in lock["patches"] if row["path"] == PATCH.relative_to(ROOT).as_posix())
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), row["sha256"])
        before, after = image(False), image(True)
        for name in ("m5_panel_update", "m5_panel_put_pixel"):
            original, changed = function(before, name), function(after, name)
            self.assertEqual(original.count("getenv("), changed.count("getenv("))
            self.assertEqual(original.count("pixel_trace_count++"), changed.count("pixel_trace_count++"))

    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_actual_blitter_pixels_and_trace_side_effects(self):
        bodies = []
        for postimage, prefix in ((False, "before"), (True, "after")):
            text = image(postimage)
            for name in ("update", "put_pixel"):
                body = function(text, "m5_panel_" + name)
                bodies.append(body.replace("m5_panel_" + name, prefix + "_" + name, 1))
        with tempfile.TemporaryDirectory(prefix="m5-panel-trace-") as directory:
            path = Path(directory); source = path / "panel.c"; binary = path / "panel"
            source.write_text(HARNESS + "\n".join(bodies) + MAIN)
            subprocess.run([shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
                           check=True, capture_output=True, text=True, timeout=20)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=5)
            self.assertIn("dirty-frame getenv 76801 to 2", result.stdout)


if __name__ == "__main__":
    unittest.main()

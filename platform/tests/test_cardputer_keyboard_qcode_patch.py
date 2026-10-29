"""Replay the shipped C keyboard helpers against fixed QAPI/SDK key layouts.

No QEMU guest is executed. The old preimage is a required failing control;
native/browser guest matrix, I2C, UART and framebuffer proof remains separate.
"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0016-cardputer-keyboard-qcode-map.patch"
FIXTURE = ROOT / "platform/tests/fixtures/cardputer_qkeycode_40edccac.json"


def patch_helpers(postimage):
    lines = []
    in_hunk = False
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line[:1] in (" ", "+" if postimage else "-"):
            lines.append(line[1:])
    source = "\n".join(lines)
    start = source.index("static uint8_t tca8418_event(")
    end = source.index("static void m5_panel_input(", start)
    return source[start:end]


def control_source():
    fixture = json.loads(FIXTURE.read_text())
    names = fixture["qkeycode"]
    # Preserve the actual nonalphabetical numeric enum, including all holes.
    enumeration = "enum QKeyCode {" + ",".join(
        "Q_KEY_CODE_" + name.upper() for name in names) + ",Q_KEY_CODE__MAX};\n"
    physical = [(name, row, col)
                for row, keys in enumerate(fixture["physical_rows"])
                for col, name in enumerate(keys) if name is not None]
    physical += [("SHIFT_R", 2, 1), ("CTRL_R", 3, 0),
                 ("ALT_R", 3, 2), ("META_R", 3, 1)]
    expected = "\n".join(
        f"    check_key(Q_KEY_CODE_{name}, {row}, {col});"
        for name, row, col in physical)
    return enumeration, r"""
static unsigned failures, controls;
static void expect(int ok, int qcode, const char *phase) {
    controls++;
    if (!ok) {
        failures++;
        fprintf(stderr, "qcode=%d phase=%s mismatch\n", qcode, phase);
    }
}
static void check_key(int code, int row, int col) {
    int got_row = -1, got_col = -1;
    expect(tca8418_key_pos(code, &got_row, &got_col)
        && got_row == row && got_col == col, code, "physical-position");
    /* Independently invert the SDK's raw 7x8 -> visual 4x14 conversion. */
    unsigned raw = (unsigned)(col / 2 * 10 + row + (col % 2 ? 4 : 0) + 1);
    used = 0; m5_panel_keyboard_event(code, true);
    expect(used == 1 && fifo[0] == (raw | 0x80), code, "press");
    used = 0; m5_panel_keyboard_event(code, false);
    expect(used == 1 && fifo[0] == raw, code, "release");
}
static void check_chord(int code, unsigned key_raw) {
    used = 0; m5_panel_keyboard_event(code, true);
    expect(used == 2 && fifo[0] == 0x83 && fifo[1] == (key_raw | 0x80),
           code, "fn-before-press");
    used = 0; m5_panel_keyboard_event(code, false);
    expect(used == 2 && fifo[0] == key_raw && fifo[1] == 0x03,
           code, "release-before-fn");
}
int main(void) {
""" + expected + r"""
    check_chord(Q_KEY_CODE_ESC, 0x01);
    check_chord(Q_KEY_CODE_DELETE, 0x41);
    check_chord(Q_KEY_CODE_LEFT, 0x36);
    check_chord(Q_KEY_CODE_DOWN, 0x3a);
    check_chord(Q_KEY_CODE_RIGHT, 0x40);
    check_chord(Q_KEY_CODE_UP, 0x39);
    int invalid[] = {-1, Q_KEY_CODE_UNMAPPED, Q_KEY_CODE_F1,
                     Q_KEY_CODE_CAPS_LOCK, Q_KEY_CODE__MAX, 10000};
    for (unsigned i = 0; i < ARRAY_SIZE(invalid); i++) {
        int row = -7, col = -9;
        expect(!tca8418_key_pos(invalid[i], &row, &col)
               && row == -7 && col == -9, invalid[i], "invalid-no-position");
        used = 0; m5_panel_keyboard_event(invalid[i], true);
        m5_panel_keyboard_event(invalid[i], false);
        expect(used == 0, invalid[i], "invalid-no-fifo-events");
    }
    printf("controls=%u failures=%u\n", controls, failures);
    return failures ? 1 : 0;
}
"""


STUBS = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static uint8_t fifo[8];
static unsigned used;
static void m5sw_keyboard_event(uint8_t event) {
    if (used >= ARRAY_SIZE(fifo)) abort();
    fifo[used++] = event;
}
"""


@unittest.skipUnless(shutil.which("cc"), "requires a C compiler")
class CardputerQcodeTests(unittest.TestCase):
    def replay(self, postimage):
        enumeration, controls = control_source()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "keyboard.c"
            target = Path(directory) / "keyboard"
            source.write_text(STUBS + enumeration + patch_helpers(postimage) + controls)
            subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Werror",
                            str(source), "-o", str(target)], check=True,
                           text=True, capture_output=True)
            return subprocess.run([str(target)], text=True, capture_output=True)

    def test_shipped_c_maps_all_physical_keys_and_matching_fifo_edges(self):
        result = self.replay(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("controls=204 failures=0", result.stdout)

    def test_original_range_is_a_required_failing_control(self):
        result = self.replay(False)
        self.assertNotEqual(result.returncode, 0)
        fixture = json.loads(FIXTURE.read_text())
        for key in ("q", "w", "e", "b", "n", "m", "z"):
            code = fixture["qkeycode"].index(key)
            self.assertIn(f"qcode={code} phase=physical-position mismatch", result.stderr)

    def test_enum_and_sdk_sources_are_explicitly_pinned(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["qemu_commit"], "40edccac415693c5130f91c01d84176ae6008566")
        self.assertEqual(fixture["keyboard_source"]["commit"], "50e440780492aa847378c7d3477ab912f7063bac")
        self.assertEqual(fixture["keyboard_source"]["sha256"], "ca22657f704da629e9659ba50b769f169af077aca16d9dae1c94b269ae85fd33")
        self.assertLess(fixture["qkeycode"].index("z"), fixture["qkeycode"].index("b"))


if __name__ == "__main__":
    unittest.main()

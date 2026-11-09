"""Replay the exact locked Cardputer C sources and exercise real input branches.

Host C validation only. No build cache, QEMU guest, browser or physical device
is required. Original keyboard helper source is retained as an independent
pre/post equality check; GPIO and FIFO observation glue is shimmed.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_cstack_diagnostics_opt_in_patch import function

ROOT = Path(__file__).resolve().parents[2]
PATCH_NAME = "patches/qemu-wasm-probe/0029-cardputer-adv-boot-button.patch"
PANEL = "hw/m5stopwatch/m5_spi_panel.c"
BOARD = "hw/m5stopwatch/m5cardputeradv.c"
PREIMAGE_SHA = {
    PANEL: "838695ca92b319b516ad43bd22ea4fe0be8b23dce6ba046bd542b7d5577ed26c",
    BOARD: "33236c8396be2fc1c9f5f2970dc1a92fd352dc951e782b8c1dd38c3fd9c0a9cc",
}
POSTIMAGE_SHA = {
    PANEL: "2b0eda9d99e64122a69a9ffa5c868a4fb86726d2504f87b162d54c7f6a22e786",
    BOARD: "a9503e5ab59ea0c7ffc0fad154485b58b924bbd8c94b9c95ad87fc74dcca2916",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def program(sources):
    panel, board = sources[PANEL], sources[BOARD]
    helpers = "\n".join(function(panel, name) for name in
                        ("tca8418_event", "tca8418_key_pos", "m5_panel_keyboard_event"))
    block_start = panel.index("        if (s->keyboard) {")
    block = panel[block_start:panel.index("        if (s->plc_keys) {", block_start)]
    start = board.index('    qdev_prop_set_bit(panel, "apply-madctl", true);')
    config = board[start:board.index('    qdev_prop_set_bit(panel, "invert", true);', start)]
    keys = json.loads((ROOT / "platform/tests/fixtures/cardputer_qkeycode_40edccac.json").read_text())["qkeycode"]
    enumeration = "enum QKeyCode {" + ",".join("Q_KEY_CODE_" + name.upper() for name in keys) + ",Q_KEY_CODE__MAX};\n"
    return r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
typedef struct { bool keyboard; uint32_t key_a_pin; } M5SpiPanelState;
static unsigned gpio_count, gpio_pin, gpio_level, fifo_count;
static uint8_t fifo[8];
static void esp32_gpio_set_input(unsigned pin, bool level) {
    gpio_count++; gpio_pin=pin; gpio_level=level;
}
static void m5sw_keyboard_event(uint8_t value) {
    assert(fifo_count<ARRAY_SIZE(fifo)); fifo[fifo_count++]=value;
}
static void qdev_prop_set_bit(M5SpiPanelState *s, const char *name, bool value) {
    if (!strcmp(name, "keyboard")) s->keyboard=value;
}
static void qdev_prop_set_uint32(M5SpiPanelState *s, const char *name, uint32_t value) {
    assert(!strcmp(name, "key-a-pin")); s->key_a_pin=value;
}
""" + enumeration + helpers + r"""
static void actual_dispatch(M5SpiPanelState *s, int q, bool down) {
    do {
""" + block + r"""
    } while (false);
}
static void actual_board_config(M5SpiPanelState *panel) {
""" + config + r"""
}
static void clear_observation(void) {
    gpio_count=0; gpio_pin=99; gpio_level=99; fifo_count=0;
    memset(fifo,0,sizeof(fifo));
}
int main(void) {
    M5SpiPanelState board={.keyboard=false,.key_a_pin=10};
    actual_board_config(&board);
    if(!board.keyboard || board.key_a_pin!=0 || gpio_count!=1 || gpio_pin!=0 || gpio_level!=1) {
        fprintf(stderr,"BOOT_CONFIG_FAIL pin=%u gpio_count=%u\n",board.key_a_pin,gpio_count);return 1;
    }
    for(unsigned down=0;down<2;down++) {
        clear_observation(); actual_dispatch(&board,Q_KEY_CODE_F12,down);
        if(gpio_count!=1 || gpio_pin!=0 || gpio_level!=!down || fifo_count) {
            fprintf(stderr,"BOOT_EDGE_FAIL down=%u gpio_count=%u fifo=%u\n",down,gpio_count,fifo_count);return 2;
        }
    }
    unsigned controls=2;
    // Every other symbolic QKeyCode and invalid boundary must retain the
    // unchanged keyboard helper/FIFO sequence, including Fn chord release order.
    for(int q=-1;q<=Q_KEY_CODE__MAX+1;q++) for(unsigned down=0;down<2;down++) {
        clear_observation();m5_panel_keyboard_event(q,down);
        uint8_t expected[8];memcpy(expected,fifo,sizeof(fifo));unsigned count=fifo_count;
        clear_observation();actual_dispatch(&board,q,down);
        if(q==Q_KEY_CODE_F12)continue;
        assert(!gpio_count && fifo_count==count && !memcmp(fifo,expected,sizeof(fifo)));controls++;
    }
    // A keyboard panel retaining its old non-G0 pin must not gain a new GPIO
    // side effect from the dedicated carrier. Non-keyboard boards also ignore it.
    for(unsigned pin=10;pin<=11;pin++) for(unsigned keyboard=0;keyboard<2;keyboard++) {
        board.key_a_pin=pin;board.keyboard=keyboard;
        clear_observation();actual_dispatch(&board,Q_KEY_CODE_F12,true);
        actual_dispatch(&board,Q_KEY_CODE_F12,false);assert(!gpio_count&&!fifo_count);controls++;
    }
    printf("CARDPUTER_BOOT_HOST_PASS controls=%u\n",controls);return 0;
}
"""


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "Host C compiler and git required")
class CardputerBootButtonPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="m5-cardputer-boot-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        tree = cls.directory / "source"
        subprocess.run(["git", "init", "-q", str(tree)], check=True, capture_output=True)
        cls.lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
        seen = False
        for row in cls.lock["patches"]:
            if row["path"] == PATCH_NAME:
                seen = True
                break
            args = ["git", "apply", "--include=" + PANEL, "--include=" + BOARD, str(ROOT / row["path"])]
            subprocess.run(args[:2] + ["--check"] + args[2:], cwd=tree, check=True, capture_output=True)
            subprocess.run(args, cwd=tree, check=True, capture_output=True)
        if not seen:
            raise AssertionError("New input patch is absent from the source build lock")
        cls.before = {name: (tree / name).read_text() for name in PREIMAGE_SHA}
        for name, expected in PREIMAGE_SHA.items():
            if digest((tree / name).read_bytes()) != expected:
                raise AssertionError("Exact preimage mismatch: " + name)
        patch = ROOT / PATCH_NAME
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True, capture_output=True)
        cls.after = {name: (tree / name).read_text() for name in POSTIMAGE_SHA}
        for name, expected in POSTIMAGE_SHA.items():
            actual = digest((tree / name).read_bytes())
            if actual != expected or actual != cls.lock["patched_files"][name]:
                raise AssertionError("Exact locked postimage mismatch: " + name)
        subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", "--reverse", str(patch)], cwd=tree, check=True, capture_output=True)
        if any((tree / name).read_text() != text for name, text in cls.before.items()):
            raise AssertionError("Reverse apply did not restore the exact preimage")

    def execute(self, sources, name):
        path, binary = self.directory / (name + ".c"), self.directory / name
        path.write_text(program(sources))
        subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        str(path), "-o", str(binary)], check=True, capture_output=True, text=True, timeout=30)
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)

    def test_original_missing_g0_wiring_is_required_failing_control(self):
        result = self.execute(self.before, "before")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BOOT_CONFIG_FAIL pin=10", result.stderr)

    def test_postimage_active_low_g0_keeps_all_matrix_qcodes_unchanged(self):
        result = self.execute(self.after, "after")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CARDPUTER_BOOT_HOST_PASS", result.stdout)

    def test_original_fifo_helpers_are_byte_identical(self):
        for name in ("tca8418_event", "tca8418_key_pos", "m5_panel_keyboard_event"):
            self.assertEqual(function(self.before[PANEL], name), function(self.after[PANEL], name))


if __name__ == "__main__":
    unittest.main()

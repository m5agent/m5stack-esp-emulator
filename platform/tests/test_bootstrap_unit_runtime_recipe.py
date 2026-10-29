"""Check native recipe integration without a local source cache or guest."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
NATIVE = "patches/qemu-unit-runtime/"
PERIPHERAL = "patches/qemu-m5stack-peripherals/"


def recipe():
    tree = ast.parse((ROOT / "scripts/bootstrap-unit-runtime.py").read_text())
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "PATCHES"
                        for target in node.targets))


def sections(path):
    result = {}
    current = None
    for line in (ROOT / path).read_text().splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            result[current] = []
        elif line == "-- " or line.startswith(("diff --git ", "--- ")):
            current = None
        elif current is not None:
            result[current].append(line)
    return result


def changes(path):
    return {name: [line for line in lines if line.startswith(("+", "-"))
                   and line[1:].strip()]
            for name, lines in sections(path).items()}


def new_file(path, name):
    return "\n".join(line[1:] for line in sections(path)[name]
                     if line.startswith("+")) + "\n"


class NativeRuntimeRecipeTests(unittest.TestCase):
    def test_expanded_boards_extend_the_product_recipe(self):
        patches = recipe()
        self.assertEqual(len(patches), len(set(patches)))
        for name in patches:
            self.assertTrue((ROOT / name).is_file(), name)
            self.assertNotIn("wasm", name)
            self.assertFalse(re.match(r"00(?:7[1-9]|8[0-4])-", Path(name).name))
        self.assertEqual(patches[-9:], (
            PERIPHERAL + "0085-atoms3-and-atoms3-lite-boards.patch",
            PERIPHERAL + "0086-stickc-family-boards.patch",
            PERIPHERAL + "0087-atoms3-rgb-and-dial-board.patch",
            NATIVE + "0007-native-expanded-atom-rmt-delta.patch",
            PERIPHERAL + "0089-esp32-qio-flash-model-header.patch",
            NATIVE + "0008-native-core2-atecc608-context.patch",
            PERIPHERAL + "0090-stackchan-scs-motion-observer.patch",
            PERIPHERAL + "0091-board-power-lifecycle.patch",
            PERIPHERAL + "0092-classic-touch-measurement.patch",
        ))
        self.assertLess(patches.index(NATIVE + "0004-native-classic-rmt-context.patch"),
                        patches.index(NATIVE + "0007-native-expanded-atom-rmt-delta.patch"))

    def test_context_ports_preserve_the_original_c_changes(self):
        pairs = (
            ("0003-native-high-priority-irq-context.patch", "0065-xtensa-high-priority-irq-cooperative-yield.patch"),
            ("0004-native-classic-rmt-context.patch", "0066-esp32-classic-rmt-legacy.patch"),
            ("0006-native-uart-trace-context.patch", "0070-esp32-uart-tx-virtual-clock.patch"),
        )
        for native, original in pairs:
            with self.subTest(native=native):
                self.assertEqual(changes(NATIVE + native), changes(PERIPHERAL + original))

    @unittest.skipUnless(shutil.which("git"), "Git required")
    def test_rmt_delta_replays_on_0066_and_matches_portable_source(self):
        name = "hw/m5stopwatch/m5_rmt_classic.c"
        seed = new_file(PERIPHERAL + "0066-esp32-classic-rmt-legacy.patch", name)
        expected = new_file(PERIPHERAL + "0088-classic-atom-rmt-boards.patch", name)
        patch = ROOT / NATIVE / "0007-native-expanded-atom-rmt-delta.patch"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / name
            target.parent.mkdir(parents=True)
            target.write_text(seed)
            command = ["git", "apply", "--include=" + name]
            for args in (("--check",), (), ("--reverse", "--check"), ("--reverse",)):
                result = subprocess.run(command + list(args) + [str(patch)],
                                        cwd=directory, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if not args:
                    self.assertEqual(target.read_text(), expected)
            self.assertEqual(target.read_text(), seed)

    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_native_wdt_feed_runs_while_configuration_is_locked(self):
        lines = sections(NATIVE + "0005-native-wdt-feed-context.patch")["hw/timer/esp32_timg.c"]
        postimage = "\n".join(line[1:] for line in lines if line[:1] in {" ", "+"})
        start = postimage.index("case A_TIMG_WDTFEED:")
        branch = postimage[start:postimage.index("break;", start) + len("break;")]
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
enum { A_TIMG_WDTFEED = 0x60 };
typedef struct { int id; struct { int protect_reg; } wdt; } State;
static int feeds;
static bool esp32_timg_trace_enabled(void) { return false; }
static void esp32_timg_wdt_feed(void *wdt) { (void)wdt; ++feeds; }
static void feed(State *s) { switch (A_TIMG_WDTFEED) {
''' + branch + r'''
} }
int main(void) {
    State state = { .wdt = { .protect_reg = 0 } };
    feed(&state); assert(feeds == 1);
    state.wdt.protect_reg = 0x50d83aa1;
    feed(&state); assert(feeds == 2);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.c"
            binary = Path(directory) / "feed"
            path.write_text(source)
            result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra",
                                     "-Werror", str(path), "-o", str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)


if __name__ == "__main__":
    unittest.main()

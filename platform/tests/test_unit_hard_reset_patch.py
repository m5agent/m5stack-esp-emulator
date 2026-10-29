"""Compile the actual hard-reset observer and reject stale transition state."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0087-unit-hard-reset-output-boundary.patch"


def function(source: str, name: str) -> str:
    match = re.search(r"^[^\n;]*\b" + re.escape(name) + r"\([^;]*?\)\n\{", source, re.M)
    if not match:
        raise AssertionError("missing source function: " + name)
    end = source.index("{", match.start()) + 1
    depth = 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[match.start():end]


class UnitHardResetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text()
        cls.added = "\n".join(
            line[1:] for line in cls.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )

    def test_reset_observer_precedes_post_reset_edge_notification(self):
        gpio_side = self.patch.split("--- a/hw/m5stopwatch/m5_unit_runtime.c", 1)[0]
        self.assertLess(
            gpio_side.index("gpio_notify_reset();"),
            gpio_side.index("gpio_notify(before, after);"),
        )
        self.assertEqual(self.added.count("        esp32_gpio_add_reset_listener("), 2)
        self.assertIn("device_class_set_legacy_reset(dc, unit_reset);", self.added)
        bootstrap = (ROOT / "scripts/bootstrap-unit-runtime.py").read_text()
        self.assertIn(PATCH.name, bootstrap)

    def test_unit_bootstrap_uses_forward_ports_without_rewriting_core2_history(self):
        bootstrap = (ROOT / "scripts/bootstrap-unit-runtime.py").read_text()
        for name in (
            "0003-xtensa-high-priority-irq-cooperative-yield.patch",
            "0004-esp32-classic-rmt-legacy.patch",
            "0005-esp32-timg-wdt-feed-unprotected.patch",
            "0006-esp32-uart-tx-virtual-clock.patch",
        ):
            self.assertIn("patches/qemu-unit-runtime/" + name, bootstrap)
        for name in (
            "0065-xtensa-high-priority-irq-cooperative-yield.patch",
            "0066-esp32-classic-rmt-legacy.patch",
            "0069-esp32-timg-wdt-feed-unprotected.patch",
            "0070-esp32-uart-tx-virtual-clock.patch",
        ):
            self.assertNotIn("patches/qemu-m5stack-peripherals/" + name, bootstrap)

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_actual_reset_helpers_rebase_outputs_without_counting_reset_edge(self):
        functions = "\n".join(
            function(self.added, name)
            for name in ("reset_observed_outputs", "output_reset", "unit_reset")
        )
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef struct DeviceState { int unused; } DeviceState;
typedef struct M5Unit M5Unit;
typedef enum { UNIT_RELAY, UNIT_RELAY2 } UnitKind;
struct M5Unit {
    UnitKind kind;
    int yellow, white;
    uint64_t output_transitions;
    int previous_output;
    int relay2_previous[2];
    uint64_t relay2_transitions[2];
};
#define M5_UNIT(dev) ((M5Unit *)(dev))
static int pads[49];
static int esp32_gpio_get_line(int pin) {
    assert(pin >= 0 && pin < 49);
    return pads[pin];
}
''' + functions + r'''
static void relay_edge(M5Unit *unit, int level) {
    if (unit->previous_output != level) {
        unit->previous_output = level;
        unit->output_transitions++;
    }
}
static void relay2_edge(M5Unit *unit, int pin, int level) {
    unsigned channel = pin == unit->white ? 0 : 1;
    if (unit->relay2_previous[channel] != level) {
        unit->relay2_previous[channel] = level;
        unit->relay2_transitions[channel]++;
        unit->output_transitions++;
    }
}
static void relay_reset(M5Unit *unit) {
    pads[unit->yellow] = 0;
    output_reset(unit, unit->yellow, 0);
    relay_edge(unit, pads[unit->yellow]);
}
static void relay2_reset(M5Unit *unit, bool white_high, bool yellow_high) {
    pads[unit->white] = white_high;
    pads[unit->yellow] = yellow_high;
    output_reset(unit, unit->white, white_high);
    output_reset(unit, unit->yellow, yellow_high);
    relay2_edge(unit, unit->white, white_high);
    relay2_edge(unit, unit->yellow, yellow_high);
}
int main(void) {
    M5Unit relay = {.kind=UNIT_RELAY, .yellow=5};
    pads[5] = 1;
    relay_edge(&relay, 1);
    assert(relay.previous_output == 1 && relay.output_transitions == 1);
    relay_reset(&relay);
    assert(relay.previous_output == 0 && relay.output_transitions == 0);
    pads[5] = 1;
    relay_edge(&relay, 1);
    assert(relay.previous_output == 1 && relay.output_transitions == 1);

    M5Unit relay2 = {.kind=UNIT_RELAY2, .white=8, .yellow=9};
    pads[8] = 1;
    pads[9] = 0;
    relay2_edge(&relay2, 8, 1);
    assert(relay2.relay2_previous[0] == 1);
    assert(relay2.relay2_previous[1] == 0);
    assert(relay2.relay2_transitions[0] == 1);
    assert(relay2.relay2_transitions[1] == 0);
    assert(relay2.output_transitions == 1);

    relay2_reset(&relay2, true, true);
    assert(relay2.relay2_previous[0] == 1);
    assert(relay2.relay2_previous[1] == 1);
    assert(relay2.relay2_transitions[0] == 0);
    assert(relay2.relay2_transitions[1] == 0);
    assert(relay2.output_transitions == 0);
    relay2_edge(&relay2, 8, 1);
    relay2_edge(&relay2, 9, 1);
    assert(relay2.relay2_transitions[0] == 0);
    assert(relay2.relay2_transitions[1] == 0);

    pads[8] = 0;
    relay2_edge(&relay2, 8, 0);
    assert(relay2.relay2_transitions[0] == 1);
    assert(relay2.relay2_transitions[1] == 0);
    assert(relay2.output_transitions == 1);

    M5Unit *cast = (M5Unit *)&relay;
    relay.output_transitions = 9;
    unit_reset((DeviceState *)cast);
    assert(relay.output_transitions == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit_reset.c"
            path.write_text(source)
            binary = path.with_suffix("")
            subprocess.run([
                shutil.which("cc"), "-std=c11", "-Wall", "-Wextra",
                "-Wno-unused-parameter", "-Werror", str(path), "-o", str(binary),
            ], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()

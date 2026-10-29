"""Replay actual shipped TCA8418 C cases; no QEMU guest/cache is required."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0018-tca8418-cfg0-key-interrupt.patch"
FIXTURE = ROOT / "platform/tests/fixtures/tca8418_irq_post45.json"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def patch_cases(postimage):
    lines, in_hunk = [], False
    for line in PATCH.read_text().splitlines():
        if line.startswith("@@ "):
            in_hunk = True
        elif in_hunk and line[:1] in (" ", "+" if postimage else "-"):
            lines.append(line[1:])
    source = "\n".join(lines)
    result = []
    for match in re.finditer(r"^    case M_TCA8418:", source, re.M):
        end = re.search(r"^    (?:case |default:)", source[match.end():], re.M)
        if end is None:
            raise AssertionError("Patch must retain the complete TCA8418 case")
        result.append(source[match.start():match.end() + end.start()].rstrip())
    if len(result) != 2:
        raise AssertionError("Expected the actual read and W1C case bodies")
    return result


C_STUBS = r"""
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
enum { M_TCA8418 = 1 };
typedef struct { int model; uint8_t regs[256], ptr; } M5swI2CDev;
static int gpio_level = 1;
static unsigned rises, falls;
static void esp32_gpio_set_input(int pin, int level) {
    if (pin != 11) return;
    if (level != gpio_level) { if (level) rises++; else falls++; }
    gpio_level = level;
}
"""

C_CONTROLS = r"""
static void reset(M5swI2CDev *s, int cfg1) {
    memset(s, 0, sizeof(*s)); s->model = M_TCA8418;
    s->regs[1] = cfg1 ? 0x11 : 0x01; g_keyboard = s;
    g_key_event_head = g_key_event_count = 0;
    gpio_level = 1; rises = falls = 0;
}
static void sample(const char *name, M5swI2CDev *s, int value) {
    printf("{\"case\":\"%s\",\"value\":%d,\"count\":%u,\"status\":%u,\"gpio\":%d,\"ptr\":%u,\"rises\":%u,\"falls\":%u}\n",
           name, value, g_key_event_count, s->regs[2], gpio_level,
           s->ptr, rises, falls);
}
int main(void) {
    M5swI2CDev s;
    /* N's actual 4x14 position is (3,8): FIFO press=0xac/release=0x2c. */
    reset(&s, 0); m5sw_keyboard_event(0xac);
    int event = read_reg(&s, 4);
    sample("press-popped-awaiting-w1c", &s, event);
    /* This is the original driver's drain -> new release -> W1C window. */
    m5sw_keyboard_event(0x2c);
    sample("release-arrived-before-w1c", &s, 0);
    write_reg(&s, 2, 1);
    sample("w1c-with-release-pending", &s, 0);
    event = read_reg(&s, 4);
    sample("release-popped-awaiting-w1c", &s, event);
    write_reg(&s, 2, 1);
    sample("release-w1c-complete", &s, 0);

    /* A poll/extra rising-edge handler can also see no flag before arrival. */
    reset(&s, 0); event = read_reg(&s, 2);
    m5sw_keyboard_event(0x2c); write_reg(&s, 2, 1);
    sample("empty-status-new-event-w1c", &s, event);

    reset(&s, 0); s.regs[2] = 0x1f; m5sw_keyboard_event(0x2c);
    write_reg(&s, 2, 0x05);
    sample("w1c-other-bits-preserved", &s, 0);
    reset(&s, 0); s.regs[2] = 0x1f; m5sw_keyboard_event(0x2c);
    write_reg(&s, 2, 0x08);
    sample("non-key-w1c-preserves-key", &s, 0);
    reset(&s, 0); m5sw_keyboard_event(0xac); (void)read_reg(&s, 4);
    write_reg(&s, 2, 0);
    sample("zero-write-retains-latch", &s, 0);

    reset(&s, 0);
    const uint8_t bytes[] = {0xac, 0x2c, 0xa6, 0x26};
    for (unsigned i = 0; i < ARRAY_SIZE(bytes); i++) m5sw_keyboard_event(bytes[i]);
    for (unsigned i = 0; i < ARRAY_SIZE(bytes); i++) {
        event = read_reg(&s, 4);
        const char *names[] = {"fifo-n-down", "fifo-n-up", "fifo-b-down", "fifo-b-up"};
        sample(names[i], &s, event);
    }
    write_reg(&s, 2, 1); sample("fifo-w1c-complete", &s, 0);

    /* Mode 1 is only a compatibility control, not a 50 us timing claim. */
    reset(&s, 1); m5sw_keyboard_event(0xac); event = read_reg(&s, 4);
    sample("cfg1-legacy-popped", &s, event);
    m5sw_keyboard_event(0x2c); write_reg(&s, 2, 1);
    sample("cfg1-legacy-w1c-pending", &s, 0);
    event = read_reg(&s, 4); write_reg(&s, 2, 1);
    sample("cfg1-legacy-final", &s, event);
    return 0;
}
"""


def control_source(postimage):
    fixture = json.loads(FIXTURE.read_text())
    fragments = fixture["fragments"]
    for row in fragments.values():
        if digest(row["source"]) != row["sha256"]:
            raise AssertionError("Bounded original C fragment identity changed")
    before = patch_cases(False)
    if before != [fragments["read_case"]["source"], fragments["write_case"]["source"]]:
        raise AssertionError("Patch preimage does not match the actual post45 cases")
    read_case, write_case = patch_cases(postimage)
    if postimage:
        for name, value in [("read_case", read_case), ("write_case", write_case)]:
            if digest(value) != fixture["patched_fragments_sha256"][name]:
                raise AssertionError("Patch postimage case identity changed")
    return fixture["source"]["license_header"] + "\n" + C_STUBS + "\n" + \
        fragments["queue_globals"]["source"] + "\n" + fragments["queue_event"]["source"] + "\n" + \
        "static uint8_t read_reg(M5swI2CDev *s, uint8_t r) {\n    switch (s->model) {\n" + \
        read_case + "\n    }\n    return s->regs[r];\n}\n" + \
        "static int write_reg(M5swI2CDev *s, uint8_t r, uint8_t data) {\n    switch (s->model) {\n" + \
        write_case + "\n    }\n    s->regs[r]=data; s->ptr++; return 0;\n}\n" + C_CONTROLS


@unittest.skipUnless(shutil.which("cc"), "requires a C compiler")
class Tca8418InterruptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {}
        for postimage in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "controller.c"
                binary = Path(directory) / "controller"
                source.write_text(control_source(postimage))
                subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                                str(source), "-o", str(binary)], check=True, capture_output=True, text=True)
                result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
                cls.results[postimage] = {row["case"]: row for row in map(json.loads, result.stdout.splitlines())}

    def test_cfg0_last_read_keeps_irq_asserted_until_w1c(self):
        rows = self.results[True]
        for name, event in [("press-popped-awaiting-w1c", 0xac), ("release-popped-awaiting-w1c", 0x2c)]:
            row = rows[name]
            self.assertEqual((row["value"], row["count"], row["status"], row["gpio"]), (event, 0, 1, 0))
        row = rows["release-w1c-complete"]
        self.assertEqual((row["count"], row["status"], row["gpio"]), (0, 0, 1))

    def test_w1c_races_have_a_required_failing_original_control(self):
        old, new = self.results[False], self.results[True]
        self.assertEqual(old["press-popped-awaiting-w1c"]["gpio"], 1)
        for name in ["w1c-with-release-pending", "empty-status-new-event-w1c"]:
            self.assertEqual((old[name]["count"], old[name]["status"], old[name]["gpio"]), (1, 0, 0))
            self.assertEqual((new[name]["count"], new[name]["status"], new[name]["gpio"]), (1, 1, 0))

    def test_other_status_bits_zero_write_and_fifo_order(self):
        rows = self.results[True]
        self.assertEqual(rows["w1c-other-bits-preserved"]["status"], 0x1b)
        self.assertEqual(rows["non-key-w1c-preserves-key"]["status"], 0x17)
        row = rows["zero-write-retains-latch"]
        self.assertEqual((row["count"], row["status"], row["gpio"]), (0, 1, 0))
        names = ["fifo-n-down", "fifo-n-up", "fifo-b-down", "fifo-b-up"]
        self.assertEqual([rows[name]["value"] for name in names], [0xac, 0x2c, 0xa6, 0x26])
        self.assertEqual([rows[name]["count"] for name in names], [3, 2, 1, 0])
        self.assertTrue(all(rows[name]["gpio"] == 0 for name in names))
        self.assertEqual((rows["fifo-w1c-complete"]["status"], rows["fifo-w1c-complete"]["gpio"]), (0, 1))
        self.assertTrue(all(rows[name]["ptr"] == 1 for name in ["w1c-other-bits-preserved", "non-key-w1c-preserves-key"]))

    def test_cfg1_legacy_path_is_unchanged_without_timing_claim(self):
        for name in ["cfg1-legacy-popped", "cfg1-legacy-w1c-pending", "cfg1-legacy-final"]:
            self.assertEqual(self.results[False][name], self.results[True][name])

    def test_source_and_official_boundary_are_explicit(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["source"]["preimage_sha256"], "3858e5eacc0e7091327951c29df057f5e05c4e359b6a5cc7185739dafdda3d6e")
        self.assertIn("GPL-2.0-or-later", fixture["source"]["license_header"])
        self.assertEqual(fixture["official_evidence"]["document"], "SCPS215G")
        self.assertEqual(fixture["official_evidence"]["pages"], [28, 29, 30])
        self.assertIn("INT_CFG=1", fixture["scope"])


if __name__ == "__main__":
    unittest.main()

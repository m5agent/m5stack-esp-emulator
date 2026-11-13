"""Replay the committed classic pending-source register implementation."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0184-classic-interrupt-source-status.patch"


def added_function(name):
    text = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                     if line.startswith("+") and not line.startswith("+++"))
    name_at = text.index(name + "(")
    start = text.rfind("\n", 0, name_at) + 1
    opening = text.index("{", name_at)
    depth = 0
    for end in range(opening, len(text)):
        depth += (text[end] == "{") - (text[end] == "}")
        if depth == 0:
            return text[start:end + 1]
    raise AssertionError("unterminated committed function")


@unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
class ClassicSourceStatusTests(unittest.TestCase):
    def test_pending_banks_and_read_only_ack_boundary(self):
        source = r"""
#include <assert.h>
#include <stdint.h>
#define ESP32_INT_MATRIX_INPUTS 69
#define ESP32_INTMATRIX(p) ((Esp32IntMatrixState *)(p))
typedef uint64_t hwaddr;
typedef struct { uint8_t irq_level[69]; } Esp32IntMatrixState;
""" + added_function("esp32_intmatrix_status_read") + "\n" + added_function(
            "esp32_intmatrix_status_write") + r"""
int main(void) {
    Esp32IntMatrixState s = {0};
    for (unsigned bank = 0; bank < 6; ++bank)
        assert(esp32_intmatrix_status_read(&s, bank * 4, 4) == 0);
    s.irq_level[20] = 1; /* TG1 watchdog, shared level-5 dispatch */
    s.irq_level[31] = 1;
    s.irq_level[32] = 1;
    s.irq_level[63] = 1;
    s.irq_level[68] = 1; /* genuine cache illegal-access interrupt */
    for (unsigned cpu = 0; cpu < 2; ++cpu) {
        assert(esp32_intmatrix_status_read(&s, cpu * 12, 4) == 0x80100000u);
        assert(esp32_intmatrix_status_read(&s, cpu * 12 + 4, 4) == 0x80000001u);
        assert(esp32_intmatrix_status_read(&s, cpu * 12 + 8, 4) == 0x10u);
        esp32_intmatrix_status_write(&s, cpu * 12, 0xffffffff, 4);
        assert(esp32_intmatrix_status_read(&s, cpu * 12, 4) == 0x80100000u);
    }
    s.irq_level[20] = 0; /* acknowledge in the source controller */
    assert(esp32_intmatrix_status_read(&s, 0, 4) == 0x80000000u);
    assert(esp32_intmatrix_status_read(&s, 12, 4) == 0x80000000u);
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "status.c"
            binary = Path(tmp) / "status"
            src.write_text(source)
            subprocess.run(["cc", "-std=c11", "-fsanitize=address,undefined",
                            str(src), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_soc_maps_the_real_dport_window(self):
        text = PATCH.read_text()
        self.assertIn("dport_mem, 0xec", text)
        self.assertIn("6 * sizeof(uint32_t)", text)
        self.assertIn(".valid.min_access_size = 4", text)


if __name__ == "__main__":
    unittest.main()

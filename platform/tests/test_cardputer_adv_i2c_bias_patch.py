"""Actual GPIO C-logic regression for ADV's passive I2C board wiring.

No QEMU runtime, guest firmware or local .work cache is used by this test.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import (
    ROOT, bootstrap_stack, program, replay,
)


PATCH = "patches/qemu-m5stack-peripherals/0051-cardputer-adv-internal-i2c-pullups.patch"
BOARD = "hw/m5stopwatch/m5cardputeradv.c"


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class CardputerAdvI2CBiasPatchTests(unittest.TestCase):
    def test_nominal_detection_and_open_drain_ack_use_actual_controller(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            sources = replay(directory / "gpio")
            board_root = directory / "board"
            board_root.mkdir()
            subprocess.run(["git", "init", "-q", str(board_root)], check=True, capture_output=True)
            stack = list(bootstrap_stack())
            if PATCH not in stack:
                stack.append(PATCH)
            for patch in stack:
                subprocess.run(["git", "apply", "--include=" + BOARD, str(ROOT / patch)], cwd=board_root, check=True, capture_output=True)
            board = (board_root / BOARD).read_text()
            begin = board.index("    Esp32GpioState *gpio = esp32_gpio_get_controller(true);")
            end = board.index("\n    DeviceState *i2c0", begin)
            wiring = board[begin:end]
            self.assertEqual(wiring.count("esp32_gpio_add_board_bias"), 2)
            self.assertNotIn("esp32_gpio_set_input", wiring)
            self.assertNotIn("esp32_gpio_set_force", wiring)

            code, _ = program(sources)
            code = code.replace("int main(int argc, char **argv)", "int flashlight_existing_main(int argc, char **argv)")
            code += "\nstatic const char cardputer_adv_i2c_bias_owner;\nstatic void board_wiring(void) {\n" + wiring + "\n}\n"
            code += r'''
static unsigned probe(void) {
    const unsigned pins[] = {9, 8, 6, 5};
    unsigned result = 0;
    for (unsigned n = 0; n < 4; ++n) {
        pin = pins[n];
        iomux(1, (1u << 9) | (1u << 7)); /* input enable + internal pull-down */
    }
    for (unsigned n = 0; n < 4; ++n) {
        unsigned input = esp32_gpio_read(&controller, 0x3c, 4);
        result = (result << 1) | ((input >> pins[n]) & 1u);
    }
    return result;
}
int main(void) {
    init_controller();
    assert(probe() == 0); /* old glue cannot distinguish the ADV */
    board_wiring();
    assert(probe() == 12); /* G9/G8 high; unrelated G6/G5 remain down */
    for (unsigned n = 8; n <= 9; ++n) {
        pin = n;
        iomux(1, 1u << 9); /* restore normal input: board pull-up is known */
        Esp32GpioPadSnapshot pad;
        assert(esp32_gpio_pad_snapshot(&controller, n, &pad));
        assert(pad.known && pad.level && pad.bias_up_count == 1);
        esp32_gpio_set_open_drain(n, true);
        latch(true); output_enable(true);
        assert((esp32_gpio_read(&controller, 0x3c, 4) >> n & 1u) == 1);
        esp32_gpio_set_input(n, 0); /* real peripheral ACK/data */
        assert((esp32_gpio_read(&controller, 0x3c, 4) >> n & 1u) == 0);
        esp32_gpio_set_input(n, 1); /* release */
        assert((esp32_gpio_read(&controller, 0x3c, 4) >> n & 1u) == 1);
        latch(false);
        assert((esp32_gpio_read(&controller, 0x3c, 4) >> n & 1u) == 0); /* master low is not forced high */
    }
    puts("PASS Cardputer-ADV passive wiring and open-drain controller ACK");
    return 0;
}
'''
            path = directory / "cardputer.c"
            path.write_text(code)
            binary = directory / "cardputer"
            command = [shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable", "-Wno-sign-compare", "-DOLD_RUNTIME=0", str(path), "-o", str(binary)]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS Cardputer-ADV", result.stdout)


if __name__ == "__main__":
    unittest.main()

"""Compile the actual PI4IOE/FT slave logic with a board GPIO pad observer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


STUB = r"""
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BIT(n) (1U << (n))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define OBJECT_DECLARE_SIMPLE_TYPE(type, name)
#define OBJECT(o) (o)
#define object_property_add(...) ((void)0)
typedef struct { uint8_t address; } I2CSlave;
typedef void DeviceState;
typedef void Error;
enum i2c_event { I2C_START_SEND, I2C_START_RECV, I2C_FINISH };

static bool gpio3 = true;

static void esp32_gpio_force_line(int pin, int level)
{
    assert(pin == 3);
    gpio3 = !!level;
}
"""


ORACLE = r"""
static C6BoardI2CDev primary = {
    .parent_obj.address = 0x43,
    .model_name = "pi4ioe",
};
static C6BoardI2CDev secondary = {
    .parent_obj.address = 0x44,
    .model_name = "pi4ioe",
};
static C6BoardI2CDev touch = {
    .parent_obj.address = 0x38,
    .model_name = "ft5x06",
};

enum {
    CHIP_ID = 0x01,
    DIRECTION = 0x03,
    DEFAULT_INPUT = 0x09,
    INPUT_STATE = 0x0f,
    MASK = 0x11,
    STATUS = 0x13,
    A = 1,
    B = 2,
};

static void wr(C6BoardI2CDev *s, uint8_t address, uint8_t value)
{
    I2CSlave *slave = &s->parent_obj;
    assert(c6_i2c_event(slave, I2C_START_SEND) == 0);
    assert(c6_i2c_send(slave, address) == 0);
    assert(c6_i2c_send(slave, value) == 0);
    assert(c6_i2c_event(slave, I2C_FINISH) == 0);
}

static uint8_t rd(C6BoardI2CDev *s, uint8_t address)
{
    I2CSlave *slave = &s->parent_obj;
    assert(c6_i2c_event(slave, I2C_START_SEND) == 0);
    assert(c6_i2c_send(slave, address) == 0);
    assert(c6_i2c_event(slave, I2C_START_RECV) == 0);
    uint8_t value = c6_i2c_recv(slave);
    assert(c6_i2c_event(slave, I2C_FINISH) == 0);
    return value;
}

static void observed(const char *name, bool result)
{
    printf("%s %d\n", name, result);
}

int main(void)
{
    c6_i2c_realize(&primary, NULL);
    c6_i2c_realize(&secondary, NULL);
    c6_i2c_realize(&touch, NULL);
    esp32c6_ft_touch_set(0, 0, 0);
    assert(rd(&primary, CHIP_ID) == 0xa2);
    assert(rd(&secondary, CHIP_ID) == 0xa2);
    assert(rd(&primary, DIRECTION) == 0);
    assert(rd(&primary, DEFAULT_INPUT) == 0);
    assert(rd(&primary, MASK) == 0);
    assert((rd(&primary, INPUT_STATE) & 3) == 3);

    wr(&primary, DEFAULT_INPUT, A | B);
    rd(&primary, STATUS);
    esp32c6_pi4ioe_button_set(1, true);
    observed("b_press_pulls_pad_low", !gpio3);
    uint8_t actual_input = rd(&primary, INPUT_STATE);
    observed("live_input_read_preserves_pending_pad", (actual_input & 3) == A && !gpio3);
    uint8_t status = rd(&primary, STATUS);
    observed("status_read_latches_b_and_releases_pad", status == B && gpio3);
    esp32c6_pi4ioe_button_set(1, true);
    observed("repeat_level_does_not_retrigger", rd(&primary, STATUS) == 0);
    esp32c6_pi4ioe_button_set(1, false);
    observed("return_to_default_does_not_latch", gpio3 && rd(&primary, STATUS) == 0);
    esp32c6_pi4ioe_button_set(1, true);
    bool second_press_asserted = !gpio3;
    status = rd(&primary, STATUS);
    observed("second_away_transition_rearms", second_press_asserted && status == B);
    esp32c6_pi4ioe_button_set(1, false);
    rd(&primary, STATUS);

    wr(&primary, MASK, B);
    esp32c6_pi4ioe_button_set(1, true);
    bool masked_high = gpio3;
    wr(&primary, MASK, 0);
    bool unmasked_low = !gpio3;
    wr(&primary, MASK, B);
    bool remasked_high = gpio3;
    status = rd(&primary, STATUS);
    observed("mask_gates_existing_status", masked_high && unmasked_low && remasked_high && status == B);
    esp32c6_pi4ioe_button_set(1, false);
    rd(&primary, STATUS);
    wr(&primary, MASK, 0);

    wr(&primary, DIRECTION, B);
    esp32c6_pi4ioe_button_set(1, true);
    observed("output_excludes_input_and_interrupt", !(rd(&primary, INPUT_STATE) & B)
             && rd(&primary, STATUS) == 0 && gpio3);
    esp32c6_pi4ioe_button_set(1, false);
    wr(&primary, DIRECTION, 0);
    rd(&primary, STATUS);

    wr(&primary, DEFAULT_INPUT, B);
    rd(&primary, STATUS);
    esp32c6_pi4ioe_button_set(0, true);
    observed("default_low_press_does_not_latch", gpio3 && rd(&primary, STATUS) == 0);
    esp32c6_pi4ioe_button_set(0, false);
    bool release_asserted = !gpio3;
    status = rd(&primary, STATUS);
    observed("default_low_release_does_latch", release_asserted && status == A);
    wr(&primary, DEFAULT_INPUT, A | B);
    rd(&primary, STATUS);

    esp32c6_pi4ioe_button_set(1, true);
    esp32c6_ft_touch_set(1, 55, 68);
    observed("touch_and_expander_share_active_low_pad", !gpio3 && rd(&touch, 0x02) == 1);
    status = rd(&primary, STATUS);
    observed("reading_pi_cannot_release_touch", status == B && !gpio3);
    esp32c6_pi4ioe_button_set(1, false);
    rd(&primary, STATUS);
    esp32c6_ft_touch_set(0, 55, 68);
    observed("released_sources_return_high", gpio3 && rd(&touch, 0x02) == 0);

    esp32c6_pi4ioe_button_set(0, true);
    esp32c6_ft_touch_set(1, 55, 68);
    esp32c6_ft_touch_set(0, 55, 68);
    observed("touch_release_cannot_release_pi", !gpio3 && rd(&primary, STATUS) == A);
    rd(&primary, STATUS);
    esp32c6_pi4ioe_button_set(0, false);
    rd(&primary, STATUS);

    /* Simulate a second-expander pending bit without inventing a board input. */
    secondary.regs[STATUS] = B;
    wr(&secondary, MASK, 0);
    bool second_isolated = gpio3;
    status = rd(&secondary, STATUS);
    observed("secondary_pending_has_no_gpio3_connection", second_isolated && status == B && gpio3);

    esp32c6_ft_touch_set(1, 55, 68);
    wr(&primary, CHIP_ID, 1);
    observed("expander_reset_cannot_release_touch", !gpio3 && rd(&touch, 0x02) == 1);
    esp32c6_ft_touch_set(0, 55, 68);
    observed("reset_clears_pending_and_defaults", gpio3 && rd(&primary, STATUS) == 0
             && rd(&primary, DIRECTION) == 0 && rd(&primary, DEFAULT_INPUT) == 0 && rd(&primary, MASK) == 0);
    return 0;
}
"""


def compile_and_run(source, cc):
    controller = source / "hw/misc/esp32c6_board_i2c.c"
    contents = controller.read_text()
    # Preserve the actual file's function order. QOM declarations after realize
    # are outside these I2C callbacks and GPIO-pad assertions.
    core = contents[contents.index("enum {"):contents.index("static void c6_prop_get_i64(")]
    realize = contents[contents.index("static void c6_i2c_realize("):
                       contents.index("static Property c6_i2c_props[]")]
    with tempfile.TemporaryDirectory(prefix="nesso-pi4ioe-c-") as out:
        c_file = Path(out) / "controller.c"
        binary = c_file.with_suffix("")
        c_file.write_text(STUB + core + realize + ORACLE)
        subprocess.run([cc, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-Wno-unused-variable",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(c_file), "-o", str(binary), "-lm"], check=True, timeout=30)
        process = subprocess.run([str(binary)], check=True, capture_output=True,
                                 text=True, timeout=10)
    observations = {name: bool(int(value))
                    for name, value in (line.split() for line in process.stdout.splitlines())}
    return hashlib.sha256(contents.encode()).hexdigest(), observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    digest, results = compile_and_run(args.source, args.cc)
    assert len(results) == 17
    failures = {name for name, passed in results.items() if not passed}
    if args.baseline:
        assert {"b_press_pulls_pad_low", "return_to_default_does_not_latch",
                "mask_gates_existing_status", "reading_pi_cannot_release_touch",
                "touch_release_cannot_release_pi"} <= failures, failures
    else:
        assert not failures, failures
    print(json.dumps({"status": "PASS", "baseline": args.baseline,
                      "controller_source_sha256": digest, "observations": results}, indent=2))


if __name__ == "__main__":
    main()

"""Run actual GPIO + Nesso board C callbacks; this is not a guest ISR test."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


STUB = r"""
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define BIT(n) (1U << (n))
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define HWADDR_PRIx PRIx64
#define A_GPIO_STRAP 0x38
#define ESP32_GPIO(o) ((Esp32GpioState *)(o))
#define OBJECT_DECLARE_SIMPLE_TYPE(type, name)
#define OBJECT(o) (o)
#define object_property_add(...) ((void)0)
#define DEVICE_LITTLE_ENDIAN 0
typedef uint64_t hwaddr;
typedef void Object;
typedef void DeviceState;
typedef void Error;
typedef int ResetType;
typedef struct { uint8_t address; } I2CSlave;
enum i2c_event { I2C_START_SEND, I2C_START_RECV, I2C_FINISH };
typedef struct { int irq; uint32_t strap_mode; uint32_t irq_pin_count; } Esp32GpioState;
typedef void (*esp32_gpio_out_cb)(void *, int, int);
typedef struct {
    uint64_t (*read)(void *, hwaddr, unsigned);
    void (*write)(void *, hwaddr, uint64_t, unsigned);
    int endianness;
} MemoryRegionOps;
static bool irq_level;
static unsigned irq_transitions;
static void qemu_set_irq(int irq, int level)
{
    assert(irq == 30);
    irq_transitions += irq_level != !!level;
    irq_level = !!level;
}
static void error_setg(Error **errp, const char *text)
{
    (void)errp;
    fprintf(stderr, "unexpected realize failure: %s\n", text);
    abort();
}
"""


ORACLE = r"""
static Esp32GpioState gpio = { .irq = 30, .irq_pin_count = 31 };
static C6BoardI2CDev primary = { .parent_obj.address = 0x43, .model_name = "pi4ioe" };
static C6BoardI2CDev secondary = { .parent_obj.address = 0x44, .model_name = "pi4ioe" };
static C6BoardI2CDev touch = { .parent_obj.address = 0x38, .model_name = "ft5x06" };
static unsigned listener_calls;
static void listener(void *opaque, int pin, int level)
{
    (void)opaque;
    assert(pin == 9);
    listener_calls++;
}
static void out(const char *name, bool value) { printf("%s %d\n", name, value); }
static uint32_t r(unsigned addr) { return esp32_gpio_read(&gpio, addr, 4); }
static void w(unsigned addr, uint32_t value) { esp32_gpio_write(&gpio, addr, value, 4); }
static void cfg(unsigned pin, unsigned type, unsigned routes)
{
    w(0x74 + 4 * pin, (type << 7) | (routes << 13));
}
static void clear(void) { w(0x4c, UINT32_MAX); }
static void fresh(void)
{
    memset(g_regs, 0, sizeof(g_regs));
    memset(g_output_signals, 0, sizeof(g_output_signals));
    memset(g_listeners, 0, sizeof(g_listeners));
    g_ext_in = ~0ULL;
    g_open_drain = g_force_mask = g_force_level = 0;
    irq_level = false;
    irq_transitions = 0;
}
static void wr(C6BoardI2CDev *s, uint8_t reg, uint8_t value)
{
    I2CSlave *p = &s->parent_obj;
    assert(c6_i2c_event(p, I2C_START_SEND) == 0);
    assert(c6_i2c_send(p, reg) == 0);
    assert(c6_i2c_send(p, value) == 0);
    assert(c6_i2c_event(p, I2C_FINISH) == 0);
}
static uint8_t rd(C6BoardI2CDev *s, uint8_t reg)
{
    I2CSlave *p = &s->parent_obj;
    assert(c6_i2c_event(p, I2C_START_SEND) == 0);
    assert(c6_i2c_send(p, reg) == 0);
    assert(c6_i2c_event(p, I2C_START_RECV) == 0);
    uint8_t value = c6_i2c_recv(p);
    assert(c6_i2c_event(p, I2C_FINISH) == 0);
    return value;
}
int main(void)
{
    const uint32_t b = BIT(9);
    esp32_gpio_realize(&gpio, NULL);
    fresh();
    cfg(9, 2, 1);
    out("configure_edge_does_not_invent_event", r(0x44) == 0 && !irq_level);
    esp32_gpio_set_input(9, 0);
    out("falling_raw_and_cpu_pending", r(0x44) == b && r(0x5c) == b && irq_level);
    esp32_gpio_set_input(9, 0);
    out("repeat_level_has_no_extra_irq_transition", irq_transitions == 1);
    clear();
    out("w1tc_acknowledges_edge", r(0x44) == 0 && r(0x5c) == 0 && !irq_level);
    esp32_gpio_set_input(9, 1);
    out("falling_ignores_rising", r(0x44) == 0 && !irq_level);
    cfg(9, 1, 1);
    esp32_gpio_set_input(9, 0);
    out("rising_ignores_falling", r(0x44) == 0 && !irq_level);
    esp32_gpio_set_input(9, 1);
    out("rising_routes_pending", r(0x44) == b && r(0x5c) == b && irq_level);
    clear();
    cfg(9, 3, 1);
    esp32_gpio_set_input(9, 0);
    bool first = irq_level && r(0x44) == b;
    clear();
    esp32_gpio_set_input(9, 1);
    out("any_edge_captures_both_directions", first && irq_level && r(0x44) == b);

    fresh();
    cfg(9, 2, 0);
    esp32_gpio_set_input(9, 0);
    out("route_mask_preserves_raw_capture", r(0x44) == b && r(0x5c) == 0 && !irq_level);
    cfg(9, 2, 1);
    out("enable_routes_old_pending", r(0x44) == b && r(0x5c) == b && irq_level);
    cfg(9, 2, 0);
    out("disable_preserves_pending", r(0x44) == b && r(0x5c) == 0 && !irq_level);
    cfg(9, 2, 2);
    out("nmi_mask_is_not_normal_cpu_route", r(0x60) == b && r(0x5c) == 0 && !irq_level);
    cfg(9, 0, 1);
    out("type_change_preserves_latched_event", r(0x44) == b && irq_level);
    clear();
    esp32_gpio_set_input(9, 1);
    esp32_gpio_set_input(9, 0);
    out("disabled_type_has_no_new_event", r(0x44) == 0 && !irq_level);
    cfg(9, 1, 1);
    out("type_change_does_not_synthesize_edge", r(0x44) == 0 && !irq_level);

    fresh();
    cfg(9, 4, 1);
    esp32_gpio_set_input(9, 0);
    out("low_level_asserts", r(0x44) == b && irq_level);
    clear();
    out("w1tc_active_low_reasserts", r(0x44) == b && r(0x5c) == b && irq_level);
    esp32_gpio_set_input(9, 1);
    out("inactive_level_keeps_latch_until_ack", r(0x44) == b && irq_level);
    clear();
    out("inactive_level_can_be_acknowledged", r(0x44) == 0 && !irq_level);
    cfg(9, 5, 1);
    out("type_change_to_active_high_asserts", r(0x44) == b && irq_level);
    clear();
    out("w1tc_active_high_reasserts", r(0x44) == b && irq_level);
    cfg(9, 2, 1);
    clear();
    out("type_change_to_edge_allows_ack", r(0x44) == 0 && !irq_level);

    fresh();
    cfg(9, 0, 1);
    cfg(10, 0, 1);
    w(0x48, b | BIT(10));
    out("w1ts_sets_multiple_pending", r(0x44) == (b | BIT(10)) && r(0x5c) == (b | BIT(10)) && irq_level);
    w(0x4c, b);
    out("partial_ack_keeps_other_source_asserted", r(0x44) == BIT(10) && irq_level);
    w(0x5c, UINT32_MAX);
    out("cpu_view_is_read_only", r(0x5c) == BIT(10));
    out("write_alias_reads_are_zero", r(0x48) == 0 && r(0x4c) == 0);
    clear();
    out("last_ack_deasserts_irq", r(0x44) == 0 && !irq_level);
    cfg(31, 3, 1);
    w(0x48, BIT(31));
    w(0x54, UINT32_MAX);
    esp32_gpio_set_input(31, 0);
    out("c6_nonexistent_pins_do_not_latch", r(0x44) == 0 && r(0x50) == 0 && !irq_level);

    fresh();
    cfg(9, 3, 1);
    esp32_gpio_add_out_listener(9, listener, NULL);
    w(0x24, b);
    out("gpio_output_transition_reaches_irq_and_listener", r(0x44) == b && irq_level && listener_calls == 1);
    clear();
    w(0x08, b);
    out("gpio_output_set_reaches_irq_and_listener", r(0x44) == b && irq_level && listener_calls == 2);
    clear();
    esp32_gpio_set_input(9, 0);
    out("push_pull_output_masks_external_low", r(0x44) == 0 && esp32_gpio_get_line(9) == 1);
    esp32_gpio_set_open_drain(9, true);
    out("open_drain_resolution_reaches_irq", r(0x44) == b && irq_level && esp32_gpio_get_line(9) == 0);
    clear();
    esp32_gpio_force_line(9, 1);
    out("board_force_line_reaches_irq", r(0x44) == b && irq_level && esp32_gpio_get_line(9) == 1);

    fresh();
    c6_i2c_realize(&primary, NULL);
    c6_i2c_realize(&secondary, NULL);
    c6_i2c_realize(&touch, NULL);
    esp32c6_ft_touch_set(0, 0, 0);
    wr(&primary, 0x09, 3);
    rd(&primary, 0x13);
    cfg(3, 4, 1);
    esp32c6_pi4ioe_button_set(1, true);
    out("pi4ioe_source_flows_through_gpio_controller", esp32_gpio_get_line(3) == 0 && r(0x44) == BIT(3) && r(0x5c) == BIT(3) && irq_level);
    esp32c6_ft_touch_set(1, 55, 68);
    bool pending = rd(&primary, 0x13) == 2;
    clear();
    out("pi_ack_cannot_release_touch_irq", pending && esp32_gpio_get_line(3) == 0 && r(0x44) == BIT(3) && irq_level);
    esp32c6_pi4ioe_button_set(1, false);
    esp32c6_ft_touch_set(0, 55, 68);
    clear();
    out("all_board_sources_released_then_ack_clears", esp32_gpio_get_line(3) == 1 && r(0x44) == 0 && !irq_level);
    esp32c6_pi4ioe_button_set(0, true);
    esp32c6_ft_touch_set(1, 55, 68);
    esp32c6_ft_touch_set(0, 55, 68);
    clear();
    out("touch_release_cannot_release_pi_irq", esp32_gpio_get_line(3) == 0 && irq_level && r(0x44) == BIT(3));
    esp32_gpio_reset_hold(&gpio, 0);
    out("soc_reset_clears_irq_not_external_source", !irq_level && r(0x44) == 0 && r(0x5c) == 0 && (r(0x80) & ((7U << 7) | (31U << 13))) == 0 && esp32_gpio_get_line(3) == 0);
    cfg(3, 4, 1);
    out("reconfigure_level_after_reset_sees_held_source", irq_level && r(0x44) == BIT(3));
    pending = rd(&primary, 0x13) == 1;
    clear();
    out("source_ack_after_reset_releases_controller", pending && esp32_gpio_get_line(3) == 1 && !irq_level && r(0x44) == 0);
    esp32c6_pi4ioe_button_set(0, false);
    esp32c6_ft_touch_set(1, 55, 68);
    wr(&primary, 0x01, 1);
    clear();
    out("expander_reset_preserves_touch_controller_irq", esp32_gpio_get_line(3) == 0 && irq_level && r(0x44) == BIT(3));
    esp32c6_ft_touch_set(0, 55, 68);
    clear();
    out("shared_pad_final_cleanup", esp32_gpio_get_line(3) == 1 && r(0x44) == 0 && !irq_level);
#if GPIO_IRQ_HAS_UNREALIZE
    esp32_gpio_unrealize(&gpio);
#endif
    gpio.irq_pin_count = 0;
    fresh();
    esp32_gpio_realize(&gpio, NULL);
    cfg(9, 2, 1);
    esp32_gpio_set_input(9, 0);
    out("opt_out_preserves_pad_without_irq_capture", esp32_gpio_get_line(9) == 0 && r(0x44) == 0 && !irq_level);
    w(0x48, b);
    out("opt_out_preserves_legacy_status_storage", r(0x44) == b && r(0x5c) == 0 && !irq_level);
    esp32_gpio_reset_hold(&gpio, 0);
    out("opt_out_preserves_legacy_reset_behavior", r(0x44) == b && r(0x80 + 6 * 4) == ((2U << 7) | BIT(13)) && !irq_level);
    return 0;
}
"""


def compile_and_run(source, cc):
    names = ("hw/gpio/esp32_gpio.c", "hw/misc/esp32c6_board_i2c.c")
    gpio, board = [(source / name).read_text() for name in names]
    gpio_core = gpio[gpio.index("#define GPIO_NPINS"):gpio.index("static void esp32_gpio_init(")]
    board_core = board[board.index("enum {"):board.index("static void c6_prop_get_i64(")]
    board_realize = board[board.index("static void c6_i2c_realize("):board.index("static Property c6_i2c_props[]")]
    with tempfile.TemporaryDirectory(prefix="c6-gpio-irq-c-") as out:
        c_file = Path(out) / "controller.c"
        binary = c_file.with_suffix("")
        features = "#define GPIO_IRQ_HAS_UNREALIZE %d\n" % ("static void esp32_gpio_unrealize(" in gpio)
        c_file.write_text(features + STUB + gpio_core + board_core + board_realize + ORACLE)
        subprocess.run([cc, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function",
                        "-Wno-sign-compare", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(c_file), "-o", str(binary), "-lm"], check=True, timeout=30)
        result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=10)
    observations = {name: bool(int(value)) for name, value in
                    (line.split() for line in result.stdout.splitlines())}
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names}
    return hashes, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    hashes, results = compile_and_run(args.source, args.cc)
    failures = {name for name, passed in results.items() if not passed}
    assert len(results) == 45, len(results)
    if args.baseline:
        assert {"falling_raw_and_cpu_pending", "enable_routes_old_pending",
                "w1tc_active_low_reasserts", "pi4ioe_source_flows_through_gpio_controller",
                "soc_reset_clears_irq_not_external_source"} <= failures, failures
        assert results["shared_pad_final_cleanup"]
    else:
        assert not failures, failures
    print(json.dumps({"status": "PASS", "kind": "actual-C host control; not guest ISR",
                      "baseline": args.baseline, "source_sha256": hashes,
                      "observations": results}, indent=2))


if __name__ == "__main__":
    main()

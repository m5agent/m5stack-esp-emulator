"""GPIO-route observer contracts; no QEMU process, firmware or Device API."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/qemu-m5stack-peripherals/0038-unit-pwm-route-refresh.patch'


def sections():
    return {part.splitlines()[0].split(' b/', 1)[1]: part
            for part in PATCH.read_text().split('diff --git ')[1:]}


class UnitPwmRoutePatchTests(unittest.TestCase):
    def test_changes_only_the_controller_route_observer_and_layout_filter(self):
        parts = sections()
        self.assertEqual(set(parts), {
            'hw/gpio/esp32_gpio.c', 'hw/misc/esp32_ledc.c',
            'hw/m5stopwatch/m5_unit_gpio.c', 'include/hw/misc/esp32_ledc.h'})
        endpoint = parts['hw/m5stopwatch/m5_unit_gpio.c']
        self.assertIn('+        if (g->s3 == s3 &&', endpoint)
        self.assertEqual(sum(line.startswith('@@ ') for line in endpoint.splitlines()), 1)
        # The patch does not change either MMIO path or the original QOM gate.
        all_added = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        for forbidden in ('esp32_ledc_write(', 'esp32_ledc_read(', 'num_get(',
                          'led_set_intensity(', 'channel_duty_reg[', 'timer_conf_reg['):
            self.assertNotIn(forbidden, all_added)

    def test_realized_instances_are_layout_matched_and_removed_on_unrealize(self):
        part = sections()['hw/misc/esp32_ledc.c']
        self.assertIn('if (s->esp32s3_layout == esp32s3_layout)', part)
        self.assertIn('ledc_observe(s);', part)
        self.assertIn('QLIST_INSERT_HEAD(&ledc_devices, s, route_observer_next)', part)
        self.assertIn('QLIST_REMOVE(s, route_observer_next)', part)
        self.assertIn('dc->unrealize = esp32_ledc_unrealize', part)

    def test_patch_is_appended_after_readback_and_docs_keep_candidate_boundary(self):
        tree = ast.parse((ROOT / 'scripts/bootstrap-unit-runtime.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'PATCHES' for t in n.targets))
        patches = ast.literal_eval(node.value)
        self.assertEqual(patches[-2:], (
            'patches/qemu-m5stack-peripherals/0037-s3-ledc-duty-readback.patch',
            PATCH.relative_to(ROOT).as_posix()))
        self.assertEqual(len(patches), len(set(patches)))
        for name in ('patches/qemu-unit-runtime/README.md', 'patches/qemu-m5stack-peripherals/README.md'):
            text = (ROOT / name).read_text()
            self.assertIn(PATCH.name, text)
            self.assertIn('OPEN', text)
            self.assertIn('fade', text)
            self.assertIn('candidate', text)

    @unittest.skipUnless(shutil.which('cc'), 'C compiler unavailable')
    def test_actual_route_hunk_notifies_only_for_changed_in_range_signal_bits(self):
        # Compile the actual postimage hunk around the route register store.
        # Only the outer original MMIO size guard and callback spy are stubs.
        part = sections()['hw/gpio/esp32_gpio.c']
        hunk = next(h for h in re.split(r'^@@[^\n]*\n', part, flags=re.M)
                    if 'uint32_t previous' in h)
        postimage = ''.join(line[1:] + '\n' for line in hunk.splitlines()
                            if line.startswith((' ', '+')) and not line.startswith('+++'))
        code = postimage[postimage.index('            uint32_t previous'):postimage.index('            /*')]
        source = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
static uint32_t g_regs[512];
static bool g_gpio_s3;
static unsigned calls;
static void esp32_ledc_gpio_route_changed(bool s3) { assert(s3 == g_gpio_s3); calls++; }
static void write_route(unsigned addr, uint64_t value) {
    if (addr < sizeof(g_regs)) {
''' + code + '''
    }
}
int main(void) {
    for (unsigned layout = 0; layout < 2; layout++) {
        g_gpio_s3 = layout;
        unsigned base = layout ? 0x554 : 0x530, pins = layout ? 49 : 40;
        for (unsigned pin = 0; pin < pins; pin++) {
            unsigned address = base + pin * 4;
            g_regs[address / 4] = 0;
            unsigned before = calls;
            write_route(address, 73); assert(calls == before + 1);
            write_route(address, 73); assert(calls == before + 1);
            write_route(address, 73 | (1u << 10)); assert(calls == before + 1);
            write_route(address, 73 | (1u << 9)); assert(calls == before + 2);
            write_route(address, 74); assert(calls == before + 3);
        }
        unsigned before = calls;
        write_route(base - 4, 123); write_route(base + pins * 4, 123);
        write_route(0x900, 123); assert(calls == before);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'route.c'
            binary = path.with_suffix('')
            path.write_text(source)
            subprocess.run([shutil.which('cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(path), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()

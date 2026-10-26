"""Scoped patch contracts; the C fragment check never runs QEMU or firmware."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/qemu-m5stack-peripherals/0037-s3-ledc-duty-readback.patch'


def added_c():
    return ''.join(line[1:] for line in PATCH.read_text().splitlines(keepends=True)
                   if line.startswith('+') and not line.startswith('+++'))


class LedcReadbackPatchTests(unittest.TestCase):
    def test_patch_only_adds_the_s3_read_branch(self):
        text = PATCH.read_text()
        self.assertEqual(re.findall(r'^diff --git (.+)$', text, re.M),
                         ['a/hw/misc/esp32_ledc.c b/hw/misc/esp32_ledc.c'])
        self.assertEqual(sum(line.startswith('@@ ') for line in text.splitlines()), 1)
        self.assertFalse(any(line.startswith('-') and not line.startswith('---') for line in text.splitlines()))
        code = added_c()
        self.assertIn('s->esp32s3_layout && addr < 0xa0', code)
        self.assertIn('addr % 0x14', code)
        self.assertIn('offset == 8 || offset == 16', code)
        self.assertIn('s->channel_duty_reg[addr / 0x14] & 0x7ffff', code)
        for forbidden in ('channel_conf0_reg', 'timer_conf_reg', 'ledc_observe', 'sig_out_en'):
            self.assertNotIn(forbidden, code)

    def test_bootstrap_appends_the_patch_after_classic_compatibility(self):
        tree = ast.parse((ROOT / 'scripts/bootstrap-unit-runtime.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'PATCHES' for t in n.targets))
        patches = ast.literal_eval(node.value)
        position = patches.index(PATCH.relative_to(ROOT).as_posix())
        self.assertEqual(patches[position - 1:position + 1], (
            'patches/qemu-m5stack-peripherals/0036-core2-soft-i2c-handoff-compat.patch',
            PATCH.relative_to(ROOT).as_posix()))
        self.assertEqual(len(patches), len(set(patches)))

    def test_documentation_keeps_immediate_model_and_current_cycle_gap_visible(self):
        for name in ('patches/qemu-unit-runtime/README.md', 'patches/qemu-m5stack-peripherals/README.md'):
            text = (ROOT / name).read_text()
            self.assertIn(PATCH.name, text)
            self.assertIn('settled set+update', text)
            self.assertIn('current-cycle', text)
            self.assertIn('fade', text)

    @unittest.skipUnless(shutil.which('cc'), 'C compiler unavailable for isolated read-branch contract')
    def test_actual_added_c_masks_all_eight_channels_and_does_not_intercept_classic_or_other_addresses(self):
        # Compile the actual added patch lines, rather than a Python copy of
        # the address arithmetic. The sentinel is the untouched legacy path.
        harness = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef struct { bool esp32s3_layout; uint32_t channel_duty_reg[16]; } State;
static uint64_t read_added(State *s, uint64_t addr) {
''' + added_c() + '''
    return UINT64_C(0xfeedface);
}
int main(void) {
    State state = {0};
    const uint32_t values[] = {0, 1, 0x12345, 0x7ffff, 0x80000, 0xffffffff};
    state.esp32s3_layout = true;
    for (unsigned ch = 0; ch < 8; ch++) {
        for (unsigned n = 0; n < sizeof(values) / sizeof(values[0]); n++) {
            state.channel_duty_reg[ch] = values[n];
            assert(read_added(&state, ch * 20 + 8) == (values[n] & UINT32_C(524287)));
            assert(read_added(&state, ch * 20 + 16) == (values[n] & UINT32_C(524287)));
        }
        for (unsigned off = 0; off < 20; off++) {
            if (off != 8 && off != 16) {
                assert(read_added(&state, ch * 20 + off) == UINT64_C(0xfeedface));
            }
        }
    }
    for (unsigned addr = 160; addr < 512; addr++) {
        assert(read_added(&state, addr) == UINT64_C(0xfeedface));
    }
    state.esp32s3_layout = false;
    for (unsigned addr = 0; addr < 512; addr++) {
        assert(read_added(&state, addr) == UINT64_C(0xfeedface));
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'readback.c'
            binary = Path(temporary) / 'readback'
            source.write_text(harness)
            subprocess.run([shutil.which('cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()

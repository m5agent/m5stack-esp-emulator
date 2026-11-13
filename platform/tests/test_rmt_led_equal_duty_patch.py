"""Replay the shipped LED endpoint and decode original FastLED pulse words."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_classic_atom_rmt_patch import ROUTE_STUBS, ROUTE_CONTROLS
from test_bootstrap_unit_runtime_recipe import recipe
from test_unit_flashlight_cold_pad_patch import bootstrap_stack
from test_spi_panel_read_cursor_patch import function

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'hw/m5stopwatch/m5_unit_gpio.c'
PATCH = 'patches/qemu-m5stack-peripherals/0191-rmt-led-equal-duty-symbol.patch'

CONTROLS = r'''
static void original_words(uint32_t *symbols, bool low_first) {
    for (unsigned led=0;led<25;led++) {
        uint32_t rgb=(0x123456U+led*0x050307U)&0xffffff;
        uint32_t grb=((rgb&0xff00)<<8)|((rgb>>8)&0xff00)|(rgb&0xff);
        for (unsigned bit=0;bit<24;bit++) {
            uint32_t word=grb&(1U<<(23-bit))?0x00188018:0x0024800c;
            symbols[led*24+bit]=low_first?(word<<16)|(word>>16):word;
        }
    }
}
static void check_colors(GPIOUnit *g) {
    for(unsigned led=0;led<g->leds;led++)
        assert(g->rgb[led]==(OLD_DECODER?0:(0x123456U+led*0x050307U)&0xffffff));
}
static void equal_duty(void) {
    M5Unit cu={"key",27,0},su={"rgb",35,0};
    GPIOUnit classic={.s3=false,.unit=&cu,.leds=25},s3={.s3=true,.unit=&su,.leds=3};
    classic.next=&s3;gpio_units=&classic;classic_route=87;s3_route=81;
    uint32_t symbols[600];
    for(unsigned low_first=0;low_first<2;low_first++) {
        original_words(symbols,low_first);
        m5_unit_rmt_tx_routed(0,symbols,600,40000000,false);
        m5_unit_rmt_tx(0,symbols,72,40000000);
        check_colors(&classic);check_colors(&s3);
    }
    assert(classic.frames==2 && s3.frames==2);
    if(OLD_DECODER) {puts("original-12-36-and-24-24-all-black-negative PASS");return;}
    puts("original-25-LED-and-S3-both-level-orders-exact-RGB PASS");
    uint32_t expected[25];memcpy(expected,classic.rgb,sizeof(expected));
    for(unsigned mode=0;mode<7;mode++) {
        original_words(symbols,false);
        double hz=40000000;
        if(mode==0) symbols[599]&=~0x7fffU;
        if(mode==1) symbols[599]&=~(0x7fffU<<16);
        if(mode==2) symbols[599]|=BIT(31);
        if(mode==3) symbols[599]&=~BIT(15);
        if(mode==4) hz=0;
        if(mode==5) hz=NAN;
        if(mode==6) hz=-1;
        m5_unit_rmt_tx_routed(0,symbols,600,hz,false);
        assert(classic.frames==2 && classic.incomplete_frames==mode+1);
        assert(!memcmp(expected,classic.rgb,sizeof(expected)));
    }
    puts("zero-phase-same-level-and-invalid-clock-atomic-negative PASS");
}
'''


@unittest.skipUnless(shutil.which('cc'), 'requires a C compiler')
class RmtLedEqualDutyTests(unittest.TestCase):
    def test_replayed_original_words_old_negative_new_positive_and_invalid(self):
        fixture = json.loads((ROOT / 'platform/tests/fixtures/classic_atom_rmt_route.json').read_text())
        old = fixture['fragment']
        self.assertEqual(hashlib.sha256(old.encode()).hexdigest(), fixture['fragment_sha256'])
        self.assertIn(PATCH, recipe())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            target = root / SOURCE
            for patch in bootstrap_stack(full=True):
                if patch == PATCH:
                    break
                subprocess.run(['git', 'apply', '--include=' + SOURCE, str(ROOT / patch)],
                               cwd=root, check=True, capture_output=True)
            before = target.read_text()
            self.assertIn(old, before)
            for flags in (['--check'], []):
                subprocess.run(['git', 'apply', *flags, str(ROOT / PATCH)],
                               cwd=root, check=True, capture_output=True)
            current = '\n\n'.join(function(target.read_text(), name) for name in (
                'm5_unit_rmt_tx_routed', 'm5_unit_rmt_tx', 'm5_unit_gpio_rgb_value'))
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / PATCH)],
                           cwd=root, check=True, capture_output=True)
            self.assertEqual(target.read_text(), before)
            for prior, model in ((True, old), (False, current)):
                source = root / 'control.c'
                binary = root / 'control'
                existing = ROUTE_CONTROLS.replace('int main(void)', 'static int existing_controls(void)')
                source.write_text('#define OLD_DECODER ' + str(int(prior)) + '\n' +
                                  ROUTE_STUBS + model + existing + CONTROLS +
                                  '\nint main(void){existing_controls();equal_duty();return 0;}\n')
                compiled = subprocess.run([shutil.which('cc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-function', '-fsanitize=address,undefined',
                    str(source), '-lm', '-o', str(binary)], capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                ran = subprocess.run([str(binary)], capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertIn('short-negative PASS', ran.stdout)
                self.assertIn('all-black-negative PASS' if prior else 'invalid-clock-atomic-negative PASS', ran.stdout)


if __name__ == '__main__':
    unittest.main()

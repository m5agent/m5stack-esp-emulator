"""Replay actual GC0308 SCCB helpers against page/identity/reset boundaries.

The preimage uses its actual generic read/write fallback. This C-only test
requires no .work files or sensor runtime and does not prove guest capture or
physical sensor behavior.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0057-gc0308-sccb-register-pages.patch"
SOURCE = "hw/m5stopwatch/m5sw_i2c_devs.c"


def function(source, name):
    match = re.search(r"static (?:void|uint8_t|int) " + name + r"\(", source)
    if match is None:
        raise AssertionError("actual SCCB function missing: " + name)
    start = source.index("{", match.start())
    depth = 0
    for index in range(start, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated actual SCCB function")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { unsigned unused; } I2CSlave;
'''
MAIN = r'''
int main(int argc,char **argv) {
    assert(argc==2);M5swI2CDev s={0};s.regs[0]=0x9b;
    switch(atoi(argv[1])) {
    case 0: /* Official defaults write page-1 register zero before re-probe. */
        write_reg(&s,0xfe,1);write_reg(&s,0,0xf5);
        assert(read_reg(&s,0)==0xf5);
        write_reg(&s,0xfe,0);assert(read_reg(&s,0)==0x9b);break;
    case 1: /* The same address stores different values on the two pages. */
        write_reg(&s,0x31,0xa1);write_reg(&s,0xfe,1);
        write_reg(&s,0x31,0xb2);assert(read_reg(&s,0x31)==0xb2);
        write_reg(&s,0xfe,0);assert(read_reg(&s,0x31)==0xa1);
        write_reg(&s,0xfe,1);assert(read_reg(&s,0x31)==0xb2);break;
    case 2: /* Page-zero PID cannot be overwritten by SCCB writes. */
        write_reg(&s,0,0);assert(read_reg(&s,0)==0x9b);
        write_reg(&s,0,0xff);assert(read_reg(&s,0)==0x9b);break;
    case 3: /* Driver's 0xf0 software reset clears both writable banks. */
        write_reg(&s,0x31,0xa1);write_reg(&s,0xfe,1);write_reg(&s,0x31,0xb2);
        write_reg(&s,0xfe,0xf0);assert(read_reg(&s,0xfe)==0);
        assert(read_reg(&s,0)==0x9b && read_reg(&s,0x31)==0);
        write_reg(&s,0xfe,1);assert(read_reg(&s,0x31)==0 && read_reg(&s,0)==0);
        write_reg(&s,0xfe,0);assert(read_reg(&s,0)==0x9b);break;
    case 4: /* Repeated default/framesize/re-probe cycles preserve identity. */
        for(unsigned cycle=0;cycle<4;cycle++) {
            write_reg(&s,0xfe,0);assert(read_reg(&s,0)==0x9b);
            write_reg(&s,0xfe,0xf0);write_reg(&s,0xfe,0);
            write_reg(&s,0x24,0xa6);write_reg(&s,0xfe,1);write_reg(&s,0,0xf5);
            write_reg(&s,0x54,0x22);write_reg(&s,0xfe,0);
            assert(read_reg(&s,0)==0x9b && read_reg(&s,0x24)==0xa6);
        }break;
    case 5: /* Ordinary page-zero register read/write remains supported. */
        write_reg(&s,0x24,0x16);assert(read_reg(&s,0x24)==0x16);break;
    default:return 2;
    }
    puts("PASS actual GC0308 SCCB page/identity/reset boundary");return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class Gc0308SccbPagesPatchTests(unittest.TestCase):
    def test_actual_sccb_helpers_and_generic_preimage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    # Reproduce the exact SCCB preimage before later PMIC changes.
                    break
                subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            self.assertIn('s->model = M_GENERIC;', before.split('!strcmp(m, "gc0308")', 1)[1].split('} else', 1)[0])
            self.assertIn('s->model = M_GC0308;', after.split('!strcmp(m, "gc0308")', 1)[1].split('} else', 1)[0])
            self.assertIn("return gc0308_read_reg(s, r);", function(after, "dev_read_reg"))
            self.assertIn("gc0308_write_reg(s, r, data);", function(after, "dev_send"))
            for label, source in (("baseline", before), ("fixed", after)):
                state = source[source.index("typedef struct M5swI2CDev"):source.index("} M5swI2CDev;") + len("} M5swI2CDev;")]
                if label == "baseline":
                    # These are the exact generic callback fallback statements,
                    # selected by the GC0308 preimage's M_GENERIC realization.
                    read = function(source, "dev_read_reg").rsplit("    return ", 1)[1].split("\n}", 1)[0]
                    write = function(source, "dev_send").rsplit("    s->regs[r] = data;", 1)[1]
                    helpers = "static uint8_t read_reg(M5swI2CDev *s,uint8_t r){return " + read + "}\n"
                    helpers += "static int write_reg(M5swI2CDev *s,uint8_t r,uint8_t data){s->regs[r] = data;" + write
                else:
                    helpers = function(source, "gc0308_read_reg") + "\n" + function(source, "gc0308_write_reg")
                    helpers += "\n#define read_reg gc0308_read_reg\n#define write_reg gc0308_write_reg\n"
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + state + helpers + MAIN)
                compile_result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
                for case in range(6):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed" or case == 5:
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0, "preimage must fail the new SCCB boundary")


if __name__ == "__main__":
    unittest.main()

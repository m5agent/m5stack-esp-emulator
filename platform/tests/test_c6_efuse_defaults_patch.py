"""Actual C3/C6 realize and class-chain controls for unprovisioned C6 eFuses."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from test_c6_wifi_tsf_patch import function

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name('fixtures') / 'c6_efuse_defaults'
PATCH = ROOT / 'patches/qemu-esp32c6-uiflow2-adapters/0021-c6-efuse-unprovisioned-defaults.patch'
STUB = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
typedef void DeviceState; typedef void Error;
typedef void (*DeviceRealize)(DeviceState *, Error **);
typedef struct DeviceClass { DeviceRealize realize; } DeviceClass;
typedef DeviceClass ObjectClass;
typedef struct ESPEfuseClass { DeviceClass parent_class; } ESPEfuseClass;
typedef struct ESPEfuseBlocks { uint32_t rd_mac_spi_sys_3,rd_sys_part1_data4; uint8_t other[64]; } ESPEfuseBlocks;
typedef struct ESPEfuseState { void *klass;void *blk;uint8_t *mirror;struct {ESPEfuseBlocks blocks;} efuses; } ESPEfuseState;
#define ESP_EFUSE(p) ((ESPEfuseState *)(p))
#define DEVICE_CLASS(p) ((DeviceClass *)(p))
#define OBJECT_CHECK(t,p,n) ((t *)(p))
#define OBJECT_GET_CLASS(t,p,n) ((t *)ESP_EFUSE(p)->klass)
#define OBJECT_CLASS_CHECK(t,p,n) ((t *)(p))
#define REG32(n,o)
#define FIELD(r,f,s,w) enum { r##_##f##_SHIFT=s, r##_##f##_MASK=((1u<<(w))-1)<<(s) };
#define FIELD_DP32(v,r,f,n) (((v)&~r##_##f##_MASK)|(((n)<<r##_##f##_SHIFT)&r##_##f##_MASK))
static void device_class_set_parent_realize(DeviceClass *dc,DeviceRealize next,DeviceRealize *parent){*parent=dc->realize;dc->realize=next;}
static ESPEfuseBlocks stored;static uint8_t backing[sizeof(ESPEfuseBlocks)];static int base_calls;
static void base_realize(DeviceState *dev,Error **errp){
 ESPEfuseState*s=ESP_EFUSE(dev);assert(++base_calls==1);
 if(s->blk){s->efuses.blocks=stored;s->mirror=NULL;}
 else {memset(&s->efuses.blocks,0,sizeof(s->efuses.blocks));memset(backing,0,sizeof(backing));s->mirror=backing;s->efuses.blocks.other[7]=0xa5;}
}
'''
MAIN = r'''
int main(int argc,char **argv){
 assert(argc==2);int test=atoi(argv[1]);ESP32C3EfuseClass c3={0};ESP32C6EfuseClass c6={0};ESPEfuseState s={0};
 DEVICE_CLASS(&c3)->realize=base_realize;esp32c3_efuse_class_init((ObjectClass*)&c3,NULL);memcpy(&c6.parent_class,&c3,sizeof(c3));setup_c6(&c6);
 assert(c3.parent_realize==base_realize && c6.parent_class.parent_realize==base_realize);
 bool is_c6=test==1||test==3||test==4||test==5;s.klass=is_c6?(void*)&c6:(void*)&c3;
 if(test==2||test==3){s.blk=(void*)1;uint8_t*p=(void*)&stored;for(unsigned i=0;i<sizeof(stored);i++)p[i]=(i*73+11)&255;}
 DEVICE_CLASS(s.klass)->realize(&s,NULL);assert(base_calls==1);
 switch(test){
 case 0:assert(s.efuses.blocks.rd_mac_spi_sys_3==0x030c0000 && s.efuses.blocks.rd_sys_part1_data4==1);assert(!memcmp(s.mirror,&s.efuses.blocks,sizeof(stored)));break;
 case 1:assert(s.efuses.blocks.rd_mac_spi_sys_3==0 && s.efuses.blocks.rd_sys_part1_data4==0);assert(!memcmp(s.mirror,&s.efuses.blocks,sizeof(stored)));break;
 case 2:case 3:assert(!s.mirror&&!memcmp(&s.efuses.blocks,&stored,sizeof(stored)));break;
 case 4:memset(&s.efuses.blocks,0xff,sizeof(stored));memcpy(&s.efuses.blocks,s.mirror,sizeof(stored));assert(s.efuses.blocks.rd_mac_spi_sys_3==0&&s.efuses.blocks.rd_sys_part1_data4==0);break;
 case 5:assert(s.efuses.blocks.other[7]==0xa5 && s.mirror[8+7]==0xa5);break;
 default:abort();
 }
 printf("PASS efuse-default %d\n",test);return 0;
}
'''

def build(source, binary, after):
    code = STUB
    for name in ('esp32c3_efuse.h', 'esp32c6_efuse.h'):
        header = (source / 'include/hw/nvram' / name).read_text()
        code += re.sub(r'^#(?:include|pragma).*\n', '', header, flags=re.M)
    c3 = (source / 'hw/nvram/esp32c3_efuse.c').read_text()
    for name in ('esp32c3_efuse_realize', 'esp32c3_efuse_class_init'):
        code += function(c3, name)
    if after:
        c6 = (source / 'hw/nvram/esp32c6_efuse.c').read_text()
        for name in ('esp32c6_efuse_realize', 'esp32c6_efuse_class_init'):
            code += function(c6, name)
        code += 'static void setup_c6(ESP32C6EfuseClass*c){esp32c6_efuse_class_init((ObjectClass*)c,NULL);}\n'
    else:
        code += 'static void setup_c6(ESP32C6EfuseClass*c){}\n'
    binary.with_suffix('.c').write_text(code + MAIN)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    '-fsanitize=address,undefined', '-g', str(binary.with_suffix('.c')), '-o', str(binary)],
                   check=True, capture_output=True)

@unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'C compiler and git required')
class C6EfuseDefaultsTests(unittest.TestCase):
    def test_actual_realize_chain_before_after(self):
        with tempfile.TemporaryDirectory(prefix='m5-c6-efuse-') as temp:
            root = Path(temp)
            for after in (False, True):
                source = root / str(after)
                shutil.copytree(FIXTURE, source)
                if after:
                    for arguments in (['--check'], [], ['--reverse', '--check']):
                        subprocess.run(['git', 'apply', *arguments, str(PATCH)], cwd=source,
                                       check=True, capture_output=True)
                binary = root / ('after' if after else 'before')
                try:
                    build(source, binary, after)
                except subprocess.CalledProcessError as error:
                    self.fail(error.stderr.decode())
                for case in range(6):
                    with self.subTest(after=after, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True,
                                                timeout=10, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0',
                                                                     UBSAN_OPTIONS='halt_on_error=1'))
                        if after or case not in (1, 4):
                            self.assertEqual(result.returncode, 0, result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn('assert', result.stderr.lower())

if __name__ == '__main__':
    unittest.main()

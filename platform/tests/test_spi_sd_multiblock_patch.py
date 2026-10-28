"""Replay actual SPI SD command/token code against independent raw sectors."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0056-spi-sd-multiblock-transfers.patch"
SOURCE = "hw/m5stopwatch/m5_spi_sd.c"
STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
typedef struct { void (*set_cs)(void*,bool); uint8_t (*transfer)(void*,uint8_t); } M5SpiSlaveOps;
'''
MAIN = r'''
static uint8_t transfer(M5SpiSdState *s,uint8_t tx) {return sd_spi_transfer(s,tx);}
static uint8_t command(M5SpiSdState *s,unsigned cmd,uint32_t arg) {
    uint8_t data[]={0x40|cmd,arg>>24,arg>>16,arg>>8,arg,0x95};
    for(unsigned i=0;i<6;i++)transfer(s,data[i]);
    for(unsigned i=0;i<16;i++){uint8_t out=transfer(s,255);if(!(out&128))return out;}
    assert(!"command response timeout");return 255;
}
static void block(M5SpiSdState *s,unsigned value) {
    transfer(s,s->multi_write?0xfc:0xfe);
    for(unsigned i=0;i<512;i++)transfer(s,(uint8_t)(value+i));
    transfer(s,0);transfer(s,0);
    assert(transfer(s,255)==5);
}
static void read_block(M5SpiSdState *s,unsigned value) {
    unsigned i;
    for(i=0;i<16;i++)if(transfer(s,255)==0xfe)break;
    assert(i<16);
    uint8_t data[512];
    for(i=0;i<512;i++){data[i]=transfer(s,255);assert(data[i]==(uint8_t)(value+i));}
    uint16_t crc=sd_crc16(data,512);
    assert(transfer(s,255)==(crc&255));assert(transfer(s,255)==(crc>>8));
}
int main(int argc,char **argv) {
    assert(argc==2);unsigned test=atoi(argv[1]);
    M5SpiSdState s={.image=tmpfile(),.image_size=4096};assert(s.image);
    for(unsigned i=0;i<4096;i++)fputc(0,s.image);fflush(s.image);
    if(test==0){
        assert(command(&s,55,0)==1);assert(command(&s,23,3)==0);
        assert(command(&s,25,512)==0);
        for(unsigned n=0;n<3;n++)block(&s,17+n*31);
        assert(transfer(&s,0xfd)==0);assert(!s.multi_write && s.mode==SD_IDLE);
        fseeko(s.image,512,SEEK_SET);
        for(unsigned n=0;n<3;n++)for(unsigned i=0;i<512;i++)assert(fgetc(s.image)==(uint8_t)(17+n*31+i));
        assert(command(&s,55,0)==1);assert(command(&s,22,0)==0);
        unsigned i;for(i=0;i<16;i++)if(transfer(&s,255)==0xfe)break;assert(i<16);
        assert(transfer(&s,255)==0);assert(transfer(&s,255)==0);assert(transfer(&s,255)==0);assert(transfer(&s,255)==3);
    }else if(test==1){
        fseeko(s.image,512,SEEK_SET);
        for(unsigned n=0;n<3;n++)for(unsigned i=0;i<512;i++)fputc((uint8_t)(21+n*11+i),s.image);fflush(s.image);
        assert(command(&s,18,512)==0);
        for(unsigned n=0;n<3;n++)read_block(&s,21+n*11);
        assert(command(&s,12,0)==0);assert(!s.multi_read && s.mode==SD_IDLE);
    }else if(test==2){
        assert(command(&s,24,0)==0);block(&s,33);assert(s.mode==SD_IDLE);
        assert(command(&s,17,0)==0);read_block(&s,33);
        assert(command(&s,22,0)==5); /* CMD22 without APP_CMD is illegal. */
        assert(command(&s,23,0)==5);
    }else{
        assert(command(&s,25,4096)==0x20);assert(command(&s,18,4096)==0x20);
        fseeko(s.image,0,SEEK_END);assert(ftello(s.image)==4096);
    }
    fclose(s.image);puts("PASS actual SPI SD token/raw-sector/stop/count boundary");
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class SpiSdMultiBlockPatchTests(unittest.TestCase):
    def test_actual_command_data_plane_and_single_block_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch != PATCH:
                    subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                # Existing type lacks new state fields; the negative control
                # checks old command rejection before the shared harness.
                if label == "baseline":
                    source = source.replace("    bool app_cmd;", "    bool multi_write;\n    bool multi_read;\n    bool app_cmd;")
                body = source[source.index("#define SD_BLOCK_SIZE"):source.index("void m5_spi_sd_attach")]
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + body + MAIN)
                compilation = subprocess.run([shutil.which("cc"), "-std=c11", "-D_DARWIN_C_SOURCE", "-D_POSIX_C_SOURCE=200809L", "-Wno-excess-initializers", str(path), "-o", str(binary)], capture_output=True, text=True)
                self.assertEqual(compilation.returncode, 0, compilation.stderr)
                for case in range(4):
                    with self.subTest(version=label, case=case):
                        run = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed" or case == 2:
                            self.assertEqual(run.returncode, 0, run.stderr)
                        else:
                            self.assertNotEqual(run.returncode, 0, "preimage must fail the new protocol boundary")

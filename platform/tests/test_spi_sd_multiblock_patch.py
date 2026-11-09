"""Replay actual SPI SD command/token code against independent raw sectors."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_unit_flashlight_cold_pad_patch as cold
from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0056-spi-sd-multiblock-transfers.patch"
INIT_PATCH = "patches/qemu-m5stack-peripherals/0166-spi-sd-card-init-state.patch"
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

INIT_MAIN = r'''
static uint8_t command_crc(unsigned cmd, uint32_t arg)
{
    uint64_t dividend = (((uint64_t)(0x40 | cmd) << 32) | arg) << 7;
    for (int bit = 46; bit >= 7; bit--) {
        if (dividend & (UINT64_C(1) << bit)) {
            dividend ^= UINT64_C(0x89) << (bit - 7);
        }
    }
    return ((dividend & 0x7f) << 1) | 1;
}

static uint8_t raw_command(M5SpiSdState *s, unsigned cmd, uint32_t arg, uint8_t crc)
{
    uint8_t data[] = {0x40 | cmd, arg >> 24, arg >> 16, arg >> 8, arg, crc};
    for (unsigned i = 0; i < sizeof(data); i++) {
        sd_spi_transfer(s, data[i]);
    }
    for (unsigned i = 0; i < 9; i++) {
        uint8_t response = sd_spi_transfer(s, 0xff);
        if (!(response & 0x80)) {
            return response;
        }
    }
    return 0xff;
}

static uint8_t send(M5SpiSdState *s, unsigned cmd, uint32_t arg)
{
    return raw_command(s, cmd, arg, command_crc(cmd, arg));
}

static uint32_t read_register(M5SpiSdState *s)
{
    uint32_t result = 0;
    for (unsigned i = 0; i < 4; i++) {
        result = (result << 8) | sd_spi_transfer(s, 0xff);
    }
    return result;
}

static uint8_t write_sector(M5SpiSdState *s, uint16_t crc)
{
    assert(send(s, 24, 512) == 0);
    sd_spi_transfer(s, 0xfe);
    for (unsigned i = 0; i < 512; i++) {
        sd_spi_transfer(s, (uint8_t)i);
    }
    sd_spi_transfer(s, crc >> 8);
    sd_spi_transfer(s, crc & 0xff);
    return sd_spi_transfer(s, 0xff);
}

int main(void)
{
    M5SpiSdState empty = {0};
    assert(command_crc(0, 0) == 0x95);
    assert(command_crc(8, 0x1aa) == 0x87);
    assert(send(&empty, 0, 0) == 0xff);

    M5SpiSdState card = {.image = tmpfile(), .image_size = 4096};
    assert(card.image);
    for (unsigned i = 0; i < card.image_size; i++) {
        fputc(0, card.image);
    }
    fflush(card.image);
    assert(send(&card, 0, 0) == 1);
    assert(send(&card, 59, 1) == 1);
    assert(raw_command(&card, 58, 0, 1) == 9);
    assert(send(&card, 8, 0x15a) == 1);
    assert(read_register(&card) == 0x15a);
    assert(send(&card, 58, 0) == 1);
    assert(read_register(&card) == UINT32_C(0x00ff8000));
    assert(send(&card, 17, 512) == 5);
    assert(send(&card, 41, UINT32_C(0x40000000)) == 5);
    assert(send(&card, 55, 0) == 1);
    assert(send(&card, 41, UINT32_C(0x40000000)) == 0);
    assert(send(&card, 58, 0) == 0);
    assert(read_register(&card) == UINT32_C(0x80ff8000));
    assert(send(&card, 42, 0) == 4);
    assert(send(&card, 55, 0) == 0);
    assert(send(&card, 42, 0) == 0);
    assert(send(&card, 16, 512) == 0);

    /* CRC-16/XMODEM of two repetitions of the bytes 00..ff is 0x40da. */
    assert(write_sector(&card, 0xda40) == 0x0b);
    fseeko(card.image, 512, SEEK_SET);
    for (unsigned i = 0; i < 512; i++) {
        assert(fgetc(card.image) == 0);
    }
    assert(write_sector(&card, 0x40da) == 0x05);
    assert(send(&card, 17, 512) == 0);
    uint8_t token = 0xff;
    for (unsigned i = 0; i < 16 && token == 0xff; i++) {
        token = sd_spi_transfer(&card, 0xff);
    }
    assert(token == 0xfe);
    for (unsigned i = 0; i < 512; i++) {
        assert(sd_spi_transfer(&card, 0xff) == (uint8_t)i);
    }
    assert(sd_spi_transfer(&card, 0xff) == 0x40);
    assert(sd_spi_transfer(&card, 0xff) == 0xda);
    assert(send(&card, 0, 0) == 1);
    assert(raw_command(&card, 58, 0, 1) == 1);
    assert(read_register(&card) == UINT32_C(0x00ff8000));
    fclose(card.image);
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class SpiSdMultiBlockPatchTests(unittest.TestCase):
    def source_before(self, root, patch):
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        for prior in bootstrap_stack(full=True):
            if prior == patch:
                return (root / SOURCE).read_text()
            if SOURCE in cold.patch_paths(prior):
                subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / prior)], cwd=root, check=True, capture_output=True)
        self.fail(f"{patch} is missing from the native bootstrap stack")

    def compile_harness(self, root, label, source, main):
        body = source[source.index("#define SD_BLOCK_SIZE"):source.index("void m5_spi_sd_attach")]
        path, binary = root / (label + ".c"), root / label
        path.write_text(STUBS + body + main)
        compilation = subprocess.run([shutil.which("cc"), "-std=c11", "-D_DARWIN_C_SOURCE", "-D_POSIX_C_SOURCE=200809L", "-Wno-excess-initializers", str(path), "-o", str(binary)], capture_output=True, text=True)
        self.assertEqual(compilation.returncode, 0, compilation.stderr)
        return binary

    def test_actual_command_data_plane_and_single_block_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = self.source_before(root, PATCH)
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                # Existing type lacks new state fields; the negative control
                # checks old command rejection before the shared harness.
                if label == "baseline":
                    source = source.replace("    bool app_cmd;", "    bool multi_write;\n    bool multi_read;\n    bool app_cmd;")
                binary = self.compile_harness(root, label, source, MAIN)
                for case in range(4):
                    with self.subTest(version=label, case=case):
                        run = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed" or case == 2:
                            self.assertEqual(run.returncode, 0, run.stderr)
                        else:
                            self.assertNotEqual(run.returncode, 0, "preimage must fail the new protocol boundary")

    def test_card_init_absence_and_crc_on_the_wire(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = self.source_before(root, INIT_PATCH)
            subprocess.run(["git", "apply", str(ROOT / INIT_PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / INIT_PATCH)], cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                with self.subTest(version=label):
                    binary = self.compile_harness(root, label, source, INIT_MAIN)
                    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
                    if label == "fixed":
                        self.assertEqual(run.returncode, 0, run.stderr)
                    else:
                        self.assertNotEqual(run.returncode, 0, "preimage falsely answers with no card")

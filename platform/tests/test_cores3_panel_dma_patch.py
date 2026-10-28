"""Exercise CoreS3 board wiring with the actual patched GP-SPI DMA reader.

This is a controller C-logic regression; visible guest/frame evidence is a
separate gate. No local QEMU checkout, binary or firmware fixture is required.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

BOARD = "hw/m5stopwatch/m5cores3.c"
SPI = "hw/m5stopwatch/esp32s3_gpspi.c"


def function(source, name):
    match = re.search(r"static uint32_t " + re.escape(name) + r"\(", source)
    if not match:
        raise AssertionError("actual GP-SPI function missing: " + name)
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated GP-SPI function")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define GDMA_SPI2 0
#define GDMA_SPI3 1
#define ESP_GDMA_RAM_ADDR 0x3fc80000U
#define ESP_GDMA_OUT_IDX 1
#define GDMA_LINK_REG 0
#define LOG_GUEST_ERROR 0
#define MEMTXATTRS_UNSPECIFIED 0
#define MEMTX_OK 0
#define MIN(a,b) ((a)<(b)?(a):(b))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define M5_SPI_PANEL(p) (p)
typedef struct { uint64_t transfer_generation; uint32_t current_desc_addr; } DmaConfigState;
typedef struct { uint32_t link[2]; DmaConfigState ch_conf[2][2]; } ESPGdmaState;
typedef struct { uint64_t generation; uint32_t desc_addr, desc_off; bool valid; } M5GpspiDmaCursor;
typedef struct Esp32s3GpspiState {
    ESPGdmaState *gdma;
    unsigned gdma_periph;
    int active_slave;
    struct { int gdma_periph; } slaves[2];
    M5GpspiDmaCursor dma_cursor[2];
} Esp32s3GpspiState;
static unsigned address_space_memory;
static uint8_t ram[1<<20];
static void qemu_log_mask(int mask, const char *message) { (void)mask; (void)message; }
static bool esp_gdma_get_channel_periph(ESPGdmaState *s, unsigned periph, int dir, uint32_t *channel) {
    assert(dir==ESP_GDMA_OUT_IDX);
    if (periph>1 || !s->link[periph]) return false;
    *channel=periph; return true;
}
static int address_space_read(unsigned *as, uint32_t address, int attrs, void *target, unsigned count) {
    (void)attrs;
    assert(as==&address_space_memory);
    assert(address>=0x3fc00000U && (uint64_t)address+count<=0x3fd00000ULL);
    memcpy(target,ram+(address-0x3fc00000U),count); return MEMTX_OK;
}
static void esp32s3_gpspi_attach(Esp32s3GpspiState *s, ESPGdmaState *gdma, void *co, void *panel, unsigned periph) {
    (void)co; (void)panel; s->gdma=gdma; s->gdma_periph=periph;
}
'''

MAIN = r'''
static void descriptor(unsigned address, unsigned buffer, unsigned length, unsigned next) {
    uint32_t words[]={length|(length<<12)|(next?0:1U<<30),0x3fc00000U+buffer,next?0x3fc00000U+next:0};
    memcpy(ram+address,words,sizeof(words));
}
int main(void) {
    ESPGdmaState gdma={.link={0x100,0x300}};
    Esp32s3GpspiState controller={.active_slave=-1};
    gdma.ch_conf[ESP_GDMA_OUT_IDX][0]=(DmaConfigState){1,0x3fc00100U};
    gdma.ch_conf[ESP_GDMA_OUT_IDX][1]=(DmaConfigState){1,0x3fc00300U};
    wire_panel(&controller,&gdma);
    for (unsigned n=0;n<200;n++) { ram[0x1000+n]=(n*13)^0x5a; ram[0x2000+n]=0xee; }
    descriptor(0x100,0x1000,80,0x120); descriptor(0x120,0x1050,120,0);
    descriptor(0x300,0x2000,200,0); /* Concurrent SPI3 is a different producer. */
    uint8_t output[200]={0};
    assert(gpspi_dma_pull(&controller,output,200)==200);
    assert(!memcmp(output,ram+0x1000,200)); /* Wrong board peripheral selects 0xee. */
    gdma.ch_conf[ESP_GDMA_OUT_IDX][0].transfer_generation++;
    assert(gpspi_dma_pull(&controller,output,17)==17);
    assert(gpspi_dma_pull(&controller,output+17,183)==183);
    assert(!memcmp(output,ram+0x1000,200));
    gdma.link[GDMA_SPI2]=0;
    assert(gpspi_dma_pull(&controller,output,200)==0); /* Never borrow SPI3. */
    puts("PASS CoreS3 SPI2 panel descriptor source and no cross-channel fallback");
    return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class CoreS3PanelDmaPatchTests(unittest.TestCase):
    def test_board_panel_reads_its_spi2_descriptor_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                subprocess.run(["git", "apply", "--include=" + BOARD, "--include=" + SPI, str(ROOT / patch)],
                               cwd=root, check=True, capture_output=True)
            board = (root / BOARD).read_text()
            call = re.search(r"esp32s3_gpspi_attach\(spi, gdma, NULL, M5_SPI_PANEL\(panel\), [A-Z0-9_]+\);", board)
            self.assertIsNotNone(call)
            actual = (root / SPI).read_text()
            program = (STUBS + function(actual, "gpspi_active_dma_periph") + "\n" + function(actual, "gpspi_dma_pull")
                       + "\nstatic void wire_panel(Esp32s3GpspiState *spi, ESPGdmaState *gdma) {\nvoid *panel=NULL;\n"
                       + call.group() + "\n}\n" + MAIN)
            source = root / "panel.c"
            source.write_text(program)
            binary = root / "panel"
            result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)

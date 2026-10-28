"""Replay the real GP-SPI DMA cursor across split user transactions.

Only descriptor RAM, GDMA notification/register glue and the output sink are
host shims. Descriptor traversal and user-transfer execution are extracted from
the bootstrap C source. This is controller C evidence, not a guest/hardware PASS.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0058-gpspi-dma-transfer-chunks.patch"
SOURCE = "hw/m5stopwatch/esp32s3_gpspi.c"


def function(source, name):
    match = re.search(r"static (?:void|uint32_t) " + re.escape(name) + r"\(", source)
    if match is None:
        raise AssertionError("actual GP-SPI function missing: " + name)
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated actual GP-SPI function")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define g_realloc realloc
#define ESP_GDMA_RAM_ADDR 0x3fc88000u
#define ESP_GDMA_OUT_IDX 1
#define ESP_GDMA_IN_IDX 0
#define GDMA_LINK_REG 7
#define MEMTXATTRS_UNSPECIFIED 0
#define MEMTX_OK 0
#define LOG_GUEST_ERROR 0
#define R_ADDR 0x04
#define R_USER 0x10
#define R_USER1 0x14
#define R_USER2 0x18
#define R_MS_DLEN 0x1c
#define R_DMA_CONF 0x30
#define R_DMA_INT_RAW 0x3c
#define R_W0 0x98
#define USER_MOSI (1u<<27)
#define USER_MISO (1u<<28)
#define USER_ADDR (1u<<30)
#define USER_COMMAND (1u<<31)
#define DMA_TX_ENA (1u<<28)
#define DMA_RX_ENA (1u<<27)
#define INT_TRANS_DONE (1u<<12)
#define RAM_BASE 0x3fc00000u
typedef int GdmaPeripheral;
typedef struct ESPGdmaState {
    uint32_t link;
    void (*callback)(void *, GdmaPeripheral, int);
    void *opaque;
    unsigned link_reads;
} ESPGdmaState;
typedef struct Esp32s3GpspiState {
    uint32_t regs[0x40];
    ESPGdmaState *gdma;
    uint32_t gdma_periph;
    int active_slave,last_slave;
    struct { int gdma_periph; } slaves[4];
    bool dma_reload;
    uint32_t desc_addr,desc_off;
    uint8_t *buf,rx[4096];
    uint32_t buf_size,rx_len;
} Esp32s3GpspiState;
static uint8_t ram[1<<20],output[200000];
static uint32_t output_size,irq_count;
static int address_space_memory;
static int address_space_read(void *space,uint32_t address,int attrs,void *dst,uint32_t size) {
    assert(space==&address_space_memory && attrs==0 && address>=RAM_BASE);
    assert(address-RAM_BASE+size<=sizeof(ram));
    memcpy(dst,ram+address-RAM_BASE,size);return MEMTX_OK;
}
static bool esp_gdma_get_channel_periph(ESPGdmaState *g,uint32_t periph,int dir,uint32_t *channel) {
    assert(g && periph==2 && dir==ESP_GDMA_OUT_IDX);*channel=0;return true;
}
static uint32_t esp_gdma_read_chan_register(ESPGdmaState *g,int dir,uint32_t channel,int reg) {
    assert(dir==ESP_GDMA_OUT_IDX && channel==0 && reg==GDMA_LINK_REG);
    g->link_reads++;return g->link;
}
static void esp_gdma_set_start_callback(ESPGdmaState *g,GdmaPeripheral periph,int dir,
                                       void (*callback)(void *,GdmaPeripheral,int),void *opaque) {
    assert(periph==2 && dir==ESP_GDMA_OUT_IDX);g->callback=callback;g->opaque=opaque;
}
static bool esp_gdma_write_channel(ESPGdmaState *g,uint32_t channel,uint8_t *data,uint32_t count) {
    (void)g;(void)channel;(void)data;(void)count;assert(!"unexpected receive-DMA path");return false;
}
static void qemu_log_mask(int mask,const char *message) {(void)mask;(void)message;assert(!"GDMA channel missing");}
static void sink(Esp32s3GpspiState *s,const uint8_t *data,uint32_t size,bool command) {
    (void)s;assert(!command && output_size+size<=sizeof(output));
    memcpy(output+output_size,data,size);output_size+=size;
}
static void gpspi_forward_slave(Esp32s3GpspiState *s,const uint8_t *tx,uint32_t size,uint8_t *rx,bool capture) {
    (void)tx;(void)size;(void)rx;assert(s->active_slave<0 && !capture);
}
static void gpspi_update_irq(Esp32s3GpspiState *s) {assert(s->regs[R_DMA_INT_RAW/4]&INT_TRANS_DONE);irq_count++;}
'''


MAIN = r'''
static uint8_t pattern(unsigned index) {return (index*29u+(index/251u)*17u)&255;}
static void chain(unsigned head,unsigned data,unsigned total,unsigned capacity,unsigned seed) {
    unsigned count=(total+capacity-1)/capacity;
    assert(capacity<4096 && head+count*12<data && data+total<=sizeof(ram));
    for(unsigned offset=0;offset<total;offset++)ram[data+offset]=pattern(seed+offset);
    for(unsigned index=0,offset=0;index<count;index++) {
        uint32_t size=MIN(capacity,total-offset);
        uint32_t descriptor[3]={size<<12|1u<<31,RAM_BASE+data+offset,RAM_BASE+head+(index+1)*12};
        if(index+1==count){descriptor[0]|=1u<<30;descriptor[2]=RAM_BASE+0xf0000;}
        memcpy(ram+head+index*12,descriptor,12);offset+=size;
    }
}
static void start(Esp32s3GpspiState *s,unsigned head) {
    s->gdma->link=head;
    if(s->gdma->callback)s->gdma->callback(s->gdma->opaque,2,ESP_GDMA_OUT_IDX);
}
static void transfer(Esp32s3GpspiState *s,unsigned size) {
    assert(size>0 && size<=32768);s->regs[R_MS_DLEN/4]=size*8-1;gpspi_exec(s);
}
static void expect(unsigned offset,unsigned size,unsigned seed) {
    for(unsigned index=0;index<size;index++)assert(output[offset+index]==pattern(seed+index));
}
int main(int argc,char **argv) {
    assert(argc==2);ESPGdmaState g={0};
    Esp32s3GpspiState s={.gdma=&g,.gdma_periph=2,.active_slave=-1,.last_slave=-1,.dma_reload=true};
    s.regs[R_USER/4]=USER_MOSI;s.regs[R_DMA_CONF/4]=DMA_TX_ENA;
    #if FIXED_VERSION
    gpspi_bind_dma(&s,2);assert(g.callback && g.opaque==&s);
    #endif
    switch(atoi(argv[1])) {
    case 0: /* Real Cardputer 64800-byte canvas: one START, two SPI chunks. */
        chain(0x1000,0x10000,64800,4092,0);start(&s,0x1000);
        transfer(&s,32032);transfer(&s,32768);
        assert(output_size==64800 && g.link_reads==1);expect(0,64800,0);break;
    case 1: /* Preserve both descriptor index and in-node offset across chunks. */
        chain(0x1000,0x10000,12000,257,31);start(&s,0x1000);
        transfer(&s,17);transfer(&s,113);transfer(&s,3000);transfer(&s,4096);transfer(&s,4774);
        assert(output_size==12000 && g.link_reads==1);expect(0,12000,31);break;
    case 2: /* EOF ends this chain even when its next pointer is nonzero. */
        chain(0x1000,0x10000,80,31,53);start(&s,0x1000);transfer(&s,80);transfer(&s,16);
        assert(output_size==80 && !s.desc_addr && g.link_reads==1);expect(0,80,53);break;
    case 3: /* An actual new START must re-arm even the same descriptor head. */
        chain(0x1000,0x10000,128,47,71);start(&s,0x1000);transfer(&s,64);
        start(&s,0x1000);transfer(&s,64);
        assert(output_size==128 && g.link_reads==2);expect(0,64,71);expect(64,64,71);break;
    case 4: /* A new START can bind a different head before prior-chain EOF. */
        chain(0x1000,0x10000,128,47,91);chain(0x3000,0x50000,64,31,100003);
        start(&s,0x1000);transfer(&s,64);start(&s,0x3000);transfer(&s,64);
        assert(output_size==128 && g.link_reads==2);expect(0,64,91);expect(64,64,100003);break;
    case 5: /* One short descriptor transfer retains its exact legacy bytes. */
        chain(0x1000,0x10000,256,4092,109);start(&s,0x1000);transfer(&s,256);
        assert(output_size==256 && g.link_reads==1);expect(0,256,109);break;
    case 6: /* Incoming-DMA notification must not rewind the outgoing cursor. */
        chain(0x1000,0x10000,128,47,131);start(&s,0x1000);transfer(&s,64);
        #if FIXED_VERSION
        g.callback(g.opaque,2,ESP_GDMA_IN_IDX);assert(!s.dma_reload);
        #endif
        transfer(&s,64);assert(output_size==128 && g.link_reads==1);expect(0,128,131);break;
    default:return 2;
    }
    assert(irq_count);free(s.buf);puts("PASS actual GP-SPI DMA chunk/rearm/EOF cursor");return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class GpspiDmaChunkPatchTests(unittest.TestCase):
    def test_actual_gpspi_chunks_rearm_and_eof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                names = ["gpspi_active_dma_periph"]
                if label == "fixed":
                    names += ["gpspi_dma_start", "gpspi_bind_dma"]
                names += ["gpspi_dma_pull", "gpspi_exec"]
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + "\n".join(function(source, name) for name in names) + MAIN)
                compiled = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-unused-parameter", "-DFIXED_VERSION=" + str(int(label == "fixed")), str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                for case in range(7):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "baseline" and case in {0, 1, 2, 6}:
                            self.assertNotEqual(result.returncode, 0, "old per-user rewind must fail the independent byte/cursor oracle")
                        else:
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

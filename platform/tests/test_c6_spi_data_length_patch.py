"""Actual SPI C paths with bounded bus/GDMA stubs; no guest or hardware claim."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "c6_spi_data_length"
PATCH = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0015-c6-spi2-data-length.patch"
SOURCE = "hw/ssi/esp32c3_spi.c"

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define DMA_RX_ENA (1u<<27)
#define DMA_TX_ENA (1u<<28)
#define SPI_TRANS_DONE (1u<<12)
#define CMD_PP 2
#define GDMA_SPI2 0
#define ESP_GDMA_OUT_IDX 1
#define ESP_GDMA_IN_IDX 0
#define R_SPI_MEM_USER_USR_COMMAND_MASK (1u<<31)
#define R_SPI_MEM_USER_USR_ADDR_MASK (1u<<30)
#define R_SPI_MEM_USER_USR_DUMMY_MASK (1u<<29)
#define R_SPI_MEM_USER_USR_MISO_MASK (1u<<28)
#define R_SPI_MEM_USER_USR_MOSI_MASK (1u<<27)
#define FIELD_EX32(v,r,f) field_##r##_##f(v)
static uint32_t field_SPI_MEM_MISO_DLEN_USR_MISO_DBITLEN(uint32_t v) { return v & 1023; }
static uint32_t field_SPI_MEM_MOSI_DLEN_USR_MOSI_DBITLEN(uint32_t v) { return v & 1023; }
static uint32_t field_SPI_MEM_USER2_USR_COMMAND_VALUE(uint32_t v) { return v & 65535; }
static uint32_t field_SPI_MEM_USER2_USR_COMMAND_BITLEN(uint32_t v) { return (v>>28)&15; }
static uint32_t field_SPI_MEM_USER1_USR_ADDR_BITLEN(uint32_t v) { return (v>>26)&63; }
static uint32_t field_SPI_MEM_USER1_USR_DUMMY_CYCLELEN(uint32_t v) { return v&63; }
static uint32_t field_SPI_MEM_ADDR_USR_ADDR_VALUE(uint32_t v) { return v; }
static uint32_t bswap32(uint32_t v) { return __builtin_bswap32(v); }
typedef struct {
    bool (*is_manual_enc_enabled)(void *);
    bool (*is_ciphertext_spi_visible)(void *);
    void (*read_ciphertext)(void *,void *,uint32_t *,uint32_t *,uint32_t *);
} ESP32C3XtsAesClass;
#define ESP32C3_XTS_AES_GET_CLASS(p) ((ESP32C3XtsAesClass *)(p))
typedef struct { int unused; } ESPGdmaState;
typedef struct {
    uint32_t cmd,cmd_bytes,addr,addr_bytes;
    uint8_t mode_byte;
    bool has_mode_byte;
    uint32_t dummy_bytes,extra_dummy_bytes;
    void *data;
    uint32_t tx_bytes,rx_bytes;
} ESP32C3SpiTransaction;
typedef struct {
    void *spi,*xts_aes;
    ESPGdmaState *gdma;
    int cs_gpio[3];
    uint32_t mem_user,mem_user1,mem_user2,mem_addr,mem_miso_len,mem_mosi_len;
    uint32_t dma_conf,dma_int_raw,flash_qio_header_bytes;
    bool m5_spi2,m5_rx_from_slave;
    int m5_slave_cs;
    void *m5_slave_opaque,*m5_sink_opaque;
    uint8_t (*m5_slave_transfer)(void *,uint8_t);
    void (*m5_sink)(void *,const uint8_t *,uint32_t,bool);
    uint32_t data_reg[16];
} ESP32C3SpiState;
static unsigned clocked,out_calls,in_calls,out_requested,in_written,cs_edges;
static unsigned supplied=4096;
static bool out_bound=true,in_bound=true;
static uint8_t mosi[32768],dma_payload[4096],received[4096];
static uint8_t rx_oracle(unsigned i) { return (uint8_t)(0xd3u ^ (i*29u)); }
static uint32_t ssi_transfer(void *bus,uint8_t byte) {
    (void)bus;
    assert(clocked<sizeof(mosi));
    mosi[clocked]=byte;
    return rx_oracle(clocked++);
}
static int esp32_gpio_get_line(int pin) { (void)pin; return 1; }
static void qemu_set_irq(int irq,int level) { (void)irq;(void)level;cs_edges++; }
static void esp32c3_spi_update_irq(ESP32C3SpiState *s) { (void)s; }
static bool esp_gdma_get_channel_periph(ESPGdmaState *s,int periph,int dir,uint32_t *channel) {
    assert(s);assert(periph==GDMA_SPI2);*channel=0;
    return dir==ESP_GDMA_OUT_IDX ? out_bound : in_bound;
}
/* Descriptor transport is the explicit stub boundary. Return only supplied
 * bytes, allowing the actual SPI path to decide its length and completion. */
static uint32_t esp_gdma_complete_out_descriptor(ESPGdmaState *s,uint32_t channel,
                                                uint8_t *data,uint32_t size) {
    assert(s);assert(channel==0);assert(size<=sizeof(dma_payload));
    out_calls++;out_requested=size;
    unsigned n=MIN(size,supplied);memcpy(data,dma_payload,n);return n;
}
static uint32_t esp_gdma_complete_in_descriptor(ESPGdmaState *s,uint32_t channel,
                                               const uint8_t *data,uint32_t size) {
    assert(s);assert(channel==0);assert(size<=sizeof(received));
    in_calls++;in_written=size;memcpy(received,data,size);return size;
}
'''

MAIN = r'''
static void set_lengths(ESP32C3SpiState *s,unsigned tx,unsigned rx) {
    s->mem_user=(tx?R_SPI_MEM_USER_USR_MOSI_MASK:0)|(rx?R_SPI_MEM_USER_USR_MISO_MASK:0);
    s->mem_mosi_len=tx?tx*8-1:0;s->mem_miso_len=rx?rx*8-1:0;
}
static void expect_tx(unsigned n,const uint8_t *data) {
    assert(clocked==n);assert(!memcmp(mosi,data,n));
}
static void expect_rx(unsigned n) {
    assert(in_calls==1);assert(in_written==n);
    for(unsigned i=0;i<n;i++)assert(received[i]==rx_oracle(i));
}
int main(int argc,char **argv) {
    assert(argc==2);unsigned test=(unsigned)atoi(argv[1]);ESPGdmaState gdma={0};
    ESP32C3SpiState *s=calloc(1,sizeof(*s));assert(s);s->m5_spi2=true;s->gdma=&gdma;
    uint8_t fifo[64];for(unsigned i=0;i<64;i++)fifo[i]=(uint8_t)(0x91u+i*7u);
    for(unsigned i=0;i<sizeof(dma_payload);i++)dma_payload[i]=(uint8_t)(0x3bu+i*11u);
    memcpy(s->data_reg,fifo,64);
    switch(test) {
    case 0: /* Enabled TX DMA without an OUT channel: never read FIFO as 32 KiB. */
        s->dma_conf=DMA_TX_ENA;out_bound=false;set_lengths(s,32768,0);
        esp32c3_spi_begin_transaction(s);
        assert(!clocked&&!cs_edges&&!s->dma_int_raw&&!out_calls);break;
    case 1: /* Independent RX DMA and TX FIFO modes retain actual MOSI bytes. */
        s->dma_conf=DMA_RX_ENA;set_lengths(s,16,16);
        esp32c3_spi_begin_transaction(s);expect_tx(16,fifo);expect_rx(16);break;
    case 2: /* Original display regression needs the full 352-byte payload. */
        s->dma_conf=DMA_TX_ENA;set_lengths(s,352,0);
        esp32c3_spi_begin_transaction(s);expect_tx(352,dma_payload);assert(out_requested==352);break;
    case 3: /* The declared 18-bit maximum never exceeds the existing buffer. */
        s->dma_conf=DMA_TX_ENA;set_lengths(s,32768,0);
        esp32c3_spi_begin_transaction(s);expect_tx(4096,dma_payload);assert(out_requested==4096);break;
    case 4: /* A short descriptor transmits only bytes actually supplied. */
        s->dma_conf=DMA_TX_ENA;supplied=17;set_lengths(s,352,0);
        esp32c3_spi_begin_transaction(s);expect_tx(17,dma_payload);break;
    case 5: /* An empty/failed descriptor cannot fabricate completion. */
        s->dma_conf=DMA_TX_ENA;supplied=0;set_lengths(s,352,0);
        esp32c3_spi_begin_transaction(s);
        assert(out_calls==1&&!clocked&&!cs_edges&&!s->dma_int_raw);break;
    case 6: /* No GDMA object must not silently switch to FIFO mode. */
        s->dma_conf=DMA_TX_ENA;s->gdma=NULL;set_lengths(s,32768,0);
        esp32c3_spi_begin_transaction(s);
        assert(!clocked&&!cs_edges&&!s->dma_int_raw&&!out_calls);break;
    case 7: /* RX buffer cap plus TX FIFO cap, with distinct nonzero data. */
        s->dma_conf=DMA_RX_ENA;set_lengths(s,32768,32768);
        esp32c3_spi_begin_transaction(s);assert(clocked==4096);
        assert(!memcmp(mosi,fifo,64));for(unsigned i=64;i<4096;i++)assert(!mosi[i]);
        expect_rx(4096);break;
    case 8:
        s->dma_conf=DMA_RX_ENA;set_lengths(s,0,32768);
        esp32c3_spi_begin_transaction(s);assert(clocked==4096);expect_rx(4096);break;
    case 9: /* FIFO-only full duplex clamps both sides to W0..W15. */
        set_lengths(s,32768,32768);esp32c3_spi_begin_transaction(s);expect_tx(64,fifo);
        for(unsigned i=0;i<64;i++) {
            assert(((uint8_t *)s->data_reg)[i]==rx_oracle(i));
        }
        break;
    case 10:
        set_lengths(s,32768,0);esp32c3_spi_begin_transaction(s);expect_tx(64,fifo);break;
    case 11: /* SPI1 still decodes its 10-bit field, independently of HP SPI2. */
        s->m5_spi2=false;s->dma_conf=DMA_TX_ENA;set_lengths(s,257,0);
        esp32c3_spi_begin_transaction(s);expect_tx(1,fifo);assert(!out_calls);break;
    case 12: /* MOSI disabled cannot consume or emit an OUT descriptor. */
        s->dma_conf=DMA_TX_ENA|DMA_RX_ENA;set_lengths(s,0,352);
        esp32c3_spi_begin_transaction(s);assert(clocked==352&&!out_calls);
        for(unsigned i=0;i<clocked;i++) {
            assert(!mosi[i]);
        }
        expect_rx(352);break;
    case 13: /* Missing IN channel does not dereference it or invent RX writes. */
        s->dma_conf=DMA_RX_ENA;in_bound=false;set_lengths(s,16,352);
        esp32c3_spi_begin_transaction(s);assert(clocked==352&&!in_calls);
        assert(!memcmp(mosi,fifo,16));break;
    case 14: /* Short TX plus longer RX clocks zero only after supplied bytes. */
        s->dma_conf=DMA_TX_ENA|DMA_RX_ENA;supplied=3;set_lengths(s,352,352);
        esp32c3_spi_begin_transaction(s);assert(clocked==352);
        assert(!memcmp(mosi,dma_payload,3));for(unsigned i=3;i<352;i++)assert(!mosi[i]);
        expect_rx(352);break;
    default:return 2;
    }
    free(s);puts("PASS actual C6 SPI transaction");return 0;
}
'''

# These are deliberately fixed expectations for the preserved unsafe candidate.
UNSAFE_FAIL = {0, 1, 5, 6, 7, 12, 13}
CASES = 15


def patched_source(directory, patch):
    target = directory / SOURCE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((FIXTURE / "preimage.c").read_bytes())
    result = subprocess.run(
        ["git", "apply", "--include=" + SOURCE, str(patch)], cwd=directory,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    subprocess.run(
        ["git", "apply", "--reverse", "--check", "--include=" + SOURCE, str(patch)],
        cwd=directory, check=True, capture_output=True, text=True, timeout=30,
    )
    return target.read_text()


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class C6SpiDataLengthTests(unittest.TestCase):
    def test_actual_transaction_before_and_after(self):
        self.assertTrue(PATCH.is_file(), "Apply the C6 0015 model commit before this test commit")
        with tempfile.TemporaryDirectory(prefix="m5-c6-spi-host-") as temp:
            directory = Path(temp)
            for label, patch in (("unsafe", FIXTURE / "unsafe-length.patch"), ("fixed", PATCH)):
                source = patched_source(directory, patch)
                code = directory / (label + ".c")
                binary = directory / label
                code.write_text(STUBS + source + MAIN)
                result = subprocess.run(
                    ["cc", "-std=c11", "-g", "-O1", "-Wall", "-Wextra", "-Werror",
                     "-Wno-unused-parameter", "-Wno-sign-compare", "-fsanitize=address,undefined",
                     "-fno-omit-frame-pointer", str(code), "-o", str(binary)],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:abort_on_error=0",
                           UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                for case in range(CASES):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], env=env,
                                                capture_output=True, text=True, timeout=10)
                        if label == "unsafe" and case in UNSAFE_FAIL:
                            self.assertNotEqual(result.returncode, 0, result.stdout)
                            if case == 0:
                                self.assertIn("AddressSanitizer: heap-buffer-overflow", result.stderr)
                            else:
                                self.assertIn("Assertion", result.stderr)
                        else:
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertIn("PASS actual C6 SPI transaction", result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", type=Path, default=PATCH,
                        help="Explicit candidate for independent pre-merge review")
    args, remaining = parser.parse_known_args()
    PATCH = args.patch.resolve()
    unittest.main(argv=[__file__, *remaining])

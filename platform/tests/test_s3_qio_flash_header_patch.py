"""Actual S3 SPI handlers: Flash phase alignment and mixed-length FIFO bounds.

SSI is a byte-clock transport fixture. This is a controller contract, separate
from the same-firmware guest NVS/reset acceptance.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0095-s3-qio-flash-model-header.patch"


def patched(path):
    lines, active = [], False
    for line in PATCH.read_text().splitlines():
        if line.startswith("diff --git "):
            active = line.endswith(" b/" + path)
        elif active and not line.startswith(("+++", "---", "@@")):
            if line.startswith(("+", " ")):
                lines.append(line[1:])
    return "\n".join(lines)


def function(source, name):
    match = re.search(r"(?m)^static (?:inline )?void " + name
                      + r"\s*\([^;{}]*\)\s*\{", source)
    if not match:
        raise AssertionError("complete actual handler missing: " + name)
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                    lambda m: " " * len(m.group()), source, flags=re.S)
    depth = 0
    for end in range(masked.index("{", match.start()), len(masked)):
        depth += (masked[end] == "{") - (masked[end] == "}")
        if depth == 0:
            return source[match.start():end + 1]
    raise AssertionError(name)


PREFIX = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define MAX(a,b) ((a)>(b)?(a):(b))
#define FIELD_EX32(v,reg,field) (((uint32_t)(v)>>reg##_##field##_SHIFT)&reg##_##field##_VALUE)
#define SPI_MEM_MISC_CS0_DIS_SHIFT 0
#define SPI_MEM_MISC_CS0_DIS_VALUE 1
#define SPI_MEM_MISC_CS1_DIS_SHIFT 1
#define SPI_MEM_MISC_CS1_DIS_VALUE 1
#define SPI_MEM_ADDR_USR_ADDR_VALUE_SHIFT 0
#define SPI_MEM_ADDR_USR_ADDR_VALUE_VALUE 0xffffffffU
#define SPI_MEM_USER1_USR_ADDR_BITLEN_SHIFT 26
#define SPI_MEM_USER1_USR_ADDR_BITLEN_VALUE 63
#define SPI_MEM_USER1_USR_DUMMY_CYCLELEN_SHIFT 0
#define SPI_MEM_USER1_USR_DUMMY_CYCLELEN_VALUE 63
#define SPI_MEM_USER2_USR_COMMAND_VALUE_SHIFT 0
#define SPI_MEM_USER2_USR_COMMAND_VALUE_VALUE 65535
#define SPI_MEM_USER2_USR_COMMAND_BITLEN_SHIFT 28
#define SPI_MEM_USER2_USR_COMMAND_BITLEN_VALUE 15
#define SPI_MEM_MISO_DLEN_USR_MISO_DBITLEN_SHIFT 0
#define SPI_MEM_MISO_DLEN_USR_MISO_DBITLEN_VALUE 1023
#define SPI_MEM_MOSI_DLEN_USR_MOSI_DBITLEN_SHIFT 0
#define SPI_MEM_MOSI_DLEN_USR_MOSI_DBITLEN_VALUE 1023
#define R_SPI_MEM_USER_USR_ADDR_MASK (1U<<30)
#define R_SPI_MEM_USER_USR_DUMMY_MASK (1U<<29)
#define R_SPI_MEM_USER_USR_MISO_MASK (1U<<28)
#define R_SPI_MEM_USER_USR_MOSI_MASK (1U<<27)
#define CMD_PP 2
typedef struct ESP32S3XtsAesState { int unused; } ESP32S3XtsAesState;
typedef struct ESP32S3XtsAesClass {
 bool (*is_manual_enc_enabled)(ESP32S3XtsAesState *);
 bool (*is_ciphertext_spi_visible)(ESP32S3XtsAesState *);
 void (*read_ciphertext)(ESP32S3XtsAesState *,void *,uint32_t *,uint32_t *,uint32_t *);
} ESP32S3XtsAesClass;
#define ESP32S3_XTS_AES_GET_CLASS(s) ((ESP32S3XtsAesClass *)0)
typedef struct ESP32S3SpiState {
 void *spi; int cs_gpio[3]; uint32_t misc,flash_qio_header_bytes;
 uint32_t mem_addr,mem_user,mem_user1,mem_user2,mem_miso_len,mem_mosi_len,data_reg[16];
 ESP32S3XtsAesState *xts_aes;
} ESP32S3SpiState;
typedef struct ESP32S3SpiTransaction {
 uint32_t cmd,cmd_bytes,addr,addr_bytes,dummy_bytes,extra_dummy_bytes;
 void *data; uint32_t tx_bytes,rx_bytes;
} ESP32S3SpiTransaction;
static uint32_t bswap32(uint32_t x) { return __builtin_bswap32(x); }
static unsigned clocks,payload_at;
static uint8_t wire[512],pattern[]={0x5a,0xe1,0x02,0xff,0x91,0x83,0x44,0x76,0x80,0xa2};
static bool flash_fixture;
static uint32_t ssi_transfer(void *bus,uint32_t byte) {
 (void)bus; assert(clocks<sizeof(wire)); wire[clocks]=(uint8_t)byte;
 unsigned index=clocks++;
 if (!flash_fixture) return 0xa0+index;
 return index<payload_at ? 0 : pattern[(index-payload_at)%sizeof(pattern)];
}
static void qemu_set_irq(int irq,int value) { (void)irq;(void)value; }
typedef struct Property { const char *name; unsigned initial; } Property;
#define DEFINE_PROP_UINT32(name,type,field,value) {name,value}
#define DEFINE_PROP_END_OF_LIST() {0,0}
"""

MAIN = r"""
static void clear(bool flash,unsigned header) {
 clocks=0; memset(wire,0xcc,sizeof(wire));flash_fixture=flash;payload_at=1+3+header;
}
static void read_case(unsigned header,unsigned address_bytes,unsigned dummy_bytes) {
 ESP32S3SpiState s={0};s.flash_qio_header_bytes=header;
 s.mem_user=R_SPI_MEM_USER_USR_ADDR_MASK|R_SPI_MEM_USER_USR_MISO_MASK|R_SPI_MEM_USER_USR_DUMMY_MASK;
 s.mem_addr=address_bytes==3 ? 0x00123456 : 0x123456a5;
 s.mem_user1=((address_bytes*8-1)<<26)|(dummy_bytes*8-1);
 s.mem_user2=(7u<<28)|0xeb;s.mem_miso_len=8*8-1;s.misc=2; /* only flash CS0 */
 clear(true,header);esp32s3_spi_begin_transaction(&s);
 assert(!memcmp(s.data_reg,pattern,8));assert(clocks==1+3+header+8);
 assert(wire[0]==0xeb && wire[1]==0x12 && wire[2]==0x34 && wire[3]==0x56);
}
int main(void) {
 assert(esp32s3_spi_properties[0].initial==5);
 read_case(3,3,1); /* is25lp128: no +2 payload displacement */
 read_case(5,3,1); /* Winbond / GigaDevice retains its existing count */
 read_case(3,4,1);read_case(5,4,1); /* address-packed mode byte is counted once */
 ESP32S3SpiState s={0};
 uint8_t tx[8]={0x80,0x90,0,1,0,0xbb,0xcc,0xdd};
 struct { uint8_t before; uint8_t data[2]; uint8_t after[4]; } rx;
 memset(&rx,0x7e,sizeof(rx));clear(false,0);
 esp32s3_spi_txrx_buffer(&s,tx,5,rx.data,2);
 assert(rx.before==0x7e && rx.data[0]==0xa0 && rx.data[1]==0xa1);
 for(unsigned i=0;i<4;i++)assert(rx.after[i]==0x7e);
 assert(clocks==5 && !memcmp(wire,tx,5));
 uint8_t out[5];memset(out,0x7e,sizeof(out));clear(false,0);
 esp32s3_spi_txrx_buffer(&s,tx,2,out,5);
 assert(clocks==5 && wire[0]==0x80 && wire[1]==0x90);
 for(unsigned i=2;i<5;i++)assert(wire[i]==0);
 for(unsigned i=0;i<5;i++)assert(out[i]==0xa0+i);
 clear(false,0);esp32s3_spi_txrx_buffer(&s,NULL,0,out,5);
 assert(clocks==5);for(unsigned i=0;i<5;i++)assert(wire[i]==0 && out[i]==0xa0+i);
 clear(false,0);esp32s3_spi_txrx_buffer(&s,tx,5,NULL,0);assert(clocks==5);
 /* PSRAM-only QIOR must never inherit either flash bridge value. */
 s.mem_user=R_SPI_MEM_USER_USR_ADDR_MASK|R_SPI_MEM_USER_USR_MISO_MASK;
 s.mem_addr=0x123456;s.mem_user1=23u<<26;s.mem_user2=(7u<<28)|0xeb;
 s.mem_miso_len=4*8-1;s.misc=1;
 for(unsigned header=3;header<=5;header+=2) {
  s.flash_qio_header_bytes=header;clear(false,0);esp32s3_spi_begin_transaction(&s);
  assert(clocks==1+3+4);
 }
 /* Ordinary READ has no automatic QIO phase. */
 s.misc=2;s.mem_user2=(7u<<28)|3;clear(false,0);esp32s3_spi_begin_transaction(&s);
 assert(clocks==1+3+4);
 return 0;
}
"""


@unittest.skipUnless(shutil.which("cc"), "C compiler required")
class S3QioFlashHeaderPatchTests(unittest.TestCase):
    def implementation(self):
        source = patched("hw/ssi/esp32s3_spi.c")
        names = ["esp32s3_spi_txrx_buffer", "esp32s3_spi_dummy_cycles", "esp32s3_spi_cs_set",
                 "esp32s3_spi_perform_transaction", "esp32s3_spi_get_addr",
                 "esp32s3_spi_get_dummy", "esp32s3_spi_begin_transaction"]
        table = source[source.index("static Property esp32s3_spi_properties[]"):
                       source.index("static void esp32s3_spi_class_init")]
        return "\n".join(function(source, name) for name in names) + table

    def run_c(self, implementation):
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory) / "test.c", Path(directory) / "test"
            source.write_text(PREFIX + implementation + MAIN)
            result = subprocess.run([shutil.which("cc"), "-std=gnu11", "-O1",
                                     str(source), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return subprocess.run([str(binary)], capture_output=True, text=True)

    def test_real_spi_phase_and_fifo_boundaries(self):
        result = self.run_c(self.implementation())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_independent_regressions_are_rejected(self):
        source = self.implementation()
        changes = [
            ("modeled_dummy < s->flash_qio_header_bytes ?\n"
             "                    s->flash_qio_header_bytes - modeled_dummy : 0;",
             "modeled_dummy < 5 ? 5 - modeled_dummy : 0;"),
            ("if (i < tx_bytes)", "if (byte < tx_bytes)"),
            ("if (i < rx_bytes)", "if (byte < rx_bytes)"),
        ]
        for before, after in changes:
            with self.subTest(regression=before):
                self.assertEqual(source.count(before), 1)
                self.assertNotEqual(self.run_c(source.replace(before, after)).returncode, 0)

    def test_model_configuration_precedes_spi_realization(self):
        source = patched("hw/xtensa/esp32s3.c")
        self.assertIn("flash_size == 16 * MiB ? 3 : 5", source)
        self.assertLess(source.index('"flash-qio-header-bytes"'),
                        source.index("sysbus_realize(SYS_BUS_DEVICE(&ss->spi1)"))


if __name__ == "__main__":
    unittest.main()

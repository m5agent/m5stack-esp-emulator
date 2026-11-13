"""Compile the actual C6 SPI/GPIO paths; chip-select oracles are bus observations."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile
import unittest

from test_c6_spi_data_length_patch import ROOT, STUBS as SPI_STUBS

FIXTURE = Path(__file__).with_name("fixtures") / "c6_spi_chip_select"
DMA_FIXTURE = FIXTURE.with_name("c6_spi_data_length")
PATCH15 = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0015-c6-spi2-data-length.patch"
PATCH16 = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0016-c6-spi2-chip-select-routing.patch"
SPI = "hw/ssi/esp32c3_spi.c"
GPIO = "hw/gpio/esp32_gpio.c"

STUBS = SPI_STUBS.replace(
    'static int esp32_gpio_get_line(int pin) { (void)pin; return 1; }', ''
).replace(
    'uint32_t dma_conf,dma_int_raw,flash_qio_header_bytes;',
    '''uint32_t dma_conf,dma_int_raw,flash_qio_header_bytes,dma_int_ena;
    uint32_t mem_ctrl,mem_ctrl1,mem_ctrl2,mem_clock,mem_rd_st,mem_sus_st;
    uint32_t c6_misc,c6_din_mode,c6_din_num,c6_dout_mode;
    bool m5_cs_active;'''
) + r'''
#include <inttypes.h>
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1u<<(n))
#define HWADDR_PRIx PRIx64
#define SPI1_DEBUG 0
#define SPI1_WARNING 0
#define R_SPI_DMA_CONF 0x30
#define R_SPI_MEM_CMD_USR_MASK (1u<<18)
#define ESP32C3_SPI_BUF_WORDS 16
#define ESP32C3_SPI(p) ((ESP32C3SpiState *)(p))
#define ESP32_GPIO(p) ((Esp32GpioState *)(p))
#define A_GPIO_STRAP 0x38
#define FIELD_DP32(v,r,f,d) (((v)&~R_##r##_##f##_MASK)|(((uint32_t)(d)<<R_##r##_##f##_SHIFT)&R_##r##_##f##_MASK))
typedef uint64_t hwaddr;
typedef void Object;
typedef int ResetType;
typedef struct { uint32_t strap_mode; } Esp32GpioState;
typedef void (*esp32_gpio_out_cb)(void *,int,int);
static void esp32c3_spi_special_command(ESP32C3SpiState *s,uint32_t command) { abort(); }
'''

MAIN = r'''
static unsigned sink_calls,radio_calls,edge_count;
static struct { int pin,level; } edges[64];
static bool sink_selected;
static uint8_t sink_byte;
static void sink(void *opaque,const uint8_t *data,uint32_t length,bool command) {
    assert(length==1);assert(command);sink_calls++;sink_byte=data[0];
    sink_selected=!esp32_gpio_get_line(17);
}
static uint8_t radio(void *opaque,uint8_t byte) {
    assert(!esp32_gpio_get_line(23));radio_calls++;return 0x5a;
}
static void edge(void *opaque,int pin,int level) {
    assert(edge_count<ARRAY_SIZE(edges));edges[edge_count].pin=pin;
    edges[edge_count++].level=level;
}
static void reg_write(unsigned address,uint32_t value) {
    esp32_gpio_write(NULL,address,value,4);
}
static void gpio_level(int pin,int value) { reg_write(value?8:12,1u<<pin); }
static void gpio_enable(int pin,bool enabled) { reg_write(enabled?0x24:0x28,1u<<pin); }
static void route(int pin,unsigned cfg) { reg_write(0x554+4*pin,cfg); }
static void misc(ESP32C3SpiState *s,unsigned value) { esp32c3_spi_write(s,0x20,value,4); }
static void send(ESP32C3SpiState *s) {
    s->mem_user=R_SPI_MEM_USER_USR_MOSI_MASK;s->mem_mosi_len=7;
    s->mem_miso_len=0;((uint8_t *)s->data_reg)[0]=0x28;
    esp32c3_spi_write(s,0,BIT(24),4);
}
static void selected_once(void) {
    assert(sink_calls==1&&sink_selected&&sink_byte==0x28&&!radio_calls);
}
static void no_panel(void) { assert(!sink_calls); }
static void two_edges(int pin) {
    assert(edge_count==2);assert(edges[0].pin==pin&&edges[0].level==0);
    assert(edges[1].pin==pin&&edges[1].level==1);
}
int main(int argc,char **argv) {
    assert(argc==2);int test=atoi(argv[1]);ESPGdmaState gdma={0};
    ESP32C3SpiState s={.m5_spi2=true,.gdma=&gdma,.m5_slave_cs=23,
        .m5_slave_transfer=radio,.m5_sink=sink};
    esp32c3_spi_reset_hold(&s,0);
    for(unsigned pin=0;pin<32;pin++)route(pin,128);
    for(int pin=16;pin<=23;pin++) {gpio_enable(pin,true);gpio_level(pin,1);}
    gpio_level(16,0);misc(&s,0x3e);
    esp32_gpio_add_out_listener(17,edge,NULL);esp32_gpio_add_out_listener(23,edge,NULL);
    switch(test) {
    case 0: /* Both devices deselected: a display-off byte must go nowhere. */
        send(&s);no_panel();assert(!radio_calls);break;
    case 1: /* Real manual panel selection remains supported. */
        gpio_level(17,0);edge_count=0;send(&s);selected_once();assert(!edge_count);break;
    case 2: /* Existing manual radio selection must not reach the panel. */
        gpio_level(23,0);edge_count=0;send(&s);no_panel();assert(radio_calls==1&&!edge_count);break;
    case 3: /* CS0 is signal 68, not the GPIO_OUT register's high level. */
        route(17,68);edge_count=0;send(&s);selected_once();two_edges(17);
        assert(esp32_gpio_get_line(17)==1);break;
    case 4: /* CS1 route with only CS0 enabled must stay deselected. */
        route(17,101);edge_count=0;send(&s);no_panel();assert(!edge_count);break;
    case 5:
        route(17,68);misc(&s,0x3f);edge_count=0;send(&s);no_panel();assert(!edge_count);break;
    case 6: /* Output inversion alone makes this active-low panel unselected. */
        route(17,68|BIT(8));edge_count=0;send(&s);no_panel();
        assert(esp32_gpio_get_line(17)==0);break;
    case 7: /* GPIO inversion and SPI positive polarity cancel on the wire. */
        route(17,68|BIT(8));misc(&s,0x3e|BIT(7));edge_count=0;
        send(&s);selected_once();two_edges(17);break;
    case 8: /* Positive CS polarity alone is not active-low panel selection. */
        route(17,68);misc(&s,0x3e|BIT(7));edge_count=0;
        send(&s);no_panel();assert(esp32_gpio_get_line(17)==0);break;
    case 9: /* OEN_SEL chooses GPIO_ENABLE, which is disabled here. */
        route(17,68|BIT(9));gpio_enable(17,false);edge_count=0;
        send(&s);no_panel();assert(!edge_count&&esp32_gpio_get_line(17)==1);break;
    case 10:
        route(17,68|BIT(9));edge_count=0;send(&s);selected_once();two_edges(17);break;
    case 11: /* Peripheral OE drives CS even when GPIO_ENABLE is zero. */
        route(17,68);gpio_enable(17,false);edge_count=0;
        send(&s);selected_once();two_edges(17);break;
    case 12: /* OEN inversion tri-states the otherwise enabled peripheral. */
        route(17,68|BIT(10));edge_count=0;send(&s);no_panel();assert(!edge_count);break;
    case 13: /* Held CS has one falling edge, and MISC clear releases it. */
        route(17,68);misc(&s,0x3e|BIT(30));edge_count=0;
        send(&s);assert(esp32_gpio_get_line(17)==0);send(&s);
        assert(sink_calls==2&&edge_count==1);misc(&s,0x3e);two_edges(17);
        assert(esp32_gpio_get_line(17)==1);break;
    case 14: /* Reset must deassert held CS and restore only CS0 enabled. */
        route(17,68);misc(&s,0x3e|BIT(30));edge_count=0;send(&s);
        esp32c3_spi_reset_hold(&s,0);two_edges(17);
        assert(s.c6_misc==0x3e&&!s.m5_cs_active&&esp32_gpio_get_line(17)==1);break;
    case 15: /* Hardware CS1 routes the bytes to the radio, never the panel. */
        route(23,101);misc(&s,0x3d);edge_count=0;send(&s);
        no_panel();assert(radio_calls==1&&s.m5_rx_from_slave);two_edges(23);break;
    case 16: case 17: case 18: case 19: /* Independent CS2..CS5 signal numbers. */
        {unsigned cs=(unsigned)test-14;route(17,100+cs);
        misc(&s,0x3f&~BIT(cs));edge_count=0;send(&s);selected_once();two_edges(17);break;}
    case 20: /* Unconnected output signals do not select the panel. */
        route(17,42);edge_count=0;send(&s);no_panel();assert(!edge_count);break;
    case 21: /* Remapping held CS back to GPIO releases it immediately. */
        route(17,68);misc(&s,0x3e|BIT(30));edge_count=0;send(&s);
        route(17,128);two_edges(17);send(&s);assert(sink_calls==1);break;
    case 22: /* Failed TX DMA is rejected before any CS edge or slave byte. */
        route(17,68);out_bound=false;s.dma_conf=DMA_TX_ENA;edge_count=0;
        send(&s);assert(!edge_count&&!sink_calls&&!radio_calls&&!clocked);break;
    case 23: /* SPI1 still uses SSI GPIO and does not drive C6 matrix signals. */
        s.m5_spi2=false;s.m5_sink=NULL;s.m5_slave_transfer=NULL;
        s.mem_user=R_SPI_MEM_USER_USR_MOSI_MASK;s.mem_user2=0;s.mem_mosi_len=7;
        cs_edges=0;edge_count=0;esp32c3_spi_begin_transaction(&s);
        assert(cs_edges==2&&!edge_count&&clocked==1);break;
    default:return 2;
    }
    puts("PASS actual C6 SPI and GPIO chip select");return 0;
}
'''

BEFORE_PASS = {1, 2, 22, 23}
CASES = 24


def apply(directory, patch, reverse_check=False):
    args = ["git", "apply", "--include=" + SPI, "--include=" + GPIO]
    if reverse_check:
        args += ["--reverse", "--check"]
    result = subprocess.run([*args, str(patch)], cwd=directory, capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class C6SpiChipSelectTests(unittest.TestCase):
    def test_actual_controller_gpio_matrix_before_and_after(self):
        self.assertTrue(PATCH15.is_file(), "C6 0015 model patch required")
        self.assertTrue(PATCH16.is_file(), "C6 0016 model patch required")
        with tempfile.TemporaryDirectory(prefix="m5-c6-cs-host-") as temp:
            directory = Path(temp)
            for name in (SPI, GPIO):
                (directory / name).parent.mkdir(parents=True, exist_ok=True)
            (directory / SPI).write_text((DMA_FIXTURE / "preimage.c").read_text() +
                                        (FIXTURE / "spi-register-preimage.c").read_text())
            (directory / GPIO).write_bytes((FIXTURE / "gpio-preimage.c").read_bytes())
            apply(directory, PATCH15)
            sources = [("before", (directory / SPI).read_text(), (directory / GPIO).read_text())]
            apply(directory, PATCH16)
            apply(directory, PATCH16, reverse_check=True)
            sources.append(("after", (directory / SPI).read_text(), (directory / GPIO).read_text()))
            for label, spi, gpio in sources:
                source, binary = directory / (label + ".c"), directory / label
                source.write_text(STUBS + (FIXTURE / "registers.h").read_text() + gpio + spi + MAIN)
                result = subprocess.run(
                    ["cc", "-std=c11", "-g", "-O1", "-Wall", "-Wextra", "-Werror",
                     "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-sign-compare",
                     "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                     str(source), "-o", str(binary)], capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:abort_on_error=0",
                           UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
                for case in range(CASES):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], env=env,
                                                capture_output=True, text=True, timeout=10)
                        if label == "before" and case not in BEFORE_PASS:
                            self.assertNotEqual(result.returncode, 0, result.stdout)
                            self.assertIn("Assertion", result.stderr)
                        else:
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertIn("PASS actual C6 SPI and GPIO chip select", result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch15", type=Path, default=PATCH15)
    parser.add_argument("--patch16", type=Path, default=PATCH16)
    args, remaining = parser.parse_known_args()
    PATCH15, PATCH16 = args.patch15.resolve(), args.patch16.resolve()
    unittest.main(argv=[__file__, *remaining])

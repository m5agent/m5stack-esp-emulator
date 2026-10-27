"""Exercise the actual classic SPI DMA/FIFO patch without local build caches."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0050-esp32-spi-panel-dma-transaction.patch"
PRELUDE = ROOT / "patches/qemu-unit-runtime/0001-reconstructed-xtensa-source.patch"


def extract_function(text: str, name: str) -> str:
    start = text.index("static void " + name + "(")
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        depth += (text[index] == "{") - (text[index] == "}")
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError("unterminated source function")


def actual_implementation() -> str:
    added = "\n".join(line[1:] for line in PRELUDE.read_text().splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    helper = extract_function(added, "esp32_spi_m5_dma_panel")
    sections = PATCH.read_text().split("\n@@ ")[1:]
    dma_hunk = sections[0].split("\n", 1)[1]
    old = "\n".join(line[1:] for line in dma_hunk.splitlines() if line[:1] in {" ", "-"})
    new = "\n".join(line[1:] for line in dma_hunk.splitlines() if line[:1] in {" ", "+"})
    old = old[old.index("static void esp32_spi_m5_dma_panel("):]
    new = new[new.index("static void esp32_spi_m5_dma_panel("):]
    if old not in helper:
        raise AssertionError("DMA patch no longer matches its actual source preimage")
    helper = helper.replace(old, new, 1)
    transaction_hunk = next(section.split("\n", 1)[1] for section in sections
                            if "esp32_spi_transaction" in section.split("\n", 1)[0])
    transaction = "\n".join(line[1:] for line in transaction_hunk.splitlines()
                            if line[:1] in {" ", "+"})
    transaction = transaction[transaction.index("    if (!s->m5_panel)"):]
    arm = next(line[1:] for line in PATCH.read_text().splitlines()
               if line.startswith("+        s->m5_dma_out_link = value"))
    return (helper + "\nstatic void arm(Esp32SpiState *s, uint32_t value) {\n" + arm
            + "\n}\nstatic void transfer(Esp32SpiState *s, Esp32SpiTransaction *t) {\n"
            + transaction + "\n}\n")


STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define ESP32_SPI_BUF_WORDS 16
#define MIN(a,b) ((uint64_t)(a) < (uint64_t)(b) ? (uint64_t)(a) : (uint64_t)(b))
typedef struct {} M5SpiPanelState;
typedef struct {
    uint32_t data_reg[16], m5_dma_out_link;
    M5SpiPanelState *m5_panel;
    int m5_dc_pin;
} Esp32SpiState;
typedef struct { uint32_t *data; int data_tx_bytes, data_rx_bytes; } Esp32SpiTransaction;
static uint8_t ram[1 << 20], panel[16384], wire[16384];
static unsigned panel_length, wire_length, descriptor_reads;
static int dc_level = 1;
static bool expected_command;
static Esp32SpiState *current;
static void *allocation;
static size_t allocation_size;
static void *g_malloc(size_t size) {
    assert(!allocation); allocation = malloc(size); allocation_size = size; return allocation;
}
static void g_free(void *pointer) { assert(pointer == allocation); free(pointer); allocation = NULL; }
static void cpu_physical_memory_read(uint32_t address, void *target, size_t length) {
    assert(address >= 0x3ff00000U && (uint64_t)address + length <= 0x40000000ULL);
    if (length == 12) descriptor_reads++;
    memcpy(target, ram + (address & 0xfffff), length);
}
static int esp32_gpio_get_line(int pin) { assert(pin == 15); return dc_level; }
static void esp32_spi_txrx_buffer(Esp32SpiState *s, void *buf, int tx, int rx) {
    assert(s == current && tx >= 0 && rx >= 0);
    uintptr_t address = (uintptr_t)buf, first = (uintptr_t)s->data_reg;
    if (allocation && buf == allocation) assert((unsigned)tx <= allocation_size && !rx);
    else assert(address >= first && address + (unsigned)(tx > rx ? tx : rx) <= first + 64);
    assert(wire_length + (unsigned)tx <= sizeof(wire));
    memcpy(wire + wire_length, buf, tx); wire_length += tx;
}
static void m5_spi_panel_write(M5SpiPanelState *s, const uint8_t *buf, uint32_t length, bool command) {
    assert(s == current->m5_panel && command == expected_command);
    assert(panel_length + length <= sizeof(panel));
    memcpy(panel + panel_length, buf, length); panel_length += length;
}
"""

MAIN = r"""
static void clear_output(void) { panel_length = wire_length = descriptor_reads = 0; }
static void descriptor(unsigned at, unsigned length, bool eof, unsigned buffer, unsigned next) {
    uint32_t words[] = { length | (length << 12) | (eof ? 1U << 30 : 0) | 1U << 31,
                         0x3ff00000U + buffer, next ? 0x3ff00000U + next : 0 };
    memcpy(ram + at, words, sizeof(words));
}
int main(void) {
    M5SpiPanelState panel_state;
    Esp32SpiState state = { .m5_panel = &panel_state, .m5_dc_pin = 15 };
    current = &state;
    for (unsigned i = 0; i < 64; i++) ((uint8_t *)state.data_reg)[i] = i;
    for (unsigned i = 0; i < 128; i++) ram[0x2000 + i] = i ^ 0x83;
    for (unsigned i = 0; i < 192; i++) ram[0x4000 + i] = i ^ 0x5a;
    descriptor(0x100, 128, false, 0x2000, 0x120);
    descriptor(0x120, 192, true, 0x4000, 0);
    Esp32SpiTransaction transaction = { .data = state.data_reg, .data_tx_bytes = 300 };
    arm(&state, (1U << 29) | 0x100);
    assert(panel_length == 0 && wire_length == 0); /* OUT_LINK must not flush. */
    transfer(&state, &transaction);
    assert(state.m5_dma_out_link == 0 && panel_length == 300 && wire_length == 300);
    assert(!memcmp(panel, ram + 0x2000, 128));
    assert(!memcmp(panel + 128, ram + 0x4000, 172)); /* MOSI length bounds the last descriptor. */
    assert(!memcmp(panel, wire, 300) && descriptor_reads == 2);
    clear_output();
    transaction.data_tx_bytes = 5;
    transfer(&state, &transaction); /* The next FIFO transfer must not replay stale DMA. */
    assert(panel_length == 5 && !memcmp(panel, state.data_reg, 5));
    clear_output();
    transaction.data_tx_bytes = 250;
    transfer(&state, &transaction);
    assert(panel_length == 250 && wire_length == 250);
    for (unsigned i = 0; i < 250; i++) assert(panel[i] == (i % 64));
    clear_output();
    transaction.data = &state.data_reg[8]; transaction.data_tx_bytes = 97;
    transfer(&state, &transaction);
    for (unsigned i = 0; i < 97; i++) assert(panel[i] == 32 + i % 32);
    clear_output();
    dc_level = 0; expected_command = true;
    transaction.data = state.data_reg; transaction.data_tx_bytes = 7;
    transfer(&state, &transaction); assert(panel_length == 7);
    clear_output();
    descriptor(0x100, 20, true, 0x2000, 0);
    arm(&state, (1U << 29) | 0x100); transaction.data_tx_bytes = 100;
    transfer(&state, &transaction);
    assert(panel_length == 20 && wire_length == 20); /* Short chains never invent a FIFO tail. */
    clear_output();
    descriptor(0x100, 0, false, 0x2000, 0x100);
    arm(&state, (1U << 29) | 0x100);
    transfer(&state, &transaction);
    assert(panel_length == 0 && wire_length == 0 && descriptor_reads == 4096);
    clear_output();
    arm(&state, (1U << 29) | 0x100); arm(&state, 0);
    state.m5_panel = NULL; transaction.data_tx_bytes = 3;
    transfer(&state, &transaction);
    assert(panel_length == 0 && wire_length == 3 && descriptor_reads == 0);
    return 0;
}
"""


class Core2SpiDmaPatchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_actual_dma_and_fifo_code_preserves_bytes_and_transaction_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "spi.c"
            binary = Path(directory) / "spi"
            source.write_text(STUBS + actual_implementation() + MAIN)
            result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                                     str(source), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)


if __name__ == "__main__":
    unittest.main()

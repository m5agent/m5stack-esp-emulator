"""Compile the actual pending-IRQ remap patch and replay its level semantics."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0064-esp32-intmatrix-pending-irq-remap.patch"
)


def hunk_postimage(file_marker: str, hunk_marker: str) -> str:
    text = PATCH.read_text()
    start = text.index(file_marker)
    end = text.find("\n--- a/", start + len(file_marker))
    section = text[start:] if end < 0 else text[start:end]
    hunk_at = section.index(hunk_marker)
    hunk_start = section.rfind("\n@@ ", 0, hunk_at)
    if hunk_start < 0:
        raise AssertionError("patch hunk header not found")
    hunk_end = section.find("\n@@ ", hunk_at)
    hunk = section[hunk_start:] if hunk_end < 0 else section[hunk_start:hunk_end]
    lines = hunk.splitlines()[1:]
    return "\n".join(
        line[1:] for line in lines if line[:1] in {" ", "+"}
    )


def extract_function(text: str, name: str) -> str:
    start = text.index("static void " + name + "(")
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        depth += (text[index] == "{") - (text[index] == "}")
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError("unterminated function")


STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

#define ESP32_CPU_COUNT 2
#define ESP32_INT_MATRIX_INPUTS 69
#define ESP32_INTMATRIX(opaque) ((Esp32IntMatrixState *)(opaque))

typedef struct {
    int nextint;
    int extint[8];
} Esp32CpuConfig;

typedef struct {
    Esp32CpuConfig *config;
} Esp32CpuEnv;

typedef struct {
    Esp32CpuEnv env;
} XtensaCPU;

typedef int *qemu_irq;

typedef struct {
    qemu_irq *outputs[ESP32_CPU_COUNT];
    uint8_t irq_map[ESP32_CPU_COUNT][ESP32_INT_MATRIX_INPUTS];
    uint8_t irq_level[ESP32_INT_MATRIX_INPUTS];
    XtensaCPU *cpu[ESP32_CPU_COUNT];
} Esp32IntMatrixState;

typedef struct {
    uint32_t trans_done;
    uint32_t trans_inten;
    qemu_irq irq;
} Esp32SpiState;

static void qemu_set_irq(qemu_irq irq, int level)
{
    assert(irq != NULL);
    *irq = level;
}

static char *getenv(const char *name)
{
    (void) name;
    return NULL;
}
"""


MAIN = r"""
int main(void)
{
    int irq[4] = { -1, -1, -1, -1 };
    qemu_irq outputs0[] = { &irq[0], &irq[1] };
    qemu_irq outputs1[] = { &irq[2], &irq[3] };
    Esp32CpuConfig cpu_config = {
        .nextint = 2,
        .extint = { 4, 5 },
    };
    XtensaCPU cpu0 = { .env.config = &cpu_config };
    XtensaCPU cpu1 = { .env.config = &cpu_config };
    Esp32IntMatrixState matrix = {
        .outputs = { outputs0, outputs1 },
        .cpu = { &cpu0, &cpu1 },
    };

    for (int cpu = 0; cpu < ESP32_CPU_COUNT; cpu++) {
        for (int input = 0; input < ESP32_INT_MATRIX_INPUTS; input++) {
            matrix.irq_map[cpu][input] = 6;
        }
    }
    esp32_intmatrix_irq_handler(&matrix, 31, 1);
    assert(irq[0] == 0 && irq[1] == 0 && irq[2] == 0 && irq[3] == 0);

    matrix.irq_map[0][31] = 5;
    esp32_intmatrix_update_outputs(&matrix);
    assert(irq[0] == 0 && irq[1] == 1 && irq[2] == 0 && irq[3] == 0);

    esp32_intmatrix_irq_handler(&matrix, 32, 1);
    matrix.irq_map[0][32] = 5;
    esp32_intmatrix_update_outputs(&matrix);
    esp32_intmatrix_irq_handler(&matrix, 31, 0);
    assert(irq[1] == 1);
    esp32_intmatrix_irq_handler(&matrix, 32, 0);
    assert(irq[1] == 0);

    int transaction_irq = -1;
    Esp32SpiState spi = {
        .irq = &transaction_irq,
    };
    spi.trans_done = 1;
    spi.trans_inten = 0;
    esp32_spi_update_irq(&spi);
    assert(transaction_irq == 0);
    spi.trans_inten = 1;
    esp32_spi_update_irq(&spi);
    assert(transaction_irq == 1);
    spi.trans_done = 0;
    esp32_spi_update_irq(&spi);
    assert(transaction_irq == 0);
    return 0;
}
"""


class Core2IntMatrixPendingRemapPatchTests(unittest.TestCase):
    @unittest.skipUnless(
        shutil.which("cc"), "C compiler required"
    )
    def test_pending_level_is_forwarded_when_mapping_changes(self):
        matrix_hunk = hunk_postimage(
            "--- a/hw/xtensa/esp32_intc.c",
            "esp32_intmatrix_update_outputs",
        )
        spi_hunk = hunk_postimage(
            "--- a/hw/ssi/esp32_spi.c",
            "esp32_spi_update_irq",
        )
        matrix_update = extract_function(
            matrix_hunk, "esp32_intmatrix_update_outputs"
        )
        matrix_handler = extract_function(
            matrix_hunk, "esp32_intmatrix_irq_handler"
        )
        spi_update = extract_function(spi_hunk, "esp32_spi_update_irq")
        source = (
            STUBS
            + "\n"
            + matrix_update
            + "\n"
            + matrix_handler
            + "\n"
            + spi_update
            + "\n"
            + MAIN
        )
        with tempfile.TemporaryDirectory() as directory:
            c_path = Path(directory) / "pending_irq.c"
            binary = Path(directory) / "pending_irq"
            c_path.write_text(source)
            compile_result = subprocess.run(
                [
                    shutil.which("cc"),
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(c_path),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            subprocess.run(
                [str(binary)],
                check=True,
                capture_output=True,
                timeout=5,
            )

    def test_patch_recomputes_mapping_and_models_spi_status(self):
        text = PATCH.read_text()
        self.assertIn("uint8_t irq_level[ESP32_INT_MATRIX_INPUTS];", text)
        self.assertIn("esp32_intmatrix_update_outputs(s);", text)
        self.assertIn("s->trans_done && s->trans_inten", text)
        self.assertIn("FIELD_DP32(0, SPI_SLAVE, TRANS_DONE", text)


if __name__ == "__main__":
    unittest.main()

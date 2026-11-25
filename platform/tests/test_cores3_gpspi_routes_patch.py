"""Run the locked GP-SPI routing functions against independent CS/host inputs."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0041-cores3-gpspi-host-routes.patch"

SHIM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define BIT(n) (1u << (n))
#define ESP32_GPIO_MUX_GPIO_MATRIX 1
typedef struct {
    unsigned out_sel, mux_path, override_mask;
    bool oen_sel, enable_reg, oen_inv, out_inv;
} Esp32GpioPadSnapshot;
typedef struct {
    int cs0_signal, clk_pin, clk_signal, mosi_pin, mosi_signal;
} M5GpspiPanelRoute;
typedef struct Esp32s3GpspiState {
    struct Esp32s3GpspiState *board_bus;
    const M5GpspiPanelRoute *panel_route;
    uint32_t regs[0x40], gdma_periph;
    int panel_cs_pin, panel_cs_level, active_slave;
    struct { int gdma_periph; } slaves[2];
} Esp32s3GpspiState;

static Esp32GpioPadSnapshot pad = {
    .out_sel = 71, .mux_path = ESP32_GPIO_MUX_GPIO_MATRIX
};
static int clk_route = 66, mosi_route = 68;
static int gpio;
static int *esp32_gpio_get_controller(bool s3) {
    assert(s3);
    return &gpio;
}
static bool esp32_gpio_pad_snapshot(int *controller, unsigned pin,
                                   Esp32GpioPadSnapshot *out) {
    assert(controller == &gpio && pin == 3);
    *out = pad;
    return true;
}
static int esp32_gpio_matrix_out_signal(int pin, bool s3) {
    assert(s3 && (pin == 36 || pin == 37));
    return pin == 36 ? clk_route : mosi_route;
}
'''

CONTROL = r'''
int main(void) {
    const M5GpspiPanelRoute spi2_route = {110, 36, 101, 37, 103};
    const M5GpspiPanelRoute spi3_route = {71, 36, 66, 37, 68};
    Esp32s3GpspiState spi2 = {
        .board_bus = &spi2, .panel_route = &spi2_route, .gdma_periph = 0,
        .panel_cs_pin = 3, .panel_cs_level = 1, .active_slave = -1,
        .slaves = {{-1}, {2}}
    };
    Esp32s3GpspiState spi3 = {
        .board_bus = &spi2, .panel_route = &spi3_route, .gdma_periph = 1
    };
    assert(gpspi_panel_selected(&spi3, true));
    assert(!gpspi_panel_selected(&spi3, false));
    assert(!gpspi_panel_selected(&spi2, true));
    spi3.regs[R_MISC / 4] = MISC_CS0_DIS;
    assert(!gpspi_panel_selected(&spi3, true));
    spi3.regs[R_MISC / 4] = MISC_CK_DIS;
    assert(!gpspi_panel_selected(&spi3, true));
    spi3.regs[R_MISC / 4] = MISC_CS0_POL;
    assert(!gpspi_panel_selected(&spi3, true));
    pad.out_inv = true;
    assert(gpspi_panel_selected(&spi3, true));
    pad.oen_sel = true;
    assert(!gpspi_panel_selected(&spi3, true));
    pad.enable_reg = true;
    mosi_route = 103;
    assert(!gpspi_panel_selected(&spi3, true));
    mosi_route = 68;
    assert(gpspi_panel_selected(&spi3, true));

    pad.out_sel = 256;
    assert(!gpspi_panel_selected(&spi2, true));
    spi2.panel_cs_level = 0;
    assert(gpspi_panel_selected(&spi2, true));
    assert(gpspi_active_dma_periph(&spi2) == 0);
    assert(gpspi_active_dma_periph(&spi3) == 1);
    spi2.active_slave = 0;       /* Shared SD, bound to the transferring host. */
    assert(gpspi_active_dma_periph(&spi2) == 0);
    assert(gpspi_active_dma_periph(&spi3) == 1);
    spi2.active_slave = 1;       /* Preserve explicit legacy slave overrides. */
    assert(gpspi_active_dma_periph(&spi3) == 2);
}
'''


class CoreS3GpspiRoutes(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler is required")
    def test_cs_selection_and_per_host_dma(self):
        patch = PATCH.read_text(encoding="utf-8")
        controller = patch.split("diff --git ", 2)[1]
        postimage = "\n".join(
            row[1:] for row in controller.splitlines()
            if row.startswith((" ", "+")) and not row.startswith("+++")
        )
        macros = "\n".join(
            re.findall(r"^#define (?:R_MISC|MISC_(?:CS0_DIS|CS0_POL|CK_DIS))\s+.+$",
                       postimage, flags=re.MULTILINE)
        )
        functions = []
        for name in ("gpspi_panel_selected", "gpspi_active_dma_periph"):
            body = re.search(rf"^static \w+ {name}\(.+?^\}}$", postimage,
                             re.MULTILINE | re.DOTALL)
            self.assertIsNotNone(body, name)
            functions.append(body.group(0))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "routes.c"
            binary = source.with_suffix("")
            source.write_text("\n".join((SHIM, macros, *functions, CONTROL)), encoding="utf-8")
            subprocess.run(["cc", "-std=c11", "-Wall", "-Werror", source, "-o", binary], check=True)
            subprocess.run([binary], check=True)

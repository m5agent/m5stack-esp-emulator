"""Compile the actual board wiring patch; firmware tests use Device Service."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PRELUDE = ROOT / "patches/qemu-unit-runtime/0001-reconstructed-xtensa-source.patch"
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0049-core2-offline-wifi-controller.patch"


def prelude_wiring() -> str:
    """Recover this complete postimage block from the source prelude."""
    text = PRELUDE.read_text()
    marker = "@@ -762,17 +924,30 @@ static void esp32_machine_init_openeth"
    block = text[text.index(marker):].split("\n@@ ", 1)[0]
    lines = block.splitlines()[1:]
    postimage = "\n".join(line[1:] for line in lines if line[:1] in {" ", "+"})
    postimage = postimage.split("\nstatic void esp32_machine_init_sd", 1)[0]
    return """static void esp32_machine_init_openeth(Esp32SocState *ss)
{
    SysBusDevice *sbd;
    MemoryRegion *sys_mem = get_system_memory();
    hwaddr reg_base = DR_REG_EMAC_BASE;
""" + postimage + "\n"


STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef uint64_t hwaddr;
typedef int qemu_irq;
typedef int MemoryRegion;
typedef struct DeviceState {
    int kind;
    bool realized, radio, host_backend;
    int timers;
} DeviceState;
typedef DeviceState SysBusDevice;
typedef struct Esp32SocState { DeviceState *eth, *wifi_dev; int intmatrix; } Esp32SocState;
#define TYPE_ESP32_WIFI "misc.esp32_wifi"
#define M5_BOARD_NONE 0
#define M5_BOARD_CORE2 1
#define DR_REG_EMAC_BASE 0x3ff69000
#define DR_REG_WIFI_BASE 0x3ff73000
#define ETS_ETH_MAC_INTR_SOURCE 38
#define ETS_WIFI_MAC_INTR_SOURCE 0
#define SYS_BUS_DEVICE(dev) (dev)
#define DEVICE(dev) (dev)
#define OBJECT(dev) (dev)
static int m5_board, error_fatal, map_count, irq_count, create_count;
static bool wired_requested, wifi_requested;
static DeviceState wired, wifi, fallback;
static MemoryRegion system_memory;
static MemoryRegion *get_system_memory(void) { return &system_memory; }
static qemu_irq qdev_get_gpio_in(void *dev, int index) { assert(dev); return index; }
static DeviceState *qemu_create_nic_device(const char *type, bool defaults, void *alias) {
    assert(defaults && !alias);
    if (!strcmp(type, "open_eth")) return wired_requested ? &wired : NULL;
    assert(!strcmp(type, TYPE_ESP32_WIFI));
    return wifi_requested ? &wifi : NULL;
}
static DeviceState *qdev_new(const char *type) {
    assert(!strcmp(type, TYPE_ESP32_WIFI));
    create_count++;
    return &fallback;
}
static void sysbus_realize_and_unref(SysBusDevice *dev, int *error) {
    assert(error == &error_fatal);
    dev->realized = true;
    if (dev->kind == 2) { dev->radio = true; dev->timers = 2; }
}
static void sysbus_connect_irq(SysBusDevice *dev, int output, qemu_irq irq) {
    assert(dev->realized && output == 0);
    if (dev->kind == 2) { assert(irq == ETS_WIFI_MAC_INTR_SOURCE); irq_count++; }
    else assert(irq == ETS_ETH_MAC_INTR_SOURCE);
}
static MemoryRegion *sysbus_mmio_get_region(SysBusDevice *dev, int index) {
    assert(dev->realized && (index == 0 || index == 1)); return &system_memory;
}
static void memory_region_add_subregion(MemoryRegion *mem, hwaddr address, MemoryRegion *sub) {
    assert(mem && sub && (address == DR_REG_EMAC_BASE || address == DR_REG_EMAC_BASE + 0x400));
}
static void esp32_soc_add_periph_device(MemoryRegion *mem, DeviceState *dev, hwaddr address) {
    assert(mem && dev->realized && address == DR_REG_WIFI_BASE); map_count++;
}
static void object_property_set_bool(DeviceState *dev, const char *name, bool value, int *error) {
    assert(dev->realized && !strcmp(name, "radio-enabled") && !value && error == &error_fatal);
    dev->radio = false; dev->timers = 0;
}
"""

MAIN = r"""
static void run_case(int board, bool wired_on, bool wifi_on) {
    Esp32SocState soc = {0};
    m5_board = board; wired_requested = wired_on; wifi_requested = wifi_on;
    map_count = irq_count = create_count = 0;
    wired = (DeviceState){ .kind = 1, .host_backend = wired_on };
    wifi = (DeviceState){ .kind = 2, .host_backend = wifi_on };
    fallback = (DeviceState){ .kind = 2 };
    esp32_machine_init_openeth(&soc);
    assert((soc.eth != NULL) == wired_on);
    if (wifi_on) {
        assert(soc.wifi_dev == &wifi && wifi.radio && wifi.host_backend && wifi.timers == 2);
        assert(map_count == 1 && irq_count == 1 && create_count == 0);
    } else if (board == M5_BOARD_CORE2) {
        assert(soc.wifi_dev == &fallback && fallback.realized);
        assert(!fallback.radio && !fallback.host_backend && fallback.timers == 0);
        assert(map_count == 1 && irq_count == 1 && create_count == 1);
    } else {
        assert(!soc.wifi_dev && map_count == 0 && irq_count == 0 && create_count == 0);
    }
}
int main(void) {
    for (int board = M5_BOARD_NONE; board <= M5_BOARD_CORE2; board++)
        for (int wired_on = 0; wired_on < 2; wired_on++)
            for (int wifi_on = 0; wifi_on < 2; wifi_on++)
                run_case(board, wired_on, wifi_on);
    return 0;
}
"""


class Core2OfflineWifiPatchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and Git required")
    def test_replayed_c_wires_offline_mac_and_preserves_explicit_network(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            board = temporary / "hw/xtensa/esp32.c"
            board.parent.mkdir(parents=True)
            original = prelude_wiring()
            board.write_text(original)
            subprocess.run(["git", "apply", str(PATCH)], cwd=temporary,
                           check=True, capture_output=True)
            harness = temporary / "controller.c"
            binary = temporary / "controller"
            harness.write_text(STUBS + board.read_text() + MAIN)
            subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(harness), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)
            subprocess.run(["git", "apply", "--reverse", str(PATCH)], cwd=temporary,
                           check=True, capture_output=True)
            self.assertEqual(board.read_text(), original)


if __name__ == "__main__":
    unittest.main()

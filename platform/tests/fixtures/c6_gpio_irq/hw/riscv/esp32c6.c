/*
 * ESP32-C6 SoC and machine
 *
 * Copyright (c) 2026 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */
#include "qemu/osdep.h"
#include "hw/qdev-clock.h"
#include "qemu/log.h"
#include "qemu/error-report.h"
#include "hw/qdev-properties.h"
#include "qemu/units.h"
#include "qemu/datadir.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "hw/hw.h"
#include "hw/boards.h"
#include "hw/loader.h"
#include "hw/riscv/riscv_hart.h"
#include "target/riscv/esp_cpu.h"
#include "hw/riscv/boot.h"
#include "hw/riscv/numa.h"
#include "sysemu/device_tree.h"
#include "sysemu/sysemu.h"
#include "sysemu/kvm.h"
#include "sysemu/runstate.h"
#include "sysemu/reset.h"
#include "net/net.h"
#include "elf.h"
#include "exec/address-spaces.h"
#include "hw/misc/esp32c6_reg.h"
#include "hw/misc/esp32c6_cache.h"
#include "hw/misc/esp32c6_pcr.h"
#include "hw/misc/esp32c6_lp.h"
#include "hw/misc/esp32c6_spi_mem.h"
#include "hw/misc/esp32c6_i2c_ana_mst.h"
#include "hw/misc/esp32c6_jtag.h"
#include "hw/misc/esp32c6_modem.h"
#include "hw/misc/unimp.h"
#include "hw/char/esp32c6_uart.h"
#include "hw/gpio/esp32c6_gpio.h"
#include "hw/nvram/esp32c6_efuse.h"
#include "hw/riscv/esp32c6_clk.h"
#include "hw/riscv/esp32c6_intmatrix.h"
#include "hw/misc/esp32c6_intpri.h"
#include "hw/misc/esp32c6_sha.h"
#include "hw/i2c/esp32_i2c.h"
#include "hw/misc/esp32c6_board_i2c.h"
#include "hw/misc/esp32c6_nesso_panel.h"
#include "hw/misc/esp32c6_rmt.h"
#include "hw/misc/esp32c6_soft_i2c.h"
#include "hw/misc/esp32c6_sx1262.h"
#include "hw/misc/esp32c6_i2s.h"
#include "hw/misc/esp32_ledc.h"
#include "hw/timer/esp32c6_timg.h"
#include "hw/timer/esp32c6_systimer.h"
#include "hw/ssi/esp32c6_spi.h"
#include "hw/ssi/esp32c3_spi.h"
#include "hw/dma/esp32c6_gdma.h"
#include "hw/misc/esp32c6_wifi.h"
#include "hw/misc/esp32c6_aes.h"

#define ESP32C6_RESET_ADDRESS       0x40000000
#define ESP32C6_RESET_GPIO_NAME     "esp32c6.machine.reset_gpio"
#define MB (1024*1024)

#define ESP32C6_IRAM_SIZE           (512 * 1024)
#define ESP32C6_RTC_SIZE            (16 * 1024)
#define ESP32C6_IROM_SIZE           (320 * 1024)
#define ESP32C6_APB_SARADC_SIZE    0x100
#define ESP32C6_APB_SARADC_BASE    0x6000e000

struct Esp32C6MachineState {
    MachineState parent;

    EspRISCVCPU soc;
    BusState periph_bus;

    qemu_irq cpu_reset;

    DeviceState *eth;
    DeviceState *wifi;
    ESPAesState aes;
    ESP32C6IntMatrixState intmatrix;
    ESP32C6IntpriState intpri;
    ESP32C6UARTState uart[ESP32C6_UART_COUNT];
    ESP32C6GPIOState gpio;
    ESP32C6CacheState cache;
    ESP32C6EfuseState efuse;
    ESP32C6ClockState clock;
    ESP32C6TimgState timg[2];
    ESP32C6SysTimerState systimer;
    ESP32C6SpiState spi1;
    ESP32C6GdmaState gdma;
    ESP32C6ShaState sha;
    Esp32LEDCState ledc;
    ESP32C6UsbJtagState jtag;
    ESP32C6PcrState pcr;
    ESP32C6LpState lp;
    ESP32C6SpiMemState spi_mem;
    ESP32C6I2cAnaMstState i2c_ana_mst;
    ESP32C6ModemState modem;
    DeviceState *i2c0;
    DeviceState *spi2;
    uint32_t saradc_regs[ESP32C6_APB_SARADC_SIZE / sizeof(uint32_t)];
    MemoryRegion saradc_iomem;
};

#define TYPE_ESP32C6_MACHINE MACHINE_TYPE_NAME("esp32c6")
OBJECT_DECLARE_SIMPLE_TYPE(Esp32C6MachineState, ESP32C6_MACHINE)

enum MemoryRegions {
    ESP32C6_MEMREGION_IROM,
    ESP32C6_MEMREGION_DRAM,
    ESP32C6_MEMREGION_IRAM,
    ESP32C6_MEMREGION_RTCFAST,
};

static const struct MemmapEntry {
    hwaddr base;
    hwaddr size;
} esp32c6_memmap[] = {
    [ESP32C6_MEMREGION_IROM]    = { 0x40000000,  ESP32C6_IROM_SIZE },
    [ESP32C6_MEMREGION_DRAM]    = { 0x40800000,  ESP32C6_IRAM_SIZE },
    [ESP32C6_MEMREGION_IRAM]    = { 0x40800000,  ESP32C6_IRAM_SIZE },
    [ESP32C6_MEMREGION_RTCFAST] = { 0x50000000,  ESP32C6_RTC_SIZE },
};

static void esp32c6_button_gpio9_set(Object *obj, Visitor *v,
                                     const char *name, void *opaque,
                                     Error **errp)
{
    bool pressed;

    if (visit_type_bool(v, name, &pressed, errp)) {
        /* Schematic: GPIO9 is active-low with an external 10 kOhm pull-up. */
        esp32_gpio_set_input(9, pressed ? 0 : 1);
    }
}

static void esp32c6_gpio_level_get(Object *obj, Visitor *v,
                                   const char *name, void *opaque,
                                   Error **errp)
{
    int pin = GPOINTER_TO_INT(opaque);
    bool level = esp32_gpio_get_line(pin) != 0;

    visit_type_bool(v, name, &level, errp);
}

static void esp32c6_reset_request(void *opaque, int n, int level)
{
    if (level) {
        qemu_system_reset_request(SHUTDOWN_CAUSE_GUEST_RESET);
    }
}

static void esp32c6_init_spi_flash(Esp32C6MachineState *ms, BlockBackend *blk)
{
    DeviceState *spi_master = DEVICE(&ms->spi1);
    BusState *spi_bus = qdev_get_child_bus(spi_master, "spi");
    const char *flash_model = NULL;
    int64_t image_size = blk_getlength(blk);

    switch (image_size) {
        case 2 * MB:
            flash_model = "w25x16";
            break;
        case 4 * MB:
            flash_model = "gd25q32";
            break;
        case 8 * MB:
            flash_model = "gd25q64";
            break;
        case 16 * MB:
            flash_model = "is25lp128";
            break;
        default:
            error_report("Drive size error: only 2, 4, 8, and 16MB images are supported");
            return;
    }

    DeviceState *flash_dev = qdev_new(flash_model);
    qdev_prop_set_drive(flash_dev, "drive", blk);
    qdev_prop_set_uint8(flash_dev, "cs", 1);
    qdev_prop_set_bit(flash_dev, "four-bytes-address", true);
    qdev_realize(flash_dev, spi_bus, &error_fatal);
    qdev_connect_gpio_out_named(spi_master, SSI_GPIO_CS, 0,
                                qdev_get_gpio_in_named(flash_dev, SSI_GPIO_CS, 0));
}

static void esp32c6_init_openeth(Esp32C6MachineState *ms)
{
    MemoryRegion *sys_mem = get_system_memory();

    DeviceState *open_eth_dev = qemu_create_nic_device("open_eth", true, NULL);
    if (!open_eth_dev) {
        return;
    }

    ms->eth = open_eth_dev;

    SysBusDevice *sbd = SYS_BUS_DEVICE(open_eth_dev);
    sysbus_realize(sbd, &error_fatal);

    MemoryRegion *mr = sysbus_mmio_get_region(sbd, 0);
    memory_region_add_subregion_overlap(sys_mem, DR_REG_EMAC_BASE, mr, 0);
    mr = sysbus_mmio_get_region(sbd, 1);
    memory_region_add_subregion_overlap(sys_mem, DR_REG_EMAC_BASE + 0x400, mr, 0);

    sysbus_connect_irq(sbd, 0,
                       qdev_get_gpio_in(DEVICE(&ms->intmatrix), 0 /* WIFI_MAC / ETH_MAC */));
}

static void esp32c6_load_firmware(MachineState *machine)
{
    Esp32C6MachineState *ms = ESP32C6_MACHINE(machine);
    const char *bios_filename = NULL;

    if (machine->firmware) {
        bios_filename = machine->firmware;
    }

    if (machine->kernel_filename) {
        if (bios_filename) {
            qemu_log("Warning: both -bios and -kernel specified. Loading -kernel file.\n");
        }
        bios_filename = machine->kernel_filename;
    }

    if (bios_filename) {
        RISCVHartArrayState hart = {
            .harts = &ms->soc.parent_obj,
            .num_harts = 1,
        };

        uint64_t elf_entry = ESP32C6_RESET_ADDRESS;
        int load_result = load_elf_ram_sym(bios_filename, NULL, NULL, NULL,
                        &elf_entry, NULL, NULL, NULL, 0,
                        EM_RISCV, 1, 0, NULL, false, NULL);

        if (load_result > 0) {
            qemu_log("Loading kernel at address 0x%08" PRIx64 "\n", elf_entry);
            riscv_load_kernel(machine, &hart, elf_entry, false, NULL);
            if (elf_entry != ESP32C6_RESET_ADDRESS) {
                qdev_prop_set_uint64(DEVICE(&ms->soc), "resetvec", elf_entry);
            }
        } else {
            int size = load_image_targphys_as(bios_filename, ESP32C6_RESET_ADDRESS,
                                             ESP32C6_IROM_SIZE, &address_space_memory);
            if (size < 0) {
                error_report("Error: could not load ROM/bios binary '%s' (max %u bytes)",
                             bios_filename, (unsigned)ESP32C6_IROM_SIZE);
                exit(1);
            }
        }
    } else {
        char *rom_binary = qemu_find_file(QEMU_FILE_TYPE_BIOS, "esp32c6-rom.bin");
        if (rom_binary == NULL) {
            error_report("Error: -bios argument not set, and esp32c6-rom.bin not found");
            exit(1);
        }

        int size = load_image_targphys_as(rom_binary, ESP32C6_RESET_ADDRESS,
                                         ESP32C6_IROM_SIZE, CPU(&ms->soc)->as);
        if (size < 0) {
            error_report("Error: could not load ROM binary '%s'", rom_binary);
            exit(1);
        }

        g_free(rom_binary);
    }
}

/*
 * The C6 bootloader calibrates the temperature sensor through the APB
 * SARADC and spins on APB_SARADC_INT_RAW[31] after starting a one-shot
 * ADC1 sample.  The real conversion latency is not relevant to firmware
 * boot, so report the done bit as soon as the start bit is written.
 */
static uint64_t esp32c6_saradc_read(void *opaque, hwaddr addr,
                                     unsigned int size)
{
    Esp32C6MachineState *s = opaque;
    uint32_t value;

    if (addr >= ESP32C6_APB_SARADC_SIZE || (addr & 3)) {
        return 0;
    }
    value = s->saradc_regs[addr / 4];
    if (addr == 0x44 && (s->saradc_regs[0x20 / 4] & (1u << 31))) {
        value |= 1u << 31;
    }
    return value;
}

static void esp32c6_saradc_write(void *opaque, hwaddr addr,
                                 uint64_t value, unsigned int size)
{
    Esp32C6MachineState *s = opaque;

    if (addr >= ESP32C6_APB_SARADC_SIZE || (addr & 3)) {
        return;
    }
    if (addr == 0x44) {
        s->saradc_regs[addr / 4] &= ~(uint32_t)value;
        return;
    }
    s->saradc_regs[addr / 4] = (uint32_t)value;
    if (addr == 0x20 && (value & (1u << 31))) {
        s->saradc_regs[0x44 / 4] |= 1u << 31;
    }
}

static const MemoryRegionOps esp32c6_saradc_ops = {
    .read = esp32c6_saradc_read,
    .write = esp32c6_saradc_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32c6_machine_init(MachineState *machine)
{
    BlockBackend *blk = NULL;
    DriveInfo *dinfo = drive_get(IF_MTD, 0, 0);
    if (dinfo) {
        qemu_log("Adding SPI flash device\n");
        blk = blk_by_legacy_dinfo(dinfo);
    } else {
        qemu_log("Not initializing SPI Flash\n");
    }

    Esp32C6MachineState *ms = ESP32C6_MACHINE(machine);
    const char *m5_board = getenv("M5SW_C6_BOARD");
    if (!m5_board || !m5_board[0]) {
        m5_board = "nesso-n1";
    }
    bool board_nesso = !strcmp(m5_board, "nesso-n1");
    bool board_nanoc6 = !strcmp(m5_board, "nanoc6");

    object_initialize_child(OBJECT(ms), "soc", &ms->soc, TYPE_ESP_RISCV_CPU);
    qdev_prop_set_uint64(DEVICE(&ms->soc), "resetvec", ESP32C6_RESET_ADDRESS);
    /* The ESP32-C6 implements the Espressif PMA CSR extension */
    qdev_prop_set_bit(DEVICE(&ms->soc), "has-pma", true);
    /* The ESP32-C6 repurposes mie (0x304) as a per-line external-interrupt
     * enable bitmap (MXIE) per TRM §1.5.2 Reg 1.8 / §1.6.2; the intmatrix
     * uses cpu->mie_enabled as a second per-line gate alongside
     * PLIC_MXINT_ENABLE_REG.  Required for TEE-flavoured IDF builds that
     * mask/unmask interrupts via RV_SET_CSR(mie, …). */
    qdev_prop_set_bit(DEVICE(&ms->soc), "mie-as-bitmap", true);

    const struct MemmapEntry *memmap = esp32c6_memmap;
    MemoryRegion *sys_mem = get_system_memory();

    MemoryRegion *irom = g_new(MemoryRegion, 1);
    memory_region_init_rom(irom, NULL, "esp32c6.irom",
                          memmap[ESP32C6_MEMREGION_IROM].size, &error_fatal);
    memory_region_add_subregion(sys_mem, memmap[ESP32C6_MEMREGION_IROM].base, irom);

    MemoryRegion *iram = g_new(MemoryRegion, 1);
    memory_region_init_ram(iram, NULL, "esp32c6.iram",
                          memmap[ESP32C6_MEMREGION_IRAM].size, &error_fatal);
    memory_region_add_subregion(sys_mem, memmap[ESP32C6_MEMREGION_IRAM].base, iram);

    MemoryRegion *dram = g_new(MemoryRegion, 1);
    memory_region_init_alias(dram, NULL, "esp32c6.dram", iram, 0,
                             memmap[ESP32C6_MEMREGION_DRAM].size);
    memory_region_add_subregion(sys_mem, memmap[ESP32C6_MEMREGION_DRAM].base, dram);

    MemoryRegion *rtcram = g_new(MemoryRegion, 1);
    memory_region_init_ram(rtcram, NULL, "esp32c6.rtcram",
                          memmap[ESP32C6_MEMREGION_RTCFAST].size, &error_fatal);
    memory_region_add_subregion(sys_mem, memmap[ESP32C6_MEMREGION_RTCFAST].base, rtcram);

    esp32c6_load_firmware(machine);

    qdev_realize(DEVICE(&ms->soc), NULL, &error_fatal);

    qbus_init(&ms->periph_bus, sizeof(ms->periph_bus),
              TYPE_SYSTEM_BUS, DEVICE(&ms->soc), "esp32c6-periph-bus");

    qdev_init_gpio_in_named(DEVICE(&ms->soc), esp32c6_reset_request,
                           ESP32C6_RESET_GPIO_NAME, 1);

    /* Initialize child objects */
    for (int i = 0; i < ESP32C6_UART_COUNT; ++i) {
        char name[16];
        snprintf(name, sizeof(name), "uart%d", i);
        object_initialize_child(OBJECT(machine), name, &ms->uart[i], TYPE_ESP32C6_UART);
        snprintf(name, sizeof(name), "serial%d", i);
        object_property_add_alias(OBJECT(machine), name, OBJECT(&ms->uart[i]), "chardev");
        qdev_prop_set_chr(DEVICE(&ms->uart[i]), "chardev", serial_hd(i));
    }

    object_initialize_child(OBJECT(machine), "intmatrix", &ms->intmatrix, TYPE_ESP32C6_INTMATRIX);
    object_initialize_child(OBJECT(machine), "intpri", &ms->intpri, TYPE_ESP32C6_INTPRI);
    object_initialize_child(OBJECT(machine), "gpio", &ms->gpio, TYPE_ESP32C6_GPIO);
    object_initialize_child(OBJECT(machine), "extmem", &ms->cache, TYPE_ESP32C6_CACHE);
    object_initialize_child(OBJECT(machine), "efuse", &ms->efuse, TYPE_ESP32C6_EFUSE);
    object_initialize_child(OBJECT(machine), "clock", &ms->clock, TYPE_ESP32C6_CLOCK);
    object_initialize_child(OBJECT(machine), "gdma", &ms->gdma, TYPE_ESP32C6_GDMA);
    object_initialize_child(OBJECT(machine), "sha", &ms->sha, TYPE_ESP32C6_SHA);
    object_initialize_child(OBJECT(machine), "aes", &ms->aes, TYPE_ESP32C6_AES);
    object_initialize_child(OBJECT(machine), "ledc", &ms->ledc, TYPE_ESP32_LEDC);
    qdev_prop_set_bit(DEVICE(&ms->ledc), "compact-layout", true);
    object_initialize_child(OBJECT(machine), "timg0", &ms->timg[0], TYPE_ESP32C6_TIMG);
    object_initialize_child(OBJECT(machine), "timg1", &ms->timg[1], TYPE_ESP32C6_TIMG);
    object_initialize_child(OBJECT(machine), "systimer", &ms->systimer, TYPE_ESP32C6_SYSTIMER);
    object_initialize_child(OBJECT(machine), "spi1", &ms->spi1, TYPE_ESP32C6_SPI);
    object_initialize_child(OBJECT(machine), "jtag", &ms->jtag, TYPE_ESP32C6_JTAG);
    object_initialize_child(OBJECT(machine), "pcr", &ms->pcr, TYPE_ESP32C6_PCR);
    object_initialize_child(OBJECT(machine), "lp", &ms->lp, TYPE_ESP32C6_LP);
    object_initialize_child(OBJECT(machine), "spi_mem", &ms->spi_mem, TYPE_ESP32C6_SPI_MEM);
    object_initialize_child(OBJECT(machine), "i2c_ana_mst", &ms->i2c_ana_mst, TYPE_ESP32C6_I2C_ANA_MST);
    object_initialize_child(OBJECT(machine), "modem_lpcon", &ms->modem, TYPE_ESP32C6_MODEM);

    /* Interrupt matrix + PLIC */
    DeviceState *intmatrix_dev = DEVICE(&ms->intmatrix);
    {
        object_property_set_link(OBJECT(&ms->intmatrix), "cpu", OBJECT(&ms->soc), &error_abort);
        sysbus_realize(SYS_BUS_DEVICE(&ms->intmatrix), &error_fatal);

        MemoryRegion *map_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->intmatrix), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_INTERRUPT_BASE, map_mr, 0);

        MemoryRegion *plic_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->intmatrix), 1);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_PLIC_MX_BASE, plic_mr, 0);

        for (int i = 0; i <= ESP32C6_CPU_INT_COUNT; i++) {
            qemu_irq cpu_input = qdev_get_gpio_in_named(DEVICE(&ms->soc), ESP_CPU_IRQ_LINES_NAME, i);
            qdev_connect_gpio_out_named(intmatrix_dev, ESP32C6_INT_MATRIX_OUTPUT_NAME, i, cpu_input);
        }
    }

    esp32c6_init_openeth(ms);

    /* USB Serial JTAG — connect to serial_hd(2) to avoid doubling UART0 */
    {
        qdev_prop_set_chr(DEVICE(&ms->jtag), "chardev", serial_hd(ESP32C6_UART_COUNT));
        sysbus_realize(SYS_BUS_DEVICE(&ms->jtag), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->jtag), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_USB_SERIAL_JTAG_BASE, mr, 0);
        sysbus_connect_irq(SYS_BUS_DEVICE(&ms->jtag), 0,
                           qdev_get_gpio_in(intmatrix_dev,
                                           C6_ETS_USB_SERIAL_JTAG_INTR_SOURCE));
    }

    /* SPI1 (Flash) */
    {
        ms->spi1.parent.xts_aes = NULL;
        if (blk) {
            /* Match the m25p80 model selected in esp32c6_init_spi_flash. */
            qdev_prop_set_uint32(DEVICE(&ms->spi1), "flash-qio-header-bytes",
                                blk_getlength(blk) == 16 * MB ? 3 : 5);
        }
        sysbus_realize(SYS_BUS_DEVICE(&ms->spi1), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->spi1), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_SPI1_BASE, mr, 0);
        if (blk) {
            esp32c6_init_spi_flash(ms, blk);
        }
    }

    /* HP SPI2: display and SX1262 buses on Nesso N1. */
    if (board_nesso) {
        ms->spi2 = qdev_new(TYPE_ESP32C3_SPI);
        qdev_prop_set_bit(ms->spi2, "m5-spi2", true);
        sysbus_realize_and_unref(SYS_BUS_DEVICE(ms->spi2), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(ms->spi2), 0);
        memory_region_add_subregion_overlap(sys_mem, 0x60081000, mr, 0);

        DeviceState *panel = qdev_new(TYPE_ESP32C6_NESSO_PANEL);
        object_property_add_child(qdev_get_machine(), "nesso-panel",
                                  OBJECT(panel));
        qdev_realize(panel, NULL, &error_fatal);
        esp32c3_spi_set_m5_sink(ms->spi2, panel,
                                esp32c6_nesso_panel_write);
        esp32c3_spi_set_gdma(ms->spi2, ESP_GDMA(&ms->gdma));
        sysbus_connect_irq(
            SYS_BUS_DEVICE(ms->spi2), 0,
            qdev_get_gpio_in(intmatrix_dev, C6_ETS_SPI2_INTR_SOURCE));
        esp32c6_sx1262_attach_soft_spi(ms->spi2, 23, 20, 21, 22, 19, 15);
    }

    /* UARTs */
    for (int i = 0; i < ESP32C6_UART_COUNT; ++i) {
        const hwaddr uart_base[] = { DR_REG_UART_BASE, DR_REG_UART1_BASE };
        sysbus_realize(SYS_BUS_DEVICE(&ms->uart[i]), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->uart[i]), 0);
        memory_region_add_subregion_overlap(sys_mem, uart_base[i], mr, 0);
        sysbus_connect_irq(SYS_BUS_DEVICE(&ms->uart[i]), 0,
                           qdev_get_gpio_in(intmatrix_dev, C6_ETS_UART0_INTR_SOURCE + i));
    }

    /* GPIO */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->gpio), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->gpio), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_GPIO_BASE, mr, 0);
    }
    /*
     * The WiFi/PHY register blocks exist even without a host network.
     * A missing backend represents an isolated radio, not absent silicon.
     */
    {
        DeviceState *wifi = qemu_create_nic_device(TYPE_ESP32C6_WIFI, true, NULL);
        if (!wifi) {
            wifi = qdev_new(TYPE_ESP32C6_WIFI);
        }
        {
            ms->wifi = wifi;
            sysbus_realize(SYS_BUS_DEVICE(wifi), &error_fatal);
            memory_region_add_subregion_overlap(
                sys_mem, 0x600ad000,
                sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 0), 2);
            memory_region_add_subregion_overlap(
                sys_mem, 0x600a0000,
                sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 1), 2);
            memory_region_add_subregion_overlap(
                sys_mem, 0x600a7000,
                sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 2), 2);
            memory_region_add_subregion_overlap(
                sys_mem, 0x600a4000,
                sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 3), 2);
            memory_region_add_subregion_overlap(
                sys_mem, 0x600a9000,
                sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 4), 2);
            memory_region_add_subregion_overlap(
                sys_mem, 0x600af000,
                sysbus_mmio_get_region(SYS_BUS_DEVICE(wifi), 5), 2);
            sysbus_connect_irq(
                SYS_BUS_DEVICE(wifi), 0,
                qdev_get_gpio_in(intmatrix_dev, 0));
        }
    }

    /* Bluetooth AES is a separate, always-present DMA engine. */
    {
        DeviceState *ble_aes = qdev_new("esp32c6.ble-aes");
        sysbus_realize_and_unref(SYS_BUS_DEVICE(ble_aes), &error_fatal);
        memory_region_add_subregion_overlap(
            sys_mem, 0x600a9400,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(ble_aes), 0), 3);
    }

    /* LPPERI exposes RNG_DATA at +0x08 independently of WiFi networking. */
    {
        DeviceState *rng = qdev_new("esp32c6.rng");
        sysbus_realize_and_unref(SYS_BUS_DEVICE(rng), &error_fatal);
        memory_region_add_subregion_overlap(
            sys_mem, 0x600b2800,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(rng), 0), 1);
    }

    /* LEDC: six channels and four timers using the compact register layout. */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->ledc), &error_fatal);
        MemoryRegion *mr =
            sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->ledc), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_LEDC_BASE, mr, 0);
    }

    /* RMT: TX channels 0/1, RX channels 2/3, plus hardware symbol RAM. */
    {
        DeviceState *rmt = qdev_new(TYPE_ESP32C6_RMT);
        sysbus_realize_and_unref(SYS_BUS_DEVICE(rmt), &error_fatal);
        memory_region_add_subregion_overlap(
            sys_mem, 0x60006000,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(rmt), 0), 1);
        memory_region_add_subregion_overlap(
            sys_mem, 0x60006400,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(rmt), 1), 1);
        sysbus_connect_irq(SYS_BUS_DEVICE(rmt), 0,
                           qdev_get_gpio_in(intmatrix_dev, 49));
    }

    /*
     * ESP32-C6 HP I2C0. Nesso N1 exposes its PI4IOE expanders and FT5x06
     * touch controller through this bus. The same bus is also attached to
     * the software-I2C bridge used by M5GFX's pre-board-detect probe.
     */
    if (board_nesso) {
        ms->i2c0 = qdev_new(TYPE_ESP32_I2C);
        sysbus_realize_and_unref(SYS_BUS_DEVICE(ms->i2c0), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(ms->i2c0), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_I2C_EXT_BASE, mr, 0);
        sysbus_connect_irq(SYS_BUS_DEVICE(ms->i2c0), 0,
                           qdev_get_gpio_in(intmatrix_dev,
                                            C6_ETS_I2C_EXT0_INTR_SOURCE));

        I2CBus *i2c_bus = (I2CBus *)qdev_get_child_bus(ms->i2c0, "i2c");
        static const struct {
            const char *name;
            const char *model;
            uint8_t address;
        } board_i2c_devs[] = {
            { "nesso-pi4ioe1", "pi4ioe", 0x43 },
            { "nesso-pi4ioe2", "pi4ioe", 0x44 },
            { "nesso-ft5x06", "ft5x06", 0x38 },
            { "nesso-bmi270", "bmi270", 0x68 },
            { "nesso-bq27220", "bq27220", 0x55 },
            { "nesso-aw32001", "aw32001", 0x49 },
        };
        for (int i = 0; i < ARRAY_SIZE(board_i2c_devs); i++) {
            DeviceState *dev = qdev_new(TYPE_ESP32C6_BOARD_I2C_DEV);
            qdev_prop_set_string(dev, "model", board_i2c_devs[i].model);
            qdev_prop_set_uint8(dev, "address", board_i2c_devs[i].address);
            object_property_add_child(qdev_get_machine(), board_i2c_devs[i].name,
                                      OBJECT(dev));
            qdev_realize_and_unref(dev, (BusState *)i2c_bus, &error_fatal);
        }
        esp32c6_soft_i2c_init_pins(i2c_bus, 10, 8);
    }

    if (board_nesso) {
        /*
         * Nesso N1 strap topology seen by M5GFX: GPIO18 is tied low and the
         * SYS I2C pads are pulled high. The touch controller owns GPIO3.
         */
        esp32_gpio_set_input(18, 0);
        esp32_gpio_set_input(8, 1);
        esp32_gpio_set_input(10, 1);
        esp32_gpio_force_line(3, 1);
    } else if (board_nanoc6) {
        /* NanoC6: GPIO9 button, GPIO7 blue LED, GPIO19 RGB power, GPIO20 data. */
        esp32_gpio_set_input(9, 1);
    } else {
        error_report("unknown ESP32-C6 M5 board: %s", m5_board);
        exit(1);
    }

    /* Cache (EXTMEM) */
    {
        if (blk) {
            ms->cache.flash_blk = blk;
        }
        sysbus_realize(SYS_BUS_DEVICE(&ms->cache), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->cache), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_EXTMEM_BASE, mr, 0);
        memory_region_add_subregion_overlap(sys_mem, ms->cache.cache_base, &ms->cache.cache, 0);
    }

    /* eFuse */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->efuse), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->efuse), 0);
        /* The broad LP register window overlaps this hardware subregion. */
        memory_region_add_subregion_overlap(sys_mem, DR_REG_EFUSE_BASE, mr, 1);
        sysbus_connect_irq(SYS_BUS_DEVICE(&ms->efuse), 0,
                           qdev_get_gpio_in(intmatrix_dev, C6_ETS_EFUSE_INTR_SOURCE));
    }

    /* PCR (Peripheral Clock and Reset) */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->pcr), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->pcr), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_SYSCON_BASE, mr, 0);
    }

    /* LP domain (LP_CLKRST, LP_AON, LP_TIMER, RTC_I2C) */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->lp), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->lp), 0);
        memory_region_add_subregion_overlap(sys_mem, ESP32C6_LP_BASE, mr, 0);
        qdev_connect_gpio_out_named(DEVICE(&ms->lp), ESP32C6_LP_RESET_GPIO, 0,
                                    qdev_get_gpio_in_named(DEVICE(&ms->soc),
                                        ESP32C6_RESET_GPIO_NAME, 0));
    }

    /* SPI0 MEM controller (MMU, timing calibration) */
    {
        if (blk) {
            ms->spi_mem.flash_blk = blk;
        }
        ms->spi_mem.dcache_mr = &ms->cache.cache;
        sysbus_realize(SYS_BUS_DEVICE(&ms->spi_mem), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->spi_mem), 0);
        memory_region_add_subregion_overlap(sys_mem, ESP32C6_SPI_MEM_BASE, mr, 0);
    }

    /* I2C Analog Master */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->i2c_ana_mst), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->i2c_ana_mst), 0);
        memory_region_add_subregion_overlap(sys_mem, ESP32C6_I2C_ANA_MST_BASE, mr, 0);
    }

    /* APB SARADC: bootloader temperature-sensor calibration handshake. */
    {
        memory_region_init_io(&ms->saradc_iomem, OBJECT(machine),
                              &esp32c6_saradc_ops, ms,
                              "esp32c6.apb_saradc",
                              ESP32C6_APB_SARADC_SIZE);
        memory_region_add_subregion_overlap(sys_mem, ESP32C6_APB_SARADC_BASE,
                                            &ms->saradc_iomem, 0);
    }

    /* GDMA */
    {
        object_property_set_link(OBJECT(&ms->gdma), "soc_mr", OBJECT(dram), &error_abort);
        sysbus_realize(SYS_BUS_DEVICE(&ms->gdma), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->gdma), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_GDMA_BASE, mr, 0);
        for (int i = 0; i < ESP32C6_GDMA_CHANNEL_COUNT; i++) {
            qdev_connect_gpio_out_named(DEVICE(&ms->gdma), ESP_GDMA_IRQ_IN_NAME, i,
                                        qdev_get_gpio_in(intmatrix_dev, C6_ETS_DMA_IN_CH0_INTR_SOURCE + i));
            qdev_connect_gpio_out_named(DEVICE(&ms->gdma), ESP_GDMA_IRQ_OUT_NAME, i,
                                        qdev_get_gpio_in(intmatrix_dev, C6_ETS_DMA_OUT_CH0_INTR_SOURCE + i));
        }
    }

    /* I2S0: Nesso N1 GPIO11 1-bit delta-sigma buzzer output. */
    esp32c6_i2s_board_init(sys_mem, &ms->gdma, intmatrix_dev);

    /* AES uses the C6 GDMA request and interrupt matrix, as on silicon. */
    {
        ms->aes.gdma = ESP_GDMA(&ms->gdma);
        sysbus_realize(SYS_BUS_DEVICE(&ms->aes), &error_fatal);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_AES_BASE,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->aes), 0), 0);
        sysbus_connect_irq(SYS_BUS_DEVICE(&ms->aes), 0,
            qdev_get_gpio_in(intmatrix_dev, C6_ETS_AES_INTR_SOURCE));
    }

    /* SHA */
    {
        ms->sha.parent.parent.gdma = ESP_GDMA(&ms->gdma);
        sysbus_realize(SYS_BUS_DEVICE(&ms->sha), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->sha), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_SHA_BASE, mr, 0);
        sysbus_connect_irq(SYS_BUS_DEVICE(&ms->sha), 0,
                           qdev_get_gpio_in(intmatrix_dev, C6_ETS_SHA_INTR_SOURCE));
    }

    /* MODEM_LPCON (modem clock control) */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->modem), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->modem), 0);
        memory_region_add_subregion_overlap(sys_mem, ESP32C6_MODEM_BASE, mr, 0);
        MemoryRegion *syscon_mr =
            sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->modem), 1);
        memory_region_add_subregion_overlap(
            sys_mem,
            ESP32C6_MODEM_SYSCON_BASE,
            syscon_mr,
            0);
    }

    /* System clock */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->clock), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->clock), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_SYSTEM_BASE, mr, 0);
    }

    /* INTPRI — software-triggered cross-core interrupts */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->intpri), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->intpri), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_INTPRI_BASE, mr, 0);

        for (int i = 0; i < ESP32C6_INTPRI_CPU_INTR_COUNT; i++) {
            sysbus_connect_irq(SYS_BUS_DEVICE(&ms->intpri), i,
                               qdev_get_gpio_in(intmatrix_dev, C6_ETS_FROM_CPU_INTR0_SOURCE + i));
        }
    }

    /* Timer Groups */
    for (int tg = 0; tg < 2; tg++) {
        qdev_connect_clock_in(DEVICE(&ms->timg[tg]), "wdt-clock",
                              ms->pcr.wdt_clock[tg]);
        sysbus_realize(SYS_BUS_DEVICE(&ms->timg[tg]), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->timg[tg]), 0);
        const hwaddr timg_base[] = { DR_REG_TIMERGROUP0_BASE, DR_REG_TIMERGROUP1_BASE };
        memory_region_add_subregion_overlap(sys_mem, timg_base[tg], mr, 0);

        const int tg0_src[] = { C6_ETS_TG0_T0_LEVEL_INTR_SOURCE, C6_ETS_TG0_WDT_LEVEL_INTR_SOURCE };
        const int tg1_src[] = { C6_ETS_TG1_T0_LEVEL_INTR_SOURCE, C6_ETS_TG1_WDT_LEVEL_INTR_SOURCE };
        const int *src = tg == 0 ? tg0_src : tg1_src;

        qdev_connect_gpio_out_named(DEVICE(&ms->timg[tg]), ESP32C6_T0_IRQ_INTERRUPT, 0,
                                    qdev_get_gpio_in(intmatrix_dev, src[0]));
        qdev_connect_gpio_out_named(DEVICE(&ms->timg[tg]), ESP32C6_WDT_IRQ_INTERRUPT, 0,
                                    qdev_get_gpio_in(intmatrix_dev, src[1]));

        const int wdt_reset_reason = tg == 0 ? ESP32C6_CORE_MWDT0 : ESP32C6_CORE_MWDT1;
        qdev_connect_gpio_out_named(DEVICE(&ms->timg[tg]), ESP32C6_WDT_IRQ_RESET, 0,
                                    qdev_get_gpio_in(DEVICE(&ms->lp), wdt_reset_reason));
    }

    /* System timer */
    {
        sysbus_realize(SYS_BUS_DEVICE(&ms->systimer), &error_fatal);
        MemoryRegion *mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(&ms->systimer), 0);
        memory_region_add_subregion_overlap(sys_mem, DR_REG_SYSTIMER_BASE, mr, 0);
        for (int i = 0; i < ESP_SYSTIMER_IRQ_COUNT; i++) {
            sysbus_connect_irq(SYS_BUS_DEVICE(&ms->systimer), i,
                               qdev_get_gpio_in(intmatrix_dev, C6_ETS_SYSTIMER_TARGET0_INTR_SOURCE + i));
        }
    }

    esp32_gpio_set_input(9, 1);
    object_property_add(OBJECT(machine), "button-gpio9", "bool",
                        NULL, esp32c6_button_gpio9_set, NULL, NULL);
    object_property_add(OBJECT(machine), "gpio7-level", "bool",
                        esp32c6_gpio_level_get, NULL, NULL,
                        GINT_TO_POINTER(7));
    object_property_add(OBJECT(machine), "gpio9-level", "bool",
                        esp32c6_gpio_level_get, NULL, NULL,
                        GINT_TO_POINTER(9));
    object_property_add(OBJECT(machine), "gpio19-level", "bool",
                        esp32c6_gpio_level_get, NULL, NULL,
                        GINT_TO_POINTER(19));

    /* Catch-all for the entire peripheral address space (priority -1000).
     * Specific devices mapped above at priority 0 take precedence. */
    create_unimplemented_device("esp32c6.peripherals", ESP32C6_IO_START_ADDR, 0x100000);
    create_unimplemented_device("esp32c6.hp_peri", 0x20000000, 0x100000);
}

static void esp32c6_machine_class_init(ObjectClass *oc, void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "Espressif ESP32-C6 machine";
    mc->default_cpu_type = TYPE_ESP_RISCV_CPU;
    mc->init = esp32c6_machine_init;
    mc->max_cpus = 1;
    mc->default_cpus = 1;
    mc->default_ram_size = 512 * 1024;
}

static const TypeInfo esp32c6_info = {
    .name = TYPE_ESP32C6_MACHINE,
    .parent = TYPE_MACHINE,
    .instance_size = sizeof(Esp32C6MachineState),
    .class_init = esp32c6_machine_class_init,
};

static void esp32c6_machine_type_init(void)
{
    type_register_static(&esp32c6_info);
}

type_init(esp32c6_machine_type_init);

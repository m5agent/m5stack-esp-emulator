/*
 * M5Stack CoreS3 board glue: ESP32-S3 + ILI9342 320x240 SPI panel,
 * AXP2101 PMIC, AW9523 GPIO expander, GC0308 camera and
 * FT5x06-compatible touch.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/xtensa/esp32s3_intc.h"
#include "hw/dma/esp_gdma.h"
#include "hw/qdev-properties.h"
#include "qapi/error.h"
#include "m5stopwatch.h"

void m5cores3_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                         ESPGdmaState *gdma)
{
    m5stopwatch_sens_init(sys_mem);
    m5stopwatch_regi2c_init(sys_mem);
    m5stopwatch_fe_init(sys_mem);
    m5stopwatch_phy_init(sys_mem);

    DeviceState *i2c0 = qdev_new(TYPE_ESP32S3_I2C);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(i2c0), &error_fatal);
    MemoryRegion *i2c0_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(i2c0), 0);
    memory_region_add_subregion_overlap(sys_mem, 0x60013000, i2c0_mr, 1);

    DeviceState *i2c1 = qdev_new(TYPE_ESP32S3_I2C);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(i2c1), &error_fatal);
    MemoryRegion *i2c1_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(i2c1), 0);
    memory_region_add_subregion_overlap(sys_mem, 0x60027000, i2c1_mr, 1);
    sysbus_connect_irq(SYS_BUS_DEVICE(i2c0), 0,
                       qdev_get_gpio_in(intmatrix, ETS_I2C_EXT0_INTR_SOURCE));
    sysbus_connect_irq(SYS_BUS_DEVICE(i2c1), 0,
                       qdev_get_gpio_in(intmatrix, ETS_I2C_EXT1_INTR_SOURCE));

    I2CBus *bus = (I2CBus *)qdev_get_child_bus(i2c0, "i2c");
    esp32s3_i2c_set_bus(i2c1, bus);

    static const struct { const char *model; uint8_t addr; } devs[] = {
        { "axp2101", 0x34 },
        { "aw9523", 0x58 },
        { "bmm150", 0x10 },
        { "gc0308", 0x21 },
        { "ltr553", 0x23 },
        { "aw88298", 0x36 },
        { "ft5x06", 0x38 },
        { "pcf8563", 0x51 },
        { "es7210", 0x40 },
        { "bmi270", 0x69 },
        { "rx8130", 0x32 },
        { "es8311", 0x18 },
    };
    for (int i = 0; i < ARRAY_SIZE(devs); i++) {
        DeviceState *d = qdev_new(TYPE_M5SW_I2C_DEV);
        qdev_prop_set_string(d, "model", devs[i].model);
        qdev_prop_set_uint8(d, "address", devs[i].addr);
        object_property_add_child(qdev_get_machine(), devs[i].model, OBJECT(d));
        qdev_realize_and_unref(d, (BusState *)bus, &error_fatal);
    }
    m5stopwatch_soft_i2c_init_pins(bus, 12, 11);

    DeviceState *cam = qdev_new(TYPE_M5_LCD_CAM);
    m5_lcd_cam_attach(cam, gdma, 320, 240);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(cam), &error_fatal);
    memory_region_add_subregion_overlap(
        sys_mem, 0x60041000,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(cam), 0), 1);
    sysbus_connect_irq(
        SYS_BUS_DEVICE(cam), 0,
        qdev_get_gpio_in(intmatrix, ETS_LCD_CAM_INTR_SOURCE));

    DeviceState *spi = qdev_new(TYPE_ESP32S3_GPSPI);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(spi), &error_fatal);
    MemoryRegion *spi_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(spi), 0);
    memory_region_add_subregion_overlap(sys_mem, 0x60025000, spi_mr, 1);
    MemoryRegion *spi2_alias = g_new(MemoryRegion, 1);
    memory_region_init_alias(spi2_alias, NULL, "m5cores3.spi2-alias",
                             spi_mr, 0, memory_region_size(spi_mr));
    memory_region_add_subregion_overlap(sys_mem, 0x60024000, spi2_alias, 1);
    esp32s3_gpspi_connect_irqs(spi, intmatrix, ETS_SPI2_INTR_SOURCE,
                                ETS_SPI3_INTR_SOURCE);

    DeviceState *panel = qdev_new(TYPE_M5_SPI_PANEL);
    qdev_prop_set_uint32(panel, "mem-width", 320);
    qdev_prop_set_uint32(panel, "mem-height", 240);
    qdev_prop_set_uint32(panel, "vis-width", 320);
    qdev_prop_set_uint32(panel, "vis-height", 240);
    qdev_prop_set_uint32(panel, "offset-x", 0);
    qdev_prop_set_uint32(panel, "offset-y", 0);
    qdev_prop_set_uint32(panel, "key-a-pin", 0);
    qdev_prop_set_uint32(panel, "key-b-pin", 0);
    qdev_prop_set_uint32(panel, "read-id", 0x000000e3);
    qdev_prop_set_bit(panel, "apply-madctl", false);
    qdev_prop_set_bit(panel, "touch", true);
    qdev_prop_set_bit(panel, "invert", true);
    qdev_realize_and_unref(panel, NULL, &error_fatal);
    esp32s3_gpspi_attach(spi, gdma, NULL, M5_SPI_PANEL(panel), GDMA_SPI3);
    esp32s3_gpspi_set_dc_pin(spi, 35);
    esp32s3_gpspi_set_panel_cs_pin(spi, 3);
    /*
     * Display and M-Bus share the ESP32-S3 SPI2 register window.  M-Bus
     * provides the external SD card on CS4 and the MAX3421E USB host on
     * CS0 with IRQ G14; the display has no readback path and is gated off
     * whenever an M-Bus slave owns the transaction.
     */
    m5_spi_sd_attach(spi, 4);
    m5_max3421e_attach(spi, 0, 14);
    esp32s3_gpspi_set_spi_slave_dma(spi, 4, GDMA_SPI2);
    esp32s3_gpspi_set_spi_slave_dma(spi, 0, GDMA_SPI2);
}

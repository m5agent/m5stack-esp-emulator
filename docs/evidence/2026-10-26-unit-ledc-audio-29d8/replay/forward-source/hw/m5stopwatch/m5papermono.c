/*
 * M5Stack PaperMono board glue: ESP32-S3R8, SSD1677 480x800 e-paper,
 * M5PM1/M5IOE1, FT5x06 touch and NFC identity.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/xtensa/esp32s3_intc.h"
#include "hw/dma/esp_gdma.h"
#include "hw/qdev-properties.h"
#include "qapi/error.h"
#include "m5stopwatch.h"

void m5papermono_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
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
        { "m5pm1", 0x6E },
        { "m5ioe1", 0x4F },
        { "ft5x06", 0x38 },
        { "rx8130", 0x32 },
        { "bmi270", 0x68 },
        { "st25r3916", 0x50 },
        { "ip2315", 0x75 },
    };
    for (int i = 0; i < ARRAY_SIZE(devs); i++) {
        DeviceState *d = qdev_new(TYPE_M5SW_I2C_DEV);
        qdev_prop_set_string(d, "model", devs[i].model);
        qdev_prop_set_uint8(d, "address", devs[i].addr);
        object_property_add_child(qdev_get_machine(), devs[i].model, OBJECT(d));
        qdev_realize_and_unref(d, (BusState *)bus, &error_fatal);
    }
    m5stopwatch_soft_i2c_init_pins(bus, 47, 48);

    DeviceState *spi2 = qdev_new(TYPE_ESP32S3_GPSPI);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(spi2), &error_fatal);
    memory_region_add_subregion_overlap(
        sys_mem, 0x60024000,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(spi2), 0), 1);
    sysbus_connect_irq(SYS_BUS_DEVICE(spi2), 0,
                       qdev_get_gpio_in(intmatrix, ETS_SPI2_INTR_SOURCE));

    DeviceState *spi3 = qdev_new(TYPE_ESP32S3_GPSPI);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(spi3), &error_fatal);
    memory_region_add_subregion_overlap(
        sys_mem, 0x60025000,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(spi3), 0), 1);
    sysbus_connect_irq(SYS_BUS_DEVICE(spi3), 0,
                       qdev_get_gpio_in(intmatrix, ETS_SPI3_INTR_SOURCE));

    DeviceState *panel = qdev_new(TYPE_M5_EPD_PANEL);
    qdev_prop_set_uint32(panel, "native-width", 800);
    qdev_prop_set_uint32(panel, "native-height", 480);
    qdev_prop_set_uint32(panel, "out-width", 480);
    qdev_prop_set_uint32(panel, "out-height", 800);
    qdev_prop_set_bit(panel, "color", false);
    qdev_prop_set_bit(panel, "rotate", true);
    qdev_prop_set_bit(panel, "touch", true);
    qdev_prop_set_uint32(panel, "touch-int-pin", 4);
    qdev_prop_set_uint32(panel, "key-a-pin", 2);
    qdev_prop_set_uint32(panel, "key-b-pin", 3);
    qdev_prop_set_uint32(panel, "key-c-pin", UINT32_MAX);
    qdev_prop_set_uint32(panel, "busy-pin", 18);
    qdev_prop_set_bit(panel, "busy-ready-level", false);
    qdev_realize_and_unref(panel, NULL, &error_fatal);
    esp32s3_gpspi_attach_epd(spi2, gdma, M5_EPD_PANEL(panel), GDMA_SPI2);
    esp32s3_gpspi_set_dc_pin(spi2, 17);
    esp32s3_gpspi_attach(spi3, gdma, NULL, NULL, GDMA_SPI3);
    m5_sx1262_attach(spi3, 41);
    m5_i2s_board_init(sys_mem, intmatrix, gdma);
}

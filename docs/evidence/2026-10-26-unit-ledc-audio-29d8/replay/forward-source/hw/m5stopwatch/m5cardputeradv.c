/*
 * M5Stack Cardputer-ADV board glue: ESP32-S3FN8 + ST7789 240x135,
 * TCA8418 keyboard controller and BMI270 IMU.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/xtensa/esp32s3_intc.h"
#include "hw/dma/esp_gdma.h"
#include "hw/qdev-properties.h"
#include "qapi/error.h"
#include "m5stopwatch.h"

void m5cardputeradv_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
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
        { "tca8418", 0x34 },
        { "bmi270", 0x69 },
        { "es8311", 0x18 },
    };
    for (int i = 0; i < ARRAY_SIZE(devs); i++) {
        DeviceState *d = qdev_new(TYPE_M5SW_I2C_DEV);
        qdev_prop_set_string(d, "model", devs[i].model);
        qdev_prop_set_uint8(d, "address", devs[i].addr);
        object_property_add_child(qdev_get_machine(), devs[i].model, OBJECT(d));
        qdev_realize_and_unref(d, (BusState *)bus, &error_fatal);
    }

    DeviceState *spi = qdev_new(TYPE_ESP32S3_GPSPI);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(spi), &error_fatal);
    MemoryRegion *spi_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(spi), 0);
    memory_region_add_subregion_overlap(sys_mem, 0x60025000, spi_mr, 1);
    esp32s3_gpspi_connect_irqs(spi, intmatrix, ETS_SPI2_INTR_SOURCE,
                                ETS_SPI3_INTR_SOURCE);

    DeviceState *panel = qdev_new(TYPE_M5_SPI_PANEL);
    qdev_prop_set_uint32(panel, "mem-width", 320);
    qdev_prop_set_uint32(panel, "mem-height", 240);
    qdev_prop_set_uint32(panel, "vis-width", 240);
    qdev_prop_set_uint32(panel, "vis-height", 135);
    qdev_prop_set_uint32(panel, "offset-x", 40);
    qdev_prop_set_uint32(panel, "offset-y", 53);
    qdev_prop_set_uint32(panel, "read-id", 0x00000081);
    qdev_prop_set_bit(panel, "apply-madctl", false);
    qdev_prop_set_bit(panel, "keyboard", true);
    qdev_prop_set_bit(panel, "invert", true);
    qdev_realize_and_unref(panel, NULL, &error_fatal);
    esp32s3_gpspi_attach(spi, gdma, NULL, M5_SPI_PANEL(panel), GDMA_SPI3);
    esp32s3_gpspi_set_dc_pin(spi, 34);
    esp32s3_gpspi_set_panel_cs_pin(spi, 37);

    DeviceState *sd_spi = qdev_new(TYPE_ESP32S3_GPSPI);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(sd_spi), &error_fatal);
    memory_region_add_subregion_overlap(
        sys_mem, 0x60024000,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(sd_spi), 0), 1);
    esp32s3_gpspi_connect_irqs(sd_spi, intmatrix, ETS_SPI2_INTR_SOURCE,
                                ETS_SPI3_INTR_SOURCE);
    esp32s3_gpspi_attach(sd_spi, gdma, NULL, M5_SPI_PANEL(panel), GDMA_SPI2);
    esp32s3_gpspi_set_dc_pin(sd_spi, 34);
    esp32s3_gpspi_set_panel_cs_pin(sd_spi, 37);
    m5_spi_sd_attach(sd_spi, 12);
    m5_st25r3916_spi_attach(spi, 6, 4);
    m5_st25r3916_spi_attach(sd_spi, 6, 4);
    m5_cc1101_spi_attach(spi, 5, 15);
    m5_cc1101_spi_attach(sd_spi, 5, 15);
}

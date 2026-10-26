/*
 * M5Stack Core2 board glue: ESP32 LX6 + ILI9342 320x240 SPI panel,
 * AXP2101/AXP192 PMIC and FT5x06-compatible touch.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "exec/address-spaces.h"
#include "hw/xtensa/esp32.h"
#include "hw/qdev-properties.h"
#include "qapi/error.h"
#include "m5stopwatch.h"

void m5core2_board_init(Esp32SocState *s)
{
    I2CBus *bus0 = (I2CBus *)qdev_get_child_bus(DEVICE(&s->i2c[0]), "i2c");
    const char *pmic_override = getenv("M5SW_CORE2_PMIC");
    bool legacy_axp192 = pmic_override && !strcmp(pmic_override, "axp192");

    /*
     * Core2 wires AXP, RTC, touch and IMU to one physical GPIO21/22 bus.
     * ESP32 has two controller register blocks, either of which firmware may
     * route to those pins. Point both controllers at the same board bus and
     * attach each slave once.
     */
    esp32_i2c_set_bus(DEVICE(&s->i2c[0]), bus0);
    esp32_i2c_set_bus(DEVICE(&s->i2c[1]), bus0);

    DeviceState *axp = qdev_new(TYPE_M5SW_I2C_DEV);
    qdev_prop_set_string(axp, "model", legacy_axp192 ? "axp192" : "axp2101");
    qdev_prop_set_uint8(axp, "address", 0x34);
    object_property_add_child(qdev_get_machine(),
                              legacy_axp192 ? "axp192" : "axp2101",
                              OBJECT(axp));
    qdev_realize_and_unref(axp, (BusState *)bus0, &error_fatal);

    if (!legacy_axp192) {
        for (uint8_t address = 0x40; address <= 0x41; address++) {
            DeviceState *ina = qdev_new(TYPE_M5SW_I2C_DEV);
            char *path = g_strdup_printf("ina3221-%02x", address);

            qdev_prop_set_string(ina, "model", "ina3221");
            qdev_prop_set_uint8(ina, "address", address);
            object_property_add_child(qdev_get_machine(), path, OBJECT(ina));
            qdev_realize_and_unref(ina, (BusState *)bus0, &error_fatal);
            g_free(path);
        }
    }

    static const struct { const char *model; uint8_t addr; const char *path; } devs[] = {
        { "ft5x06", 0x38, "core2-ft5x06" },
        { "mpu6886", 0x68, "mpu6886" },
        { "pcf8563", 0x51, "pcf8563" },
    };
    for (int i = 0; i < ARRAY_SIZE(devs); i++) {
        DeviceState *d = qdev_new(TYPE_M5SW_I2C_DEV);
        qdev_prop_set_string(d, "model", devs[i].model);
        qdev_prop_set_uint8(d, "address", devs[i].addr);
        object_property_add_child(qdev_get_machine(), devs[i].path, OBJECT(d));
        qdev_realize_and_unref(d, (BusState *)bus0, &error_fatal);
    }

    m5stopwatch_soft_i2c_init_pins(bus0, 21, 22);
    esp32_gpio_set_input(39, 1);

    DeviceState *panel = qdev_new(TYPE_M5_SPI_PANEL);
    qdev_prop_set_uint32(panel, "mem-width", 320);
    qdev_prop_set_uint32(panel, "mem-height", 240);
    qdev_prop_set_uint32(panel, "vis-width", 320);
    qdev_prop_set_uint32(panel, "vis-height", 240);
    qdev_prop_set_uint32(panel, "glass-rotation", 0);
    qdev_prop_set_uint32(panel, "offset-x", 0);
    qdev_prop_set_uint32(panel, "offset-y", 0);
    qdev_prop_set_uint32(panel, "read-id", 0x000000e3);
    qdev_prop_set_bit(panel, "apply-madctl", false);
    qdev_prop_set_bit(panel, "touch", true);
    qdev_prop_set_uint32(panel, "touch-int-pin", 39);
    qdev_prop_set_bit(panel, "immediate-update", true);
    qdev_prop_set_bit(panel, "invert", true);
    object_property_add_child(qdev_get_machine(), "m5-panel", OBJECT(panel));
    qdev_realize_and_unref(panel, NULL, &error_fatal);
    esp32_spi_attach_m5_panel(DEVICE(&s->spi[3]), panel, 15);
    m5_unit_runtime_init(false);
    m5_unit_classic_adc_init(get_system_memory());
}

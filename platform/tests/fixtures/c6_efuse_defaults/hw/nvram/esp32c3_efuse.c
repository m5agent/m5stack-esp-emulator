/*
 * ESP32-C3 eFuse emulation
 *
 * Copyright (c) 2023-2024 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "hw/nvram/esp32c3_efuse.h"


static void esp32c3_efuse_realize(DeviceState *dev, Error **errp)
{
    ESP32C3EfuseClass* esp32c3_class = ESP32C3_EFUSE_GET_CLASS(dev);
    ESPEfuseState *s = ESP_EFUSE(dev);

    /* Call the realize function of the parent class, which will initialize the efuse blocks
     * or the efuse mirror (in RAM) */
    esp32c3_class->parent_realize(dev, errp);

    /* If no file was given as efuses, create a temporary one (in RAM). */
    if (s->blk == NULL) {
        assert(s->mirror != NULL);

        /* Set the chip revision to v0.3 and write it to the file */
        s->efuses.blocks.rd_mac_spi_sys_3 = FIELD_DP32(0, EFUSE_RD_MAC_SPI_SYS_3, WAFER_VER_MINOR_LO, 3);

        /* Set the chip eFuse block revision 1.3 */
        s->efuses.blocks.rd_sys_part1_data4 = FIELD_DP32(0, EFUSE_RD_SYS_PART1_DATA4, BLK_VERSION_MAJOR, 1);
        s->efuses.blocks.rd_mac_spi_sys_3 = FIELD_DP32(s->efuses.blocks.rd_mac_spi_sys_3,
                                                       EFUSE_RD_MAC_SPI_SYS_3, BLK_VERSION_MINOR, 3);

        memcpy(s->mirror, &s->efuses.blocks, sizeof(ESPEfuseBlocks));
    }
}


static void esp32c3_efuse_init(Object *obj)
{
    /* No need to call parent's class function, this is done automatically by the QOM, even before
     * calling the current function. */
}

static void esp32c3_efuse_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ESP32C3EfuseClass* esp32c3_efuse = ESP32C3_EFUSE_CLASS(klass);

    device_class_set_parent_realize(dc, esp32c3_efuse_realize, &esp32c3_efuse->parent_realize);
}

static const TypeInfo esp32c3_efuse_info = {
    .name = TYPE_ESP32C3_EFUSE,
    .parent = TYPE_ESP_EFUSE,
    .instance_size = sizeof(ESP32C3EfuseState),
    .instance_init = esp32c3_efuse_init,
    .class_init = esp32c3_efuse_class_init,
    .class_size = sizeof(ESP32C3EfuseClass)
};

static void esp32c3_efuse_register_types(void)
{
    type_register_static(&esp32c3_efuse_info);
}

type_init(esp32c3_efuse_register_types)

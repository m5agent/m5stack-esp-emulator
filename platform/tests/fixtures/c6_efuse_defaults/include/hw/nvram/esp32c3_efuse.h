/*
 * ESP32-C3 eFuse emulation
 *
 * Copyright (c) 2023-2024 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */
#pragma once

#include "esp_efuse.h"

#define TYPE_ESP32C3_EFUSE "nvram.esp32c3.efuse"
#define ESP32C3_EFUSE(obj) OBJECT_CHECK(ESP32C3EfuseState, (obj), TYPE_ESP32C3_EFUSE)
#define ESP32C3_EFUSE_GET_CLASS(obj) OBJECT_GET_CLASS(ESP32C3EfuseClass, obj, TYPE_ESP32C3_EFUSE)
#define ESP32C3_EFUSE_CLASS(klass) OBJECT_CLASS_CHECK(ESP32C3EfuseClass, klass, TYPE_ESP32C3_EFUSE)


typedef struct ESP32C3EfuseState {
    ESPEfuseState parent;
} ESP32C3EfuseState;


typedef struct ESP32C3EfuseClass {
    ESPEfuseClass parent_class;
    DeviceRealize parent_realize;
} ESP32C3EfuseClass;


/* These registers only need to be initialized for the C3 target */
REG32(EFUSE_RD_MAC_SPI_SYS_3, 0x50)
    FIELD(EFUSE_RD_MAC_SPI_SYS_3, BLK_VERSION_MINOR, 24, 3)
    FIELD(EFUSE_RD_MAC_SPI_SYS_3, WAFER_VER_MINOR_LO, 18, 3)

REG32(EFUSE_RD_SYS_PART1_DATA4, 0x6C)
    FIELD(EFUSE_RD_SYS_PART1_DATA4, BLK_VERSION_MAJOR, 0, 2)

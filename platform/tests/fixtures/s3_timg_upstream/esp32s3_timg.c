/*
 * ESP32-S3 "Timer Group" peripheral
 *
 * Copyright (c) 2025 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */
#include "qemu/osdep.h"
#include "hw/timer/esp32s3_timg.h"

static void esp32s3_timg_class_init(ObjectClass *klass, void *data)
{
    ESPTimgClass* esp = ESP_TIMG_CLASS(klass);
    esp->m_has_t1 = true;
}

static const TypeInfo esp32s3_timg_info = {
    .name = TYPE_ESP32S3_TIMG,
    .parent = TYPE_ESP_TIMG,
    .instance_size = sizeof(ESP32S3TimgState),
    .class_size = sizeof(ESP32S3TimgClass),
    .class_init = esp32s3_timg_class_init,
};

static void esp32s3_timg_register_types(void)
{
    type_register_static(&esp32s3_timg_info);
}

type_init(esp32s3_timg_register_types)

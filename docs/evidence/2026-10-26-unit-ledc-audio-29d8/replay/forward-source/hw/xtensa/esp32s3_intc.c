/*
 * ESP32S3 Interrupt Matrix
 *
 * Copyright (c) 2019-2024 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/hw.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "hw/misc/esp32s3_reg.h"
#include "hw/xtensa/esp32s3_intc.h"

#define INTMATRIX_UNINT_VALUE   6

#define INTC_DEBUG      0
#define INTC_WARNING    0

#define IRQ_MAP(cpu, input) s->irq_map[cpu][input]

static int esp32s3_intmatrix_output_index(Esp32s3IntMatrixState *s,
                                          int cpu_index, int out_index)
{
    for (int int_index = 0;
         int_index < s->cpu[cpu_index]->env.config->nextint; ++int_index) {
        if (s->cpu[cpu_index]->env.config->extint[int_index] == out_index) {
            return int_index;
        }
    }
    return -1;
}

static void esp32s3_intmatrix_update_line(Esp32s3IntMatrixState *s,
                                          int cpu_index, int out_index)
{
    if (s->outputs[cpu_index] == NULL || out_index == INTMATRIX_UNINT_VALUE) {
        return;
    }

    int int_index = esp32s3_intmatrix_output_index(s, cpu_index, out_index);
    if (int_index < 0) {
        return;
    }

    int level = 0;
    for (int source = 0; source < ESP32S3_INT_MATRIX_INPUTS; ++source) {
        if (IRQ_MAP(cpu_index, source) == out_index &&
            s->input_levels[source]) {
            level = 1;
            break;
        }
    }
    qemu_set_irq(s->outputs[cpu_index][int_index], level);
}

static void esp32s3_intmatrix_set_route(Esp32s3IntMatrixState *s,
                                        int cpu_index, int source_index,
                                        int out_index)
{
    int old_out = s->source_out[cpu_index][source_index];

    IRQ_MAP(cpu_index, source_index) = out_index;
    s->source_out[cpu_index][source_index] = out_index;
    if (old_out != out_index) {
        esp32s3_intmatrix_update_line(s, cpu_index, old_out);
    }
    esp32s3_intmatrix_update_line(s, cpu_index, out_index);
}

static void esp32s3_intmatrix_irq_handler(void *opaque, int n, int level)
{
    Esp32s3IntMatrixState *s = ESP32S3_INTMATRIX(opaque);

    s->input_levels[n] = !!level;
    if (getenv("M5SW_INTMATRIX_TRACE") &&
        (n == 22 || n == 30 || n == 31)) {
        fprintf(stderr, "[intmatrix] source=%d level=%d line0=%u\n",
                n, level, IRQ_MAP(0, n));
        if (s->cpu[0]) {
            fprintf(stderr, "[intmatrix] intenable=%08x intset=%08x\n",
                    s->cpu[0]->env.sregs[INTENABLE],
                    s->cpu[0]->env.sregs[INTSET]);
        }
    }
    for (int i = 0; i < ESP32S3_CPU_COUNT; ++i) {
        esp32s3_intmatrix_update_line(s, i, IRQ_MAP(i, n));
    }
}

static inline uint8_t* get_map_entry(Esp32s3IntMatrixState* s, hwaddr addr)
{
    int source_index = addr / sizeof(uint32_t);
    if (source_index > ESP32S3_INT_MATRIX_INPUTS * ESP32S3_CPU_COUNT) {
#if INTC_DEBUG
        info_report("%s: source_index %d out of range", __func__, source_index);
#endif // INTC_DEBUG
        return NULL;
    }
    int cpu_index = source_index / ESP32S3_INT_MATRIX_INPUTS;
    source_index = source_index % ESP32S3_INT_MATRIX_INPUTS;
    return &IRQ_MAP(cpu_index, source_index);
}

static uint64_t esp32s3_intmatrix_read(void* opaque, hwaddr addr, unsigned int size)
{
    Esp32s3IntMatrixState *s = ESP32S3_INTMATRIX(opaque);
    uint8_t* map_entry = get_map_entry(s, addr);
    return (map_entry != NULL) ? *map_entry : 0;
}

static void esp32s3_intmatrix_write(void* opaque, hwaddr addr, uint64_t value, unsigned int size)
{
#if INTC_DEBUG
    info_report("\x1b[31m[INTC] esp32s3_intmatrix_write  addr = %ld, value=%ld\x1b[0m", addr, value);
#endif // INTC_DEBUG
    Esp32s3IntMatrixState *s = ESP32S3_INTMATRIX(opaque);
    uint8_t* map_entry = get_map_entry(s, addr);
    if (map_entry != NULL) {
        int source_index = addr / sizeof(uint32_t);
        int cpu_index = source_index / ESP32S3_INT_MATRIX_INPUTS;

        int out_index = value & 0x1f;
        if (getenv("M5SW_INTMATRIX_TRACE") &&
            (source_index == 22 || source_index == 30 ||
             source_index == 31)) {
            fprintf(stderr,
                    "[intmatrix] map source=%d line=%u level=%u\n",
                    source_index, out_index,
                    s->input_levels[source_index]);
        }
        esp32s3_intmatrix_set_route(
            s, cpu_index, source_index % ESP32S3_INT_MATRIX_INPUTS,
            out_index);
    }
}

static const MemoryRegionOps esp_intmatrix_ops = {
    .read =  esp32s3_intmatrix_read,
    .write = esp32s3_intmatrix_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32s3_intmatrix_reset_hold(Object *obj, ResetType type)
{
    Esp32s3IntMatrixState *s = ESP32S3_INTMATRIX(obj);
    memset(s->irq_map, INTMATRIX_UNINT_VALUE, sizeof(s->irq_map));
    memset(s->input_levels, 0, sizeof(s->input_levels));
    memset(s->source_out, INTMATRIX_UNINT_VALUE, sizeof(s->source_out));
    for (int i = 0; i < ESP32S3_CPU_COUNT; ++i) {
        if (s->outputs[i] == NULL) {
            continue;
        }
        for (int int_index = 0; int_index < s->cpu[i]->env.config->nextint; ++int_index) {
            qemu_irq_lower(s->outputs[i][int_index]);
        }
    }
}

static void esp32s3_intmatrix_realize(DeviceState *dev, Error **errp)
{
    Esp32s3IntMatrixState *s = ESP32S3_INTMATRIX(dev);

    for (int i = 0; i < ESP32S3_CPU_COUNT; ++i) {
        if (s->cpu[i]) {
            s->outputs[i] = xtensa_get_extints(&s->cpu[i]->env);
        }
    }
    esp32s3_intmatrix_reset_hold(OBJECT(dev), RESET_TYPE_COLD);
}

static void esp32s3_intmatrix_init(Object *obj)
{
    Esp32s3IntMatrixState *s = ESP32S3_INTMATRIX(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &esp_intmatrix_ops, s,
                          TYPE_ESP32S3_INTMATRIX, ESP32S3_INT_MATRIX_INPUTS * ESP32S3_CPU_COUNT * sizeof(uint32_t));
    sysbus_init_mmio(sbd, &s->iomem);

    qdev_init_gpio_in(DEVICE(s), esp32s3_intmatrix_irq_handler, ESP32S3_INT_MATRIX_INPUTS);
}

static Property esp32s3_intmatrix_properties[] = {
    DEFINE_PROP_LINK("cpu0", Esp32s3IntMatrixState, cpu[0], TYPE_XTENSA_CPU, XtensaCPU *),
    DEFINE_PROP_LINK("cpu1", Esp32s3IntMatrixState, cpu[1], TYPE_XTENSA_CPU, XtensaCPU *),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32s3_intmatrix_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    rc->phases.hold = esp32s3_intmatrix_reset_hold;
    dc->realize = esp32s3_intmatrix_realize;
    device_class_set_props(dc, esp32s3_intmatrix_properties);
}

static const TypeInfo esp32s3_intmatrix_info = {
    .name = TYPE_ESP32S3_INTMATRIX,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32s3IntMatrixState),
    .instance_init = esp32s3_intmatrix_init,
    .class_init = esp32s3_intmatrix_class_init
};

static void esp32s3_intmatrix_register_types(void)
{
    type_register_static(&esp32s3_intmatrix_info);
}

type_init(esp32s3_intmatrix_register_types)

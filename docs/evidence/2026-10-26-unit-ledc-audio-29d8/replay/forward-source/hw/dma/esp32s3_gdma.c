/*
 * ESP32-S3 GDMA emulation
 *
 * Copyright (c) 2023-2025 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "qemu/error-report.h"
#include "hw/dma/esp_gdma.h"
#include "hw/dma/esp32s3_gdma.h"


#define ESP32S3_GDMA_WARNING    0
#define ESP32S3_GDMA_DEBUG      0


/* For now, make sure the generic interrupt implementation matches the S3's */
_Static_assert((int) R_DMA_INT_RAW_IN_DSCR_EMPTY_MASK == (int) R_GDMA_INTERRUPT_IN_DSCR_EMPTY_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_IN_DSCR_ERR_MASK   == (int) R_GDMA_INTERRUPT_IN_DSCR_ERR_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_IN_ERR_EOF_MASK    == (int) R_GDMA_INTERRUPT_IN_ERR_EOF_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_IN_SUC_EOF_MASK    == (int) R_GDMA_INTERRUPT_IN_SUC_EOF_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_IN_DONE_MASK       == (int) R_GDMA_INTERRUPT_IN_DONE_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");

_Static_assert((int) R_DMA_INT_RAW_OUT_TOTAL_EOF_MASK == (int) R_GDMA_INTERRUPT_OUT_TOTAL_EOF_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_OUT_DSCR_ERR_MASK  == (int) R_GDMA_INTERRUPT_OUT_DSCR_ERR_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_OUT_EOF_MASK       == (int) R_GDMA_INTERRUPT_OUT_EOF_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");
_Static_assert((int) R_DMA_INT_RAW_OUT_DONE_MASK      == (int) R_GDMA_INTERRUPT_OUT_DONE_MASK, "ESP32-S3 GDMA interrupt register's fields must match the generic GDMA's");


static DmaRegister esp32s3_generic_reg(uint32_t reg)
{
    /* Even though the virtual registers are organized the same way as the virtual registers, make this table as an example
     * for other targets or drivers. */
    const DmaRegister assoc[] = {
        [R_DMA_CONF0]         = GDMA_CONF0_REG,
        [R_DMA_CONF1]         = GDMA_CONF1_REG,
        [R_DMA_INT_RAW]       = GDMA_INT_RAW_REG,
        [R_DMA_INT_ST]        = GDMA_INT_ST_REG,
        [R_DMA_INT_ENA]       = GDMA_INT_ENA_REG,
        [R_DMA_INT_CLR]       = GDMA_INT_CLR_REG,
        [R_DMA_FIFO_ST]       = GDMA_FIFO_ST_REG,
        [R_DMA_POP]           = GDMA_POP_REG,
        [R_DMA_LINK]          = GDMA_LINK_REG,
        [R_DMA_STATE]         = GDMA_STATE_REG,
        [R_DMA_SUC_EOF_DESC]  = GDMA_SUC_EOF_DESC_REG,
        [R_DMA_ERR_EOF_DESC]  = GDMA_ERR_EOF_DESC_REG,
        [R_DMA_DESC_ADDR]     = GDMA_DESC_ADDR_REG,
        [R_DMA_BF0_DESC_ADDR] = GDMA_BF0_DESC_ADDR_REG,
        [R_DMA_BF1_DESC_ADDR] = GDMA_BF1_DESC_ADDR_REG,
        [R_DMA_DUMMY_3C]      = GDMA_DUMMY_3C_REG,
        [R_DMA_DUMMY_40]      = GDMA_DUMMY_40_REG,
        [R_DMA_PRIORITY]      = GDMA_PRIORITY_REG,
        [R_DMA_PERI_SEL]      = GDMA_PERI_SEL_REG,
    };

    /* The `reg` is expressed in bytes while in the array, the entries are expressed in words */
    const uint32_t word = reg / sizeof(uint32_t);
    if (word >= sizeof(assoc)/sizeof(*assoc)) {
        return GDMA_UNKNOWN;
    }

    return assoc[word];
}


static uint64_t esp32s3_gdma_read(void *opaque, hwaddr addr, unsigned int size)
{
    ESP32S3GdmaState *s = ESP32S3_GDMA(opaque);
    ESPGdmaState *parent = &s->parent;
    uint64_t r = 0;

    /* Check which channel and which direction is being written to */
    const uint32_t chan_with_dir = addr / DMA_DIR_REGS_SIZE;
    const uint32_t chan = chan_with_dir >> 1;
    const uint32_t dir = (chan_with_dir & 1) ? ESP_GDMA_OUT_IDX : ESP_GDMA_IN_IDX;
    const uint32_t reg = addr % DMA_DIR_REGS_SIZE;

    if (chan < ESP32S3_GDMA_CHANNEL_COUNT) {
        r = esp_gdma_read_chan_register(parent, dir, chan, esp32s3_generic_reg(reg));
        if (getenv("M5SW_GDMA_TRACE") && reg <= R_DMA_INT_CLR) {
            fprintf(stderr,
                    "[gdma-mmio] rd addr=%04lx dir=%u chan=%u reg=%02x val=%08lx\n",
                    (unsigned long)addr, dir, chan, reg,
                    (unsigned long)r);
        }
    } else if (addr == A_DMA_MISC_CONF) {
        r = esp_gdma_read_register(parent, GDMA_MISC_REG);
    } else {
        /* Unknown or dummy register */
#if ESP32S3_GDMA_WARNING
        warn_report("[S3][GDMA] Unsupported read to %08lx", addr);
#endif
    }

#if ESP32S3_GDMA_DEBUG
    info_report("[S3][GDMA] Reading from %08lx (%08lx)", addr, r);
#endif

    return r;
}


static void esp32s3_gdma_write(void *opaque, hwaddr addr,
                               uint64_t value, unsigned int size)
{
    ESP32S3GdmaState *s = ESP32S3_GDMA(opaque);
    ESPGdmaState *parent = &s->parent;

#if ESP32S3_GDMA_DEBUG
    info_report("[S3][GDMA] Writing to %08lx (%08lx)", addr, value);
#endif

    /* Check which channel and which direction is being written to */
    const uint32_t chan_with_dir = addr / DMA_DIR_REGS_SIZE;
    const uint32_t chan = chan_with_dir >> 1;
    const uint32_t dir = (chan_with_dir & 1) ? ESP_GDMA_OUT_IDX : ESP_GDMA_IN_IDX;
    const uint32_t reg = addr % DMA_DIR_REGS_SIZE;

    if (getenv("M5SW_GDMA_TRACE")) {
        fprintf(stderr, "[gdma-mmio] addr=%04lx val=%08lx dir=%u chan=%u reg=%02x\n",
                (unsigned long)addr, (unsigned long)value,
                dir, chan, reg);
    }


    if (chan < ESP32S3_GDMA_CHANNEL_COUNT) {
        esp_gdma_write_chan_register(parent, dir, chan, esp32s3_generic_reg(reg), value);
    } else if (addr == A_DMA_MISC_CONF) {
        esp_gdma_write_register(parent, GDMA_MISC_REG, value);
    } else {
        /* Unknown or dummy register */
#if ESP32S3_GDMA_WARNING
        warn_report("[GDMA] Unsupported write to %08lx (%08lx)", addr, value);
#endif
    }
}

static const MemoryRegionOps esp_gdma_ops = {
    .read =  esp32s3_gdma_read,
    .write = esp32s3_gdma_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};


static void esp32s3_gdma_init(Object *obj)
{
    ESP32S3GdmaState *s = ESP32S3_GDMA(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &esp_gdma_ops, s,
                          TYPE_ESP32S3_GDMA, ESP32S3_GDMA_REGS_SIZE);
    sysbus_init_mmio(sbd, &s->iomem);
}


static void esp32s3_gdma_class_init(ObjectClass *klass, void *data)
{
    ESPGdmaClass* class = ESP_GDMA_CLASS(klass);
    /* Make sure all the peripherals are valid */
    class->is_periph_invalid = NULL;

    class->m_channel_count = ESP32S3_GDMA_CHANNEL_COUNT;
}


static const TypeInfo esp32s3_gdma_info = {
    .name = TYPE_ESP32S3_GDMA,
    .parent = TYPE_ESP_GDMA,
    .instance_size = sizeof(ESP32S3GdmaState),
    .instance_init = esp32s3_gdma_init,
    .class_init = esp32s3_gdma_class_init,
    .class_size = sizeof(ESP32S3GdmaClass)
};


static void esp32s3_gdma_register_types(void)
{
    type_register_static(&esp32s3_gdma_info);
}


type_init(esp32s3_gdma_register_types)

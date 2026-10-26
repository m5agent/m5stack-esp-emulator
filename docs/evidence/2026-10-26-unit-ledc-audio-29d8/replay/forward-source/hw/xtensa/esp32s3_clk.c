/*
 * ESP32-S3 Clocks definition
 *
 * Copyright (c) 2024 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "hw/hw.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "hw/xtensa/esp32s3_clk.h"
#include "hw/xtensa/esp32s3_clk_defs.h"

#define CLOCK_DEBUG      0
#define CLOCK_WARNING    0

static uint32_t esp32s3_read_cpu_intr(ESP32S3ClockState *s, uint32_t index)
{
    return (s->levels >> index) & 1;
}


static void esp32s3_write_cpu_intr(ESP32S3ClockState *s, uint32_t index, uint32_t value)
{
    const uint32_t field = FIELD_EX32(value, SYSTEM_CPU_INTR_FROM_CPU_0, CPU_INTR_FROM_CPU_0);
    if (field) {
        s->levels |= BIT(index);
        qemu_set_irq(s->irqs[index], 1);
    } else {
        s->levels &= ~BIT(index);
        qemu_set_irq(s->irqs[index], 0);
    }
}

static uint32_t esp32s3_clock_get_ext_dev_enc_dec_ctrl(ESP32S3ClockState *s)
{
    return s->sys_ext_dev_enc_dec_ctrl;
}

static uint64_t esp32s3_clock_read(void *opaque, hwaddr addr, unsigned int size)
{
    ESP32S3ClockState *s = ESP32S3_CLOCK(opaque);
    uint64_t r = 0;

    switch(addr) {
        case A_SYSTEM_CORE_1_CONTROL_1_REG:
                r = s->app_cpu_addr;
            break;
        case A_SYSTEM_CPU_PER_CONF:
            r = s->cpuperconf;
            break;
        case A_SYSTEM_SYSCLK_CONF:
            r = s->sysclk;
            break;
        case A_SYSTEM_PERIP_CLK_EN0:
            r = s->perip_clk_en0;
            break;
        case A_SYSTEM_PERIP_CLK_EN1:
            r = s->perip_clk_en1;
            break;
        case A_SYSTEM_PERIP_RST_EN0:
            r = s->perip_rst_en0;
            break;
        case A_SYSTEM_PERIP_RST_EN1:
            r = s->perip_rst_en1;
            break;
        case A_SYSTEM_BT_LPCK_DIV_INT:
            r = s->bt_lpck_div_int;
            if (getenv("M5SW_CLK_TRACE")) {
                fprintf(stderr, "[clk] rd %03" HWADDR_PRIx " -> %08" PRIx64 "\n",
                        addr, r);
            }
            break;
        case A_SYSTEM_BT_LPCK_DIV_FRAC:
            r = s->bt_lpck_div_frac;
            if (getenv("M5SW_CLK_TRACE")) {
                fprintf(stderr, "[clk] rd %03" HWADDR_PRIx " -> %08" PRIx64 "\n",
                        addr, r);
            }
            break;
        case A_SYSTEM_CPU_INTR_FROM_CPU_0:
        case A_SYSTEM_CPU_INTR_FROM_CPU_1:
        case A_SYSTEM_CPU_INTR_FROM_CPU_2:
        case A_SYSTEM_CPU_INTR_FROM_CPU_3:
            r = esp32s3_read_cpu_intr(s, (addr - A_SYSTEM_CPU_INTR_FROM_CPU_0) / sizeof(uint32_t));
            break;
        case A_SYSTEM_EXTERNAL_DEVICE_ENCRYPT_DECRYPT_CONTROL:
            r = s->sys_ext_dev_enc_dec_ctrl;
            break;
        default:
#if CLOCK_WARNING
            warn_report("[CLOCK] Unsupported read from %08lx\n", addr);
#endif
            break;
    }
    return r;
}

static void esp32s3_clock_write(void *opaque, hwaddr addr, uint64_t value,
                                unsigned int size)
{
    ESP32S3ClockState *s = ESP32S3_CLOCK(opaque);

    if (getenv("M5SW_CLK_TRACE")
        && (addr == A_SYSTEM_PERIP_CLK_EN0
            || addr == A_SYSTEM_PERIP_CLK_EN1
            || addr == A_SYSTEM_PERIP_RST_EN0
            || addr == A_SYSTEM_PERIP_RST_EN1
            || addr == A_SYSTEM_BT_LPCK_DIV_INT
            || addr == A_SYSTEM_BT_LPCK_DIV_FRAC)) {
        fprintf(stderr, "[clk] wr %03" HWADDR_PRIx " <- %08" PRIx64 "\n",
                addr, value);
    }
    switch(addr) {
        case A_SYSTEM_CORE_1_CONTROL_1_REG:
                s->app_cpu_addr = (uint32_t)value;
            break;
        case A_SYSTEM_PERIP_CLK_EN0:
            s->perip_clk_en0 = (uint32_t)value;
            if (s->perip_clk_en1 & BIT(9)) {
                s->perip_clk_en0 |= BIT(9);
            }
            break;
        case A_SYSTEM_PERIP_CLK_EN1:
            s->perip_clk_en1 = (uint32_t)value;
            /*
             * ESP-IDF v5.5.4's uart_ll_is_enabled() checks UART2 through the
             * EN0 register even though the real gate is EN1 bit 9.  Mirror the
             * gate so the unmodified driver can validate the port.
             */
            if (s->perip_clk_en1 & BIT(9)) {
                s->perip_clk_en0 |= BIT(9);
            } else {
                s->perip_clk_en0 &= ~BIT(9);
            }
            break;
        case A_SYSTEM_PERIP_RST_EN0:
            s->perip_rst_en0 = (uint32_t)value;
            if (s->perip_rst_en1 & BIT(9)) {
                s->perip_rst_en0 |= BIT(9);
            } else {
                s->perip_rst_en0 &= ~BIT(9);
            }
            break;
        case A_SYSTEM_PERIP_RST_EN1:
            s->perip_rst_en1 = (uint32_t)value;
            if (s->perip_rst_en1 & BIT(9)) {
                s->perip_rst_en0 |= BIT(9);
            } else {
                s->perip_rst_en0 &= ~BIT(9);
            }
            break;
        case A_SYSTEM_BT_LPCK_DIV_INT:
            s->bt_lpck_div_int = (uint32_t)value & 0xfffU;
            break;
        case A_SYSTEM_BT_LPCK_DIV_FRAC:
            /*
             * BTDM programs the LP clock source and dividers here, then
             * immediately reads the register back before returning success.
             * Preserve the implemented fields so those hardware handshakes
             * observe the same write/read semantics as the real SoC.
             */
            s->bt_lpck_div_frac = (uint32_t)value & 0x1fffffffU;
            break;
        case A_SYSTEM_CPU_INTR_FROM_CPU_0:
        case A_SYSTEM_CPU_INTR_FROM_CPU_1:
        case A_SYSTEM_CPU_INTR_FROM_CPU_2:
        case A_SYSTEM_CPU_INTR_FROM_CPU_3:
            esp32s3_write_cpu_intr(s, (addr - A_SYSTEM_CPU_INTR_FROM_CPU_0) / sizeof(uint32_t), value);
            break;
        case A_SYSTEM_EXTERNAL_DEVICE_ENCRYPT_DECRYPT_CONTROL:
            s->sys_ext_dev_enc_dec_ctrl = value;
            break;
        default:
#if CLOCK_WARNING
            warn_report("[CLOCK] Unsupported write to %08lx (%08lx)\n", addr, value);
#endif
            break;
    }
}

static const MemoryRegionOps esp32s3_clock_ops = {
    .read =  esp32s3_clock_read,
    .write = esp32s3_clock_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32s3_clock_reset_hold(Object *obj, ResetType type)
{
    ESP32S3ClockState *s = ESP32S3_CLOCK(obj);
    /* On board reset, set the proper clocks and dividers */
    s->sysclk = ( 1 << R_SYSTEM_SYSCLK_CONF_PRE_DIV_CNT_SHIFT) |
                (ESP32S3_CLK_SEL_PLL << R_SYSTEM_SYSCLK_CONF_SOC_CLK_SEL_SHIFT) |
                (40 << R_SYSTEM_SYSCLK_CONF_CLK_XTAL_FREQ_SHIFT) |
                ( 1 << R_SYSTEM_SYSCLK_CONF_CLK_DIV_EN_SHIFT);

    /* Divider for PLL clock and APB  frequency */
    s->cpuperconf = (ESP32S3_PERIOD_SEL_80 << R_SYSTEM_CPU_PER_CONF_CPUPERIOD_SEL_SHIFT) |
                    (ESP32S3_FREQ_SEL_PLL_480 << R_SYSTEM_CPU_PER_CONF_PLL_FREQ_SEL_SHIFT);

    /* Peripheral clock/reset gate reset values, including UART0/1/2. */
    s->perip_clk_en0 = 0xffffffffU;
    s->perip_clk_en0 &= ~((1U << 26) | (1U << 25) | (1U << 21) |
                          (1U << 20) | (1U << 19) | (1U << 18) |
                          (1U << 17) | (1U << 12) | (1U << 11) |
                          (1U << 10) | (1U << 8) |
                          (1U << 7) | (1U << 4));
    /* Keep the EN0 bit used by IDF's UART2 enabled check readable. */
    s->perip_clk_en0 |= BIT(9);
    s->perip_clk_en1 = (1U << 10) | (1U << 9);
    s->perip_rst_en0 = 0;
    s->perip_rst_en1 = (1U << 10) | (1U << 8) | (1U << 7) |
                       (1U << 6) | (1U << 5) | (1U << 4) |
                       (1U << 3) | (1U << 2) | (1U << 1) |
                       (1U << 0);
    s->bt_lpck_div_int = 0xfff;
    s->bt_lpck_div_frac = BIT(25) | (1U << 12) | 1U;

    /* Initialize the IRQs */
    s->levels = 0;
    for (int i = 0 ; i < ESP32S3_SYSTEM_CPU_INTR_COUNT; i++) {
        qemu_irq_lower(s->irqs[i]);
    }
}

static void esp32s3_clock_realize(DeviceState *dev, Error **errp)
{
    /* Initialize the registers */
    esp32s3_clock_reset_hold(OBJECT(dev), RESET_TYPE_COLD);
}

static void esp32s3_clock_init(Object *obj)
{
    ESP32S3ClockState *s = ESP32S3_CLOCK(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &esp32s3_clock_ops, s,
                          TYPE_ESP32S3_CLOCK, A_SYSTEM_COMB_PVT_ERR_HVT_SITE3 + sizeof(uint32_t));
    sysbus_init_mmio(sbd, &s->iomem);

    /* Initialize the output IRQ lines used to manually trigger interrupts */
    for (uint64_t i = 0; i < ESP32S3_SYSTEM_CPU_INTR_COUNT; i++) {
        sysbus_init_irq(sbd, &s->irqs[i]);
    }
}

static void esp32s3_clock_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ESP32S3ClockClass* esp32s3_clock = ESP32S3_CLOCK_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    rc->phases.hold = esp32s3_clock_reset_hold;
    dc->realize = esp32s3_clock_realize;

    esp32s3_clock->get_ext_dev_enc_dec_ctrl = esp32s3_clock_get_ext_dev_enc_dec_ctrl;
}

static const TypeInfo esp32s3_cache_info = {
    .name = TYPE_ESP32S3_CLOCK,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(ESP32S3ClockState),
    .instance_init = esp32s3_clock_init,
    .class_init = esp32s3_clock_class_init,
    .class_size = sizeof(ESP32S3ClockClass)
};

static void esp32s3_cache_register_types(void)
{
    type_register_static(&esp32s3_cache_info);
}

type_init(esp32s3_cache_register_types)

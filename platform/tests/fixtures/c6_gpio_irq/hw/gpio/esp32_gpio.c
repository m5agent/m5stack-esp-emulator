/*
 * ESP32/C3/C6 GPIO emulation
 *
 * Copyright (c) 2019 Espressif Systems (Shanghai) Co. Ltd.
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
#include "hw/registerfields.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "hw/gpio/esp32_gpio.h"

#define GPIO_NPINS 54

static uint64_t g_ext_in = ~0ULL;
static uint32_t g_regs[0x200];
static uint64_t g_open_drain;
static uint64_t g_force_mask;
static uint64_t g_force_level;
/* Only connected peripheral signals override GPIO register outputs. */
static struct {
    bool valid;
    bool level;
    bool enabled;
} g_output_signals[128];
static struct {
    esp32_gpio_out_cb cb;
    void *opaque;
} g_listeners[GPIO_NPINS];

static uint64_t gpio_line64(void);

void esp32_gpio_set_input(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    if (level) {
        g_ext_in |= 1ULL << pin;
    } else {
        g_ext_in &= ~(1ULL << pin);
    }
}

void esp32_gpio_add_out_listener(int pin, esp32_gpio_out_cb cb, void *opaque)
{
    if (pin >= 0 && pin < GPIO_NPINS) {
        g_listeners[pin].cb = cb;
        g_listeners[pin].opaque = opaque;
    }
}

void esp32_gpio_set_open_drain(int pin, bool enable)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    if (enable) {
        g_open_drain |= 1ULL << pin;
    } else {
        g_open_drain &= ~(1ULL << pin);
    }
}

void esp32_gpio_force_line(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    g_force_mask |= 1ULL << pin;
    if (level) {
        g_force_level |= 1ULL << pin;
    } else {
        g_force_level &= ~(1ULL << pin);
    }
}

int esp32_gpio_get_line(int pin)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return 1;
    }
    return (gpio_line64() >> pin) & 1;
}

static uint64_t gpio_out64(void)
{
    return (uint64_t)g_regs[0x04 / 4] |
           ((uint64_t)g_regs[0x10 / 4] << 32);
}

static uint64_t gpio_en64(void)
{
    return (uint64_t)g_regs[0x20 / 4] |
           ((uint64_t)g_regs[0x2c / 4] << 32);
}

static uint64_t gpio_line64(void)
{
    uint64_t out = gpio_out64();
    uint64_t en = gpio_en64();
    for (unsigned pin = 0; pin < GPIO_NPINS; pin++) {
        uint32_t cfg = g_regs[(0x554 + pin * 4) / 4];
        unsigned signal = cfg & 0xff;
        if (signal < ARRAY_SIZE(g_output_signals) &&
            g_output_signals[signal].valid) {
            uint64_t bit = 1ULL << pin;
            bool level = g_output_signals[signal].level ^ !!(cfg & BIT(8));
            bool enable = (cfg & BIT(9)) ? !!(en & bit) :
                          g_output_signals[signal].enabled;
            enable ^= !!(cfg & BIT(10));
            out = (out & ~bit) | (level ? bit : 0);
            en = (en & ~bit) | (enable ? bit : 0);
        }
    }
    uint64_t driven = out & en;
    uint64_t line = (driven & ~g_open_drain)
                  | ((driven & g_ext_in) & g_open_drain)
                  | (~en & g_ext_in);

    return (line & ~g_force_mask) | (g_force_level & g_force_mask);
}

static void gpio_notify(uint64_t before, uint64_t after)
{
    uint64_t diff = before ^ after;

    for (int i = 0; diff && i < GPIO_NPINS; i++) {
        if ((diff >> i) & 1) {
            if (g_listeners[i].cb) {
                g_listeners[i].cb(g_listeners[i].opaque, i,
                                  (after >> i) & 1);
            }
        }
    }
}

void esp32_gpio_set_output_signal(int signal, int level, bool enabled)
{
    if (signal < 0 || signal >= ARRAY_SIZE(g_output_signals)) {
        return;
    }
    uint64_t before = gpio_line64();
    g_output_signals[signal].valid = true;
    g_output_signals[signal].level = !!level;
    g_output_signals[signal].enabled = enabled;
    gpio_notify(before, gpio_line64());
}

static uint64_t esp32_gpio_read(void *opaque, hwaddr addr, unsigned int size)
{
    Esp32GpioState *s = ESP32_GPIO(opaque);
    uint64_t in = gpio_line64();

    switch (addr) {
    case A_GPIO_STRAP:
        return s->strap_mode;
    case 0x3c:
        return (uint32_t)in;
    case 0x40:
        return (uint32_t)(in >> 32) & 0x3fffff;
    case 0x08:
    case 0x0c:
    case 0x14:
    case 0x18:
    case 0x24:
    case 0x28:
    case 0x30:
    case 0x34:
        return 0;
    default:
        if (addr < sizeof(g_regs)) {
            return g_regs[addr / 4];
        }
        return 0;
    }
}

static void esp32_gpio_write(void *opaque, hwaddr addr,
                             uint64_t value, unsigned int size)
{
    uint64_t before = gpio_line64();
    uint64_t after;

    switch (addr) {
    case 0x08:
        g_regs[0x04 / 4] |= value;
        break;
    case 0x0c:
        g_regs[0x04 / 4] &= ~value;
        break;
    case 0x14:
        g_regs[0x10 / 4] |= value;
        break;
    case 0x18:
        g_regs[0x10 / 4] &= ~value;
        break;
    case 0x24:
        g_regs[0x20 / 4] |= value;
        break;
    case 0x28:
        g_regs[0x20 / 4] &= ~value;
        break;
    case 0x30:
        g_regs[0x2c / 4] |= value;
        break;
    case 0x34:
        g_regs[0x2c / 4] &= ~value;
        break;
    case 0x48:
        g_regs[0x44 / 4] |= value;
        break;
    case 0x4c:
        g_regs[0x44 / 4] &= ~value;
        break;
    case 0x54:
        g_regs[0x50 / 4] |= value;
        break;
    case 0x58:
        g_regs[0x50 / 4] &= ~value;
        break;
    case A_GPIO_STRAP:
    case 0x3c:
    case 0x40:
        break;
    default:
        if (addr < sizeof(g_regs)) {
            g_regs[addr / 4] = value;
            if (addr >= 0x74 && addr < 0x74 + GPIO_NPINS * 4) {
                uint64_t bit = 1ULL << ((addr - 0x74) / 4);
                if (value & (1u << 2)) {
                    g_open_drain |= bit;
                } else {
                    g_open_drain &= ~bit;
                }
            }
        }
        break;
    }
    after = gpio_line64();
    if (getenv("M5SW_GPIO_TRACE") &&
        addr >= 0x04 && addr <= 0x58) {
        fprintf(stderr,
                "[c6-gpio] wr %02" HWADDR_PRIx " <- %016" PRIx64
                " out=%016" PRIx64 " en=%016" PRIx64
                " od=%016" PRIx64 " in=%016" PRIx64
                " fm=%016" PRIx64 " fl=%016" PRIx64
                " line=%016" PRIx64 "->%016" PRIx64
                "\n",
                addr, value, gpio_out64(), gpio_en64(), g_open_drain,
                g_ext_in, g_force_mask, g_force_level, before, after);
    }
    gpio_notify(before, after);
}

static const MemoryRegionOps esp32_gpio_ops = {
    .read = esp32_gpio_read,
    .write = esp32_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32_gpio_reset_hold(Object *obj, ResetType type)
{
}

static void esp32_gpio_realize(DeviceState *dev, Error **errp)
{
}

static void esp32_gpio_init(Object *obj)
{
    Esp32GpioState *s = ESP32_GPIO(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    object_property_set_int(obj, "strap_mode", ESP32_STRAP_MODE_FLASH_BOOT,
                            &error_fatal);
    memory_region_init_io(&s->iomem, obj, &esp32_gpio_ops, s,
                          TYPE_ESP32_GPIO, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
}

static Property esp32_gpio_properties[] = {
    DEFINE_PROP_UINT32("strap_mode", Esp32GpioState, strap_mode, 0),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32_gpio_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    rc->phases.hold = esp32_gpio_reset_hold;
    dc->realize = esp32_gpio_realize;
    device_class_set_props(dc, esp32_gpio_properties);
}

static const TypeInfo esp32_gpio_info = {
    .name = TYPE_ESP32_GPIO,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32GpioState),
    .instance_init = esp32_gpio_init,
    .class_init = esp32_gpio_class_init,
    .class_size = sizeof(Esp32GpioClass),
};

static void esp32_gpio_register_types(void)
{
    type_register_static(&esp32_gpio_info);
}

type_init(esp32_gpio_register_types)

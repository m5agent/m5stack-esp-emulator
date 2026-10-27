/*
 * ESP32 GPIO emulation
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
#include "hw/misc/esp32_ledc.h"
#include "../m5stopwatch/m5stopwatch.h"
#include "../m5stopwatch/m5_unit_runtime.h"



/*
 * Minimal functional GPIO model: register storage, OUT/ENABLE W1TS/W1TC,
 * IN/IN1 computed from outputs and externally driven inputs (default: pulled up).
 * Output-change listeners let board models observe e.g. software chip-selects.
 */
#define GPIO_NPINS 54
#define GPIO_MAX_LISTENERS 8
static uint64_t g_ext_in = ~0ULL;      /* externally driven input levels */
static uint32_t g_regs[0x200];         /* 0x000..0x7ff */
static Esp32GpioState *g_gpio_device;
static bool g_gpio_s3;
static void gpio_transition_irq(uint64_t before, uint64_t after);
static void gpio_update_irq(void);
static uint64_t g_open_drain;          /* pins whose output stage is open-drain */
static uint64_t g_force_mask;          /* passive board lines forced by a model */
static uint64_t g_force_level;
static struct {
    esp32_gpio_out_cb cb;
    void *opaque;
} g_listeners[GPIO_NPINS][GPIO_MAX_LISTENERS];
static uint8_t g_listener_count[GPIO_NPINS];
static int g_trace_last_level = -1;

static uint64_t gpio_line64(void);

static int gpio_trace_pin(void)
{
    const char *value = getenv("M5SW_GPIO_TRACE_PIN");
    int pin = value ? atoi(value) : 18;

    return pin >= 0 && pin < GPIO_NPINS ? pin : 18;
}

void esp32_gpio_set_input(int pin, int level)
{
    if (pin < 0 || pin >= GPIO_NPINS) {
        return;
    }
    uint64_t before = gpio_line64();
    if (level) {
        g_ext_in |= 1ULL << pin;
    } else {
        g_ext_in &= ~(1ULL << pin);
    }
    gpio_transition_irq(before, gpio_line64());
    if (getenv("M5SW_GPIO_TRACE") &&
        (pin == 11 || pin == 12 || pin == gpio_trace_pin())) {
        fprintf(stderr, "[gpio] ext input pin=%d level=%d line=%d\n",
                pin, level, esp32_gpio_get_line(pin));
    }
}

void esp32_gpio_add_out_listener(int pin, esp32_gpio_out_cb cb, void *opaque)
{
    if (pin < 0 || pin >= GPIO_NPINS || !cb) {
        return;
    }
    if (g_listener_count[pin] >= GPIO_MAX_LISTENERS) {
        fprintf(stderr, "[gpio] listener overflow pin=%d\n", pin);
        return;
    }
    unsigned slot = g_listener_count[pin]++;
    g_listeners[pin][slot].cb = cb;
    g_listeners[pin][slot].opaque = opaque;
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
    int level = (gpio_line64() >> pin) & 1;
    if (getenv("M5SW_GPIO_TRACE") && pin == gpio_trace_pin()) {
        fprintf(stderr, "[gpio] get pin=%d level=%d force=%d\n",
                pin, level, !!(g_force_mask & (1ULL << pin)));
    }
    return level;
}

static uint64_t gpio_out64(void)
{
    return (uint64_t)g_regs[0x04 / 4] | ((uint64_t)g_regs[0x10 / 4] << 32);
}

static uint64_t gpio_en64(void)
{
    return (uint64_t)g_regs[0x20 / 4] | ((uint64_t)g_regs[0x2c / 4] << 32);
}

/*
 * Effective pin level: driven output when the pin is enabled, otherwise
 * the board's external pull-up.  Software-I2C listeners need this rather
 * than the raw OUT register, because switching a pin between output-low
 * and input is a real bus transition.
 */
static uint64_t gpio_line64(void)
{
    uint64_t out = gpio_out64();
    uint64_t en = gpio_en64();
    uint64_t driven = out & en;

    /*
     * An open-drain output can only pull low: when its latch is high the
     * actual line level is determined by the external pull-up/devices.
     * This is what makes software-I2C acknowledge bits visible to the
     * master while it is releasing SDA.
     */
    uint64_t line = (driven & ~g_open_drain)
                  | ((driven & g_ext_in) & g_open_drain)
                  | (~en & g_ext_in);
    return (line & ~g_force_mask) | (g_force_level & g_force_mask);
}

static void gpio_update_irq(void)
{
    if (!g_gpio_device) { return; }
    uint64_t line = gpio_line64();
    unsigned base = g_gpio_s3 ? 0x74 : 0x88;
    for (int pin = 0; pin < (g_gpio_s3 ? 49 : 40); pin++) {
        uint32_t cfg = g_regs[(base + pin * 4) / 4];
        unsigned type = (cfg >> 7) & 7;
        if (((cfg >> 13) & 0x1f) &&
            ((type == 4 && !(line & (1ULL << pin))) ||
             (type == 5 && (line & (1ULL << pin))))) {
            g_regs[(pin < 32 ? 0x44 : 0x50) / 4] |= 1u << (pin & 31);
        }
    }
    qemu_set_irq(g_gpio_device->irq,
        !!(g_regs[0x44 / 4] | g_regs[0x50 / 4]));
}

static void gpio_transition_irq(uint64_t before, uint64_t after)
{
    uint64_t diff = before ^ after;
    unsigned base = g_gpio_s3 ? 0x74 : 0x88;
    for (int pin = 0; pin < (g_gpio_s3 ? 49 : 40); pin++) {
        if (!(diff & (1ULL << pin))) { continue; }
        uint32_t cfg = g_regs[(base + pin * 4) / 4];
        unsigned type = (cfg >> 7) & 7;
        bool high = (after >> pin) & 1;
        if (((cfg >> 13) & 0x1f) &&
            ((type == 1 && high) || (type == 2 && !high) || type == 3)) {
            g_regs[(pin < 32 ? 0x44 : 0x50) / 4] |= 1u << (pin & 31);
        }
    }
    gpio_update_irq();
}

static void gpio_notify(uint64_t before, uint64_t after)
{
    uint64_t diff = before ^ after;
    for (int i = 0; diff && i < GPIO_NPINS; i++) {
        if ((diff >> i) & 1) {
            for (int j = 0; j < g_listener_count[i]; j++) {
                if (g_listeners[i][j].cb) {
                    g_listeners[i][j].cb(g_listeners[i][j].opaque, i,
                                         (after >> i) & 1);
                }
            }
        }
    }
}

static uint64_t esp32_gpio_read(void *opaque, hwaddr addr, unsigned int size)
{
    Esp32GpioState *s = ESP32_GPIO(opaque);
    uint64_t in = gpio_line64();
    switch (addr) {
    case A_GPIO_STRAP:
        return s->strap_mode;
    case 0x3c: {
        int trace_pin = gpio_trace_pin();
        int trace_level = (in >> trace_pin) & 1;

        if (getenv("M5SW_GPIO_TRACE") &&
            trace_level != g_trace_last_level) {
            fprintf(stderr, "[gpio] in0=0x%08x pin%d=%d\n",
                    (uint32_t)in, trace_pin, trace_level);
            g_trace_last_level = trace_level;
        }
        return (uint32_t)in;
    }
    case 0x40:
        return (uint32_t)(in >> 32) & 0x3fffff;
    case 0x08: case 0x0c: case 0x14: case 0x18:
    case 0x24: case 0x28: case 0x30: case 0x34:
        return 0;
    default:
        if (addr == (g_gpio_s3 ? 0x5c : 0x68)) { return g_regs[0x44 / 4]; }
        if (addr == (g_gpio_s3 ? 0x68 : 0x7c)) { return g_regs[0x50 / 4]; }
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
    if (getenv("M5SW_GPIO_REG_TRACE") && addr >= 0x100 && addr < 0x140) {
        fprintf(stderr, "[gpio] wr addr=0x%03" HWADDR_PRIx
                " value=0x%08" PRIx64 "\n", addr, value);
    }
    switch (addr) {
    case 0x08: g_regs[0x04 / 4] |= value; break;
    case 0x0c: g_regs[0x04 / 4] &= ~value; break;
    case 0x14: g_regs[0x10 / 4] |= value; break;
    case 0x18: g_regs[0x10 / 4] &= ~value; break;
    case 0x24: g_regs[0x20 / 4] |= value; break;
    case 0x28: g_regs[0x20 / 4] &= ~value; break;
    case 0x30: g_regs[0x2c / 4] |= value; break;
    case 0x34: g_regs[0x2c / 4] &= ~value; break;
    case 0x48: g_regs[0x44 / 4] |= value; break;
    case 0x4c: g_regs[0x44 / 4] &= ~value; break;
    case 0x54: g_regs[0x50 / 4] |= value; break;
    case 0x58: g_regs[0x50 / 4] &= ~value; break;
    case A_GPIO_STRAP: case 0x3c: case 0x40:
        break;
    default:
        if (addr < sizeof(g_regs)) {
            uint32_t previous = g_regs[addr / 4];
            unsigned output_base = g_gpio_s3 ? 0x554 : 0x530;
            g_regs[addr / 4] = value;
            if (addr >= output_base &&
                addr < output_base + (g_gpio_s3 ? 49 : 40) * 4 &&
                ((previous ^ (uint32_t)value) & 0x3ff)) {
                esp32_ledc_gpio_route_changed(g_gpio_s3);
                m5_unit_gpio_route_changed(g_gpio_s3,
                                           (addr - output_base) / 4);
            }
            /*
             * GPIO_PIN0_REG starts at 0x74 on ESP32-S3.  M5GFX's
             * pinMode(input*) uses gpio_ll_od_enable(), which leaves the
             * output enable set and relies on open-drain + latch-high
             * semantics so an external low can still pull the line down.
             */
            unsigned pin_base = g_gpio_s3 ? 0x74 : 0x88;
            if (addr >= pin_base && addr < pin_base + GPIO_NPINS * 4) {
                uint64_t pin_bit = 1ULL << ((addr - pin_base) / 4);
                if (value & (1u << 2)) {
                    g_open_drain |= pin_bit;
                } else {
                    g_open_drain &= ~pin_bit;
                }
            }
        }
        break;
    }
    gpio_notify(before, gpio_line64());
    gpio_transition_irq(before, gpio_line64());
}

static const MemoryRegionOps uart_ops = {
    .read =  esp32_gpio_read,
    .write = esp32_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32_gpio_reset_hold(Object *obj, ResetType type)
{
    memset(g_regs, 0, sizeof(g_regs));
    g_open_drain = 0;
    gpio_update_irq();
}

static void esp32_gpio_realize(DeviceState *dev, Error **errp)
{
}

static void esp32_gpio_init(Object *obj)
{
    Esp32GpioState *s = ESP32_GPIO(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    g_gpio_device = s;
    g_gpio_s3 = object_dynamic_cast(obj, "esp32s3.gpio") != NULL;

    /* Set the default value for the strap_mode property */
    object_property_set_int(obj, "strap_mode", ESP32_STRAP_MODE_FLASH_BOOT, &error_fatal);

    memory_region_init_io(&s->iomem, obj, &uart_ops, s,
                          TYPE_ESP32_GPIO, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
}

static Property esp32_gpio_properties[] = {
    /* The strap_mode needs to be explicitly set in the instance init, thus, set
     * the default value to 0. */
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

/* ESP-IDF GPIO matrix register/signal maps, v5.5: S3 I2C 89..92,
 * classic ESP32 29/30 and 95/96. Both input and output routes must match.
 */
bool esp32_gpio_matrix_i2c_pins(unsigned controller, bool s3, int *sda, int *scl)
{
    unsigned scl_signal = s3 ? 89 + controller * 2 : (controller ? 95 : 29);
    unsigned sda_signal = scl_signal + 1;
    unsigned input_base = s3 ? 0x154 : 0x130;
    unsigned output_base = s3 ? 0x554 : 0x530;
    uint32_t scl_input = g_regs[(input_base + scl_signal * 4) / 4];
    uint32_t sda_input = g_regs[(input_base + sda_signal * 4) / 4];
    *scl = scl_input & 0x3f;
    *sda = sda_input & 0x3f;
    return controller < 2 && (scl_input & 0xc0) == 0x80 &&
           (sda_input & 0xc0) == 0x80 && *scl < (s3 ? 49 : 40) &&
           *sda < (s3 ? 49 : 40) &&
           (g_regs[(output_base + *scl * 4) / 4] & 0x3ff) == scl_signal &&
           (g_regs[(output_base + *sda * 4) / 4] & 0x3ff) == sda_signal;
}

int esp32_gpio_matrix_out_signal(int pin, bool s3)
{
    if (pin < 0 || pin >= (s3 ? 49 : 40)) { return -1; }
    uint32_t value = g_regs[((s3 ? 0x554 : 0x530) + pin * 4) / 4];
    return (value & BIT(9)) ? -1 : value & 0x1ff;
}
int esp32_gpio_matrix_in_pin(unsigned signal, bool s3)
{
    if (signal > 190) { return -1; }
    uint32_t value = g_regs[((s3 ? 0x154 : 0x130) + signal * 4) / 4];
    return (value & 0xc0) == 0x80 ? value & 0x3f : -1;
}

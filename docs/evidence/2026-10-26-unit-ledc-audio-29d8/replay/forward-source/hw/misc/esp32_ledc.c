#include "qemu/osdep.h"
#include "../m5stopwatch/m5_unit_runtime.h"
#include "hw/sysbus.h"
#include "qemu/log.h"
#include "qapi/error.h"
#include "hw/qdev-properties.h"
#include "hw/misc/esp32_ledc.h"

#define ESP32_LEDC_REGS_SIZE (A_LEDC_CONF_REG + 4)

static void ledc_observe(Esp32LEDCState *s)
{
    for (unsigned channel = 0; channel < (s->esp32s3_layout ? 8 : 16); channel++) {
        unsigned timer = (s->channel_conf0_reg[channel] & 3) +
                         (!s->esp32s3_layout && channel >= 8 ? 4 : 0);
        m5_unit_pwm_observe(s->esp32s3_layout, channel,
            s->timer_conf_reg[timer], s->channel_duty_reg[channel],
            s->channel_conf0_reg[channel]);
    }
}

static uint64_t esp32_ledc_read(void *opaque, hwaddr addr, unsigned int size)
{
    Esp32LEDCState *s = ESP32_LEDC(opaque);
    uint64_t r = 0;
    if (s->esp32s3_layout && addr < 0xa0) {
        unsigned offset = addr % 0x14;
        if (offset == 8 || offset == 16) {
            /* The existing model applies duty writes immediately. Expose
             * that settled set+update state, without claiming pending/current
             * cycle, fade or active-latch timing semantics. */
            return s->channel_duty_reg[addr / 0x14] & 0x7ffff;
        }
    }
    if (s->esp32s3_layout && addr >= 0xa0 && addr < 0xc0) {
        unsigned index = (addr - 0xa0) / 8;
        r = (addr & 4) ? s->timer_value_reg[index]
                       : s->timer_conf_reg[index];
        return r;
    }
    if (s->esp32s3_layout && addr == 0xd0) {
        r = s->conf_reg;
        return r;
    }
    switch (addr) {
    case A_LEDC_HSTIMER0_CONF_REG ... A_LEDC_LSTIMER3_CONF_REG:
        r = s->timer_conf_reg[(addr - A_LEDC_HSTIMER0_CONF_REG) / 0x8];
        break;

    case A_LEDC_HSCH0_CONF0_REG:
    case A_LEDC_HSCH1_CONF0_REG:
    case A_LEDC_HSCH2_CONF0_REG:
    case A_LEDC_HSCH3_CONF0_REG:
    case A_LEDC_HSCH4_CONF0_REG:
    case A_LEDC_HSCH5_CONF0_REG:
    case A_LEDC_HSCH6_CONF0_REG:
    case A_LEDC_HSCH7_CONF0_REG:
    case A_LEDC_LSCH0_CONF0_REG:
    case A_LEDC_LSCH1_CONF0_REG:
    case A_LEDC_LSCH2_CONF0_REG:
    case A_LEDC_LSCH3_CONF0_REG:
    case A_LEDC_LSCH4_CONF0_REG:
    case A_LEDC_LSCH5_CONF0_REG:
    case A_LEDC_LSCH6_CONF0_REG:
    case A_LEDC_LSCH7_CONF0_REG:
        r = s->channel_conf0_reg[(addr - A_LEDC_HSCH0_CONF0_REG) / 0x14];
        break;
    }
    return r;
}

static uint32_t esp32_ledc_get_percent(Esp32LEDCState *s, uint32_t value, hwaddr addr)
{
    uint32_t duty_val =  (value >> 4) & ((1 << 20) - 1);
    uint32_t duty_res;
    if (((addr - A_LEDC_HSCH0_DUTY_REG) / 0x14) < 8) {
        /* get duty res for the high speed channel from high speed timer */
        duty_res = s->duty_res[(s->channel_conf0_reg[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14] & ((1 << 2) - 1))];
    } else {
        /* get duty res for the low speed channel from low speed timer */
        duty_res = s->duty_res[((s->channel_conf0_reg[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14]) & ((1 << 2) - 1)) + 4];
    }
    return duty_res ? (100 * duty_val / ((2 << (duty_res - 1)) - 1)) : 0;
}

static void esp32_ledc_write(void *opaque, hwaddr addr,
                            uint64_t value, unsigned int size)
{
    Esp32LEDCState *s = ESP32_LEDC(opaque);
    if (s->esp32s3_layout && addr >= 0xa0 && addr < 0xc0) {
        unsigned index = (addr - 0xa0) / 8;
        if (addr & 4) {
            s->timer_value_reg[index] = value;
        } else {
            s->timer_conf_reg[index] = value;
            if ((value & 0xf) != 0) {
                s->duty_res[index] = value & 0xf;
            }
        }
        ledc_observe(s);
        return;
    }
    if (s->esp32s3_layout && addr == 0xd0) {
        s->conf_reg = value;
        ledc_observe(s);
        return;
    }
    switch (addr) {
    case A_LEDC_HSTIMER0_CONF_REG ... A_LEDC_LSTIMER3_CONF_REG:
        /* get duty resolution from timer config */
        if (((uint32_t)value & ((1 << 4) - 1)) != 0) {
            s->duty_res[(addr - A_LEDC_HSTIMER0_CONF_REG) / 0x8] = (uint32_t)value & ((1 << 4) - 1);
        }
        s->timer_conf_reg[(addr - A_LEDC_HSTIMER0_CONF_REG) / 0x8] = value;
        break;

    case A_LEDC_HSCH0_CONF0_REG:
    case A_LEDC_HSCH1_CONF0_REG:
    case A_LEDC_HSCH2_CONF0_REG:
    case A_LEDC_HSCH3_CONF0_REG:
    case A_LEDC_HSCH4_CONF0_REG:
    case A_LEDC_HSCH5_CONF0_REG:
    case A_LEDC_HSCH6_CONF0_REG:
    case A_LEDC_HSCH7_CONF0_REG:
    case A_LEDC_LSCH0_CONF0_REG:
    case A_LEDC_LSCH1_CONF0_REG:
    case A_LEDC_LSCH2_CONF0_REG:
    case A_LEDC_LSCH3_CONF0_REG:
    case A_LEDC_LSCH4_CONF0_REG:
    case A_LEDC_LSCH5_CONF0_REG:
    case A_LEDC_LSCH6_CONF0_REG:
    case A_LEDC_LSCH7_CONF0_REG:
        s->channel_conf0_reg[(addr - A_LEDC_HSCH0_CONF0_REG) / 0x14] = value;
        break;

    case A_LEDC_HSCH0_DUTY_REG:
    case A_LEDC_HSCH1_DUTY_REG:
    case A_LEDC_HSCH2_DUTY_REG:
    case A_LEDC_HSCH3_DUTY_REG:
    case A_LEDC_HSCH4_DUTY_REG:
    case A_LEDC_HSCH5_DUTY_REG:
    case A_LEDC_HSCH6_DUTY_REG:
    case A_LEDC_HSCH7_DUTY_REG:
    case A_LEDC_LSCH0_DUTY_REG:
    case A_LEDC_LSCH1_DUTY_REG:
    case A_LEDC_LSCH2_DUTY_REG:
    case A_LEDC_LSCH3_DUTY_REG:
    case A_LEDC_LSCH4_DUTY_REG:
    case A_LEDC_LSCH5_DUTY_REG:
    case A_LEDC_LSCH6_DUTY_REG:
    case A_LEDC_LSCH7_DUTY_REG:
        s->channel_duty_reg[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14] = value;
        led_set_intensity(&s->led[(addr - A_LEDC_HSCH0_DUTY_REG) / 0x14], esp32_ledc_get_percent(s, value, addr));
        break;
    }
    ledc_observe(s);
}

static const MemoryRegionOps esp32_ledc_ops = {
        .read =  esp32_ledc_read,
        .write = esp32_ledc_write,
        .endianness = DEVICE_LITTLE_ENDIAN,
};

static void esp32_ledc_realize(DeviceState *dev, Error **errp)
{
    Esp32LEDCState *s = ESP32_LEDC(dev);
    for (int i = 0; i < ESP32_LEDC_CHANNEL_CNT; i++) {
        qdev_realize(DEVICE(&s->led[i]), NULL, &error_fatal);
    }
}

static void esp32_ledc_init(Object *obj)
{
    Esp32LEDCState *s = ESP32_LEDC(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    memory_region_init_io(&s->iomem, obj, &esp32_ledc_ops, s,
                          TYPE_ESP32_LEDC, ESP32_LEDC_REGS_SIZE);
    sysbus_init_mmio(sbd, &s->iomem);
    for (int i = 0; i < ESP32_LEDC_CHANNEL_CNT; i++) {
        object_initialize_child(obj, g_strdup_printf("led%d", i + 1), &s->led[i], TYPE_LED);
        s->led[i].color = (char *)"blue";
    }
}

static Property esp32_ledc_props[] = {
    DEFINE_PROP_BOOL("esp32s3-layout", Esp32LEDCState,
                     esp32s3_layout, false),
    DEFINE_PROP_END_OF_LIST(),
};

static void esp32_ledc_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    dc->realize = esp32_ledc_realize;
    device_class_set_props(dc, esp32_ledc_props);
}

static const TypeInfo esp32_ledc_info = {
        .name = TYPE_ESP32_LEDC,
        .parent = TYPE_SYS_BUS_DEVICE,
        .instance_size = sizeof(Esp32LEDCState),
        .instance_init = esp32_ledc_init,
        .class_init = esp32_ledc_class_init
};

static void esp32_ledc_register_types(void)
{
    type_register_static(&esp32_ledc_info);
}

type_init(esp32_ledc_register_types)

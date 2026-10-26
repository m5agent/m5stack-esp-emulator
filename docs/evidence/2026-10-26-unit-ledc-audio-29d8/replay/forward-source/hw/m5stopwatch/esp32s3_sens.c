/*
 * ESP32-S3 SENS/SAR-ADC compatibility model.
 *
 * UIFlow2's early boot path starts an SAR conversion and waits for
 * SENS_MEAS1_DONE_SAR (SAR_MEAS1_CTRL2[16]).  The upstream ESP32-S3
 * model leaves this address unimplemented, so the read returns zero and
 * the firmware spins forever before reaching the application.
 *
 * This is intentionally a small register-file model: it preserves writes,
 * reports conversion completion after a software start, and returns a
 * neutral ADC sample.  It is sufficient for firmware bring-up and does not
 * claim calibrated ADC accuracy.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "exec/memory.h"
#include "m5stopwatch.h"
#include "m5_unit_runtime.h"

#define SENS_SIZE       0x200
#define SENS_MEAS1_CTRL2 0x0c
#define SENS_MEAS2_CTRL2 0x30
#define SENS_TSENS_CTRL  0x50
#define MEAS_START_SAR  (1u << 17)
#define MEAS_DONE_SAR   (1u << 16)
#define MEAS_DATA_MASK  0xffffu
#define MEAS_NEUTRAL    0x0800u
#define TSENS_DUMP_OUT  (1u << 24)
#define TSENS_POWER_UP  (1u << 22)
#define TSENS_READY     (1u << 8)
#define TSENS_DATA_MASK 0xffu
#define TSENS_NEUTRAL   0x80u

typedef struct M5StopwatchSensState {
    uint32_t regs[SENS_SIZE / sizeof(uint32_t)];
    bool classic;
    bool meas1_started;
    bool meas2_started;
} M5StopwatchSensState;

static bool sens_started(M5StopwatchSensState *s, hwaddr addr)
{
    if (addr == (s->classic ? 0x54 : SENS_MEAS1_CTRL2)) {
        return s->meas1_started;
    }
    if (addr == (s->classic ? 0x94 : SENS_MEAS2_CTRL2)) {
        return s->meas2_started;
    }
    return false;
}

static uint64_t sens_read(void *opaque, hwaddr addr, unsigned size)
{
    M5StopwatchSensState *s = opaque;
    uint32_t value;

    if (addr + size > SENS_SIZE || size != 4) {
        return 0;
    }

    value = s->regs[addr / 4];
    if (sens_started(s, addr)) {
        value |= MEAS_DONE_SAR;
        unsigned adc = addr == (s->classic ? 0x94 : SENS_MEAS2_CTRL2);
        uint32_t mask = (value >> 19) & 0x3ff;
        unsigned channel = mask ? __builtin_ctz(mask) : 0;
        unsigned atten_addr = adc ? 0x38 : (s->classic ? 0x34 : 0x14);
        unsigned atten = (s->regs[atten_addr / 4] >> (channel * 2)) & 3;
        uint16_t raw = m5_unit_adc_sample(adc, channel, atten, !s->classic, MEAS_NEUTRAL);
        value = (value & ~MEAS_DATA_MASK) | raw;
    }
    if (addr == SENS_TSENS_CTRL &&
        (value & (TSENS_DUMP_OUT | TSENS_POWER_UP))) {
        value |= TSENS_READY;
        if (!(value & TSENS_DATA_MASK)) {
            value |= TSENS_NEUTRAL;
        }
    }
    return value;
}

static void sens_write(void *opaque, hwaddr addr, uint64_t value64,
                       unsigned size)
{
    M5StopwatchSensState *s = opaque;
    uint32_t value = value64;

    if (addr + size > SENS_SIZE || size != 4) {
        return;
    }

    if (addr == (s->classic ? 0x54 : SENS_MEAS1_CTRL2) && (value & MEAS_START_SAR)) {
        s->meas1_started = true;
    }
    if (addr == (s->classic ? 0x94 : SENS_MEAS2_CTRL2) && (value & MEAS_START_SAR)) {
        s->meas2_started = true;
    }
    s->regs[addr / 4] = value;
}

static const MemoryRegionOps sens_ops = {
    .read = sens_read,
    .write = sens_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

void m5stopwatch_sens_init(MemoryRegion *sys_mem)
{
    M5StopwatchSensState *s = g_new0(M5StopwatchSensState, 1);
    MemoryRegion *mr = g_new(MemoryRegion, 1);

    memory_region_init_io(mr, NULL, &sens_ops, s, "esp32s3.sens", SENS_SIZE);
    memory_region_add_subregion_overlap(sys_mem, 0x60008800, mr, 1);
}

void m5_unit_classic_adc_init(MemoryRegion *sys_mem)
{
    M5StopwatchSensState *s = g_new0(M5StopwatchSensState, 1);
    MemoryRegion *mr = g_new(MemoryRegion, 1);
    s->classic = true;
    memory_region_init_io(mr, NULL, &sens_ops, s, "esp32.unit-sens", SENS_SIZE);
    memory_region_add_subregion_overlap(sys_mem, 0x3ff48800, mr, 2);
}

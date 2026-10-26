/*
 * ESP32-S3 front-end (FE) bring-up stub.
 *
 * The UIFlow2 bootloader waits for the PHY front-end to signal completion
 * through FE offset 0x174, bit 16, before it continues with the rest of
 * the system startup.  The upstream ESP32-S3 machine has no RF/PHY model,
 * so that bit never changes and the bootloader spins in its polling loop.
 *
 * Keep the register file for writes and report the front-end as ready.
 * This is intentionally a boot-progress stub, not an RF model.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "exec/memory.h"
#include "m5stopwatch.h"

#define FE_BASE       0x60006000
#define FE_SIZE       0x1000
#define FE_STATUS     0x174
#define FE_READY      (1u << 16)

typedef struct M5StopwatchFeState {
    uint32_t regs[FE_SIZE / sizeof(uint32_t)];
} M5StopwatchFeState;

static uint64_t fe_read(void *opaque, hwaddr addr, unsigned size)
{
    M5StopwatchFeState *s = opaque;
    uint32_t value;

    if (addr + size > FE_SIZE || size != 4) {
        return 0;
    }

    value = s->regs[addr / 4];
    if (addr == FE_STATUS) {
        value |= FE_READY;
    }
    return value;
}

static void fe_write(void *opaque, hwaddr addr, uint64_t value64,
                     unsigned size)
{
    M5StopwatchFeState *s = opaque;

    if (addr + size > FE_SIZE || size != 4) {
        return;
    }

    s->regs[addr / 4] = value64;
}

static const MemoryRegionOps fe_ops = {
    .read = fe_read,
    .write = fe_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

void m5stopwatch_fe_init(MemoryRegion *sys_mem)
{
    M5StopwatchFeState *s = g_new0(M5StopwatchFeState, 1);
    MemoryRegion *mr = g_new(MemoryRegion, 1);

    memory_region_init_io(mr, NULL, &fe_ops, s, "esp32s3.fe", FE_SIZE);
    memory_region_add_subregion_overlap(sys_mem, FE_BASE, mr, 1);
}

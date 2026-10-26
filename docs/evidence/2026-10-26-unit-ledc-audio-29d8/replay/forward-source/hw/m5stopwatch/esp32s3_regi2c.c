/*
 * ESP32-S3 ROM analog-I2C ("regi2c") compatibility model.
 *
 * The ESP32-S3 boot ROM uses the word-indexed register window at
 * 0x6000e000 to talk to the on-chip analog blocks (BOD, BBPLL, APLL and
 * SAR ADC).  The window is not described in the public peripheral address
 * map, but the ROM and ESP-IDF's S2 regi2c implementation use the same
 * layout:
 *
 *   word[host_id] = block | (data << 8) | I2C_RTC_WR_CNTL
 *   word[host_id].bit25 = busy
 *
 * The master-reset path additionally polls the RTC-I2C state field in
 * word 20 (0x6000e050), bits [26:24], until it reads 7 (idle).
 *
 * This model keeps the register file and reports every transaction as
 * immediately idle.  It is a bring-up model: it does not emulate the
 * analog blocks or their calibration values, but it lets the ROM finish
 * its clock/PHY setup instead of spinning forever on an unimplemented
 * address.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "exec/memory.h"
#include "m5stopwatch.h"

#define REGI2C_BASE       0x6000e000
#define REGI2C_SIZE       0x100
#define REGI2C_WR_CNTL    (1u << 24)
#define REGI2C_BUSY       (1u << 25)
#define REGI2C_STATE_MASK (7u << 24)
#define REGI2C_STATE_IDLE (7u << 24)

typedef struct M5StopwatchRegi2cState {
    uint32_t regs[REGI2C_SIZE / sizeof(uint32_t)];
} M5StopwatchRegi2cState;

static uint64_t regi2c_read(void *opaque, hwaddr addr, unsigned size)
{
    M5StopwatchRegi2cState *s = opaque;
    uint32_t value;

    if (addr + size > REGI2C_SIZE || size != 4) {
        return 0;
    }

    value = s->regs[addr / 4];

    /*
     * Data-host words use bit 25 as the transaction-busy flag.  Word 20
     * (0x6000e050) is the RTC-I2C master-state register instead: its
     * bits [26:24] read 7 when the master is idle.  Keep the two
     * semantics separate so the ROM's busy-wait and state-wait loops
     * both terminate.
     */
    value &= ~REGI2C_BUSY;
    if (addr == 0x4c) {
        /* Analog-block command/status word: report completion. */
        value |= (1u << 24);
    } else if (addr == 0x50) {
        value &= ~REGI2C_STATE_MASK;
        value |= REGI2C_STATE_IDLE;
    }
    return value;
}

static void regi2c_write(void *opaque, hwaddr addr, uint64_t value64,
                         unsigned size)
{
    M5StopwatchRegi2cState *s = opaque;

    if (addr + size > REGI2C_SIZE || size != 4) {
        return;
    }

    s->regs[addr / 4] = value64;
}

static const MemoryRegionOps regi2c_ops = {
    .read = regi2c_read,
    .write = regi2c_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

void m5stopwatch_regi2c_init(MemoryRegion *sys_mem)
{
    M5StopwatchRegi2cState *s = g_new0(M5StopwatchRegi2cState, 1);
    MemoryRegion *mr = g_new(MemoryRegion, 1);

    memory_region_init_io(mr, NULL, &regi2c_ops, s,
                          "esp32s3.regi2c", REGI2C_SIZE);
    memory_region_add_subregion_overlap(sys_mem, REGI2C_BASE, mr, 1);
}

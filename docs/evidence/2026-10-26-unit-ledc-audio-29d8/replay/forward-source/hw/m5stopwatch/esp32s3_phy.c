/*
 * ESP32-S3 internal PHY/modem register-window stub.
 *
 * The UIFlow2 boot ROM's PHY setup touches the undocumented internal
 * window at 0x6002f000..0x60037fff.  One of its ready handshakes is the
 * bit-0 poll of 0x60033d14; without a model that bit stays zero and the
 * bootloader never reaches the application.
 *
 * This is a bring-up register-file stub, not an RF or PHY simulation.
 * It preserves writes and reports the specific ready bit at 0x60033d14.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "exec/memory.h"
#include "m5stopwatch.h"

#define PHY_BASE       0x6002f000
#define PHY_SIZE       0x9000
#define PHY_READY_REG  0x4d14
#define PHY_READY      (1u << 0)
#define PHY_COUNTER_REG 0x607c
#define PHY_RWIP_CTRL_REG 0x2000
#define PHY_RWIP_BUSY (1u << 31)
#define PHY_RWIP_ID_REG 0x2004
#define PHY_RWIP_ID 0x09001b00U
#define PHY_RWIP_TIME_REG 0x201c
#define PHY_RWIP_TIME_MASK 0x0fffffffU
#define PHY_RWIP_HALF_SLOT_NS 312500ULL

typedef struct M5StopwatchPhyState {
    uint32_t regs[PHY_SIZE / sizeof(uint32_t)];
    uint32_t counter;
} M5StopwatchPhyState;

static uint64_t phy_read(void *opaque, hwaddr addr, unsigned size)
{
    M5StopwatchPhyState *s = opaque;
    uint32_t value;

    if (addr + size > PHY_SIZE || size != 4) {
        return 0;
    }

    value = s->regs[addr / 4];
    if (addr == PHY_READY_REG) {
        value |= PHY_READY;
    } else if (addr == PHY_COUNTER_REG) {
        value = s->counter++;
    } else if (addr == PHY_RWIP_CTRL_REG) {
        /*
         * Firmware starts an RWIP control transfer by setting bit 31 and
         * polls until the baseband clears it.  The transfer completes
         * synchronously in this model while the low 31 bits retain state.
         */
        value &= ~PHY_RWIP_BUSY;
    } else if (addr == PHY_RWIP_ID_REG) {
        value = PHY_RWIP_ID;
    } else if (addr == PHY_RWIP_TIME_REG) {
        /*
         * r_rwip_time_get() starts a sample by setting bit 31 and polls
         * until the hardware returns the current 28-bit RWIP time with the
         * busy bit cleared.  BLE time advances in 312.5 us half-slots.
         */
        value = (qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) /
                 PHY_RWIP_HALF_SLOT_NS) & PHY_RWIP_TIME_MASK;
    }
    return value;
}

static void phy_write(void *opaque, hwaddr addr, uint64_t value64,
                      unsigned size)
{
    M5StopwatchPhyState *s = opaque;

    if (addr + size > PHY_SIZE || size != 4) {
        return;
    }

    s->regs[addr / 4] = value64;
}

static const MemoryRegionOps phy_ops = {
    .read = phy_read,
    .write = phy_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

void m5stopwatch_phy_init(MemoryRegion *sys_mem)
{
    M5StopwatchPhyState *s = g_new0(M5StopwatchPhyState, 1);
    MemoryRegion *mr = g_new(MemoryRegion, 1);

    memory_region_init_io(mr, NULL, &phy_ops, s, "esp32s3.phy", PHY_SIZE);
    memory_region_add_subregion_overlap(sys_mem, PHY_BASE, mr, 1);
}

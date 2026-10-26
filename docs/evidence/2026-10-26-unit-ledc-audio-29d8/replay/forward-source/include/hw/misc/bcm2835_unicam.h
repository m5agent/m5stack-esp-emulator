/*
 * BCM2835 Unicam CSI-2 receiver
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_MISC_BCM2835_UNICAM_H
#define HW_MISC_BCM2835_UNICAM_H

#include "exec/memory.h"
#include "hw/sysbus.h"
#include "qemu/timer.h"
#include "qom/object.h"

#define TYPE_BCM2835_UNICAM "bcm2835-unicam"
OBJECT_DECLARE_SIMPLE_TYPE(BCM2835UnicamState, BCM2835_UNICAM)

struct BCM2835UnicamState {
    /*< private >*/
    SysBusDevice parent_obj;

    /*< public >*/
    MemoryRegion iomem;
    MemoryRegion cmi_iomem;
    MemoryRegion *dma_mr;
    AddressSpace dma_as;
    qemu_irq irq;
    QEMUTimer *frame_timer;

    uint32_t regs[0x800 / sizeof(uint32_t)];
    uint32_t cmi;
    uint32_t frame_interval_ms;
    uint32_t max_frame_bytes;
    uint32_t pattern_seed;
    uint32_t frame_count;
    uint32_t frame_bytes;
    uint32_t frame_width;
    uint32_t frame_height;
    uint32_t frame_stride;
    bool streaming;
    bool frame_end_pending;
    bool trace;
};

#endif

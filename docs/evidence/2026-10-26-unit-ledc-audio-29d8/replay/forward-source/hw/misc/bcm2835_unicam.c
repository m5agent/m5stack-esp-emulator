/*
 * BCM2835 Unicam CSI-2 receiver
 *
 * The register layout and interrupt sequence are derived from the public
 * Raspberry Pi Linux driver:
 *   drivers/media/platform/bcm2835/{bcm2835-unicam.c,vc4-regs-unicam.h}
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "exec/address-spaces.h"
#include "hw/irq.h"
#include "hw/misc/bcm2835_unicam.h"
#include "hw/qdev-properties.h"
#include "migration/vmstate.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qemu/units.h"

enum {
    UNICAM_CTRL = 0x000,
    UNICAM_STA = 0x004,
    UNICAM_CLK = 0x010,
    UNICAM_DAT0 = 0x018,
    UNICAM_ICTL = 0x100,
    UNICAM_ISTA = 0x104,
    UNICAM_IDI0 = 0x108,
    UNICAM_IPIPE = 0x10c,
    UNICAM_IBSA0 = 0x110,
    UNICAM_IBEA0 = 0x114,
    UNICAM_IBLS = 0x118,
    UNICAM_IBWP = 0x11c,
    UNICAM_IHSTA = 0x124,
    UNICAM_IVSTA = 0x12c,
    UNICAM_DBSA0 = 0x204,
    UNICAM_DBEA0 = 0x208,
    UNICAM_DBWP = 0x20c,
    UNICAM_DBCTL = 0x300,
};

#define UNICAM_CPE          BIT(0)
#define UNICAM_IS           BIT(14)
#define UNICAM_FSI          BIT(0)
#define UNICAM_FEI          BIT(1)
#define UNICAM_LIP          BIT(5)
#define UNICAM_NS_PER_MS    1000000ULL

#define UNICAM_REG(s, off) ((s)->regs[(off) / sizeof(uint32_t)])

static void unicam_update_irq(BCM2835UnicamState *s)
{
    uint32_t enabled = UNICAM_REG(s, UNICAM_ISTA)
                       & (UNICAM_REG(s, UNICAM_ICTL) & 0x3);

    qemu_set_irq(s->irq, enabled != 0);
}

static void unicam_fill_frame(BCM2835UnicamState *s, uint8_t *data,
                              uint32_t size, uint32_t stride)
{
    uint32_t width = stride / 2;
    uint32_t height = stride ? size / stride : 0;
    uint32_t frame = s->frame_count + s->pattern_seed;

    if (!width || !height) {
        for (uint32_t i = 0; i < size; i++) {
            data[i] = (i * 37 + frame * 13) & 0xff;
        }
        return;
    }

    /*
     * Produce a deterministic Bayer-like test scene with a moving block and
     * a horizontal gradient.  The byte layout follows the currently selected
     * 16-bit Unicam output, so guest tools receive a real frame of the size
     * Linux programmed rather than a synthetic ioctl response.
     */
    for (uint32_t y = 0; y < height; y++) {
        uint16_t *line = (uint16_t *)(data + (size_t)y * stride);
        for (uint32_t x = 0; x < width; x++) {
            uint32_t px = (x * 4 + y * 2 + frame * 17) & 0x3ff;
            uint32_t block_x = (frame * 23) % MAX(width, 1);
            bool in_block = x >= block_x && x < block_x + width / 8 + 1 &&
                            y >= height / 3 && y < height * 2 / 3;

            if (in_block) {
                px = ((x / 16 + y / 16) & 1) ? 0x3ff : 0;
            }
            line[x] = cpu_to_le16(px);
        }
    }
}

static void unicam_frame_start(BCM2835UnicamState *s)
{
    uint32_t start = UNICAM_REG(s, UNICAM_IBSA0);
    uint32_t end = UNICAM_REG(s, UNICAM_IBEA0);
    uint32_t stride = UNICAM_REG(s, UNICAM_IBLS);
    uint32_t size = end > start ? end - start : 0;
    uint32_t width = stride / 2;
    uint32_t height = stride ? size / stride : 0;
    g_autofree uint8_t *frame = NULL;

    if (!s->streaming) {
        return;
    }

    size = MIN(size, s->max_frame_bytes);
    if (start && size) {
        frame = g_malloc0(size);
        unicam_fill_frame(s, frame, size, stride);
        if (address_space_write(&s->dma_as, start, MEMTXATTRS_UNSPECIFIED,
                                frame, size) != MEMTX_OK) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "unicam: DMA write failed addr=0x%08x size=%u\n",
                          start, size);
        }
        UNICAM_REG(s, UNICAM_IBWP) = start + size;
        s->frame_bytes = size;
        s->frame_width = width;
        s->frame_height = height;
        s->frame_stride = stride;
    }

    UNICAM_REG(s, UNICAM_STA) |= UNICAM_IS;
    UNICAM_REG(s, UNICAM_ISTA) |= UNICAM_FSI;
    unicam_update_irq(s);

    s->frame_end_pending = true;
    timer_mod_ns(s->frame_timer,
                 qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + UNICAM_NS_PER_MS);

    if (s->trace) {
        qemu_log("[unicam] FS frame=%u addr=0x%08x size=%u "
                 "stride=%u %ux%u\n",
                 s->frame_count, start, size, stride, width, height);
    }
}

static void unicam_frame_end(BCM2835UnicamState *s)
{
    if (!s->streaming) {
        return;
    }

    UNICAM_REG(s, UNICAM_STA) |= UNICAM_IS;
    UNICAM_REG(s, UNICAM_ISTA) |= UNICAM_FEI;
    unicam_update_irq(s);
    s->frame_count++;
    s->frame_end_pending = false;
    timer_mod_ns(s->frame_timer,
                 qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)
                 + (uint64_t)s->frame_interval_ms * UNICAM_NS_PER_MS);

    if (s->trace) {
        qemu_log("[unicam] FE frame=%u\n", s->frame_count);
    }
}

static void unicam_frame_timer(void *opaque)
{
    BCM2835UnicamState *s = opaque;

    if (s->frame_end_pending) {
        unicam_frame_end(s);
    } else {
        unicam_frame_start(s);
    }
}

static void unicam_start_stream(BCM2835UnicamState *s)
{
    s->streaming = true;
    s->frame_end_pending = false;
    timer_mod_ns(s->frame_timer,
                 qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)
                 + 5 * UNICAM_NS_PER_MS);
}

static void unicam_stop_stream(BCM2835UnicamState *s)
{
    s->streaming = false;
    s->frame_end_pending = false;
    timer_del(s->frame_timer);
    UNICAM_REG(s, UNICAM_ISTA) = 0;
    unicam_update_irq(s);
}

static uint64_t unicam_read(void *opaque, hwaddr offset, unsigned size)
{
    BCM2835UnicamState *s = opaque;

    if (offset >= sizeof(s->regs) || (offset & 3)) {
        return 0;
    }
    return UNICAM_REG(s, offset);
}

static void unicam_write(void *opaque, hwaddr offset, uint64_t value,
                         unsigned size)
{
    BCM2835UnicamState *s = opaque;
    uint32_t old;

    if (offset >= sizeof(s->regs) || (offset & 3)) {
        return;
    }

    switch (offset) {
    case UNICAM_STA:
        UNICAM_REG(s, offset) &= ~(uint32_t)value;
        unicam_update_irq(s);
        return;
    case UNICAM_ISTA:
        UNICAM_REG(s, offset) &= ~(uint32_t)value;
        unicam_update_irq(s);
        return;
    case UNICAM_ICTL:
        old = UNICAM_REG(s, offset);
        UNICAM_REG(s, offset) = value;
        if (!(old & UNICAM_LIP) && (value & UNICAM_LIP) &&
            (UNICAM_REG(s, UNICAM_CTRL) & UNICAM_CPE)) {
            unicam_start_stream(s);
        }
        return;
    case UNICAM_CTRL:
        old = UNICAM_REG(s, offset);
        UNICAM_REG(s, offset) = value;
        if ((old & UNICAM_CPE) && !(value & UNICAM_CPE)) {
            unicam_stop_stream(s);
        }
        return;
    default:
        UNICAM_REG(s, offset) = value;
        break;
    }
}

static const MemoryRegionOps unicam_ops = {
    .read = unicam_read,
    .write = unicam_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

static uint64_t unicam_cmi_read(void *opaque, hwaddr offset, unsigned size)
{
    BCM2835UnicamState *s = opaque;

    return offset == 0 ? s->cmi : 0;
}

static void unicam_cmi_write(void *opaque, hwaddr offset, uint64_t value,
                             unsigned size)
{
    BCM2835UnicamState *s = opaque;

    if (offset == 0) {
        s->cmi = value;
    }
}

static const MemoryRegionOps unicam_cmi_ops = {
    .read = unicam_cmi_read,
    .write = unicam_cmi_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

static void unicam_get_frame_count(Object *obj, Visitor *v,
                                   const char *name, void *opaque,
                                   Error **errp)
{
    BCM2835UnicamState *s = BCM2835_UNICAM(obj);
    uint32_t value = s->frame_count;

    visit_type_uint32(v, name, &value, errp);
}

static void unicam_get_frame_bytes(Object *obj, Visitor *v,
                                   const char *name, void *opaque,
                                   Error **errp)
{
    BCM2835UnicamState *s = BCM2835_UNICAM(obj);
    uint32_t value = s->frame_bytes;

    visit_type_uint32(v, name, &value, errp);
}

static void unicam_get_frame_size(Object *obj, Visitor *v,
                                  const char *name, void *opaque,
                                  Error **errp)
{
    BCM2835UnicamState *s = BCM2835_UNICAM(obj);
    char *value = g_strdup_printf("%ux%u", s->frame_width, s->frame_height);

    visit_type_str(v, name, &value, errp);
    g_free(value);
}

static void unicam_init(Object *obj)
{
    BCM2835UnicamState *s = BCM2835_UNICAM(obj);

    memory_region_init_io(&s->iomem, obj, &unicam_ops, s,
                          TYPE_BCM2835_UNICAM, 0x800);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->iomem);

    memory_region_init_io(&s->cmi_iomem, obj, &unicam_cmi_ops, s,
                          TYPE_BCM2835_UNICAM "-cmi", 4);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->cmi_iomem);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);

    s->frame_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                  unicam_frame_timer, s);

    object_property_add(obj, "frame-count", "uint32",
                        unicam_get_frame_count, NULL, NULL, NULL);
    object_property_add(obj, "frame-bytes", "uint32",
                        unicam_get_frame_bytes, NULL, NULL, NULL);
    object_property_add(obj, "frame-size", "string",
                        unicam_get_frame_size, NULL, NULL, NULL);
}

static void unicam_realize(DeviceState *dev, Error **errp)
{
    BCM2835UnicamState *s = BCM2835_UNICAM(dev);
    Object *obj = object_property_get_link(OBJECT(dev), "dma-mr", &error_abort);

    s->dma_mr = MEMORY_REGION(obj);
    address_space_init(&s->dma_as, s->dma_mr, TYPE_BCM2835_UNICAM "-dma");
    s->trace = getenv("M5SW_UNICAM_TRACE") != NULL;
}

static void unicam_reset(DeviceState *dev)
{
    BCM2835UnicamState *s = BCM2835_UNICAM(dev);

    timer_del(s->frame_timer);
    memset(s->regs, 0, sizeof(s->regs));
    s->cmi = 0;
    s->frame_count = 0;
    s->frame_bytes = 0;
    s->frame_width = 0;
    s->frame_height = 0;
    s->frame_stride = 0;
    s->streaming = false;
    s->frame_end_pending = false;
    qemu_set_irq(s->irq, 0);
}

static const Property unicam_properties[] = {
    DEFINE_PROP_UINT32("frame-interval-ms", BCM2835UnicamState,
                       frame_interval_ms, 33),
    DEFINE_PROP_UINT32("max-frame-bytes", BCM2835UnicamState,
                       max_frame_bytes, 64 * MiB),
    DEFINE_PROP_UINT32("pattern-seed", BCM2835UnicamState, pattern_seed, 0),
    DEFINE_PROP_END_OF_LIST(),
};

static const VMStateDescription vmstate_unicam = {
    .name = TYPE_BCM2835_UNICAM,
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32_ARRAY(regs, BCM2835UnicamState, 0x800 / 4),
        VMSTATE_UINT32(cmi, BCM2835UnicamState),
        VMSTATE_UINT32(frame_count, BCM2835UnicamState),
        VMSTATE_UINT32(frame_bytes, BCM2835UnicamState),
        VMSTATE_UINT32(frame_width, BCM2835UnicamState),
        VMSTATE_UINT32(frame_height, BCM2835UnicamState),
        VMSTATE_UINT32(frame_stride, BCM2835UnicamState),
        VMSTATE_BOOL(streaming, BCM2835UnicamState),
        VMSTATE_BOOL(frame_end_pending, BCM2835UnicamState),
        VMSTATE_END_OF_LIST()
    },
};

static void unicam_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = unicam_realize;
    device_class_set_legacy_reset(dc, unicam_reset);
    device_class_set_props(dc, unicam_properties);
    dc->vmsd = &vmstate_unicam;
}

static const TypeInfo unicam_info = {
    .name = TYPE_BCM2835_UNICAM,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(BCM2835UnicamState),
    .instance_init = unicam_init,
    .class_init = unicam_class_init,
};

static void unicam_register_types(void)
{
    type_register_static(&unicam_info);
}

type_init(unicam_register_types)

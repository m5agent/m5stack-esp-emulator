/*
 * ESP32-S3 RMT APB and hardware-memory model.
 *
 * The UIFlow2 IR stack uses the new RMT driver in non-DMA mode: the encoder
 * writes rmt_symbol_word_t entries into RMTMEM, starts the channel through
 * CHnCONF0, and waits for the TX_END interrupt. This model implements that
 * data path and records transmitted symbols for host-side assertions.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "hw/irq.h"
#include "hw/misc/esp32s3_reg.h"
#include "hw/sysbus.h"
#include "hw/xtensa/esp32s3_intc.h"
#include "qapi/visitor.h"
#include "m5stopwatch.h"
#include "m5_unit_runtime.h"

#define RMT_MEM_OFFSET      0x800
#define RMT_MEM_SIZE        0x800
#define RMT_TX_CHANNELS     4
#define RMT_SYMBOLS_PER_CH  48
#define RMT_MAX_TX_SYMBOLS  4096

#define RMT_CH0CONF0        0x20
#define RMT_CH4CONF0        0x30
#define RMT_CH4STATUS       0x60
#define RMT_INT_RAW         0x70
#define RMT_INT_ST          0x74
#define RMT_INT_ENA         0x78
#define RMT_INT_CLR         0x7c
#define RMT_CH0_TX_LIM      0xa0

struct M5RmtState {
    SysBusDevice parent_obj;
    MemoryRegion mmio;
    MemoryRegion mem;
    qemu_irq irq;
    uint32_t regs[RMT_MEM_OFFSET / 4];
    uint32_t symbols[RMT_MEM_SIZE / 4];
    uint32_t int_ena;
    uint32_t int_raw;
    QEMUTimer *tx_timer;
    QEMUTimer *rx_timer;
    FILE *tx_file;
    uint32_t pending_mask;
    uint32_t tx_wait_mask;
    uint32_t tx_cursor[4], tx_count[4], tx_since_threshold[4];
    uint32_t tx_frame[4][RMT_MAX_TX_SYMBOLS];
    uint64_t tx_symbols, tx_thresholds, tx_completions, tx_errors;
    uint64_t tx_last_conf, tx_last_clock, tx_last_tick_hz, tx_first_symbol;
    uint32_t rx_pending_mask;
    bool rx_injected[4];
    bool trace;
};

static M5RmtState *unit_rmt;

static void rmt_update_irq(M5RmtState *s)
{
    qemu_set_irq(s->irq, !!(s->int_raw & s->int_ena));
}

static double rmt_tick_hz(M5RmtState *s, unsigned channel, bool rx)
{
    uint32_t clock = s->regs[0xc0 / 4];
    unsigned source_id = (clock >> 24) & 3;
    /* S3 HAL selects 1=APB and 3=XTAL. RC_FAST calibration is a separate
     * unsupported clock path; never silently treat it as the crystal. */
    double source = source_id == 1 ? 80000000.0 :
                    source_id == 3 ? 40000000.0 : 0;
    double divider = ((clock >> 4) & 0xff) + 1;
    unsigned a = (clock >> 12) & 0x3f, b = (clock >> 18) & 0x3f;
    if (b) { divider += (double)a / b; }
    uint32_t conf = s->regs[((rx ? RMT_CH4CONF0 : RMT_CH0CONF0) +
                            channel * (rx ? 8 : 4)) / 4];
    unsigned channel_divider = rx ? conf & 0xff : (conf >> 8) & 0xff;
    return source / divider / MAX(channel_divider, 1);
}

static void rmt_complete_tx(M5RmtState *s, uint32_t channel, bool error)
{
    uint32_t conf = s->regs[(RMT_CH0CONF0 + channel * 4) / 4];
    uint32_t count = s->tx_count[channel];
    s->pending_mask &= ~BIT(channel);
    s->tx_wait_mask &= ~BIT(channel);
    double tick_hz = rmt_tick_hz(s, channel, false);
    s->tx_last_conf = conf;
    s->tx_last_clock = s->regs[0xc0 / 4];
    s->tx_last_tick_hz = tick_hz;
    s->tx_first_symbol = count ? s->tx_frame[channel][0] : 0;
    if (error || !tick_hz) {
        s->tx_errors++;
        s->int_raw |= BIT(4 + channel);
        rmt_update_irq(s);
        return;
    }
    m5_unit_rmt_tx(channel, s->tx_frame[channel], count, tick_hz);
    if (!s->tx_file) {
        const char *path = getenv("M5SW_RMT_TX_FILE");
        if (path) {
            s->tx_file = fopen(path, "wb");
        }
    }
    if (s->tx_file && count) {
        fwrite(s->tx_frame[channel], sizeof(uint32_t), count, s->tx_file);
        fflush(s->tx_file);
    }
    if (s->trace) {
        fprintf(stderr, "[rmt] tx channel=%u symbols=%u\n", channel, count);
    }
    s->tx_completions++;
    s->int_raw |= 1u << channel;
    rmt_update_irq(s);
}

static void rmt_progress_tx(M5RmtState *s, unsigned channel)
{
    uint32_t conf = s->regs[(RMT_CH0CONF0 + channel * 4) / 4];
    unsigned base = channel * RMT_SYMBOLS_PER_CH;
    unsigned limit = MIN(MAX((conf >> 16) & 0xf, 1) * RMT_SYMBOLS_PER_CH,
                         ARRAY_SIZE(s->symbols) - base);
    unsigned threshold = s->regs[(RMT_CH0_TX_LIM + channel * 4) / 4] & 0x1ff;
    uint32_t event = BIT(8 + channel);

    /* A threshold means the guest may refill the consumed half of RMTMEM.
     * Do not reread it until the real ISR has acknowledged that event. */
    if (s->tx_wait_mask & BIT(channel)) {
        if (s->int_raw & event) { return; }
        s->tx_wait_mask &= ~BIT(channel);
    }
    while (s->pending_mask & BIT(channel)) {
        if (s->tx_cursor[channel] >= limit) {
            if (conf & BIT(4)) { s->tx_cursor[channel] = 0; }
            else { rmt_complete_tx(s, channel, false); return; }
        }
        uint32_t symbol = s->symbols[base + s->tx_cursor[channel]++];
        unsigned a = symbol & 0x7fff, b = (symbol >> 16) & 0x7fff;
        if (!a) { rmt_complete_tx(s, channel, false); return; }
        if (s->tx_count[channel] == RMT_MAX_TX_SYMBOLS) {
            /* A missing terminator must never fabricate a completed frame. */
            rmt_complete_tx(s, channel, true); return;
        }
        s->tx_frame[channel][s->tx_count[channel]++] = symbol;
        s->tx_symbols++;
        if (!b) { rmt_complete_tx(s, channel, false); return; }
        if (threshold && ++s->tx_since_threshold[channel] >= threshold) {
            s->tx_since_threshold[channel] = 0;
            s->tx_thresholds++;
            s->int_raw |= event;
            if (s->int_ena & event) {
                s->tx_wait_mask |= BIT(channel);
                rmt_update_irq(s);
                return;
            }
        }
    }
}

static void rmt_tx_timer(void *opaque)
{
    M5RmtState *s = opaque;
    uint32_t pending = s->pending_mask;

    for (uint32_t channel = 0; channel < RMT_TX_CHANNELS; channel++) {
        if (pending & (1u << channel)) {
            rmt_progress_tx(s, channel);
        }
    }
    if (s->pending_mask) {
        timer_mod(s->tx_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
    }
}

static void rmt_rx_timer(void *opaque)
{
    M5RmtState *s = opaque;
    uint32_t pending = s->rx_pending_mask;
    s->rx_pending_mask = 0;

    for (uint32_t channel = 0; channel < 4; channel++) {
        if (pending & (1u << channel)) {
            s->int_raw |= 1u << (16 + channel);
        }
    }
    rmt_update_irq(s);
}

static void rmt_inject_rx(M5RmtState *s, uint32_t channel)
{
    const char *path = getenv("M5SW_RMT_RX_FILE");
    g_autofree uint8_t *data = NULL;
    gsize size = 0;
    uint32_t count;

    double tick_hz = rmt_tick_hz(s, channel, true);
    if (!tick_hz) { return; }
    count = m5_unit_rmt_rx(channel,
        &s->symbols[(4 + channel) * RMT_SYMBOLS_PER_CH], RMT_SYMBOLS_PER_CH, tick_hz);
    if (count) {
        s->regs[(RMT_CH4STATUS + channel * 4) / 4] =
            (channel + 4) * RMT_SYMBOLS_PER_CH + count;
        s->rx_pending_mask |= 1u << channel;
        timer_mod(s->rx_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 20);
        return;
    }
    if (!path || s->rx_injected[channel]) { return; }
    if (!g_file_get_contents(path, (gchar **)&data, &size, NULL)) {
        return;
    }
    count = MIN(size / sizeof(uint32_t), RMT_SYMBOLS_PER_CH);
    memcpy(&s->symbols[(4 + channel) * RMT_SYMBOLS_PER_CH],
           data, count * sizeof(uint32_t));
    /* mem_waddr_ex is an absolute RMTMEM word address; each channel
     * occupies 48 words on ESP32-S3 and starts at (channel + 4) * 48. */
    s->regs[(RMT_CH4STATUS + channel * 4) / 4] =
        (channel + 4) * 48 + count;
    s->rx_injected[channel] = true;
    s->rx_pending_mask |= 1u << channel;
    timer_mod(s->rx_timer,
              qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 20);
    if (s->trace) {
        fprintf(stderr, "[rmt] rx inject channel=%u symbols=%u\n",
                channel, count);
    }
}

void m5_unit_rmt_rx_arrived(void)
{
    M5RmtState *s = unit_rmt;
    if (!s) { return; }
    for (unsigned channel = 0; channel < 4; channel++) {
        if ((s->regs[(RMT_CH4CONF0 + channel * 8 + 4) / 4] & 1u) &&
            !(s->rx_pending_mask & (1u << channel))) {
            rmt_inject_rx(s, channel);
        }
    }
}

static uint64_t rmt_read(void *opaque, hwaddr addr, unsigned size)
{
    M5RmtState *s = opaque;

    if (addr == RMT_INT_RAW) {
        return s->int_raw;
    }
    if (addr == RMT_INT_ST) {
        return s->int_raw & s->int_ena;
    }
    if (addr == RMT_INT_ENA) {
        return s->int_ena;
    }
    return addr < RMT_MEM_OFFSET ? s->regs[addr / 4] : 0;
}

static void rmt_write(void *opaque, hwaddr addr, uint64_t value,
                      unsigned size)
{
    M5RmtState *s = opaque;
    uint32_t v = value;

    if (s->trace) {
        fprintf(stderr, "[rmt] wr %03x <- %08x\n", (unsigned)addr, v);
    }
    if (addr == RMT_INT_ENA) {
        s->int_ena = v;
        rmt_update_irq(s);
        return;
    }
    if (addr == RMT_INT_CLR) {
        s->int_raw &= ~v;
        rmt_update_irq(s);
        if (s->pending_mask) {
            timer_mod(s->tx_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
        }
        return;
    }
    if (addr >= RMT_CH0CONF0 && addr < RMT_CH0CONF0 + RMT_TX_CHANNELS * 4) {
        uint32_t channel = (addr - RMT_CH0CONF0) / 4;
        s->regs[addr / 4] = v & ~(BIT(0) | BIT(7));
        if (v & BIT(7)) {
            s->pending_mask &= ~BIT(channel);
            s->tx_wait_mask &= ~BIT(channel);
        }
        if (v & 1u) {
            s->tx_cursor[channel] = s->tx_count[channel] = 0;
            s->tx_since_threshold[channel] = 0;
            s->tx_wait_mask &= ~BIT(channel);
            s->pending_mask |= 1u << channel;
            timer_mod(s->tx_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
        }
        return;
    }
    if (addr >= RMT_CH4CONF0 && addr < RMT_CH4CONF0 + 4 * 8) {
        uint32_t offset = addr - RMT_CH4CONF0;
        uint32_t channel = offset / 8;
        if ((offset % 8) == 4) {
            bool was_enabled = s->regs[addr / 4] & 1u;
            s->regs[addr / 4] = v;
            if (!was_enabled && (v & 1u)) {
                rmt_inject_rx(s, channel);
            }
            return;
        }
    }
    if (addr < RMT_MEM_OFFSET) {
        s->regs[addr / 4] = v;
    }
}

static const MemoryRegionOps rmt_ops = {
    .read = rmt_read,
    .write = rmt_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

static uint64_t rmt_mem_read(void *opaque, hwaddr addr, unsigned size)
{
    return ((M5RmtState *)opaque)->symbols[addr / 4];
}

static void rmt_mem_write(void *opaque, hwaddr addr, uint64_t value,
                          unsigned size)
{
    M5RmtState *s = opaque;
    s->symbols[addr / 4] = value;
    /* ISR acknowledgement precedes the refill stores. Settle from the last
     * actual APB write, rather than racing the guest halfway through a refill. */
    if (s->pending_mask) {
        timer_mod(s->tx_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
    }
}

static const MemoryRegionOps rmt_mem_ops = {
    .read = rmt_mem_read, .write = rmt_mem_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4, .valid.max_access_size = 4,
    .impl.min_access_size = 4, .impl.max_access_size = 4,
};

static void rmt_count_get(Object *o, Visitor *v, const char *name,
                          void *opaque, Error **errp)
{
    uint64_t count = *(uint64_t *)opaque;
    visit_type_uint64(v, name, &count, errp);
}

static void rmt_reset(DeviceState *dev)
{
    M5RmtState *s = M5_RMT(dev);
    memset(s->regs, 0, sizeof(s->regs));
    memset(s->symbols, 0, sizeof(s->symbols));
    s->int_ena = 0;
    s->int_raw = 0;
    s->pending_mask = 0;
    s->tx_wait_mask = 0;
    memset(s->tx_cursor, 0, sizeof(s->tx_cursor));
    memset(s->tx_count, 0, sizeof(s->tx_count));
    memset(s->tx_since_threshold, 0, sizeof(s->tx_since_threshold));
    s->tx_symbols = s->tx_thresholds = s->tx_completions = s->tx_errors = 0;
    s->tx_last_conf = s->tx_last_clock = s->tx_last_tick_hz = s->tx_first_symbol = 0;
    s->rx_pending_mask = 0;
    memset(s->rx_injected, 0, sizeof(s->rx_injected));
    timer_del(s->tx_timer);
    timer_del(s->rx_timer);
}

static void rmt_init(Object *obj)
{
    M5RmtState *s = M5_RMT(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    unit_rmt = s;

    memory_region_init_io(&s->mmio, obj, &rmt_ops, s, TYPE_M5_RMT,
                          RMT_MEM_OFFSET);
    memory_region_init_io(&s->mem, obj, &rmt_mem_ops, s, TYPE_M5_RMT ".mem",
                         RMT_MEM_SIZE);
    sysbus_init_mmio(sbd, &s->mmio);
    sysbus_init_mmio(sbd, &s->mem);
    sysbus_init_irq(sbd, &s->irq);
    s->trace = getenv("M5SW_RMT_TRACE") != NULL;
    s->tx_timer = timer_new_ms(QEMU_CLOCK_REALTIME, rmt_tx_timer, s);
    s->rx_timer = timer_new_ms(QEMU_CLOCK_REALTIME, rmt_rx_timer, s);
    object_property_add(obj, "tx-symbols", "uint64", rmt_count_get, NULL, NULL, &s->tx_symbols);
    object_property_add(obj, "tx-threshold-events", "uint64", rmt_count_get, NULL, NULL, &s->tx_thresholds);
    object_property_add(obj, "tx-completions", "uint64", rmt_count_get, NULL, NULL, &s->tx_completions);
    object_property_add(obj, "tx-errors", "uint64", rmt_count_get, NULL, NULL, &s->tx_errors);
    object_property_add(obj, "tx-last-conf", "uint64", rmt_count_get, NULL, NULL, &s->tx_last_conf);
    object_property_add(obj, "tx-last-clock", "uint64", rmt_count_get, NULL, NULL, &s->tx_last_clock);
    object_property_add(obj, "tx-last-tick-hz", "uint64", rmt_count_get, NULL, NULL, &s->tx_last_tick_hz);
    object_property_add(obj, "tx-first-symbol", "uint64", rmt_count_get, NULL, NULL, &s->tx_first_symbol);
}

static void rmt_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    device_class_set_legacy_reset(dc, rmt_reset);
}

static const TypeInfo rmt_info = {
    .name = TYPE_M5_RMT,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(M5RmtState),
    .instance_init = rmt_init,
    .class_init = rmt_class_init,
};

static void rmt_register(void)
{
    type_register_static(&rmt_info);
}
type_init(rmt_register)

void esp32s3_rmt_init(MemoryRegion *sys_mem, DeviceState *intmatrix)
{
    DeviceState *dev = qdev_new(TYPE_M5_RMT);
    object_property_add_child(qdev_get_machine(), "rmt0", OBJECT(dev));
    sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
    memory_region_add_subregion_overlap(
        sys_mem, DR_REG_RMT_BASE,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(dev), 0), 1);
    memory_region_add_subregion_overlap(
        sys_mem, DR_REG_RMT_BASE + RMT_MEM_OFFSET,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(dev), 1), 1);
    sysbus_connect_irq(SYS_BUS_DEVICE(dev), 0,
                       qdev_get_gpio_in(intmatrix, ETS_RMT_INTR_SOURCE));
}

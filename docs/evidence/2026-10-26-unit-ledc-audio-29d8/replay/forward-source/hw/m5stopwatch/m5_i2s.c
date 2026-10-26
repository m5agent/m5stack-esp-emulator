/*
 * ESP32-S3 I2S register front-end.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "hw/dma/esp_gdma.h"
#include "hw/irq.h"
#include "hw/sysbus.h"
#include "hw/xtensa/esp32s3_intc.h"
#include "m5stopwatch.h"

#define R_INT_RAW  0x0c
#define R_INT_ST   0x10
#define R_INT_ENA  0x14
#define R_INT_CLR  0x18
#define R_RX_CONF  0x20
#define R_TX_CONF  0x24
#define RX_UPDATE  (1u << 8)
#define TX_UPDATE  (1u << 8)
#define RX_START   (1u << 2)
#define TX_START   (1u << 2)

struct M5I2SState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    qemu_irq irq;
    uint32_t regs[0x1000 / 4];
    uint32_t int_ena;
    uint32_t int_raw;
    ESPGdmaState *gdma;
    uint32_t port;
    FILE *pcm_file;
    uint64_t pcm_bytes;
    uint64_t pcm_limit;
    uint32_t pcm_writes;
    bool pcm_started;
    QEMUTimer *tx_timer;
    int64_t capture_until_ms;
    int64_t dma_due_ms;
    uint32_t dma_events;
    bool dma_irq;
    bool tx_started;
    bool dma_active;
    uint32_t dma_channel;
    QEMUTimer *rx_timer;
    uint8_t *rx_pcm;
    uint32_t rx_pcm_size;
    uint32_t rx_pcm_pos;
    uint32_t rx_dma_channel;
    int64_t rx_dma_due_ms;
    bool rx_started;
    bool rx_dma_active;
    bool trace;
};

static void i2s_update_irq(M5I2SState *s)
{
    qemu_set_irq(s->irq, !!(s->int_raw & s->int_ena));
}

static uint64_t i2s_read(void *opaque, hwaddr addr, unsigned size)
{
    M5I2SState *s = opaque;
    switch (addr) {
    case R_INT_RAW:
        return s->int_raw;
    case R_INT_ST:
        return s->int_raw & s->int_ena;
    case R_INT_ENA:
        return s->int_ena;
    default:
        return addr < sizeof(s->regs) ? s->regs[addr / 4] : 0;
    }
}

static void i2s_capture_tx(M5I2SState *s)
{
    uint32_t channel;
    uint32_t bytes;
    GdmaPeripheral periph = s->port ? GDMA_I2S1 : GDMA_I2S0;

    if (!s->gdma
        || !esp_gdma_get_channel_periph(s->gdma, periph,
                                         ESP_GDMA_OUT_IDX, &channel)) {
        return;
    }
    s->dma_channel = channel;
    s->dma_active = true;
    bytes = esp_gdma_get_out_transfer_size(s->gdma, channel, 1 << 20);
    if (!bytes) {
        return;
    }
    if (s->trace) {
        fprintf(stderr, "[i2s%d] dma start bytes=%u\n", s->port, bytes);
    }
}

static bool i2s_store_pcm(M5I2SState *s, const uint8_t *buffer, uint32_t bytes);

static void i2s_complete_dma(M5I2SState *s, uint32_t channel)
{
    const uint32_t snapshot_size = 4096;
    g_autofree uint8_t *buffer = g_malloc0(snapshot_size);
    uint32_t bytes;

    if (!s->gdma) {
        return;
    }
    bytes = esp_gdma_complete_out_descriptor(
        s->gdma, channel, buffer, snapshot_size);
    if (!bytes) {
        if (s->trace) {
            fprintf(stderr, "[i2s%d] dma complete empty chan=%u\n",
                    s->port, channel);
        }
        return;
    }
    if (s->trace) {
        fprintf(stderr, "[i2s%d] dma read chan=%u bytes=%u head=",
                s->port, channel, bytes);
        for (uint32_t i = 0; i < MIN(bytes, 16); i++) {
            fprintf(stderr, "%02x", buffer[i]);
        }
        fprintf(stderr, "\n");
    }
    i2s_store_pcm(s, buffer, bytes);
    s->dma_events++;
}

static bool i2s_store_pcm(M5I2SState *s, const uint8_t *buffer, uint32_t bytes)
{
    uint32_t write_size;

    if (!bytes || s->pcm_bytes >= s->pcm_limit) {
        return false;
    }
    if (!s->pcm_started) {
        bool any_nonzero = false;
        for (uint32_t i = 0; i < bytes; i++) {
            if (buffer[i]) {
                any_nonzero = true;
                break;
            }
        }
        if (!any_nonzero) {
            return false;
        }
        const char *path = getenv("M5SW_I2S_PCM_FILE");
        if (!path) {
            return false;
        }
        s->pcm_file = fopen(path, "wb");
        if (!s->pcm_file) {
            return false;
        }
        s->pcm_started = true;
    }
    write_size = MIN(bytes, s->pcm_limit - s->pcm_bytes);
    if (write_size) {
        fwrite(buffer, 1, write_size, s->pcm_file);
        fflush(s->pcm_file);
        s->pcm_bytes += write_size;
        s->pcm_writes++;
    }
    if (s->trace) {
        fprintf(stderr,
                "[i2s%d] pcm bytes=%u total=%" PRIu64
                " writes=%u\n",
                s->port, write_size, s->pcm_bytes, s->pcm_writes);
    }
    return true;
}

static void i2s_tx_timer(void *opaque)
{
    M5I2SState *s = opaque;
    const uint32_t snapshot_size = 1 << 20;
    g_autofree uint8_t *buffer = NULL;
    uint32_t channel;
    uint32_t bytes;
    GdmaPeripheral periph = s->port ? GDMA_I2S1 : GDMA_I2S0;

    if (qemu_clock_get_ms(QEMU_CLOCK_REALTIME) >= s->capture_until_ms
        || s->pcm_bytes >= s->pcm_limit) {
        return;
    }
    timer_mod(s->tx_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 1);
    if (s->dma_irq && s->dma_active && s->dma_events < 128
        && qemu_clock_get_ms(QEMU_CLOCK_REALTIME) >= s->dma_due_ms) {
        if (s->trace) {
            fprintf(stderr, "[i2s%d] dma completion due chan=%u\n",
                    s->port, s->dma_channel);
        }
        i2s_complete_dma(s, s->dma_channel);
        s->dma_active = false;
        s->dma_due_ms = qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 20;
    }
    if (!s->gdma
        || !esp_gdma_get_channel_periph(s->gdma, periph,
                                         ESP_GDMA_OUT_IDX, &channel)) {
        return;
    }
    if (!s->dma_active) {
        s->dma_channel = channel;
        s->dma_active = true;
        s->dma_due_ms = qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 20;
    }
    if (s->dma_irq) {
        return;
    }

    buffer = g_malloc(snapshot_size);
    bytes = esp_gdma_snapshot_out_channel(s->gdma, channel, buffer,
                                          snapshot_size);
    if (s->trace) {
        fprintf(stderr, "[i2s%d] timer snapshot bytes=%u writes=%u head=",
                s->port, bytes, s->pcm_writes);
        for (uint32_t i = 0; i < MIN(bytes, 16); i++) {
            fprintf(stderr, "%02x", buffer[i]);
        }
        fprintf(stderr, "\n");
    }
    if (!bytes) {
        return;
    }
    i2s_store_pcm(s, buffer, bytes);
}

static void i2s_rx_timer(void *opaque)
{
    M5I2SState *s = opaque;
    uint8_t buffer[4096];
    uint32_t available;
    uint32_t chunk;
    uint32_t sent;

    if (!s->rx_started || !s->rx_dma_active || !s->gdma
        || !s->rx_pcm || !s->rx_pcm_size) {
        return;
    }
    if (qemu_clock_get_ms(QEMU_CLOCK_REALTIME) < s->rx_dma_due_ms) {
        timer_mod(s->rx_timer,
                  qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
        return;
    }
    available = s->rx_pcm_size - s->rx_pcm_pos;
    if (!available) {
        s->rx_pcm_pos = 0;
        available = s->rx_pcm_size;
    }
    chunk = MIN(available, sizeof(buffer));
    memcpy(buffer, s->rx_pcm + s->rx_pcm_pos, chunk);
    s->rx_pcm_pos = (s->rx_pcm_pos + chunk) % s->rx_pcm_size;
    sent = esp_gdma_complete_in_descriptor(
        s->gdma, s->rx_dma_channel, buffer, chunk);
    if (s->trace) {
        fprintf(stderr, "[i2s%d] rx dma inject chan=%u bytes=%u\n",
                s->port, s->rx_dma_channel, sent);
    }
    s->rx_dma_due_ms = qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 20;
    timer_mod(s->rx_timer,
              qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
}

static void i2s_rx_start(M5I2SState *s)
{
    uint32_t channel;
    const char *path = getenv("M5SW_I2S_RX_PCM_FILE");
    GdmaPeripheral periph = s->port ? GDMA_I2S1 : GDMA_I2S0;

    if (!s->gdma
        || !esp_gdma_get_channel_periph(s->gdma, periph,
                                         ESP_GDMA_IN_IDX, &channel)) {
        return;
    }
    s->rx_dma_channel = channel;
    s->rx_dma_active = true;
    s->rx_pcm_pos = 0;
    s->rx_dma_due_ms = qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 20;
    if (path) {
        g_autofree char *contents = NULL;
        gsize length = 0;
        if (g_file_get_contents(path, &contents, &length, NULL) && length) {
            g_free(s->rx_pcm);
            s->rx_pcm = (uint8_t *)contents;
            contents = NULL;
            s->rx_pcm_size = length;
        }
    }
    timer_mod(s->rx_timer,
              qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2);
}

static void i2s_write(void *opaque, hwaddr addr, uint64_t value,
                      unsigned size)
{
    M5I2SState *s = opaque;
    uint32_t v = value;

    if (s->trace) {
        fprintf(stderr, "[i2s] wr %03x <- %08x\n",
                (unsigned)addr, v);
    }
    switch (addr) {
    case R_INT_ENA:
        s->int_ena = v;
        i2s_update_irq(s);
        break;
    case R_INT_CLR:
        s->int_raw &= ~v;
        i2s_update_irq(s);
        break;
    case R_RX_CONF:
        if ((v & RX_START) && !s->rx_started) {
            i2s_rx_start(s);
        }
        s->rx_started = !!(v & RX_START);
        s->regs[addr / 4] = v & ~RX_UPDATE;
        break;
    case R_TX_CONF:
        if ((v & TX_START) && !s->tx_started) {
            i2s_capture_tx(s);
            if (!s->pcm_started) {
                s->pcm_writes = 0;
                s->pcm_bytes = 0;
            }
            s->dma_events = 0;
            s->capture_until_ms =
                qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 2000;
            s->dma_due_ms = qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 500;
            timer_mod(s->tx_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 1);
        }
        s->tx_started = !!(v & TX_START);
        s->regs[addr / 4] = v & ~TX_UPDATE;
        break;
    default:
        if (addr < sizeof(s->regs)) {
            s->regs[addr / 4] = v;
        }
        break;
    }
}

static const MemoryRegionOps i2s_ops = {
    .read = i2s_read,
    .write = i2s_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

static void i2s_reset(DeviceState *dev)
{
    M5I2SState *s = M5_I2S(dev);
    memset(s->regs, 0, sizeof(s->regs));
    s->int_ena = 0;
    s->int_raw = 0;
    s->tx_started = false;
    s->dma_active = false;
    s->dma_channel = 0;
    s->rx_started = false;
    s->rx_dma_active = false;
    s->rx_dma_channel = 0;
    s->pcm_started = false;
    if (s->rx_timer) {
        timer_del(s->rx_timer);
    }
    if (s->tx_timer) {
        timer_del(s->tx_timer);
    }
}

static void i2s_init(Object *obj)
{
    M5I2SState *s = M5_I2S(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    memory_region_init_io(&s->iomem, obj, &i2s_ops, s, TYPE_M5_I2S, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    s->trace = getenv("M5SW_I2S_TRACE") != NULL;
    s->dma_irq = getenv("M5SW_I2S_DMA_IRQ") != NULL;
    s->pcm_limit = 4 << 20;
    s->tx_timer = timer_new_ms(QEMU_CLOCK_REALTIME, i2s_tx_timer, s);
    s->rx_timer = timer_new_ms(QEMU_CLOCK_REALTIME, i2s_rx_timer, s);
}

void m5_i2s_attach(DeviceState *dev, ESPGdmaState *gdma, uint32_t port)
{
    M5I2SState *s = M5_I2S(dev);
    s->gdma = gdma;
    s->port = port;
}

static void i2s_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    device_class_set_legacy_reset(dc, i2s_reset);
}

static const TypeInfo i2s_info = {
    .name = TYPE_M5_I2S,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(M5I2SState),
    .instance_init = i2s_init,
    .class_init = i2s_class_init,
};

static void i2s_register(void)
{
    type_register_static(&i2s_info);
}
type_init(i2s_register)

void m5_i2s_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                       ESPGdmaState *gdma)
{
    static const struct {
        hwaddr base;
        int irq_source;
    } ports[] = {
        { 0x6000f000, ETS_I2S0_INTR_SOURCE },
        { 0x6002d000, ETS_I2S1_INTR_SOURCE },
    };

    for (int i = 0; i < ARRAY_SIZE(ports); i++) {
        DeviceState *dev = qdev_new(TYPE_M5_I2S);
        m5_i2s_attach(dev, gdma, i);
        sysbus_realize_and_unref(SYS_BUS_DEVICE(dev), &error_fatal);
        memory_region_add_subregion_overlap(
            sys_mem, ports[i].base,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(dev), 0), 1);
        sysbus_connect_irq(
            SYS_BUS_DEVICE(dev), 0,
            qdev_get_gpio_in(intmatrix, ports[i].irq_source));
    }
}

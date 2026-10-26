/*
 * ESP32 classic I2S controller model.
 *
 * The original ESP32 uses the I2S block's own linked-list DMA engine rather
 * than the GDMA block found on ESP32-S3.  Core2 uses I2S0 for both the NS4168
 * speaker path and the SPM1423 PDM microphone path.  This model consumes the
 * real IDF DMA descriptors and provides host PCM capture/injection at the
 * controller boundary.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "exec/address-spaces.h"
#include "hw/irq.h"
#include "hw/misc/esp32_reg.h"
#include "hw/qdev-properties.h"
#include "hw/sysbus.h"
#include "qemu/timer.h"
#include "m5stopwatch.h"

#define R_CONF          0x008
#define R_INT_RAW       0x00c
#define R_INT_ST        0x010
#define R_INT_ENA       0x014
#define R_INT_CLR       0x018
#define R_OUT_LINK      0x030
#define R_IN_LINK       0x034
#define R_OUT_EOF_DESC  0x038
#define R_IN_EOF_DESC   0x03c
#define R_STATE         0x0bc

#define CONF_TX_RESET       BIT(0)
#define CONF_RX_RESET       BIT(1)
#define CONF_TX_FIFO_RESET  BIT(2)
#define CONF_RX_FIFO_RESET  BIT(3)
#define CONF_TX_START       BIT(4)
#define CONF_RX_START       BIT(5)

#define LINK_STOP           BIT(28)
#define LINK_START          BIT(29)
#define LINK_RESTART        BIT(30)
#define LINK_ADDR_MASK      0x000fffff

#define INT_RX_EOF          BIT(9)
#define INT_TX_EOF          BIT(12)
#define INT_RX_DSCR_ERR     BIT(13)
#define INT_TX_DSCR_ERR     BIT(14)

#define I2S_DESC_SIZE       12
#define I2S_DESC_MAX_BYTES  4092
#define I2S_PCM_MAX_BYTES   (4 << 20)
#define I2S_DMA_PERIOD_MS   10

typedef struct M5Esp32I2SState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    qemu_irq irq;
    uint32_t port;
    uint32_t regs[0x1000 / 4];
    uint32_t int_ena;
    uint32_t int_raw;
    QEMUTimer *tx_timer;
    QEMUTimer *rx_timer;
    uint32_t tx_desc;
    uint32_t tx_first_desc;
    uint32_t rx_desc;
    uint32_t rx_first_desc;
    bool tx_running;
    bool rx_running;
    bool trace;
    FILE *pcm_file;
    uint64_t pcm_bytes;
    uint32_t pcm_writes;
    bool pcm_started;
    uint8_t *rx_pcm;
    uint32_t rx_pcm_size;
    uint32_t rx_pcm_pos;
} M5Esp32I2SState;

typedef struct M5Esp32I2SDesc {
    uint32_t dw0;
    uint32_t buffer;
    uint32_t next;
} M5Esp32I2SDesc;

static void i2s_update_irq(M5Esp32I2SState *s)
{
    qemu_set_irq(s->irq, !!(s->int_raw & s->int_ena));
}

static bool i2s_store_pcm(M5Esp32I2SState *s, const uint8_t *buffer,
                          uint32_t bytes)
{
    uint32_t write_size;

    if (!bytes || s->pcm_bytes >= I2S_PCM_MAX_BYTES) {
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
    write_size = MIN(bytes, I2S_PCM_MAX_BYTES - s->pcm_bytes);
    fwrite(buffer, 1, write_size, s->pcm_file);
    fflush(s->pcm_file);
    s->pcm_bytes += write_size;
    s->pcm_writes++;
    if (s->trace) {
        fprintf(stderr,
                "[esp32-i2s%d] pcm bytes=%u total=%" PRIu64
                " writes=%u\n",
                s->port, write_size, s->pcm_bytes, s->pcm_writes);
    }
    return true;
}

static uint32_t i2s_desc_decode_addr(uint32_t link_reg)
{
    /*
     * The legacy I2S link register stores the low 20 bits of an internal-RAM
     * address.  IDF places I2S descriptors in ESP32 DRAM at 0x3ffxxxxx.
     */
    return 0x3ff00000u | (link_reg & LINK_ADDR_MASK);
}

static bool i2s_read_desc(uint32_t addr, M5Esp32I2SDesc *desc)
{
    uint8_t raw[I2S_DESC_SIZE];

    if (!addr || address_space_read(&address_space_memory, addr,
                                    MEMTXATTRS_UNSPECIFIED, raw,
                                    sizeof(raw)) != MEMTX_OK) {
        return false;
    }
    desc->dw0 = ldl_le_p(raw);
    desc->buffer = ldl_le_p(raw + 4);
    desc->next = ldl_le_p(raw + 8);
    return true;
}

static bool i2s_write_desc_length(uint32_t addr, uint32_t length)
{
    uint8_t raw[4];
    uint32_t dw0;

    if (address_space_read(&address_space_memory, addr,
                           MEMTXATTRS_UNSPECIFIED, raw, sizeof(raw))
        != MEMTX_OK) {
        return false;
    }
    dw0 = ldl_le_p(raw);
    dw0 = (dw0 & ~0x00fff000u) | ((length & 0xfff) << 12);
    stl_le_p(raw, dw0);
    return address_space_write(&address_space_memory, addr,
                               MEMTXATTRS_UNSPECIFIED, raw,
                               sizeof(raw)) == MEMTX_OK;
}

static uint32_t i2s_desc_bytes(const M5Esp32I2SDesc *desc)
{
    uint32_t bytes = desc->dw0 & 0xfff;

    return bytes ? MIN(bytes, I2S_DESC_MAX_BYTES) : 4096;
}

static uint32_t i2s_next_desc(const M5Esp32I2SDesc *desc, uint32_t current,
                              uint32_t first)
{
    if (desc->next && desc->next != current) {
        return desc->next;
    }
    return (desc->dw0 & BIT(30)) ? first : 0;
}

static void i2s_tx_timer(void *opaque)
{
    M5Esp32I2SState *s = opaque;
    M5Esp32I2SDesc desc;
    g_autofree uint8_t *buffer = NULL;
    uint32_t bytes;

    if (!s->tx_running || !s->tx_desc) {
        return;
    }
    if (!i2s_read_desc(s->tx_desc, &desc)) {
        s->int_raw |= INT_TX_DSCR_ERR;
        i2s_update_irq(s);
        s->tx_running = false;
        return;
    }
    bytes = i2s_desc_bytes(&desc);
    buffer = g_malloc0(bytes);
    if (bytes && address_space_read(&address_space_memory, desc.buffer,
                                    MEMTXATTRS_UNSPECIFIED, buffer,
                                    bytes) != MEMTX_OK) {
        s->int_raw |= INT_TX_DSCR_ERR;
        i2s_update_irq(s);
        s->tx_running = false;
        return;
    }
    if (s->trace) {
        fprintf(stderr,
                "[esp32-i2s%d] tx desc=%08x buffer=%08x bytes=%u next=%08x\n",
                s->port, s->tx_desc, desc.buffer, bytes, desc.next);
    }
    i2s_store_pcm(s, buffer, bytes);
    s->regs[R_OUT_EOF_DESC / 4] = s->tx_desc;
    s->int_raw |= INT_TX_EOF;
    i2s_update_irq(s);
    s->tx_desc = i2s_next_desc(&desc, s->tx_desc, s->tx_first_desc);
    if (!s->tx_desc) {
        s->tx_running = false;
        return;
    }
    timer_mod(s->tx_timer,
              qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + I2S_DMA_PERIOD_MS);
}

static void i2s_load_rx_pcm(M5Esp32I2SState *s)
{
    const char *path = getenv("M5SW_I2S_RX_PCM_FILE");
    g_autofree char *contents = NULL;
    gsize length = 0;

    g_free(s->rx_pcm);
    s->rx_pcm = NULL;
    s->rx_pcm_size = 0;
    s->rx_pcm_pos = 0;
    if (!path) {
        return;
    }
    if (g_file_get_contents(path, &contents, &length, NULL) && length) {
        s->rx_pcm = (uint8_t *)contents;
        contents = NULL;
        s->rx_pcm_size = length;
    }
}

static void i2s_rx_timer(void *opaque)
{
    M5Esp32I2SState *s = opaque;
    M5Esp32I2SDesc desc;
    g_autofree uint8_t *buffer = NULL;
    uint32_t bytes;
    uint32_t available;
    uint32_t first;

    if (!s->rx_running || !s->rx_desc) {
        return;
    }
    if (!i2s_read_desc(s->rx_desc, &desc)) {
        s->int_raw |= INT_RX_DSCR_ERR;
        i2s_update_irq(s);
        s->rx_running = false;
        return;
    }
    bytes = i2s_desc_bytes(&desc);
    buffer = g_malloc0(bytes);
    if (s->rx_pcm_size && bytes) {
        available = s->rx_pcm_size - s->rx_pcm_pos;
        if (!available) {
            s->rx_pcm_pos = 0;
            available = s->rx_pcm_size;
        }
        first = MIN(bytes, available);
        memcpy(buffer, s->rx_pcm + s->rx_pcm_pos, first);
        if (first < bytes) {
            memcpy(buffer + first, s->rx_pcm,
                   MIN(bytes - first, s->rx_pcm_size));
        }
        s->rx_pcm_pos = (s->rx_pcm_pos + first) % s->rx_pcm_size;
    }
    if (bytes && address_space_write(&address_space_memory, desc.buffer,
                                     MEMTXATTRS_UNSPECIFIED, buffer,
                                     bytes) != MEMTX_OK) {
        s->int_raw |= INT_RX_DSCR_ERR;
        i2s_update_irq(s);
        s->rx_running = false;
        return;
    }
    i2s_write_desc_length(s->rx_desc, bytes);
    if (s->trace) {
        fprintf(stderr,
                "[esp32-i2s%d] rx desc=%08x buffer=%08x bytes=%u next=%08x\n",
                s->port, s->rx_desc, desc.buffer, bytes, desc.next);
    }
    s->regs[R_IN_EOF_DESC / 4] = s->rx_desc;
    s->int_raw |= INT_RX_EOF;
    i2s_update_irq(s);
    s->rx_desc = i2s_next_desc(&desc, s->rx_desc, s->rx_first_desc);
    if (!s->rx_desc) {
        s->rx_running = false;
        return;
    }
    timer_mod(s->rx_timer,
              qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + I2S_DMA_PERIOD_MS);
}

static uint64_t i2s_read(void *opaque, hwaddr addr, unsigned size)
{
    M5Esp32I2SState *s = opaque;

    switch (addr) {
    case R_INT_RAW:
        return s->int_raw;
    case R_INT_ST:
        return s->int_raw & s->int_ena;
    case R_INT_ENA:
        return s->int_ena;
    case R_STATE:
        return (!s->tx_running ? BIT(0) : 0) |
               (!s->rx_running ? BIT(2) : 0);
    default:
        return addr < sizeof(s->regs) ? s->regs[addr / 4] : 0;
    }
}

static void i2s_write_link(M5Esp32I2SState *s, hwaddr addr, uint32_t value,
                           bool tx)
{
    uint32_t first;

    s->regs[addr / 4] = value;
    first = i2s_desc_decode_addr(value);
    if (tx) {
        s->tx_first_desc = first;
        if (value & (LINK_START | LINK_RESTART)) {
            s->tx_desc = first;
            s->tx_running = true;
            if (s->regs[R_CONF / 4] & CONF_TX_START) {
                timer_mod(s->tx_timer,
                          qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL)
                          + I2S_DMA_PERIOD_MS);
            }
        }
        if (value & LINK_STOP) {
            s->tx_running = false;
            timer_del(s->tx_timer);
        }
    } else {
        s->rx_first_desc = first;
        if (value & (LINK_START | LINK_RESTART)) {
            s->rx_desc = first;
            s->rx_running = true;
            i2s_load_rx_pcm(s);
            if (s->regs[R_CONF / 4] & CONF_RX_START) {
                timer_mod(s->rx_timer,
                          qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL)
                          + I2S_DMA_PERIOD_MS);
            }
        }
        if (value & LINK_STOP) {
            s->rx_running = false;
            timer_del(s->rx_timer);
        }
    }
}

static void i2s_write(void *opaque, hwaddr addr, uint64_t value,
                      unsigned size)
{
    M5Esp32I2SState *s = opaque;
    uint32_t v = value;
    bool old_tx_start;
    bool old_rx_start;

    if (s->trace) {
        fprintf(stderr, "[esp32-i2s%d] wr %03x <- %08x\n",
                s->port, (unsigned)addr, v);
    }
    switch (addr) {
    case R_INT_ENA:
        s->int_ena = v;
        i2s_update_irq(s);
        return;
    case R_INT_CLR:
        s->int_raw &= ~v;
        i2s_update_irq(s);
        return;
    case R_CONF:
        old_tx_start = !!(s->regs[addr / 4] & CONF_TX_START);
        old_rx_start = !!(s->regs[addr / 4] & CONF_RX_START);
        if (v & CONF_TX_RESET) {
            s->tx_running = false;
            timer_del(s->tx_timer);
            s->tx_desc = 0;
        }
        if (v & CONF_RX_RESET) {
            s->rx_running = false;
            timer_del(s->rx_timer);
            s->rx_desc = 0;
        }
        s->regs[addr / 4] = v & ~(CONF_TX_RESET | CONF_RX_RESET |
                                  CONF_TX_FIFO_RESET | CONF_RX_FIFO_RESET);
        if ((v & CONF_TX_START) && !old_tx_start && s->tx_first_desc) {
            s->tx_desc = s->tx_first_desc;
            s->tx_running = true;
            if (!s->pcm_started) {
                s->pcm_writes = 0;
                s->pcm_bytes = 0;
            }
            timer_mod(s->tx_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL)
                      + I2S_DMA_PERIOD_MS);
        }
        if ((v & CONF_RX_START) && !old_rx_start && s->rx_first_desc) {
            s->rx_desc = s->rx_first_desc;
            s->rx_running = true;
            i2s_load_rx_pcm(s);
            timer_mod(s->rx_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL)
                      + I2S_DMA_PERIOD_MS);
        }
        if (!(v & CONF_TX_START)) {
            s->tx_running = false;
            timer_del(s->tx_timer);
        }
        if (!(v & CONF_RX_START)) {
            s->rx_running = false;
            timer_del(s->rx_timer);
        }
        return;
    case R_OUT_LINK:
        i2s_write_link(s, addr, v, true);
        return;
    case R_IN_LINK:
        i2s_write_link(s, addr, v, false);
        return;
    default:
        if (addr < sizeof(s->regs)) {
            s->regs[addr / 4] = v;
        }
    }
}

static const MemoryRegionOps i2s_ops = {
    .read = i2s_read,
    .write = i2s_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
};

static void i2s_reset(DeviceState *dev)
{
    M5Esp32I2SState *s = M5_ESP32_I2S(dev);

    timer_del(s->tx_timer);
    timer_del(s->rx_timer);
    memset(s->regs, 0, sizeof(s->regs));
    s->int_ena = 0;
    s->int_raw = 0;
    s->tx_desc = 0;
    s->tx_first_desc = 0;
    s->rx_desc = 0;
    s->rx_first_desc = 0;
    s->tx_running = false;
    s->rx_running = false;
    s->pcm_started = false;
    qemu_set_irq(s->irq, 0);
}

static void i2s_init(Object *obj)
{
    M5Esp32I2SState *s = M5_ESP32_I2S(obj);

    memory_region_init_io(&s->iomem, obj, &i2s_ops, s,
                          TYPE_M5_ESP32_I2S, 0x1000);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->iomem);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
    s->tx_timer = timer_new_ms(QEMU_CLOCK_VIRTUAL, i2s_tx_timer, s);
    s->rx_timer = timer_new_ms(QEMU_CLOCK_VIRTUAL, i2s_rx_timer, s);
    s->trace = getenv("M5SW_I2S_TRACE") != NULL;
}

static void i2s_finalize(Object *obj)
{
    M5Esp32I2SState *s = M5_ESP32_I2S(obj);

    timer_free(s->tx_timer);
    timer_free(s->rx_timer);
    if (s->pcm_file) {
        fclose(s->pcm_file);
    }
    g_free(s->rx_pcm);
}

static void i2s_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, i2s_reset);
}

static const TypeInfo i2s_info = {
    .name = TYPE_M5_ESP32_I2S,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(M5Esp32I2SState),
    .instance_init = i2s_init,
    .instance_finalize = i2s_finalize,
    .class_init = i2s_class_init,
};

static void i2s_register_types(void)
{
    type_register_static(&i2s_info);
}

type_init(i2s_register_types)

void m5_esp32_i2s_board_init(MemoryRegion *sys_mem, BusState *periph_bus,
                             DeviceState *intmatrix)
{
    static const struct {
        hwaddr base;
        int irq;
    } ports[] = {
        { DR_REG_I2S_BASE, ETS_I2S0_INTR_SOURCE },
        { DR_REG_I2S1_BASE, ETS_I2S1_INTR_SOURCE },
    };

    for (uint32_t i = 0; i < ARRAY_SIZE(ports); i++) {
        DeviceState *dev = qdev_new(TYPE_M5_ESP32_I2S);
        M5Esp32I2SState *s = M5_ESP32_I2S(dev);
        char name[16];

        s->port = i;
        snprintf(name, sizeof(name), "esp32.i2s%u", i);
        object_property_add_child(qdev_get_machine(), name, OBJECT(dev));
        qdev_realize(dev, periph_bus, &error_fatal);
        memory_region_add_subregion_overlap(
            sys_mem, ports[i].base,
            sysbus_mmio_get_region(SYS_BUS_DEVICE(dev), 0), 0);
        sysbus_connect_irq(SYS_BUS_DEVICE(dev), 0,
                           qdev_get_gpio_in(intmatrix, ports[i].irq));
    }
}

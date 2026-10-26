/*
 * ESP32-S3 GP-SPI2 master (subset): user-defined transactions with
 * command/address/MOSI phases, W0..W15 buffer or GDMA out-link as source.
 * Quad/dual line modes do not change the byte stream, so they are accepted
 * transparently. Bytes are forwarded to an attached CO5300 panel model.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "exec/address-spaces.h"
#include "hw/dma/esp_gdma.h"
#include "qapi/error.h"
#include "m5stopwatch.h"

#define R_CMD      0x00
#define R_ADDR     0x04
#define R_USER     0x10
#define R_USER1    0x14
#define R_USER2    0x18
#define R_MS_DLEN  0x1c
#define R_DMA_CONF 0x30
#define R_DMA_INT_ENA 0x34
#define R_DMA_INT_CLR 0x38
#define R_DMA_INT_RAW 0x3c
#define R_DMA_INT_ST  0x40
#define R_DMA_INT_SET 0x44
#define R_W0       0x98
#define R_DATE     0xf0

#define CMD_USR      (1u << 24)
#define USER_MOSI    (1u << 27)
#define USER_MISO    (1u << 28)
#define USER_ADDR    (1u << 30)
#define USER_COMMAND (1u << 31)
#define DMA_RX_ENA   (1u << 27)
#define DMA_TX_ENA   (1u << 28)
#define INT_TRANS_DONE (1u << 12)

#define M5_GPSPI_MAX_SLAVES 4

typedef struct M5GpspiSlave {
    const M5SpiSlaveOps *ops;
    void *opaque;
    int cs_pin;
    int cs_level;
    int gdma_periph;
} M5GpspiSlave;

struct Esp32s3GpspiState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    qemu_irq irq;
    qemu_irq irq_alias;
    uint32_t regs[0x40];
    ESPGdmaState *gdma;
    Co5300State *panel;
    M5SpiPanelState *spi_panel;
    M5EpdPanelState *epd_panel;
    uint32_t gdma_periph;
    int dc_pin;
    int panel_cs_pin;
    int panel_cs_level;
    M5GpspiSlave slaves[M5_GPSPI_MAX_SLAVES];
    int slave_count;
    int active_slave;
    int last_slave;
    uint8_t rx[4096];
    uint32_t rx_len;
    /* DMA cursor */
    bool dma_reload;
    int debug_id;
    uint32_t desc_addr;
    uint32_t desc_off;
    uint8_t *buf;
    uint32_t buf_size;
};

static void gpspi_update_irq(Esp32s3GpspiState *s)
{
    int level = !!(s->regs[R_DMA_INT_RAW / 4] &
                   s->regs[R_DMA_INT_ENA / 4]);

    if (getenv("M5SW_GPSPI_TRACE")) {
        fprintf(stderr, "[gpspi-irq] level=%d raw=%08x ena=%08x\n",
                level, s->regs[R_DMA_INT_RAW / 4],
                s->regs[R_DMA_INT_ENA / 4]);
    }
    qemu_set_irq(s->irq, level);
    qemu_set_irq(s->irq_alias, level);
}

static void sink(Esp32s3GpspiState *s, const uint8_t *b, uint32_t n,
                 bool command_phase)
{
    if (s->dc_pin >= 0) {
        command_phase = !esp32_gpio_get_line(s->dc_pin);
    }
    if (getenv("M5SW_SPI_XFER_TRACE") && n) {
        fprintf(stderr, "[spi-xfer] %c len=%u first=%02x\n",
                command_phase ? 'C' : 'D', n, b[0]);
    }
    if (s->panel && n && s->active_slave < 0 &&
        (s->panel_cs_pin < 0 || !s->panel_cs_level)) {
        co5300_write(s->panel, b, n);
    }
    if (s->spi_panel && n && s->active_slave < 0 &&
        (s->panel_cs_pin < 0 || !s->panel_cs_level)) {
        m5_spi_panel_write(s->spi_panel, b, n, command_phase);
    }
    if (s->epd_panel && n && s->active_slave < 0 &&
        (s->panel_cs_pin < 0 || !s->panel_cs_level)) {
        m5_epd_panel_write(s->epd_panel, b, n, command_phase);
    }
}

static void gpspi_forward_slave(Esp32s3GpspiState *s,
                                const uint8_t *tx, uint32_t n,
                                uint8_t *rx, bool capture)
{
    M5GpspiSlave *slave;

    if (getenv("M5SW_SPI_XFER_TRACE")) {
        fprintf(stderr, "[gpspi-forward] active=%d n=%u capture=%d\n",
                s->active_slave, n, capture);
    }
    if (s->active_slave < 0) {
        return;
    }
    slave = &s->slaves[s->active_slave];
    if (!slave->ops || slave->cs_level != 0) {
        return;
    }
    for (uint32_t i = 0; i < n; i++) {
        uint8_t value = slave->ops->transfer(slave->opaque, tx[i]);
        if (capture) {
            rx[i] = value;
        }
    }
}

static uint32_t gpspi_active_dma_periph(Esp32s3GpspiState *s)
{
    if (s->active_slave >= 0 &&
        s->slaves[s->active_slave].gdma_periph >= 0) {
        return s->slaves[s->active_slave].gdma_periph;
    }
    return s->gdma_periph;
}

static void gpspi_cs_line(void *opaque, int pin, int level)
{
    Esp32s3GpspiState *s = opaque;
    M5GpspiSlave *slave = NULL;
    int index;

    for (index = 0; index < s->slave_count; index++) {
        if (s->slaves[index].cs_pin == pin) {
            slave = &s->slaves[index];
            break;
        }
    }
    if (!slave) {
        if (pin == s->panel_cs_pin) {
            s->panel_cs_level = level;
            if (!level) {
                s->active_slave = -1;
            }
        }
        return;
    }
    if (getenv("M5SW_SPI_XFER_TRACE")) {
        fprintf(stderr, "[gpspi-cs] pin=%d level=%d index=%d slave=%p\n",
                pin, level, index, slave->opaque);
    }
    if (level == slave->cs_level) {
        return;
    }
    slave->cs_level = level;
    s->active_slave = level ? -1 : index;
    if (slave->ops && slave->ops->set_cs) {
        slave->ops->set_cs(slave->opaque, level);
    }
}

/* Pull n bytes from the GDMA out-link chain bound to SPI2 */
static uint32_t gpspi_dma_pull(Esp32s3GpspiState *s, uint8_t *dst, uint32_t n)
{
    uint32_t got = 0;
    const uint32_t periph = gpspi_active_dma_periph(s);
    if (!s->gdma) {
        return 0;
    }
    if (s->dma_reload) {
        uint32_t ch;
        if (!esp_gdma_get_channel_periph(s->gdma, periph,
                                         ESP_GDMA_OUT_IDX, &ch)) {
            qemu_log_mask(LOG_GUEST_ERROR, "gpspi: no GDMA out channel\n");
            return 0;
        }
        uint32_t link = esp_gdma_read_chan_register(s->gdma, ESP_GDMA_OUT_IDX, ch, GDMA_LINK_REG);
        s->desc_addr = ((ESP_GDMA_RAM_ADDR >> 20) << 20) | (link & 0xFFFFF);
        s->desc_off = 0;
        s->dma_reload = false;
    }
    while (got < n && s->desc_addr) {
        uint32_t d[3];
        if (address_space_read(&address_space_memory, s->desc_addr, MEMTXATTRS_UNSPECIFIED,
                               d, sizeof(d)) != MEMTX_OK) {
            break;
        }
        uint32_t len = (d[0] >> 12) & 0xfff;
        bool eof = (d[0] >> 30) & 1;
        uint32_t avail = len > s->desc_off ? len - s->desc_off : 0;
        uint32_t take = MIN(avail, n - got);
        if (take) {
            address_space_read(&address_space_memory, d[1] + s->desc_off,
                               MEMTXATTRS_UNSPECIFIED, dst + got, take);
            got += take;
            s->desc_off += take;
        }
        if (s->desc_off >= len) {
            s->desc_off = 0;
            s->desc_addr = eof ? 0 : d[2];
        }
    }
    return got;
}

static void gpspi_exec(Esp32s3GpspiState *s)
{
    uint32_t user = s->regs[R_USER / 4];
    uint8_t tmp[8];
    uint8_t xfer[4096];
    uint32_t xfer_len = 0;
    if (s->active_slave < 0) {
        s->last_slave = -1;
    }
    memset(xfer, 0xff, sizeof(xfer));
    if (user & USER_COMMAND) {
        uint32_t bits = ((s->regs[R_USER2 / 4] >> 28) & 0xf) + 1;
        uint32_t v = s->regs[R_USER2 / 4] & 0xffff;
        uint32_t nb = (bits + 7) / 8;
        for (uint32_t i = 0; i < nb; i++) {
            tmp[i] = v >> (8 * i);
        }
        sink(s, tmp, nb, true);
        gpspi_forward_slave(s, tmp, nb, NULL, false);
    }
    if (user & USER_ADDR) {
        uint32_t bits = ((s->regs[R_USER1 / 4] >> 27) & 0x1f) + 1;
        uint32_t v = s->regs[R_ADDR / 4];
        uint32_t nb = (bits + 7) / 8;
        for (uint32_t i = 0; i < nb; i++) {
            tmp[i] = v >> (8 * (nb - 1 - i));
        }
        sink(s, tmp, nb, false);
        gpspi_forward_slave(s, tmp, nb, NULL, false);
    }
    if (user & USER_MOSI) {
        uint32_t bits = (s->regs[R_MS_DLEN / 4] & 0x3ffff) + 1;
        uint32_t nb = (bits + 7) / 8;
        if (s->regs[R_DMA_CONF / 4] & DMA_TX_ENA) {
            /* Each user transaction starts from the DMA link head again. */
            s->dma_reload = true;
            if (nb > s->buf_size) {
                s->buf = g_realloc(s->buf, nb);
                s->buf_size = nb;
            }
            uint32_t got = gpspi_dma_pull(s, s->buf, nb);
            xfer_len = MIN(got, sizeof(xfer));
            memcpy(xfer, s->buf, xfer_len);
            sink(s, s->buf, got, false);
        } else {
            for (int i = 0; i < 16; i++) {
                uint32_t v = s->regs[R_W0 / 4 + i];
                xfer[i * 4 + 0] = v; xfer[i * 4 + 1] = v >> 8;
                xfer[i * 4 + 2] = v >> 16; xfer[i * 4 + 3] = v >> 24;
            }
            xfer_len = MIN(nb, sizeof(xfer));
            sink(s, xfer, xfer_len, false);
        }
    }
    if (user & USER_MISO) {
        uint32_t bits = (s->regs[R_MS_DLEN / 4] & 0x3ffff) + 1;
        uint32_t nb = (bits + 7) / 8;
        uint32_t copy = MIN(nb, sizeof(xfer));

        memset(s->rx, 0, sizeof(s->rx));
        if (s->active_slave >= 0) {
            s->last_slave = s->active_slave;
            gpspi_forward_slave(s, xfer, copy, s->rx, true);
            s->rx_len = copy;
            bool rx_dma = s->regs[R_DMA_CONF / 4] & DMA_RX_ENA;
            if (getenv("M5SW_SPI_XFER_TRACE")) {
                fprintf(stderr, "[spi-dma] conf=%08x gdma=%p rx_dma=%d\n",
                        s->regs[R_DMA_CONF / 4], (void *)s->gdma, rx_dma);
            }
            if (s->gdma && rx_dma) {
                uint32_t ch;
                const uint32_t periph = gpspi_active_dma_periph(s);
                if (esp_gdma_get_channel_periph(s->gdma, periph,
                                                ESP_GDMA_IN_IDX, &ch)) {
                    bool ok = esp_gdma_write_channel(s->gdma, ch,
                                                     s->rx, copy);
                    if (getenv("M5SW_SPI_XFER_TRACE")) {
                        fprintf(stderr,
                                "[spi-dma-rx] ch=%u len=%u ok=%d\n",
                                ch, copy, ok);
                    }
                } else {
                    if (getenv("M5SW_SPI_XFER_TRACE")) {
                        fprintf(stderr, "[spi-dma-rx] no in channel\n");
                    }
                    qemu_log_mask(LOG_GUEST_ERROR,
                                  "gpspi: no GDMA in channel\n");
                }
            }
            if (getenv("M5SW_SPI_XFER_TRACE") && copy) {
                fprintf(stderr,
                        "[spi-rx] len=%u first=%02x last=%02x"
                        " tx0=%02x tx1=%02x tx2=%02x tx3=%02x\n",
                        copy, s->rx[0], s->rx[copy - 1],
                        xfer[0], xfer[1], xfer[2], xfer[3]);
            }
        }
    } else if (user & USER_MOSI) {
        gpspi_forward_slave(s, xfer, xfer_len, NULL, false);
    }
    s->regs[R_DMA_INT_RAW / 4] |= INT_TRANS_DONE;
    gpspi_update_irq(s);
}

static uint64_t gpspi_read_reg(Esp32s3GpspiState *s, hwaddr addr)
{
    if (getenv("M5SW_SPI_XFER_TRACE") && s->last_slave >= 0) {
        fprintf(stderr, "[gpspi-mmio] rd %03x\n", (unsigned)addr);
    }
    if (getenv("M5SW_GPSPI_POLL_TRACE") &&
        (addr == R_CMD || addr == R_DMA_INT_RAW || addr == R_DMA_INT_ST)) {
        fprintf(stderr, "[gpspi-poll] id=%d rd %03x\n",
                s->debug_id, (unsigned)addr);
    }
    switch (addr) {
    case R_CMD:
        return s->regs[0] & ~CMD_USR;
    case R_DMA_INT_ST:
        return s->regs[R_DMA_INT_RAW / 4] & s->regs[R_DMA_INT_ENA / 4];
    case R_DATE:
        return 0x2101190;
    default:
        if (s->last_slave >= 0 && addr >= R_W0 && addr < R_W0 + 0x40
            && s->rx_len) {
            uint32_t offset = addr - R_W0;
            uint32_t value = 0;
            for (uint32_t i = 0; i < 4 && offset + i < s->rx_len; i++) {
                value |= (uint32_t)s->rx[offset + i] << (8 * i);
            }
            if (getenv("M5SW_SPI_XFER_TRACE")) {
                fprintf(stderr, "[spi-rx] read W0+%02x=%08x\n",
                        offset, value);
            }
            return value;
        }
        /*
         * A direct SPI panel must only answer while its CS pin is asserted.
         * Returning the panel ID for every W0..W15 read makes unrelated
         * M5GFX autodetect probes observe the same ST7789 ID and select the
         * wrong board (for example Cardputer becomes DinMeter).
         */
        if (s->spi_panel
            && (s->panel_cs_pin < 0 || !s->panel_cs_level)
            && addr >= R_W0 && addr < R_W0 + 0x40) {
            return m5_spi_panel_read_id(s->spi_panel);
        }
        return addr < 0x100 ? s->regs[addr / 4] : 0;
    }
}

static uint64_t gpspi_read(void *opaque, hwaddr addr, unsigned size)
{
    Esp32s3GpspiState *s = opaque;
    uint64_t value = gpspi_read_reg(s, addr & ~3ULL);
    unsigned shift = (addr & 3) * 8;
    unsigned bits = size * 8;

    value >>= shift;
    if (bits < 64) {
        value &= MAKE_64BIT_MASK(0, bits);
    }
    return value;
}

static void gpspi_write_reg(Esp32s3GpspiState *s, hwaddr addr, uint64_t val)
{
    if (getenv("M5SW_GPSPI_TRACE") &&
        (addr == R_CMD || addr == R_USER || addr == R_USER1 ||
         addr == R_USER2 || addr == R_MS_DLEN || addr == R_DMA_CONF ||
         addr == R_DMA_INT_ENA || addr == R_DMA_INT_CLR ||
         addr == R_DMA_INT_RAW || addr == R_DMA_INT_SET)) {
        fprintf(stderr, "[gpspi-trace] write %03x=%08x\n",
                (unsigned)addr, (unsigned)val);
    }
    if (getenv("M5SW_SPI_XFER_TRACE") && s->slave_count
        && (s->active_slave >= 0 || addr == R_CMD || addr == R_DMA_CONF
            || addr == R_MS_DLEN || addr == R_USER
            || addr == R_USER1 || addr == R_USER2)) {
        fprintf(stderr, "[gpspi-mmio] wr %03x <- %08x\n",
                (unsigned)addr, (unsigned)val);
    }
    switch (addr) {
    case R_CMD:
        s->regs[0] = val & ~(CMD_USR | (1u << 23));
        if (val & CMD_USR) {
            gpspi_exec(s);
        }
        break;
    case R_DMA_CONF:
        if ((val & DMA_TX_ENA) && !(s->regs[R_DMA_CONF / 4] & DMA_TX_ENA)) {
            s->dma_reload = true;
        }
        s->regs[addr / 4] = val;
        break;
    case R_DMA_INT_CLR:
        s->regs[R_DMA_INT_RAW / 4] &= ~val;
        gpspi_update_irq(s);
        break;
    case R_DMA_INT_SET:
        s->regs[R_DMA_INT_RAW / 4] |= val;
        gpspi_update_irq(s);
        break;
    case R_DMA_INT_ENA:
        s->regs[addr / 4] = val;
        gpspi_update_irq(s);
        break;
    default:
        if (getenv("M5SW_SPI_XFER_TRACE") && s->slave_count &&
            addr >= R_W0 && addr < R_W0 + 0x40 && val != 0xffffffff) {
            fprintf(stderr, "[spi-tx] W0+%02x <- %08x\n",
                    (unsigned)(addr - R_W0), (unsigned)val);
        }
        if (addr < 0x100) {
            s->regs[addr / 4] = val;
        }
        break;
    }
}

static void gpspi_write(void *opaque, hwaddr addr, uint64_t val, unsigned size)
{
    Esp32s3GpspiState *s = opaque;
    hwaddr aligned = addr & ~3ULL;
    unsigned shift = (addr & 3) * 8;
    unsigned bits = size * 8;

    if (size != 4 || aligned != addr) {
        uint64_t merged = gpspi_read_reg(s, aligned);
        uint64_t mask = MAKE_64BIT_MASK(shift, bits);

        merged = (merged & ~mask) | ((val << shift) & mask);
        val = merged;
        addr = aligned;
    }
    gpspi_write_reg(s, addr, val);
}

static const MemoryRegionOps gpspi_ops = {
    .read = gpspi_read,
    .write = gpspi_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
    .impl.min_access_size = 1,
    .impl.max_access_size = 4,
};

static void gpspi_init(Object *obj)
{
    Esp32s3GpspiState *s = ESP32S3_GPSPI(obj);
    static int next_debug_id;
    memory_region_init_io(&s->iomem, obj, &gpspi_ops, s, TYPE_ESP32S3_GPSPI, 0x1000);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->iomem);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq_alias);
    s->active_slave = -1;
    s->last_slave = -1;
    s->panel_cs_pin = -1;
    s->panel_cs_level = 1;
    s->debug_id = next_debug_id++;
}

static const TypeInfo gpspi_info = {
    .name = TYPE_ESP32S3_GPSPI,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32s3GpspiState),
    .instance_init = gpspi_init,
};

static void gpspi_register(void)
{
    type_register_static(&gpspi_info);
}
type_init(gpspi_register)

void esp32s3_gpspi_attach(DeviceState *dev, ESPGdmaState *gdma,
                          Co5300State *co, M5SpiPanelState *spi,
                          uint32_t gdma_periph)
{
    Esp32s3GpspiState *s = ESP32S3_GPSPI(dev);
    s->gdma = gdma;
    s->panel = co;
    s->spi_panel = spi;
    s->epd_panel = NULL;
    s->gdma_periph = gdma_periph;
    s->dc_pin = -1;
}

void esp32s3_gpspi_attach_epd(DeviceState *dev, ESPGdmaState *gdma,
                              M5EpdPanelState *panel, uint32_t gdma_periph)
{
    Esp32s3GpspiState *s = ESP32S3_GPSPI(dev);
    s->gdma = gdma;
    s->panel = NULL;
    s->spi_panel = NULL;
    s->epd_panel = panel;
    s->gdma_periph = gdma_periph;
    s->dc_pin = -1;
}

void esp32s3_gpspi_set_dc_pin(DeviceState *dev, int pin)
{
    ESP32S3_GPSPI(dev)->dc_pin = pin;
}

void esp32s3_gpspi_set_panel_cs_pin(DeviceState *dev, int pin)
{
    Esp32s3GpspiState *s = ESP32S3_GPSPI(dev);

    s->panel_cs_pin = pin;
    s->panel_cs_level = 1;
    if (pin >= 0) {
        esp32_gpio_add_out_listener(pin, gpspi_cs_line, s);
    }
}

void esp32s3_gpspi_attach_spi_slave(DeviceState *dev,
                                    const M5SpiSlaveOps *ops,
                                    void *opaque, int cs_pin)
{
    Esp32s3GpspiState *s = ESP32S3_GPSPI(dev);
    int index = s->slave_count++;

    assert(index < M5_GPSPI_MAX_SLAVES);
    s->slaves[index].ops = ops;
    s->slaves[index].opaque = opaque;
    s->slaves[index].cs_pin = cs_pin;
    s->slaves[index].cs_level = 1;
    s->slaves[index].gdma_periph = -1;
    esp32_gpio_set_input(cs_pin, 1);
    esp32_gpio_add_out_listener(cs_pin, gpspi_cs_line, s);
}

void esp32s3_gpspi_set_spi_slave_dma(DeviceState *dev, int cs_pin,
                                     uint32_t gdma_periph)
{
    Esp32s3GpspiState *s = ESP32S3_GPSPI(dev);

    for (int index = 0; index < s->slave_count; index++) {
        if (s->slaves[index].cs_pin == cs_pin) {
            s->slaves[index].gdma_periph = gdma_periph;
            return;
        }
    }
    assert(0 && "GP-SPI slave CS is not attached");
}

/* ---- board glue ---- */
#include "hw/xtensa/esp32s3_intc.h"
#include "hw/qdev-properties.h"

void esp32s3_gpspi_connect_irqs(DeviceState *dev, DeviceState *intmatrix,
                                int irq_a, int irq_b)
{
    sysbus_connect_irq(SYS_BUS_DEVICE(dev), 0,
                       qdev_get_gpio_in(intmatrix, irq_a));
    sysbus_connect_irq(SYS_BUS_DEVICE(dev), 1,
                       qdev_get_gpio_in(intmatrix, irq_b));
}

void m5stopwatch_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                            ESPGdmaState *gdma)
{
    m5stopwatch_sens_init(sys_mem);
    m5stopwatch_regi2c_init(sys_mem);
    m5stopwatch_fe_init(sys_mem);
    m5stopwatch_phy_init(sys_mem);

    /* I2C0 @ 0x60013000 with the board's sensors/PMIC/expander */
    DeviceState *i2c0 = qdev_new(TYPE_ESP32S3_I2C);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(i2c0), &error_fatal);
    MemoryRegion *i2c0_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(i2c0), 0);
    memory_region_add_subregion_overlap(sys_mem, 0x60013000,
        i2c0_mr, 1);

    /*
     * I2C1 @ 0x60027000. M5Unified uses port 1 for the on-board bus,
     * while other firmwares (including the factory UserDemo) use port 0.
     * Give each port its own register file and interrupt source, but let
     * both controllers address the same device bus.
     */
    DeviceState *i2c1 = qdev_new(TYPE_ESP32S3_I2C);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(i2c1), &error_fatal);
    MemoryRegion *i2c1_mr = sysbus_mmio_get_region(SYS_BUS_DEVICE(i2c1), 0);
    memory_region_add_subregion_overlap(sys_mem, 0x60027000,
        i2c1_mr, 1);
    sysbus_connect_irq(SYS_BUS_DEVICE(i2c0), 0,
                       qdev_get_gpio_in(intmatrix, ETS_I2C_EXT0_INTR_SOURCE));
    sysbus_connect_irq(SYS_BUS_DEVICE(i2c1), 0,
                       qdev_get_gpio_in(intmatrix, ETS_I2C_EXT1_INTR_SOURCE));
    I2CBus *bus = (I2CBus *)qdev_get_child_bus(i2c0, "i2c");
    esp32s3_i2c_set_bus(i2c1, bus);
    static const struct { const char *model; uint8_t addr; } devs[] = {
        { "m5pm1", 0x6E }, { "m5ioe1", 0x4F }, { "cst820", 0x15 },
        { "bmi270", 0x68 }, { "rx8130", 0x32 }, { "es8311", 0x18 },
    };
    for (int i = 0; i < ARRAY_SIZE(devs); i++) {
        DeviceState *d = qdev_new(TYPE_M5SW_I2C_DEV);
        qdev_prop_set_string(d, "model", devs[i].model);
        qdev_prop_set_uint8(d, "address", devs[i].addr);
        /* stable QOM paths for QMP: /machine/m5pm1, /machine/bmi270, ... */
        object_property_add_child(qdev_get_machine(), devs[i].model, OBJECT(d));
        qdev_realize_and_unref(d, (BusState *)bus, &error_fatal);
    }
    m5stopwatch_soft_i2c_init(bus);

    /* GP-SPI2 @ 0x60024000 driving the CO5300 AMOLED */
    DeviceState *spi = qdev_new(TYPE_ESP32S3_GPSPI);
    Esp32s3GpspiState *ss = ESP32S3_GPSPI(spi);
    ss->gdma = gdma;
    sysbus_realize_and_unref(SYS_BUS_DEVICE(spi), &error_fatal);
    memory_region_add_subregion_overlap(sys_mem, 0x60024000,
        sysbus_mmio_get_region(SYS_BUS_DEVICE(spi), 0), 1);
    sysbus_connect_irq(SYS_BUS_DEVICE(spi), 0,
                       qdev_get_gpio_in(intmatrix, ETS_SPI2_INTR_SOURCE));
    DeviceState *panel = qdev_new(TYPE_CO5300);
    qdev_realize_and_unref(panel, NULL, &error_fatal);
    ss->panel = CO5300(panel);
}

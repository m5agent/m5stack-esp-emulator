/*
 * ESP32-S3 I2C master controller (subset sufficient for ESP-IDF i2c_master driver)
 * Part of the M5Stack StopWatch board support.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/fifo8.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "hw/i2c/i2c.h"
#include "m5stopwatch.h"

#define I2C_FIFO_LEN 32

#define R_CTR        0x04
#define R_SR         0x08
#define R_FIFO_ST    0x14
#define R_FIFO_CONF  0x18
#define R_DATA       0x1c
#define R_INT_RAW    0x20
#define R_INT_CLR    0x24
#define R_INT_ENA    0x28
#define R_INT_ST     0x2c
#define R_COMD0      0x58
#define R_DATE       0xf8
#define R_TXFIFO_MEM 0x100
#define R_RXFIFO_MEM 0x180

#define CTR_TRANS_START (1u << 5)
#define CTR_FSM_RST     (1u << 10)
#define CTR_CONF_UPGATE (1u << 11)
#define FIFO_CONF_RX_RST (1u << 12)
#define FIFO_CONF_TX_RST (1u << 13)

#define INT_RXFIFO_WM     (1u << 0)
#define INT_TXFIFO_WM     (1u << 1)
#define INT_END_DETECT    (1u << 3)
#define INT_BYTE_DONE     (1u << 4)
#define INT_TRANS_COMPLETE (1u << 7)
#define INT_TRANS_START   (1u << 9)
#define INT_NACK          (1u << 10)

#define OP_WRITE   1
#define OP_STOP    2
#define OP_READ    3
#define OP_END     4
#define OP_RSTART  6

struct Esp32s3I2CState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    qemu_irq irq;
    I2CBus *bus;
    I2CBus *board_bus;
    unsigned controller_index;
    uint32_t regs[0x40];      /* plain storage for unspecified regs (0x00..0xff) */
    uint32_t cmd[8];
    uint32_t int_raw, int_ena;
    uint8_t txfifo[I2C_FIFO_LEN];
    uint32_t tx_rd, tx_wr;     /* tx fifo is linear: refilled after each start */
    uint8_t rxfifo[I2C_FIFO_LEN];
    uint32_t rx_rd, rx_wr;
    bool need_addr;           /* next written byte is an address byte */
    bool in_xfer;             /* i2c_start_transfer succeeded and not ended */
    bool nacked;
};

static void s3i2c_update_irq(Esp32s3I2CState *s)
{
    qemu_set_irq(s->irq, !!(s->int_raw & s->int_ena));
}

static uint32_t rx_cnt(Esp32s3I2CState *s) { return s->rx_wr - s->rx_rd; }
static uint32_t tx_cnt(Esp32s3I2CState *s) { return s->tx_wr - s->tx_rd; }

static void s3i2c_end_xfer(Esp32s3I2CState *s)
{
    if (s->in_xfer) {
        i2c_end_transfer(s->bus);
        s->in_xfer = false;
    }
    s->need_addr = true;
}

static void s3i2c_run(Esp32s3I2CState *s)
{
    if (!s->in_xfer) {
        s->bus = m5_unit_i2c_route(s->board_bus, s->controller_index, true);
    }
    m5stopwatch_soft_i2c_set_hardware_active_on_bus(s->bus);
    for (int i = 0; i < 8; i++) {
        uint32_t c = s->cmd[i];
        int op = (c >> 11) & 7;
        int n = c & 0xff;
        bool ack_check = (c >> 8) & 1;
        switch (op) {
        case OP_RSTART:
            if (s->in_xfer) {
                /*
                 * QEMU has no distinct repeated-start callback.  A FINISH
                 * followed by a fresh START keeps the slave register pointer
                 * intact while clearing any stale bus ownership from a
                 * preceding NACK/read transaction.
                 */
                i2c_end_transfer(s->bus);
                s->in_xfer = false;
            }
            s->need_addr = true;
            s->nacked = false;
            break;
        case OP_WRITE:
            for (int k = 0; k < n; k++) {
                uint8_t b = 0xff;
                if (tx_cnt(s)) {
                    b = s->txfifo[s->tx_rd++ % I2C_FIFO_LEN];
                }
                if (getenv("M5SW_I2C_CTRL_TRACE")) {
                    fprintf(stderr, "[i2c-ctrl] write[%d/%d]=%02x need_addr=%d tx=%u/%u\n",
                            k, n, b, s->need_addr, s->tx_rd, s->tx_wr);
                }
                if (s->need_addr) {
                    s->need_addr = false;
                    bool recv = b & 1;
                    if (getenv("M5SW_I2C_CTRL_TRACE")) {
                        fprintf(stderr, "[i2c-ctrl] addr-byte=%02x recv=%d\n",
                                b, recv);
                    }
                    if (i2c_start_transfer(s->bus, b >> 1, recv) != 0) {
                        s->in_xfer = false;
                        s->nacked = true;
                    } else {
                        s->in_xfer = true;
                    }
                } else if (s->in_xfer) {
                    if (i2c_send(s->bus, b) != 0) {
                        s->nacked = true;
                    }
                }
                if (s->nacked && ack_check) {
                    s->cmd[i] |= 1u << 31;
                    s->int_raw |= INT_NACK;
                    s3i2c_end_xfer(s);
                    s->tx_rd = s->tx_wr = 0;
                    /*
                     * Keep processing the remaining command words.  ESP-IDF
                     * programs a trailing END/STOP after a checked write; on
                     * a missing device the controller still completes that
                     * command list instead of stranding it after NACK.
                     */
                    break;
                }
            }
            break;
        case OP_READ:
            for (int k = 0; k < n; k++) {
                uint8_t b = s->in_xfer ? i2c_recv(s->bus) : 0xff;
                if (rx_cnt(s) < I2C_FIFO_LEN) {
                    s->rxfifo[s->rx_wr++ % I2C_FIFO_LEN] = b;
                }
            }
            break;
        case OP_STOP:
            s->cmd[i] |= 1u << 31;
            s3i2c_end_xfer(s);
            s->int_raw |= INT_TRANS_COMPLETE;
            s->tx_rd = s->tx_wr = 0;
            return;
        case OP_END:
            s->cmd[i] |= 1u << 31;
            s->int_raw |= INT_END_DETECT;
            /* hardware continues to own the bus; tx fifo is refilled by sw */
            s->tx_rd = s->tx_wr = 0;
            return;
        default:
            break;
        }
        s->cmd[i] |= 1u << 31;
    }
}

static uint64_t s3i2c_read(void *opaque, hwaddr addr, unsigned size)
{
    Esp32s3I2CState *s = opaque;
    if (getenv("M5SW_I2C_CTRL_TRACE")) {
        char *path = object_get_canonical_path(OBJECT(s));
        fprintf(stderr, "[i2c-ctrl] %s rd %03" HWADDR_PRIx " size=%u\n",
                path, addr, size);
        g_free(path);
    }
    switch (addr) {
    case R_SR:
        return ((rx_cnt(s) & 0x3f) << 8) | ((tx_cnt(s) & 0x3f) << 18);
    case R_DATA:
        if (rx_cnt(s)) {
            return s->rxfifo[s->rx_rd++ % I2C_FIFO_LEN];
        }
        return 0;
    case R_INT_RAW:
        return s->int_raw;
    case R_INT_ENA:
        return s->int_ena;
    case R_INT_ST:
        return s->int_raw & s->int_ena;
    case R_COMD0 ... R_COMD0 + 0x1c:
        return s->cmd[(addr - R_COMD0) / 4];
    case R_DATE:
        return 0x20070201;
    case R_TXFIFO_MEM ... R_TXFIFO_MEM + 0x7f:
        /*
         * The FIFO RAM is byte-addressed even though ESP-IDF normally accesses
         * it with 32-bit loads/stores.  Return a little-endian word so a driver
         * can move up to four queued bytes per access.
         */
        {
            hwaddr off = addr - R_TXFIFO_MEM;
            uint32_t value = 0;
            for (unsigned i = 0; i < 4 && off + i < I2C_FIFO_LEN; i++) {
                value |= (uint32_t)s->txfifo[off + i] << (i * 8);
            }
            return value;
        }
    case R_RXFIFO_MEM ... R_RXFIFO_MEM + 0x7f:
        {
            hwaddr off = addr - R_RXFIFO_MEM;
            uint32_t value = 0;
            for (unsigned i = 0; i < 4 && off + i < s->rx_wr; i++) {
                value |= (uint32_t)s->rxfifo[off + i] << (i * 8);
            }
            return value;
        }
    default:
        if (addr < 0x100) {
            return s->regs[addr / 4];
        }
        return 0;
    }
}

static void s3i2c_write(void *opaque, hwaddr addr, uint64_t val, unsigned size)
{
    Esp32s3I2CState *s = opaque;
    if (getenv("M5SW_I2C_CTRL_TRACE")) {
        char *path = object_get_canonical_path(OBJECT(s));
        fprintf(stderr,
                "[i2c-ctrl] %s wr %03" HWADDR_PRIx
                "=%08" PRIx64 " size=%u\n",
                path, addr, val, size);
        g_free(path);
    }
    switch (addr) {
    case R_CTR:
        if (val & CTR_FSM_RST) {
            s3i2c_end_xfer(s);
        }
        s->regs[addr / 4] = val & ~(CTR_TRANS_START | CTR_CONF_UPGATE | CTR_FSM_RST);
        if (val & CTR_TRANS_START) {
            if (getenv("M5SW_I2C_CTRL_TRACE")) {
                char *path = object_get_canonical_path(OBJECT(s));
                fprintf(stderr,
                        "[i2c-ctrl] %s start cmd=%08x,%08x,%08x,%08x\n",
                        path, s->cmd[0], s->cmd[1], s->cmd[2], s->cmd[3]);
                g_free(path);
            }
            s3i2c_run(s);
            s3i2c_update_irq(s);
        }
        break;
    case R_FIFO_CONF:
        if (val & FIFO_CONF_RX_RST) {
            s->rx_rd = s->rx_wr = 0;
        }
        if (val & FIFO_CONF_TX_RST) {
            s->tx_rd = s->tx_wr = 0;
        }
        s->regs[addr / 4] = val;
        break;
    case R_DATA:
        if (tx_cnt(s) < I2C_FIFO_LEN) {
            s->txfifo[s->tx_wr++ % I2C_FIFO_LEN] = val & 0xff;
        }
        break;
    case R_INT_CLR:
        s->int_raw &= ~val;
        s3i2c_update_irq(s);
        break;
    case R_INT_ENA:
        s->int_ena = val;
        s3i2c_update_irq(s);
        break;
    case R_COMD0 ... R_COMD0 + 0x1c:
        s->cmd[(addr - R_COMD0) / 4] = val;
        break;
    case R_TXFIFO_MEM ... R_TXFIFO_MEM + 0x7f: {
        hwaddr off = addr - R_TXFIFO_MEM;
        if (getenv("M5SW_I2C_CTRL_TRACE")) {
            fprintf(stderr, "[i2c-ctrl] txfifo[%03lx]=%08lx\n",
                    (unsigned long)off, (unsigned long)val);
        }
        for (unsigned i = 0; i < 4 && off + i < I2C_FIFO_LEN; i++) {
            s->txfifo[off + i] = (val >> (i * 8)) & 0xff;
            if (off + i + 1 > s->tx_wr) {
                s->tx_wr = off + i + 1;
            }
        }
        break;
    }
    default:
        if (addr < 0x100) {
            s->regs[addr / 4] = val;
        }
        break;
    }
}

static const MemoryRegionOps s3i2c_ops = {
    .read = s3i2c_read,
    .write = s3i2c_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

static void s3i2c_reset(DeviceState *dev)
{
    Esp32s3I2CState *s = ESP32S3_I2C(dev);
    memset(s->regs, 0, sizeof(s->regs));
    memset(s->cmd, 0, sizeof(s->cmd));
    s->int_raw = s->int_ena = 0;
    s->tx_rd = s->tx_wr = s->rx_rd = s->rx_wr = 0;
    s->need_addr = true;
    s->in_xfer = false;
}

static void s3i2c_init(Object *obj)
{
    Esp32s3I2CState *s = ESP32S3_I2C(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    memory_region_init_io(&s->iomem, obj, &s3i2c_ops, s, TYPE_ESP32S3_I2C, 0x200);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    static unsigned next_controller;
    s->bus = i2c_init_bus(DEVICE(obj), "i2c");
    s->board_bus = s->bus;
    s->controller_index = next_controller++;
}

void esp32s3_i2c_set_bus(DeviceState *dev, I2CBus *bus)
{
    ESP32S3_I2C(dev)->bus = bus;
    ESP32S3_I2C(dev)->board_bus = bus;
}

static void s3i2c_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    device_class_set_legacy_reset(dc, s3i2c_reset);
}

static const TypeInfo s3i2c_info = {
    .name = TYPE_ESP32S3_I2C,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Esp32s3I2CState),
    .instance_init = s3i2c_init,
    .class_init = s3i2c_class_init,
};

static void s3i2c_register(void)
{
    type_register_static(&s3i2c_info);
}
type_init(s3i2c_register)

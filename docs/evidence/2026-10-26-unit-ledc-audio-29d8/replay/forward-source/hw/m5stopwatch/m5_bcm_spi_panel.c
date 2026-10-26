/*
 * M5Stack BCM2835 SPI panel sink.
 *
 * Linux panel-mipi-dbi drives the CardputerZero ST7789v3 through BCM SPI0.
 * This SSI peripheral snoops the DCS command/data stream using the panel D/C
 * GPIO and reconstructs the RGB565 framebuffer for deterministic UI capture.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/gpio/bcm2835_gpio.h"
#include "hw/misc/m5_bcm_spi_panel.h"
#include "qemu/module.h"
#include "qemu/timer.h"

#define M5_BCM_PANEL_WIDTH   320
#define M5_BCM_PANEL_HEIGHT  170
#define M5_BCM_PANEL_DC_PIN  25

struct M5BcmSpiPanelState {
    SSIPeripheral parent_obj;

    uint16_t *mem;
    QEMUTimer *dump_timer;
    char *dump_path;
    uint8_t cmd;
    uint8_t params[4];
    unsigned pidx;
    uint16_t xs, xe, ys, ye, cx, cy;
    uint8_t pix_hi;
    bool pix_half;
    bool dirty;
    uint32_t pixel_count;
};

static uint32_t m5_bcm_panel_pixel_rgb(M5BcmSpiPanelState *s, int x, int y)
{
    uint16_t value = s->mem[y * M5_BCM_PANEL_WIDTH + x];
    uint32_t r = ((value >> 11) & 0x1f) * 255 / 31;
    uint32_t g = ((value >> 5) & 0x3f) * 255 / 63;
    uint32_t b = (value & 0x1f) * 255 / 31;

    return (r << 16) | (g << 8) | b;
}

static void m5_bcm_panel_dump(M5BcmSpiPanelState *s)
{
    FILE *file;

    if (!s->dump_path || !s->dirty) {
        return;
    }
    file = fopen(s->dump_path, "wb");
    if (!file) {
        return;
    }
    fprintf(file, "P6\n%d %d\n255\n",
            M5_BCM_PANEL_WIDTH, M5_BCM_PANEL_HEIGHT);
    for (int y = 0; y < M5_BCM_PANEL_HEIGHT; y++) {
        for (int x = 0; x < M5_BCM_PANEL_WIDTH; x++) {
            uint32_t rgb = m5_bcm_panel_pixel_rgb(s, x, y);
            uint8_t bytes[3] = { rgb >> 16, rgb >> 8, rgb };
            fwrite(bytes, sizeof(bytes), 1, file);
        }
    }
    fclose(file);
    s->dirty = false;
}

static void m5_bcm_panel_dump_tick(void *opaque)
{
    M5BcmSpiPanelState *s = opaque;

    m5_bcm_panel_dump(s);
    timer_mod(s->dump_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 250000000);
}

static void m5_bcm_panel_put_pixel(M5BcmSpiPanelState *s, uint16_t value)
{
    int x = s->cx;
    int y = s->cy;

    if (x >= 0 && x < M5_BCM_PANEL_WIDTH &&
        y >= 0 && y < M5_BCM_PANEL_HEIGHT) {
        s->mem[y * M5_BCM_PANEL_WIDTH + x] = value;
        s->pixel_count++;
        s->dirty = true;
    }
    if (++s->cx > s->xe) {
        s->cx = s->xs;
        if (++s->cy > s->ye) {
            s->cy = s->ys;
        }
    }
}

static uint32_t m5_bcm_panel_transfer(SSIPeripheral *dev, uint32_t value)
{
    M5BcmSpiPanelState *s = M5_BCM_SPI_PANEL(dev);
    uint8_t byte = value;
    bool dc = bcm2835_gpio_get_level(M5_BCM_PANEL_DC_PIN);

    if (!dc) {
        if (getenv("M5SW_BCM_SPI_PANEL_TRACE")) {
            fprintf(stderr, "[bcm-panel] cmd=%02x\n", byte);
        }
        s->cmd = byte;
        s->pidx = 0;
        s->pix_half = false;
        return 0;
    }

    switch (s->cmd) {
    case 0x2a:
    case 0x2b:
        if (s->pidx < 4) {
            s->params[s->pidx++] = byte;
        }
        if (s->pidx == 4) {
            uint16_t start = (s->params[0] << 8) | s->params[1];
            uint16_t end = (s->params[2] << 8) | s->params[3];
            if (s->cmd == 0x2a) {
                s->xs = MIN(start, M5_BCM_PANEL_WIDTH - 1);
                s->xe = MIN(end, M5_BCM_PANEL_WIDTH - 1);
                s->cx = s->xs;
            } else {
                s->ys = MIN(start, M5_BCM_PANEL_HEIGHT - 1);
                s->ye = MIN(end, M5_BCM_PANEL_HEIGHT - 1);
                s->cy = s->ys;
            }
        }
        break;
    case 0x2c:
        if (!s->pix_half) {
            s->pix_hi = byte;
            s->pix_half = true;
        } else {
            m5_bcm_panel_put_pixel(s, (s->pix_hi << 8) | byte);
            if (getenv("M5SW_BCM_SPI_PANEL_TRACE") &&
                (s->pixel_count == 1 || !(s->pixel_count % 50000))) {
                fprintf(stderr, "[bcm-panel] pixels=%u cmd=%02x "
                        "window=(%u,%u)-(%u,%u)\n",
                        s->pixel_count, s->cmd, s->xs, s->ys, s->xe, s->ye);
            }
            s->pix_half = false;
        }
        break;
    default:
        break;
    }
    return 0;
}

static void m5_bcm_panel_realize(SSIPeripheral *dev, Error **errp)
{
    M5BcmSpiPanelState *s = M5_BCM_SPI_PANEL(dev);
    const char *dump_path = getenv("M5SW_BCM_SPI_PANEL_DUMP");

    s->mem = g_new0(uint16_t, M5_BCM_PANEL_WIDTH * M5_BCM_PANEL_HEIGHT);
    s->xe = M5_BCM_PANEL_WIDTH - 1;
    s->ye = M5_BCM_PANEL_HEIGHT - 1;
    if (dump_path && *dump_path) {
        s->dump_path = g_strdup(dump_path);
        s->dump_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                     m5_bcm_panel_dump_tick, s);
        timer_mod(s->dump_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 250000000);
    }
}

static void m5_bcm_panel_reset(DeviceState *dev)
{
    M5BcmSpiPanelState *s = M5_BCM_SPI_PANEL(dev);

    memset(s->mem, 0, M5_BCM_PANEL_WIDTH * M5_BCM_PANEL_HEIGHT *
           sizeof(*s->mem));
    s->cmd = 0;
    s->pidx = 0;
    s->xs = 0;
    s->ys = 0;
    s->xe = M5_BCM_PANEL_WIDTH - 1;
    s->ye = M5_BCM_PANEL_HEIGHT - 1;
    s->cx = 0;
    s->cy = 0;
    s->pix_half = false;
    s->dirty = false;
    s->pixel_count = 0;
}

static void m5_bcm_panel_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    SSIPeripheralClass *ssc = SSI_PERIPHERAL_CLASS(klass);

    dc->desc = "M5Stack BCM2835 SPI panel sink";
    device_class_set_legacy_reset(dc, m5_bcm_panel_reset);
    ssc->realize = m5_bcm_panel_realize;
    ssc->transfer = m5_bcm_panel_transfer;
    ssc->cs_polarity = SSI_CS_NONE;
}

static const TypeInfo m5_bcm_panel_info = {
    .name = TYPE_M5_BCM_SPI_PANEL,
    .parent = TYPE_SSI_PERIPHERAL,
    .instance_size = sizeof(M5BcmSpiPanelState),
    .class_init = m5_bcm_panel_class_init,
};

static void m5_bcm_panel_register_types(void)
{
    type_register_static(&m5_bcm_panel_info);
}

type_init(m5_bcm_panel_register_types)

/*
 * Minimal ESP32-S3 LCD_CAM camera front-end.
 *
 * The camera sensor is configured through SCCB by the guest.  This model
 * supplies deterministic RGB565 frames through the real LCD_CAM interrupt
 * and GDMA RX descriptor path used by esp32-camera.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/timer.h"
#include "hw/dma/esp_gdma.h"
#include "hw/irq.h"
#include "hw/sysbus.h"
#include "m5stopwatch.h"

#define R_CAM_CTRL   0x04
#define R_CAM_CTRL1  0x08
#define R_CAM_RGB    0x0c
#define R_INT_ENA    0x64
#define R_INT_RAW    0x68
#define R_INT_ST     0x6c
#define R_INT_CLR    0x70
#define CAM_UPDATE   (1u << 4)
#define CAM_START    (1u << 29)
#define CAM_RESET    (1u << 30)
#define CAM_AFIFO_RST (1u << 31)
#define CAM_VSYNC_INT (1u << 2)

struct M5LcdCamState {
    SysBusDevice parent_obj;
    MemoryRegion iomem;
    qemu_irq irq;
    ESPGdmaState *gdma;
    uint32_t regs[0x100 / 4];
    uint32_t int_ena;
    uint32_t int_raw;
    uint32_t width;
    uint32_t height;
    uint32_t frame_seed;
    bool frame_auto_increment;
    uint32_t frame_offset;
    uint32_t frame_bytes;
    uint32_t chunk_len;
    uint32_t chunks_left;
    uint8_t *frame_data;
    uint32_t frame_data_size;
    bool started;
    bool dma_armed;
    QEMUTimer *capture_timer;
};

static void lcd_cam_update_irq(M5LcdCamState *s)
{
    qemu_set_irq(s->irq, !!(s->int_raw & s->int_ena));
}

static uint16_t camera_pattern_pixel(M5LcdCamState *s, uint32_t pixel)
{
    uint32_t area = MAX(1u, s->width * s->height);
    uint32_t p = pixel % area;
    uint32_t x = p % MAX(1u, s->width);
    uint32_t y = p / MAX(1u, s->width);
    uint8_t r, g, b;

    uint32_t band = (y * 4 / MAX(1u, s->height) + s->frame_seed) & 3;
    if (band == 0) {
        r = 235; g = 48; b = 48;
    } else if (band == 1) {
        r = 235; g = 190; b = 35;
    } else if (band == 2) {
        r = 40; g = 190; b = 80;
    } else {
        r = 35; g = 105; b = 235;
    }
    if ((x % 40) < 2 || (y % 40) < 2) {
        r = g = b = 245;
    }
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
}

static void lcd_cam_fill_frame(M5LcdCamState *s, uint8_t *data, uint32_t len)
{
    uint32_t frame_bytes = MAX(2u, s->width * s->height * 2);
    if (s->frame_data && s->frame_data_size >= frame_bytes) {
        for (uint32_t i = 0; i < len; i++) {
            data[i] = s->frame_data[(s->frame_offset + i) % frame_bytes];
        }
        s->frame_offset = (s->frame_offset + len) % frame_bytes;
        return;
    }
    for (uint32_t i = 0; i < len; i += 2) {
        uint32_t offset = (s->frame_offset + i) % frame_bytes;
        uint16_t pixel = camera_pattern_pixel(s, offset / 2);
        data[i] = pixel & 0xff;
        if (i + 1 < len) {
            data[i + 1] = pixel >> 8;
        }
    }
    s->frame_offset = (s->frame_offset + len) % frame_bytes;
}

static void lcd_cam_capture(M5LcdCamState *s)
{
    uint32_t channel;
    uint32_t len = s->chunk_len;
    g_autofree uint8_t *data = g_malloc0(len);

    if (!(s->int_ena & CAM_VSYNC_INT)) {
        timer_mod(s->capture_timer,
                  qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + 10);
        return;
    }

    lcd_cam_fill_frame(s, data, len);
    if (s->gdma) {
        bool found = esp_gdma_get_channel_periph(
            s->gdma, GDMA_LCDCAM, ESP_GDMA_IN_IDX, &channel);
        if (!found) {
            if (getenv("M5SW_CAMERA_TRACE")) {
                fprintf(stderr, "[lcd-cam] waiting for camera GDMA channel\n");
            }
            /*
             * The esp32-camera driver only programs the IN_LINK after its
             * first VSYNC event.  A real sensor keeps producing VSYNC while
             * the DMA channel is idle, so do the same instead of waiting for
             * a DMA transfer that cannot start yet.
             */
            s->int_raw |= CAM_VSYNC_INT;
            lcd_cam_update_irq(s);
            timer_mod(s->capture_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + 10);
            return;
        }
        s->dma_armed = false;
        if (s->chunks_left) {
            esp_gdma_complete_in_descriptor(s->gdma, channel, data, len);
            esp_gdma_set_chan_interrupt(s->gdma, ESP_GDMA_IN_IDX, channel,
                                        R_GDMA_INTERRUPT_IN_SUC_EOF_MASK);
            s->chunks_left--;
            timer_mod(s->capture_timer,
                      qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + 1);
        } else {
            if (s->frame_auto_increment) {
                s->frame_seed++;
            }
            s->int_raw |= CAM_VSYNC_INT;
            lcd_cam_update_irq(s);
            if (getenv("M5SW_CAMERA_TRACE")) {
                fprintf(stderr, "[lcd-cam] frame complete bytes=%u\n",
                        s->frame_bytes);
            }
        }
    }
}

static void lcd_cam_gdma_started(void *opaque, GdmaPeripheral periph, int dir)
{
    M5LcdCamState *s = opaque;

    if (getenv("M5SW_CAMERA_TRACE")) {
        fprintf(stderr,
                "[lcd-cam] gdma-start periph=%u dir=%d started=%d\n",
                periph, dir, s->started);
    }
    if (periph == GDMA_LCDCAM && dir == ESP_GDMA_IN_IDX) {
        s->dma_armed = true;
    }
}

static uint64_t lcd_cam_read(void *opaque, hwaddr addr, unsigned size)
{
    M5LcdCamState *s = opaque;
    switch (addr) {
    case R_INT_ENA:
        return s->int_ena;
    case R_INT_RAW:
        return s->int_raw;
    case R_INT_ST:
        return s->int_raw & s->int_ena;
    default:
        return addr < sizeof(s->regs) ? s->regs[addr / 4] : 0;
    }
}

static void lcd_cam_write(void *opaque, hwaddr addr, uint64_t value,
                          unsigned size)
{
    M5LcdCamState *s = opaque;
    uint32_t v = value;

    switch (addr) {
    case R_CAM_CTRL:
        s->regs[addr / 4] = v & ~CAM_UPDATE;
        break;
    case R_CAM_CTRL1: {
        bool start = !!(v & CAM_START);
        bool rising = start && !s->started;
        if (getenv("M5SW_CAMERA_TRACE")) {
            fprintf(stderr, "[lcd-cam] ctrl1=%08x start=%d rising=%d armed=%d\n",
                    (unsigned)v, start, rising, s->dma_armed);
        }
        s->regs[addr / 4] = v & ~(CAM_RESET | CAM_AFIFO_RST);
        s->started = start;
        if (rising) {
            s->frame_bytes = MAX(2u, s->width * s->height * 2);
            s->chunk_len = (v & 0xffff) + 1;
            s->chunks_left = (s->frame_bytes + s->chunk_len - 1)
                           / s->chunk_len;
            s->frame_offset = 0;
            lcd_cam_capture(s);
        }
        break;
    }
    case R_INT_ENA:
        s->int_ena = v;
        lcd_cam_update_irq(s);
        break;
    case R_INT_CLR:
        s->int_raw &= ~v;
        lcd_cam_update_irq(s);
        break;
    default:
        if (addr < sizeof(s->regs)) {
            s->regs[addr / 4] = v;
        }
        break;
    }
}

static const MemoryRegionOps lcd_cam_ops = {
    .read = lcd_cam_read,
    .write = lcd_cam_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
    .impl.min_access_size = 4,
    .impl.max_access_size = 4,
};

static void lcd_cam_reset(DeviceState *dev)
{
    M5LcdCamState *s = M5_LCD_CAM(dev);
    memset(s->regs, 0, sizeof(s->regs));
    s->int_ena = 0;
    s->int_raw = 0;
    s->frame_offset = 0;
    s->frame_bytes = 0;
    s->chunk_len = 0;
    s->chunks_left = 0;
    s->started = false;
    s->dma_armed = false;
}

static bool frame_auto_increment_get(Object *obj, Error **errp)
{
    return M5_LCD_CAM(obj)->frame_auto_increment;
}

static void frame_auto_increment_set(Object *obj, bool value, Error **errp)
{
    M5_LCD_CAM(obj)->frame_auto_increment = value;
}

static void lcd_cam_init(Object *obj)
{
    M5LcdCamState *s = M5_LCD_CAM(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    memory_region_init_io(&s->iomem, obj, &lcd_cam_ops, s,
                          TYPE_M5_LCD_CAM, 0x1000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    object_property_add_uint32_ptr(
        obj, "frame-seed", &s->frame_seed, OBJ_PROP_FLAG_READWRITE);
    object_property_add_bool(
        obj, "auto-increment", frame_auto_increment_get,
        frame_auto_increment_set);
    s->capture_timer = timer_new_ms(QEMU_CLOCK_VIRTUAL,
                                    (QEMUTimerCB *)lcd_cam_capture, s);
}

static void lcd_cam_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    device_class_set_legacy_reset(dc, lcd_cam_reset);
}

static const TypeInfo lcd_cam_info = {
    .name = TYPE_M5_LCD_CAM,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(M5LcdCamState),
    .instance_init = lcd_cam_init,
    .class_init = lcd_cam_class_init,
};

static void lcd_cam_register(void)
{
    type_register_static(&lcd_cam_info);
}
type_init(lcd_cam_register)

void m5_lcd_cam_attach(DeviceState *dev, ESPGdmaState *gdma,
                       uint32_t width, uint32_t height)
{
    M5LcdCamState *s = M5_LCD_CAM(dev);
    object_property_add_child(qdev_get_machine(), "m5-lcd-cam", OBJECT(dev));
    s->gdma = gdma;
    s->width = width;
    s->height = height;
    esp_gdma_set_start_callback(gdma, GDMA_LCDCAM, ESP_GDMA_IN_IDX,
                                lcd_cam_gdma_started, s);
    const char *frame_path = getenv("M5SW_CAMERA_FRAME");
    if (frame_path) {
        gsize size = 0;
        if (!g_file_get_contents(frame_path, (gchar **)&s->frame_data,
                                 &size, NULL)) {
            s->frame_data = NULL;
            size = 0;
        }
        s->frame_data_size = MIN(size, UINT32_MAX);
    }
}

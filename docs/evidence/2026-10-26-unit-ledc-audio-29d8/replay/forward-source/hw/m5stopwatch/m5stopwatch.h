/* M5Stack StopWatch board models for the Espressif QEMU esp32s3 machine */
#pragma once
#include "hw/sysbus.h"
#include "hw/i2c/i2c.h"
#include "ui/console.h"

#define TYPE_ESP32S3_I2C "esp32s3.i2c"
OBJECT_DECLARE_SIMPLE_TYPE(Esp32s3I2CState, ESP32S3_I2C)
void esp32s3_i2c_set_bus(DeviceState *dev, I2CBus *bus);

#define TYPE_ESP32S3_GPSPI "esp32s3.gpspi"
OBJECT_DECLARE_SIMPLE_TYPE(Esp32s3GpspiState, ESP32S3_GPSPI)

#define TYPE_M5SW_I2C_DEV "m5sw-i2c-dev"
#define TYPE_M5SW_IP2315 "m5sw-ip2315"
#define TYPE_CO5300 "co5300"
OBJECT_DECLARE_SIMPLE_TYPE(Co5300State, CO5300)

#define TYPE_M5_SPI_PANEL "m5.spi-panel"
OBJECT_DECLARE_SIMPLE_TYPE(M5SpiPanelState, M5_SPI_PANEL)

#define TYPE_M5_EPD_PANEL "m5.epd-panel"
OBJECT_DECLARE_SIMPLE_TYPE(M5EpdPanelState, M5_EPD_PANEL)

#define TYPE_M5_LCD_CAM "m5.lcd-cam"
OBJECT_DECLARE_SIMPLE_TYPE(M5LcdCamState, M5_LCD_CAM)

#define TYPE_M5_I2S "m5.i2s"
OBJECT_DECLARE_SIMPLE_TYPE(M5I2SState, M5_I2S)

#define TYPE_M5_ESP32_I2S "m5.esp32-i2s"
OBJECT_DECLARE_SIMPLE_TYPE(M5Esp32I2SState, M5_ESP32_I2S)

#define TYPE_M5_RMT "m5.rmt"
OBJECT_DECLARE_SIMPLE_TYPE(M5RmtState, M5_RMT)

typedef struct M5SpiSlaveOps {
    void (*set_cs)(void *opaque, int level);
    uint8_t (*transfer)(void *opaque, uint8_t tx);
} M5SpiSlaveOps;

typedef struct M5Imx219FrameConfig {
    bool available;
    bool streaming;
    uint32_t width;
    uint32_t height;
    uint32_t lanes;
    uint32_t bpp;
    uint32_t orientation;
    uint32_t exposure;
    uint32_t analog_gain;
    uint32_t digital_gain;
    uint32_t test_pattern;
    uint32_t test_color[4];
    uint64_t frame_interval_ns;
    uint32_t frame_count;
} M5Imx219FrameConfig;

bool m5sw_imx219_frame_config(M5Imx219FrameConfig *config);
void m5sw_imx219_note_frame(void);

typedef enum {
    M5_BOARD_NONE = 0,
    M5_BOARD_STOPWATCH,
    M5_BOARD_STICKS3,
    M5_BOARD_ATOMS3R,
    M5_BOARD_CORES3,
    M5_BOARD_CARDPUTER_ADV,
    M5_BOARD_STAMPLC,
    M5_BOARD_STACKCHAN,
    M5_BOARD_PAPERMONO,
    M5_BOARD_PAPERCOLOR,
    M5_BOARD_CORE2,
} M5Board;

extern M5Board m5_board;

/* GPIO glue (implemented in hw/gpio/esp32_gpio.c) */
typedef void (*esp32_gpio_out_cb)(void *opaque, int pin, int level);
void esp32_gpio_set_input(int pin, int level);
void esp32_gpio_add_out_listener(int pin, esp32_gpio_out_cb cb, void *opaque);
void esp32_gpio_set_open_drain(int pin, bool enable);
void esp32_gpio_force_line(int pin, int level);
int esp32_gpio_get_line(int pin);

/* Display byte sink interface used by GP-SPI2 */
void co5300_cs(Co5300State *s, int level);
void co5300_write(Co5300State *s, const uint8_t *buf, uint32_t len);
struct ESPGdmaState;
void m5_spi_panel_write(M5SpiPanelState *s, const uint8_t *buf, uint32_t len,
                        bool command_phase);
uint32_t m5_spi_panel_read_id(M5SpiPanelState *s);
void m5_epd_panel_write(M5EpdPanelState *s, const uint8_t *buf, uint32_t len,
                        bool command_phase);
void m5_lcd_cam_attach(DeviceState *dev, struct ESPGdmaState *gdma,
                       uint32_t width, uint32_t height);
void m5_i2s_attach(DeviceState *dev, struct ESPGdmaState *gdma, uint32_t port);
void m5_i2s_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                       struct ESPGdmaState *gdma);
void m5_esp32_i2s_board_init(MemoryRegion *sys_mem, BusState *periph_bus,
                             DeviceState *intmatrix);
void esp32s3_rmt_init(MemoryRegion *sys_mem, DeviceState *intmatrix);
void esp32s3_gpspi_attach(DeviceState *dev, struct ESPGdmaState *gdma,
                          Co5300State *co, M5SpiPanelState *spi,
                          uint32_t gdma_periph);
void esp32s3_gpspi_set_dc_pin(DeviceState *dev, int pin);
void esp32s3_gpspi_set_panel_cs_pin(DeviceState *dev, int pin);
void esp32s3_gpspi_connect_irqs(DeviceState *dev, DeviceState *intmatrix,
                                int irq_a, int irq_b);
void esp32s3_gpspi_attach_spi_slave(DeviceState *dev,
                                    const M5SpiSlaveOps *ops,
                                    void *opaque, int cs_pin);
void esp32s3_gpspi_set_spi_slave_dma(DeviceState *dev, int cs_pin,
                                     uint32_t gdma_periph);
void m5_sx1262_attach(DeviceState *spi, int cs_pin);
void m5_st25r3916_spi_attach(DeviceState *spi, int cs_pin, int irq_pin);
void m5_cc1101_spi_attach(DeviceState *spi, int cs_pin, int gdo0_pin);
void m5_spi_sd_attach(DeviceState *spi, int cs_pin);
void m5_max3421e_attach(DeviceState *spi, int cs_pin, int irq_pin);
void m5_scs_servo_attach(DeviceState *uart);
void m5_uart_echo_attach(DeviceState *uart, const char *enable_env);
DeviceState *m5soc_get_uart_device(int index);
struct CanBusState *m5_can_bus_create(void);
void esp32s3_gpspi_attach_epd(DeviceState *dev, struct ESPGdmaState *gdma,
                              M5EpdPanelState *panel, uint32_t gdma_periph);

/* Touch injection into the CST820 model */
void m5sw_touch_set(int pressed, int x, int y);
void m5sw_ft_touch_set(int pressed, int x, int y);
void m5sw_ft_touch_set_pin(int pressed, int x, int y, int int_pin);
void m5sw_keyboard_event(uint8_t event);
void m5sw_plc_key_set(int key, bool pressed);
void m5sw_pwr_button(int pressed);

/* Board helper */
struct ESPGdmaState;
void m5stopwatch_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                            struct ESPGdmaState *gdma);
void m5stopwatch_sens_init(MemoryRegion *sys_mem);
void m5stopwatch_regi2c_init(MemoryRegion *sys_mem);
void m5stopwatch_fe_init(MemoryRegion *sys_mem);
void m5stopwatch_phy_init(MemoryRegion *sys_mem);
void m5stopwatch_soft_i2c_init(I2CBus *bus);
void m5stopwatch_soft_i2c_init_pins(I2CBus *bus, int sda_pin, int scl_pin);
void m5stopwatch_soft_i2c_set_hardware_active(void);
void m5_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                   struct ESPGdmaState *gdma);
void m5sticks3_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                          struct ESPGdmaState *gdma);
void m5atoms3r_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                          struct ESPGdmaState *gdma);
void m5cores3_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                         struct ESPGdmaState *gdma);
void m5cardputeradv_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                               struct ESPGdmaState *gdma);
void m5stamplc_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                          struct ESPGdmaState *gdma);
void m5stackchan_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                            struct ESPGdmaState *gdma);
void m5papermono_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                            struct ESPGdmaState *gdma);
void m5papercolor_board_init(MemoryRegion *sys_mem, DeviceState *intmatrix,
                             struct ESPGdmaState *gdma);
struct Esp32SocState;
void m5core2_board_init(struct Esp32SocState *s);

/* Session-scoped external Units; hardware transactions stay in C. */
void m5_unit_runtime_init(bool s3);
I2CBus *m5_unit_i2c_route(I2CBus *fallback, unsigned controller, bool s3);

void m5stopwatch_soft_i2c_set_hardware_active_on_bus(I2CBus *bus);

void m5_unit_classic_adc_init(MemoryRegion *sys_mem);

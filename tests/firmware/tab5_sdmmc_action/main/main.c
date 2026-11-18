#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/sdmmc_host.h"
#include "esp_err.h"
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_ldo_regulator.h"
#include "freertos/task.h"
#include "esp_vfs_fat.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "sd_pwr_ctrl_by_on_chip_ldo.h"

#define ST7123_INT GPIO_NUM_23
#define MOUNT_POINT "/sdcard"

typedef struct {
    const char *path;
    const char *contents;
} probe_file_t;

static const probe_file_t files[] = {
    {MOUNT_POINT "/TAP.TXT", "Tab5 ST7123 center tap\n"},
    {MOUNT_POINT "/POINT.TXT", "x=360 y=640\n"},
};
static SemaphoreHandle_t pending_report;

static void IRAM_ATTR touch_irq(void *arg)
{
    (void)arg;
    BaseType_t higher_priority = pdFALSE;
    xSemaphoreGiveFromISR(pending_report, &higher_priority);
    if (higher_priority == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

static void read_register(i2c_master_dev_handle_t device, uint16_t address,
                          uint8_t *data, size_t len)
{
    const uint8_t index[] = {address >> 8, address & 0xff};
    ESP_ERROR_CHECK(i2c_master_transmit_receive(device, index, sizeof(index), data, len, 1000));
}

static unsigned read_be16(const uint8_t *data)
{
    return ((unsigned)data[0] << 8) | data[1];
}

// Video timings follow the official Tab5 ST7123 BSP at fe8aa051.
enum {LCD_WIDTH = 720, LCD_HEIGHT = 1280};
static esp_lcd_panel_handle_t display;
static uint16_t *lcd_frame;
static esp_ldo_channel_handle_t dsi_power;

static void present(bool complete)
{
    const uint16_t background = complete ? 0x0840 : 0x084b;
    const uint16_t start_button = complete ? 0x07e0 : 0x04df;
    for (unsigned y = 0; y < LCD_HEIGHT; ++y) {
        for (unsigned x = 0; x < LCD_WIDTH; ++x) {
            bool inside = x >= 240 && x < 480 && y >= 550 && y < 730;
            bool cross = (x >= 353 && x < 367 && y >= 590 && y < 690)
                        || (y >= 633 && y < 647 && x >= 310 && x < 410);
            lcd_frame[y * LCD_WIDTH + x] = cross ? 0xffff : inside ? start_button : background;
        }
    }
    ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(display, 0, 0, LCD_WIDTH, LCD_HEIGHT, lcd_frame));
    puts(complete ? "TAB5_TAP_SD_FRAME_COMPLETE" : "TAB5_TAP_SD_FRAME_READY");
}

static void init_display(void)
{
    const esp_ldo_channel_config_t ldo = {.chan_id = 3, .voltage_mv = 2500};
    ESP_ERROR_CHECK(esp_ldo_acquire_channel(&ldo, &dsi_power));
    esp_lcd_dsi_bus_handle_t bus;
    const esp_lcd_dsi_bus_config_t bus_config = {
        .bus_id = 0,
        .num_data_lanes = 2,
        .phy_clk_src = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
        .lane_bit_rate_mbps = 965,
    };
    ESP_ERROR_CHECK(esp_lcd_new_dsi_bus(&bus_config, &bus));

    esp_lcd_panel_io_handle_t command_io;
    const esp_lcd_dbi_io_config_t io_config = {
        .virtual_channel = 0, .lcd_cmd_bits = 8, .lcd_param_bits = 8,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_dbi(bus, &io_config, &command_io));
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(command_io, 0x01, NULL, 0));
    vTaskDelay(pdMS_TO_TICKS(30));
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(command_io, 0x11, NULL, 0));
    vTaskDelay(pdMS_TO_TICKS(120));
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(command_io, 0x29, NULL, 0));

    const esp_lcd_dpi_panel_config_t dpi = {
        .virtual_channel = 0,
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = 70,
        .in_color_format = LCD_COLOR_FMT_RGB565,
        .num_fbs = 1,
        .video_timing = {
            .h_size = LCD_WIDTH, .v_size = LCD_HEIGHT,
            .hsync_pulse_width = 2, .hsync_back_porch = 40, .hsync_front_porch = 40,
            .vsync_pulse_width = 2, .vsync_back_porch = 8, .vsync_front_porch = 220,
        },
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_dpi(bus, &dpi, &display));
    ESP_ERROR_CHECK(esp_lcd_dpi_panel_get_frame_buffer(display, 1, (void **)&lcd_frame));
    present(false);
    ESP_ERROR_CHECK(esp_lcd_panel_init(display));
}

static i2c_master_dev_handle_t init_touch(void)
{
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t device;
    const i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_1,
        .sda_io_num = GPIO_NUM_31,
        .scl_io_num = GPIO_NUM_32,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    const i2c_device_config_t part_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = 0x55,
        .scl_speed_hz = 400000,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &bus));
    ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &part_config, &device));

    uint8_t version;
    uint8_t geometry[5];
    read_register(device, 0x0000, &version, 1);
    read_register(device, 0x0005, geometry, sizeof(geometry));
    const unsigned xmax = read_be16(geometry);
    const unsigned ymax = read_be16(geometry + 2);
    printf("TAB5_TAP_SD_TOUCH_ID version=%u xmax=%u ymax=%u slots=%u\n",
           version, xmax, ymax, geometry[4]);
    configASSERT(version == 3 && xmax == 719 && ymax == 1279 && geometry[4] == 1);

    pending_report = xSemaphoreCreateBinary();
    configASSERT(pending_report);
    const gpio_config_t interrupt_config = {
        .pin_bit_mask = 1ULL << ST7123_INT,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = true,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&interrupt_config));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(ST7123_INT, touch_irq, NULL));
    return device;
}

static sdmmc_card_t *mount_sd(sd_pwr_ctrl_handle_t *power)
{
    const sd_pwr_ctrl_ldo_config_t ldo = {.ldo_chan_id = 4};
    ESP_ERROR_CHECK(sd_pwr_ctrl_new_on_chip_ldo(&ldo, power));
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.slot = SDMMC_HOST_SLOT_0;
    host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;
    host.pwr_ctrl_handle = *power;
    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.width = 4;
    slot.clk = GPIO_NUM_43;
    slot.cmd = GPIO_NUM_44;
    slot.d0 = GPIO_NUM_39;
    slot.d1 = GPIO_NUM_40;
    slot.d2 = GPIO_NUM_41;
    slot.d3 = GPIO_NUM_42;
    const esp_vfs_fat_sdmmc_mount_config_t config = {
        .format_if_mount_failed = false,
        .max_files = 2,
    };
    sdmmc_card_t *card;
    ESP_ERROR_CHECK(esp_vfs_fat_sdmmc_mount(MOUNT_POINT, &host, &slot, &config, &card));
    puts("TAB5_TAP_SD_MOUNT slot=0");
    return card;
}

static void wait_center_tap(i2c_master_dev_handle_t device)
{
    bool center_pressed = false;
    for (;;) {
        xSemaphoreTake(pending_report, portMAX_DELAY);
        uint8_t status;
        read_register(device, 0x0010, &status, 1);
        if (!(status & 0x08)) {
            printf("TAB5_TAP_SD_RELEASE status=0x%02x\n", status);
            if (center_pressed) {
                return;
            }
            continue;
        }

        uint8_t point[7];
        read_register(device, 0x0014, point, sizeof(point));
        if (!(point[0] & 0x80)) {
            center_pressed = false;
            continue;
        }
        point[0] &= 0x3f;
        unsigned x = read_be16(point);
        unsigned y = read_be16(point + 2);
        center_pressed = (x == 360 && y == 640);
        printf("TAB5_TAP_SD_POINT x=%u y=%u area=%u center=%d\n", x, y, point[4], center_pressed);
    }
}

static void write_and_verify(const probe_file_t *file)
{
    const size_t expected_len = strlen(file->contents);
    FILE *stream = fopen(file->path, "wb");
    configASSERT(stream != NULL);
    size_t written = fwrite(file->contents, 1, expected_len, stream);
    int closed = fclose(stream);
    configASSERT(written == expected_len && closed == 0);
    printf("TAB5_TAP_SD_WRITE path=%s bytes=%u\n", file->path, (unsigned)written);
    char readback[64];
    stream = fopen(file->path, "rb");
    configASSERT(stream != NULL);
    size_t received = fread(readback, 1, sizeof(readback), stream);
    closed = fclose(stream);
    configASSERT(closed == 0 && received == expected_len && memcmp(readback, file->contents, expected_len) == 0);
    printf("TAB5_TAP_SD_READBACK path=%s bytes=%u exact=1\n", file->path, (unsigned)received);
}

void app_main(void)
{
    sd_pwr_ctrl_handle_t power = NULL;
    sdmmc_card_t *card = mount_sd(&power);
    i2c_master_dev_handle_t touch = init_touch();
    init_display();
    puts("TAB5_TAP_SD_READY target_x=360 target_y=640");
    fflush(stdout);
    wait_center_tap(touch);

    for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); ++i) {
        write_and_verify(&files[i]);
    }
    ESP_ERROR_CHECK(esp_vfs_fat_sdcard_unmount(MOUNT_POINT, card));
    ESP_ERROR_CHECK(sd_pwr_ctrl_del_on_chip_ldo(power));
    present(true);
    puts("TAB5_TAP_SD_PASS");
    fflush(stdout);
}

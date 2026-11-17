#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/sdspi_host.h"
#include "driver/spi_master.h"
#include "esp_attr.h"
#include "esp_err.h"
#include "esp_vfs_fat.h"

#define SD_CS GPIO_NUM_12
#define SD_BUS SPI3_HOST

static const spi_bus_config_t bus = {
    .mosi_io_num = 14,
    .miso_io_num = 39,
    .sclk_io_num = 40,
    .quadwp_io_num = -1,
    .quadhd_io_num = -1,
    .max_transfer_sz = 8192,
};

static DMA_ATTR uint8_t output[64];
static DMA_ATTR uint8_t input[64];

static bool check_selected_card(void)
{
    static const char expected[] = "M5EMU_SEEDED_FAT32_PAYLOAD";
    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    host.slot = SD_BUS;
    host.max_freq_khz = 20000;
    sdspi_device_config_t slot = SDSPI_DEVICE_CONFIG_DEFAULT();
    slot.host_id = SD_BUS;
    slot.gpio_cs = SD_CS;
    const esp_vfs_fat_mount_config_t mount = {
        .format_if_mount_failed = false,
        .max_files = 3,
    };
    sdmmc_card_t *card;
    ESP_ERROR_CHECK(esp_vfs_fat_sdspi_mount("/sd", &host, &slot, &mount, &card));
    FILE *file = fopen("/sd/FIXTURE/ROM.BIN", "rb");
    bool match = false;
    if (file) {
        char readback[sizeof(expected)];
        size_t count = fread(readback, 1, sizeof(readback), file);
        match = count == sizeof(expected) - 1 && memcmp(readback, expected, count) == 0;
        fclose(file);
    }
    ESP_ERROR_CHECK(esp_vfs_fat_sdcard_unmount("/sd", card));
    printf("SPI_IDLE_RX selected_sd_match=%d\n", match);
    return match;
}

static bool check_idle_bus(const char *mode)
{
    const spi_device_interface_config_t config = {
        .clock_speed_hz = 20000000,
        .mode = 0,
        .spics_io_num = -1,
        .queue_size = 1,
    };
    ESP_ERROR_CHECK(gpio_set_direction(SD_CS, GPIO_MODE_INPUT_OUTPUT));
    ESP_ERROR_CHECK(gpio_set_level(SD_CS, 1));
    int cs = gpio_get_level(SD_CS);
    printf("SPI_IDLE_RX mode=%s sd_cs=%d\n", mode, cs);
    spi_device_handle_t device;
    ESP_ERROR_CHECK(spi_bus_add_device(SD_BUS, &config, &device));

    bool match = cs == 1;
    memset(output, 0xff, sizeof(output));
    for (size_t count = 1; count <= sizeof(input); count *= 4) {
        memset(input, 0, sizeof(input));
        spi_transaction_t trans = {
            .length = count * 8,
            .rxlength = count * 8,
            .tx_buffer = output,
            .rx_buffer = input,
        };
        ESP_ERROR_CHECK(spi_device_polling_transmit(device, &trans));
        unsigned ones = 0;
        for (size_t i = 0; i < count; ++i) {
            ones += input[i] == 0xff;
        }
        printf("SPI_IDLE_RX mode=%s bytes=%zu ones=%u\n", mode, count, ones);
        match &= ones == count;
    }
    uint8_t idle_byte = 0xff;
    spi_transaction_t inline_rx = {
        .length = 8,
        .flags = SPI_TRANS_USE_RXDATA,
        .tx_buffer = &idle_byte,
    };
    ESP_ERROR_CHECK(spi_device_polling_transmit(device, &inline_rx));
    printf("SPI_IDLE_RX mode=%s inline_byte=%02x\n", mode, (unsigned)inline_rx.rx_data[0]);
    ESP_ERROR_CHECK(spi_bus_remove_device(device));
    return match && inline_rx.rx_data[0] == 0xff;
}

void app_main(void)
{
    ESP_ERROR_CHECK(spi_bus_initialize(SD_BUS, &bus, SPI_DMA_CH_AUTO));
    bool selected = check_selected_card();
    bool dma = check_idle_bus("dma");
    ESP_ERROR_CHECK(spi_bus_free(SD_BUS));

    ESP_ERROR_CHECK(spi_bus_initialize(SD_BUS, &bus, SPI_DMA_DISABLED));
    bool fifo = check_idle_bus("fifo");
    ESP_ERROR_CHECK(spi_bus_free(SD_BUS));
    printf("SPI_IDLE_RX_DONE selected=%d dma=%d fifo=%d\n", selected, dma, fifo);
}

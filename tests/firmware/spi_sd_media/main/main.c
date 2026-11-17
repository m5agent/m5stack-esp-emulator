#include <dirent.h>
#include <stdio.h>
#include <string.h>
#include "driver/sdspi_host.h"
#include "driver/spi_common.h"
#include "esp_err.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"

#define MOUNT_PATH "/sd"

#if defined(PROBE_PAPER)
#define PIN_CS 47
#define PIN_SCK 39
#define PIN_MOSI 38
#define PIN_MISO 40
#else
#define PIN_CS 12
#define PIN_SCK 40
#define PIN_MOSI 14
#define PIN_MISO 39
#endif

static const char seed[] = "M5EMU_SEEDED_FAT32_PAYLOAD";
static const char proof[] = "M5EMU_PERSISTENT_SD_WRITE";

static bool matches(const char *path, const char *value)
{
    FILE *file = fopen(path, "rb");
    if (!file) {
        return false;
    }
    char actual[64];
    size_t count = fread(actual, 1, sizeof(actual), file);
    fclose(file);
    return count == strlen(value) && memcmp(actual, value, count) == 0;
}

static bool contains_file(void)
{
    DIR *dir = opendir(MOUNT_PATH "/FIXTURE");
    if (!dir) {
        return false;
    }
    bool found = false;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (strcasecmp(entry->d_name, "ROM.BIN") == 0) {
            found = true;
            break;
        }
    }
    closedir(dir);
    return found;
}

void app_main(void)
{
    const spi_bus_config_t spi = {
        .mosi_io_num = PIN_MOSI,
        .miso_io_num = PIN_MISO,
        .sclk_io_num = PIN_SCK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .data4_io_num = -1,
        .data5_io_num = -1,
        .data6_io_num = -1,
        .data7_io_num = -1,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &spi, SPI_DMA_CH_AUTO));
    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    host.slot = SPI2_HOST;
    sdspi_device_config_t slot = SDSPI_DEVICE_CONFIG_DEFAULT();
    slot.host_id = SPI2_HOST;
    slot.gpio_cs = PIN_CS;
    const esp_vfs_fat_mount_config_t mount = {
        .format_if_mount_failed = false,
        .max_files = 3,
    };
    sdmmc_card_t *card;
    esp_err_t err = esp_vfs_fat_sdspi_mount(MOUNT_PATH, &host, &slot, &mount, &card);
    if (err != ESP_OK) {
        printf("STORAGE_PROBE_MOUNT_ERROR %s\n", esp_err_to_name(err));
        puts("STORAGE_PROBE_DONE");
        return;
    }
    const bool seed_ok = contains_file() && matches(MOUNT_PATH "/FIXTURE/ROM.BIN", seed);
    const bool prior_write = matches(MOUNT_PATH "/PROOF.BIN", proof);
    printf("STORAGE_PROBE_MOUNT seed=%d prior=%d\n", seed_ok, prior_write);
    FILE *file = fopen(MOUNT_PATH "/PROOF.BIN", "wb");
    bool write_ok = false;
    if (file) {
        write_ok = fwrite(proof, 1, sizeof(proof) - 1, file) == sizeof(proof) - 1;
        write_ok = fclose(file) == 0 && write_ok;
    }
    ESP_ERROR_CHECK(esp_vfs_fat_sdcard_unmount(MOUNT_PATH, card));
    ESP_ERROR_CHECK(esp_vfs_fat_sdspi_mount(MOUNT_PATH, &host, &slot, &mount, &card));
    printf("STORAGE_PROBE_REMOUNT write=%d restored=%d\n", write_ok,
           matches(MOUNT_PATH "/PROOF.BIN", proof));
    ESP_ERROR_CHECK(esp_vfs_fat_sdcard_unmount(MOUNT_PATH, card));
    ESP_ERROR_CHECK(spi_bus_free(SPI2_HOST));
    puts("STORAGE_PROBE_DONE");
}

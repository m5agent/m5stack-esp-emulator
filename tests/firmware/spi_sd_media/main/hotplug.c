#include <stdio.h>
#include <string.h>
#include "driver/gpio.h"
#include "driver/sdspi_host.h"
#include "driver/spi_common.h"
#include "esp_err.h"
#include "esp_vfs_fat.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdmmc_cmd.h"

#define MOUNT_PATH "/sd"
#define CARD_DET GPIO_NUM_48
#define SEED_PATH MOUNT_PATH "/FIXTURE/ROM.BIN"
#define PROOF_PATH MOUNT_PATH "/PROOF.BIN"

static const char seed[] = "M5EMU_SEEDED_FAT32_PAYLOAD";
static const char proof[] = "M5EMU_PAPERDIY_HOTPLUG_PERSISTED";

static void detect_edge(void *arg)
{
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(arg, &wake);
    if (wake) {
        portYIELD_FROM_ISR();
    }
}

static bool matches(const char *path, const char *expected)
{
    FILE *file = fopen(path, "rb");
    if (!file) {
        return false;
    }
    char actual[64];
    size_t length = fread(actual, 1, sizeof(actual), file);
    fclose(file);
    return length == strlen(expected) && !memcmp(expected, actual, length);
}

static bool observe_edge(unsigned generation, int expected_level)
{
    if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(30000)) != 1) {
        puts("HOTPLUG_ERROR missing or duplicate GPIO interrupt");
        return false;
    }
    int level = gpio_get_level(CARD_DET);
    printf("HOTPLUG_IRQ generation=%u level=%d\n", generation, level);
    return level == expected_level;
}

void app_main(void)
{
    const spi_bus_config_t spi = {
        .miso_io_num = 40,
        .mosi_io_num = 38,
        .sclk_io_num = 39,
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
    slot.gpio_cs = 47;
    const esp_vfs_fat_mount_config_t mount = {
        .format_if_mount_failed = false,
        .max_files = 3,
    };
    const gpio_config_t detect = {
        .pin_bit_mask = 1ULL << CARD_DET,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .intr_type = GPIO_INTR_ANYEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&detect));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(CARD_DET, detect_edge, xTaskGetCurrentTaskHandle()));

    sdmmc_card_t *card;
    int initial_level = gpio_get_level(CARD_DET);
    esp_err_t absent = esp_vfs_fat_sdspi_mount(MOUNT_PATH, &host, &slot, &mount, &card);
    printf("HOTPLUG_INITIAL level=%d mount=%s\n", initial_level, esp_err_to_name(absent));
    if (initial_level != 1 || absent != ESP_ERR_TIMEOUT || !observe_edge(1, 0)) {
        return;
    }
    ESP_ERROR_CHECK(esp_vfs_fat_sdspi_mount(MOUNT_PATH, &host, &slot, &mount, &card));
    if (!matches(SEED_PATH, seed) || matches(PROOF_PATH, proof)) {
        puts("HOTPLUG_ERROR first mount files");
        return;
    }
    FILE *file = fopen(PROOF_PATH, "wb");
    if (!file) {
        puts("HOTPLUG_ERROR open proof");
        return;
    }
    size_t written = fwrite(proof, 1, sizeof(proof) - 1, file);
    int closed = fclose(file);
    if (written != sizeof(proof) - 1 || closed != 0) {
        puts("HOTPLUG_ERROR write proof");
        return;
    }
    ESP_ERROR_CHECK(esp_vfs_fat_sdcard_unmount(MOUNT_PATH, card));
    puts("HOTPLUG_FIRST seed=1 write=1 unmounted=1");

    if (!observe_edge(2, 1)) {
        return;
    }
    absent = esp_vfs_fat_sdspi_mount(MOUNT_PATH, &host, &slot, &mount, &card);
    printf("HOTPLUG_EJECTED mount=%s\n", esp_err_to_name(absent));
    if (absent != ESP_ERR_TIMEOUT || !observe_edge(3, 0)) {
        return;
    }
    ESP_ERROR_CHECK(esp_vfs_fat_sdspi_mount(MOUNT_PATH, &host, &slot, &mount, &card));
    bool persisted = matches(SEED_PATH, seed) && matches(PROOF_PATH, proof);
    ESP_ERROR_CHECK(esp_vfs_fat_sdcard_unmount(MOUNT_PATH, card));
    printf("HOTPLUG_REINSERT persisted=%d unmounted=1\n", persisted);
    if (persisted && observe_edge(4, 1)) {
        puts("HOTPLUG_DONE");
    }
    ESP_ERROR_CHECK(gpio_isr_handler_remove(CARD_DET));
    gpio_uninstall_isr_service();
    ESP_ERROR_CHECK(spi_bus_free(SPI2_HOST));
}

#include <stdio.h>
#include <string.h>
#include "esp_flash.h"
#include "esp_partition.h"

static unsigned char expected[8192];
static unsigned char actual[8192];

static int check(const esp_partition_t *part, const char *mode)
{
    static const struct { unsigned offset, size; } ranges[] = {
        {0, 8192}, {1, 128}, {63, 257}, {255, 513}, {4093, 259}
    };
    for (unsigned r = 0; r < sizeof(ranges) / sizeof(ranges[0]); r++) {
        unsigned offset = ranges[r].offset, size = ranges[r].size;
        memset(actual, 0xCC, sizeof(actual));
        esp_err_t err = esp_partition_read(part, offset, actual, size);
        for (unsigned i = 0; i < size; i++) {
            if (err != ESP_OK || actual[i] != expected[offset + i]) {
                printf("C6_FLASH_FAIL mode=%s range=%u byte=%u expected=%02x actual=%02x err=%d\n",
                       mode, r, i, expected[offset + i], actual[i], err);
                return 1;
            }
        }
    }
    printf("C6_FLASH_READ_PASS mode=%s ranges=5 bytes=8192\n", mode);
    return 0;
}

void app_main(void)
{
    puts("C6_FLASH_START");
    const esp_partition_t *part = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, 0x40, "probe");
    if (!part) { puts("C6_FLASH_FAIL partition"); return; }
    unsigned failures = 0;
    for (unsigned i = 0; i < sizeof(expected); i++) {
        expected[i] = (unsigned char)((i * 73u + (i >> 8) * 19u + 0xA5u) & 255u);
    }
    if (esp_partition_erase_range(part, 0, sizeof(expected)) != ESP_OK ||
        esp_partition_write(part, 0, expected, sizeof(expected)) != ESP_OK) {
        puts("C6_FLASH_FAIL write"); return;
    }
    const esp_flash_io_mode_t modes[] = {SPI_FLASH_DIO, SPI_FLASH_QIO};
    const char *names[] = {"DIO", "QIO"};
    for (unsigned m = 0; m < 2; m++) {
        esp_flash_default_chip->read_mode = modes[m];
        esp_err_t init_err = esp_flash_init(esp_flash_default_chip);
        if (init_err != ESP_OK) {
            printf("C6_FLASH_FAIL init mode=%s err=%d\n", names[m], init_err); return;
        }
        failures += check(part, names[m]);
    }
    if (esp_partition_erase_range(part, 0, sizeof(expected)) != ESP_OK) {
        puts("C6_FLASH_FAIL erase"); return;
    }
    memset(expected, 0xFF, sizeof(expected));
    failures += check(part, "QIO-erased");
    if (!failures) puts("C6_FLASH_READY");
}

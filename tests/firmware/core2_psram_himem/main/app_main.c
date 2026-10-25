#include <stdint.h>
#include <stdio.h>

#include "esp_err.h"
#include "esp32/himem.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define HIMEM_TEST_BLOCKS 2
#define HIMEM_TEST_PATTERN 0x5a

static void fill_pattern(uint8_t *memory, uint8_t block)
{
    for (size_t offset = 0; offset < ESP_HIMEM_BLKSZ; offset++) {
        memory[offset] = (uint8_t) (
            HIMEM_TEST_PATTERN
            ^ block
            ^ (offset * 37)
            ^ (offset >> 8)
        );
    }
}

static esp_err_t verify_pattern(const uint8_t *memory, uint8_t block)
{
    for (size_t offset = 0; offset < ESP_HIMEM_BLKSZ; offset++) {
        uint8_t expected = (uint8_t) (
            HIMEM_TEST_PATTERN
            ^ block
            ^ (offset * 37)
            ^ (offset >> 8)
        );
        if (memory[offset] != expected) {
            printf(
                "CORE2_HIMEM_MISMATCH block=%u offset=%u "
                "actual=%02x expected=%02x\n",
                block,
                (unsigned) offset,
                memory[offset],
                expected
            );
            return ESP_FAIL;
        }
    }
    return ESP_OK;
}

static esp_err_t run_bank_test(void)
{
    esp_himem_handle_t physical = NULL;
    esp_himem_rangehandle_t window = NULL;
    esp_err_t error;

    printf(
        "CORE2_HIMEM_PHYS_BYTES %u\n",
        (unsigned) esp_himem_get_phys_size()
    );
    printf(
        "CORE2_HIMEM_RESERVED_BYTES %u\n",
        (unsigned) esp_himem_reserved_area_size()
    );
    printf("CORE2_HIMEM_PHYS_START\n");

    error = esp_himem_alloc(
        HIMEM_TEST_BLOCKS * ESP_HIMEM_BLKSZ,
        &physical
    );
    if (error != ESP_OK) {
        printf("CORE2_HIMEM_ALLOC_ERROR %s\n", esp_err_to_name(error));
        return error;
    }
    error = esp_himem_alloc_map_range(ESP_HIMEM_BLKSZ, &window);
    if (error != ESP_OK) {
        printf(
            "CORE2_HIMEM_RANGE_ERROR %s\n",
            esp_err_to_name(error)
        );
        esp_himem_free(physical);
        return error;
    }

    for (uint8_t block = 0; block < HIMEM_TEST_BLOCKS; block++) {
        void *mapped = NULL;
        error = esp_himem_map(
            physical,
            window,
            block * ESP_HIMEM_BLKSZ,
            0,
            ESP_HIMEM_BLKSZ,
            0,
            &mapped
        );
        if (error != ESP_OK) {
            printf(
                "CORE2_HIMEM_MAP_WRITE_ERROR block=%u %s\n",
                block,
                esp_err_to_name(error)
            );
            goto cleanup;
        }
        fill_pattern(mapped, block);
        error = esp_himem_unmap(window, mapped, ESP_HIMEM_BLKSZ);
        if (error != ESP_OK) {
            printf(
                "CORE2_HIMEM_UNMAP_WRITE_ERROR block=%u %s\n",
                block,
                esp_err_to_name(error)
            );
            goto cleanup;
        }
    }

    for (int block = HIMEM_TEST_BLOCKS - 1; block >= 0; block--) {
        void *mapped = NULL;
        error = esp_himem_map(
            physical,
            window,
            (size_t) block * ESP_HIMEM_BLKSZ,
            0,
            ESP_HIMEM_BLKSZ,
            ESP_HIMEM_MAPFLAG_RO,
            &mapped
        );
        if (error != ESP_OK) {
            printf(
                "CORE2_HIMEM_MAP_READ_ERROR block=%d %s\n",
                block,
                esp_err_to_name(error)
            );
            goto cleanup;
        }
        error = verify_pattern(mapped, (uint8_t) block);
        esp_err_t unmap_error = esp_himem_unmap(
            window,
            mapped,
            ESP_HIMEM_BLKSZ
        );
        if (error == ESP_OK && unmap_error != ESP_OK) {
            error = unmap_error;
        }
        if (error != ESP_OK) {
            goto cleanup;
        }
    }

cleanup:
    if (window != NULL) {
        esp_err_t free_range_error = esp_himem_free_map_range(window);
        if (error == ESP_OK && free_range_error != ESP_OK) {
            error = free_range_error;
        }
    }
    if (physical != NULL) {
        esp_err_t free_physical_error = esp_himem_free(physical);
        if (error == ESP_OK && free_physical_error != ESP_OK) {
            error = free_physical_error;
        }
    }
    return error;
}

void app_main(void)
{
    esp_err_t error = run_bank_test();
    if (error == ESP_OK) {
        printf("CORE2_HIMEM_BANK_PASS\n");
    } else {
        printf("CORE2_HIMEM_FAIL %s\n", esp_err_to_name(error));
    }
    fflush(stdout);
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

/* Exercise the shared S3 cache IOMMU and another core's atomic TLB lookup. */
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define UNUSED_MMU_SLOT ((volatile uint32_t *)(0x600c5000u + 511 * 4))
#define MAPPING_CHANGES 200000

static const uint32_t flash_words[8] = {1, 2, 3, 4, 5, 6, 7, 8};
static _Atomic uint32_t counter;
static _Atomic bool done;

static void atomic_worker(void *arg)
{
    uint32_t iteration = 0;
    uint32_t checksum = 0;

    while (!atomic_load_explicit(&done, memory_order_acquire)) {
        /* Keep this CPU registered with the cache IOMMU between atomics. */
        checksum += ((volatile const uint32_t *)flash_words)[iteration & 7];
        atomic_fetch_add_explicit(&counter, 1, memory_order_seq_cst);
        if (!(++iteration & 4095)) {
            vTaskDelay(1);
        }
    }
    printf("S3_CACHE_ATOMIC_WORKER_DONE count=%lu checksum=%lu\n",
           (unsigned long)atomic_load(&counter), (unsigned long)checksum);
    vTaskDelete(NULL);
}

void app_main(void)
{
    BaseType_t created = xTaskCreatePinnedToCore(
        atomic_worker, "atomic", 4096, NULL, 5, NULL, 1);
    if (created != pdPASS) {
        puts("S3_CACHE_ATOMIC_CREATE_FAIL");
        return;
    }

    volatile uint32_t *slot = UNUSED_MMU_SLOT;
    uint32_t saved = *slot;
    printf("S3_CACHE_ATOMIC_BEGIN changes=%u\n", MAPPING_CHANGES);
    for (uint32_t iteration = 0; iteration < MAPPING_CHANGES; iteration++) {
        /* The final 64 KiB window is never accessed by this small image. */
        *slot = 0x8000u + (iteration & 1);
        __asm__ volatile("memw" ::: "memory");
        if (!(iteration & 255)) {
            vTaskDelay(1);
        }
    }
    *slot = saved;
    __asm__ volatile("memw" ::: "memory");
    atomic_store_explicit(&done, true, memory_order_release);
    printf("S3_CACHE_ATOMIC_PASS count=%lu\n",
           (unsigned long)atomic_load(&counter));
}

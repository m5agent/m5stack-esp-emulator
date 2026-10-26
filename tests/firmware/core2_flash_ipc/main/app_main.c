#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_partition.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define FLASH_WORKER_ITERATIONS 1000
#define FLASH_CHUNK_BYTES 4096

typedef struct {
    int core;
    SemaphoreHandle_t ready;
    SemaphoreHandle_t start;
    SemaphoreHandle_t done;
    const esp_partition_t *partition;
    esp_err_t result;
} flash_worker_context_t;

static flash_worker_context_t worker;
static uint8_t flash_buffer[FLASH_CHUNK_BYTES] __attribute__((aligned(4)));

static uint32_t read_raw_prid(void)
{
    uint32_t prid;

    __asm__ volatile("rsr.prid %0" : "=r"(prid));
    return prid;
}

static void flash_worker(void *argument)
{
    flash_worker_context_t *worker = argument;

    worker->result = ESP_OK;
    printf(
        "CORE2_FLASH_IPC_READY core=%d prid=0x%08x\n",
        worker->core,
        (unsigned) read_raw_prid()
    );
    fflush(stdout);
    xSemaphoreGive(worker->ready);
    xSemaphoreTake(worker->start, portMAX_DELAY);

    printf("CORE2_FLASH_IPC_READ_START core=%d\n", worker->core);
    fflush(stdout);
    const size_t max_offset = worker->partition->size - FLASH_CHUNK_BYTES;
    for (int iteration = 0; iteration < FLASH_WORKER_ITERATIONS; iteration++) {
        size_t offset = ((size_t) iteration * FLASH_CHUNK_BYTES) % max_offset;
        worker->result = esp_partition_read(
            worker->partition,
            offset,
            flash_buffer,
            sizeof(flash_buffer)
        );
        if (worker->result != ESP_OK) {
            printf(
                "CORE2_FLASH_IPC_ERROR core=%d iteration=%d offset=%u err=%s\n",
                worker->core,
                iteration,
                (unsigned) offset,
                esp_err_to_name(worker->result)
            );
            break;
        }
        if ((iteration + 1) % 50 == 0) {
            printf(
                "CORE2_FLASH_IPC_PROGRESS core=%d iteration=%d\n",
                worker->core,
                iteration + 1
            );
            fflush(stdout);
            vTaskDelay(pdMS_TO_TICKS(1));
        }
        taskYIELD();
    }

    if (worker->result == ESP_OK) {
        printf("CORE2_FLASH_IPC_WORKER_PASS core=%d\n", worker->core);
        fflush(stdout);
    }
    xSemaphoreGive(worker->done);
    vTaskDelete(NULL);
}

void app_main(void)
{
    const esp_partition_t *partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP,
        ESP_PARTITION_SUBTYPE_APP_FACTORY,
        NULL
    );
    if (partition == NULL) {
        printf("CORE2_FLASH_IPC_FAIL partition-missing\n");
        fflush(stdout);
        while (true) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }

    printf(
        "CORE2_FLASH_IPC_START partition_size=%u cores=%d\n",
        (unsigned) partition->size,
        portNUM_PROCESSORS
    );
    printf(
        "CORE2_FLASH_IPC_MAIN core=%d prid=0x%08x\n",
        xPortGetCoreID(),
        (unsigned) read_raw_prid()
    );
    fflush(stdout);

    worker.core = 1;
    worker.partition = partition;
    worker.ready = xSemaphoreCreateBinary();
    worker.start = xSemaphoreCreateBinary();
    worker.done = xSemaphoreCreateBinary();
    if (
        worker.ready == NULL
        || worker.start == NULL
        || worker.done == NULL
    ) {
        printf("CORE2_FLASH_IPC_FAIL semaphore-create core=%d\n", worker.core);
        fflush(stdout);
        while (true) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
    BaseType_t created = xTaskCreatePinnedToCore(
        flash_worker,
        "flash-ipc",
        4096,
        &worker,
        5,
        NULL,
        worker.core
    );
    if (created != pdPASS) {
        printf("CORE2_FLASH_IPC_FAIL task-create core=%d\n", worker.core);
        fflush(stdout);
        while (true) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }

    if (xSemaphoreTake(worker.ready, pdMS_TO_TICKS(10000)) != pdTRUE) {
        printf("CORE2_FLASH_IPC_FAIL ready-timeout core=%d\n", worker.core);
        fflush(stdout);
        while (true) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
    xSemaphoreGive(worker.start);

    bool passed = true;
    if (xSemaphoreTake(worker.done, pdMS_TO_TICKS(30000)) != pdTRUE) {
        printf(
            "CORE2_FLASH_IPC_FAIL completion-timeout core=%d\n",
            worker.core
        );
        passed = false;
    } else if (worker.result != ESP_OK) {
        passed = false;
    }

    printf(
        "CORE2_FLASH_IPC_%s\n",
        passed ? "PASS" : "FAIL"
    );
    fflush(stdout);
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

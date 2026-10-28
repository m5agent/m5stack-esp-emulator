#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "driver/spi_master.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "soc/spi_struct.h"

#define SPI_TX_BYTES 16
#define SPI_IRQ_TIMEOUT_MS 5000

static SemaphoreHandle_t transaction_done;
static volatile bool callback_seen;
static uint8_t tx_buffer[SPI_TX_BYTES]
    __attribute__((aligned(4), section(".dram1")));
static spi_device_handle_t device;

static void IRAM_ATTR transaction_post_callback(spi_transaction_t *trans)
{
    BaseType_t woken = pdFALSE;

    callback_seen = true;
    xSemaphoreGiveFromISR(transaction_done, &woken);
    if (woken == pdTRUE) {
        portYIELD_FROM_ISR();
    }
}

static void fail(const char *reason, esp_err_t error)
{
    printf(
        "CORE2_SPI_IRQ_REMAP_FAIL reason=%s err=%s slave=0x%08x\n",
        reason,
        esp_err_to_name(error),
        (unsigned) SPI3.slave.val
    );
    fflush(stdout);
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void app_main(void)
{
    printf("CORE2_SPI_IRQ_REMAP_START host=SPI3 bytes=%u\n", SPI_TX_BYTES);
    fflush(stdout);

    transaction_done = xSemaphoreCreateBinary();
    if (transaction_done == NULL) {
        fail("semaphore-create", ESP_ERR_NO_MEM);
    }
    for (size_t index = 0; index < sizeof(tx_buffer); index++) {
        tx_buffer[index] = (uint8_t) (0xa5u ^ index);
    }

    const spi_bus_config_t bus_config = {
        .mosi_io_num = 23,
        .miso_io_num = -1,
        .sclk_io_num = 18,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = SPI_TX_BYTES,
    };
    esp_err_t error = spi_bus_initialize(
        SPI3_HOST, &bus_config, SPI_DMA_DISABLED);
    if (error != ESP_OK) {
        fail("bus-initialize", error);
    }

    const spi_device_interface_config_t device_config = {
        .clock_speed_hz = 1000000,
        .mode = 0,
        .spics_io_num = 5,
        .queue_size = 1,
        .post_cb = transaction_post_callback,
    };
    error = spi_bus_add_device(SPI3_HOST, &device_config, &device);
    if (error != ESP_OK) {
        fail("device-add", error);
    }

    spi_transaction_t transaction = {
        .length = SPI_TX_BYTES * 8,
        .tx_buffer = tx_buffer,
        .user = (void *) 0x5a17,
    };
    error = spi_device_queue_trans(device, &transaction, 0);
    if (error != ESP_OK) {
        fail("queue", error);
    }
    printf("CORE2_SPI_IRQ_REMAP_QUEUE_OK\n");
    fflush(stdout);

    if (xSemaphoreTake(
            transaction_done, pdMS_TO_TICKS(SPI_IRQ_TIMEOUT_MS)) != pdTRUE) {
        fail("callback-timeout", ESP_ERR_TIMEOUT);
    }
    printf("CORE2_SPI_IRQ_REMAP_CALLBACK_OK\n");
    fflush(stdout);

    spi_transaction_t *completed = NULL;
    error = spi_device_get_trans_result(
        device, &completed, pdMS_TO_TICKS(SPI_IRQ_TIMEOUT_MS));
    if (error != ESP_OK) {
        fail("result", error);
    }
    if (completed != &transaction || !callback_seen) {
        fail("transaction-identity", ESP_ERR_INVALID_STATE);
    }

    printf(
        "CORE2_SPI_IRQ_REMAP_RESULT_OK length=%u user=0x%08x "
        "slave=0x%08x\n",
        (unsigned) transaction.length,
        (unsigned) (uintptr_t) transaction.user,
        (unsigned) SPI3.slave.val
    );
    printf("CORE2_SPI_IRQ_REMAP_PASS\n");
    fflush(stdout);

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

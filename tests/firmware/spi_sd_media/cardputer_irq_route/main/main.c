#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "esp_err.h"
#include "esp_intr_alloc.h"
#include "esp_private/periph_ctrl.h"
#include "soc/interrupts.h"
#include "soc/spi_reg.h"

enum { SPI2_INDEX = 2, SPI3_INDEX = 3 };

typedef struct {
    uint32_t after_transfer;
    uint32_t after_other_ack;
    uint32_t after_own_ack;
    uint32_t raw_after_other_ack;
} route_sample_t;

static void unexpected_isr(void *arg)
{
    const unsigned int spi = (uintptr_t)arg;
    REG_WRITE(SPI_DMA_INT_CLR_REG(spi), SPI_TRANS_DONE_INT_CLR);
}

static uint32_t pending_interrupts(void)
{
    uint32_t pending;
    __asm__ volatile("rsr.interrupt %0" : "=a"(pending) :: "memory");
    return pending;
}

static route_sample_t sample_completion(unsigned int spi, unsigned int other)
{
    /* Keep level-1 CPU delivery pending while sampling the matrix. */
    uint32_t previous_ps;
    __asm__ volatile("rsil %0, 5" : "=a"(previous_ps) :: "memory");
    REG_WRITE(SPI_USER_REG(spi), SPI_USR_MOSI);
    REG_WRITE(SPI_MS_DLEN_REG(spi), 7);
    REG_WRITE(SPI_W0_REG(spi), 0xff);
    REG_WRITE(SPI_CMD_REG(spi), SPI_UPDATE);
    while (REG_READ(SPI_CMD_REG(spi)) & SPI_UPDATE) {}
    REG_WRITE(SPI_CMD_REG(spi), SPI_USR);
    while (REG_READ(SPI_CMD_REG(spi)) & SPI_USR) {}

    route_sample_t sample;
    sample.after_transfer = pending_interrupts();
    /* An acknowledgement on the other controller must leave this IRQ up. */
    REG_WRITE(SPI_DMA_INT_CLR_REG(other), SPI_TRANS_DONE_INT_CLR);
    sample.raw_after_other_ack = REG_READ(SPI_DMA_INT_RAW_REG(spi));
    sample.after_other_ack = pending_interrupts();
    REG_WRITE(SPI_DMA_INT_CLR_REG(spi), SPI_TRANS_DONE_INT_CLR);
    sample.after_own_ack = pending_interrupts();
    __asm__ volatile("wsr.ps %0; rsync" :: "a"(previous_ps) : "memory");
    return sample;
}

static bool check_route(unsigned int spi, route_sample_t sample, uint32_t own, uint32_t both)
{
    const bool raw = (sample.raw_after_other_ack & SPI_TRANS_DONE_INT_RAW) != 0;
    const uint32_t transfer = sample.after_transfer & both;
    const uint32_t other_ack = sample.after_other_ack & both;
    const uint32_t own_ack = sample.after_own_ack & both;
    printf("GPSPI_IRQ host=%u own=%08lx transfer=%08lx other_ack=%08lx own_ack=%08lx raw=%d\n",
           spi, (unsigned long)own, (unsigned long)transfer, (unsigned long)other_ack,
           (unsigned long)own_ack, raw);
    return raw && transfer == own && other_ack == own && own_ack == 0;
}

void app_main(void)
{
    periph_module_enable(PERIPH_SPI2_MODULE);
    periph_module_enable(PERIPH_SPI3_MODULE);
    periph_module_reset(PERIPH_SPI2_MODULE);
    periph_module_reset(PERIPH_SPI3_MODULE);

    intr_handle_t spi2_intr;
    intr_handle_t spi3_intr;
    ESP_ERROR_CHECK(esp_intr_alloc(ETS_SPI2_INTR_SOURCE, ESP_INTR_FLAG_LEVEL1,
                                  unexpected_isr, (void *)SPI2_INDEX, &spi2_intr));
    ESP_ERROR_CHECK(esp_intr_alloc(ETS_SPI3_INTR_SOURCE, ESP_INTR_FLAG_LEVEL1,
                                  unexpected_isr, (void *)SPI3_INDEX, &spi3_intr));
    const uint32_t spi2_bit = BIT(esp_intr_get_intno(spi2_intr));
    const uint32_t spi3_bit = BIT(esp_intr_get_intno(spi3_intr));
    const uint32_t both = spi2_bit | spi3_bit;
    for (unsigned int spi = SPI2_INDEX; spi <= SPI3_INDEX; spi++) {
        REG_WRITE(SPI_DMA_INT_CLR_REG(spi), SPI_TRANS_DONE_INT_CLR);
        REG_WRITE(SPI_DMA_INT_ENA_REG(spi), SPI_TRANS_DONE_INT_ENA);
    }
    const bool spi2_ok = check_route(SPI2_INDEX, sample_completion(SPI2_INDEX, SPI3_INDEX), spi2_bit, both);
    const bool spi3_ok = check_route(SPI3_INDEX, sample_completion(SPI3_INDEX, SPI2_INDEX), spi3_bit, both);
    printf("STAGE_PROBE_DONE gpspi_irq_route pass=%d\n", spi2_ok && spi3_ok);
}

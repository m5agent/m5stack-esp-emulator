/*
 * ESP32 SPI controller
 *
 * Copyright (c) 2019 Espressif Systems (Shanghai) Co. Ltd.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 or
 * (at your option) any later version.
 */

static void esp32c3_spi_txrx_buffer(ESP32C3SpiState *s,
                                    const void *tx, int tx_bytes,
                                    void *rx, int rx_bytes)
{
    int bytes = MAX(tx_bytes, rx_bytes);
    for (int i = 0; i < bytes; ++i) {
        uint8_t byte = 0;
        uint32_t res;
        if (i < tx_bytes) {
            memcpy(&byte, tx + i, 1);
        }
        if (s->m5_slave_transfer &&
            !esp32_gpio_get_line(s->m5_slave_cs)) {
            res = s->m5_slave_transfer(s->m5_slave_opaque, byte);
        } else {
            res = ssi_transfer(s->spi, byte);
        }
        if (i < rx_bytes) {
            memcpy(rx + i, &res, 1);
        }
    }
}

static void esp32c3_spi_dummy_cycles(ESP32C3SpiState *s, uint32_t dummy_bytes) {
    for (int i = 0; i < dummy_bytes; i++) {
        if (s->m5_slave_transfer &&
            !esp32_gpio_get_line(s->m5_slave_cs)) {
            s->m5_slave_transfer(s->m5_slave_opaque, 0);
        } else {
            ssi_transfer(s->spi, 0);
        }
    }
}

static void esp32c3_spi_perform_transaction(ESP32C3SpiState *s, ESP32C3SpiTransaction *t)
{
    /* Keep received radio bytes even if CS is raised before the FIFO read. */
    s->m5_rx_from_slave = s->m5_spi2 && s->m5_slave_transfer &&
                          !esp32_gpio_get_line(s->m5_slave_cs);
    if (s->xts_aes != NULL)
    {
        ESP32C3XtsAesClass *xts_aes_class = ESP32C3_XTS_AES_GET_CLASS(s->xts_aes);
        bool man_enc_enabled = xts_aes_class->is_manual_enc_enabled(s->xts_aes);

        if (man_enc_enabled && xts_aes_class->is_ciphertext_spi_visible(s->xts_aes) && (t->cmd == CMD_PP)) {
            xts_aes_class->read_ciphertext(s->xts_aes, t->data, &(t->tx_bytes), &(t->addr), &(t->addr_bytes));
        }
    }
    qemu_set_irq(s->cs_gpio[0], 0);
    esp32c3_spi_txrx_buffer(s, &t->cmd, t->cmd_bytes, NULL, 0);
    esp32c3_spi_txrx_buffer(s, &t->addr, t->addr_bytes, NULL, 0);
    if (t->has_mode_byte) {
        esp32c3_spi_txrx_buffer(s, &t->mode_byte, 1, NULL, 0);
    }
    esp32c3_spi_dummy_cycles(s, t->dummy_bytes + t->extra_dummy_bytes);
    esp32c3_spi_txrx_buffer(s, t->data, t->tx_bytes, t->data, t->rx_bytes);
    if (s->m5_sink && t->tx_bytes &&
        (!s->m5_slave_transfer ||
         esp32_gpio_get_line(s->m5_slave_cs))) {
        s->m5_sink(s->m5_sink_opaque, t->data, t->tx_bytes,
                   !esp32_gpio_get_line(16));
    }
    if (getenv("M5SW_SPI_DATA_TRACE") && t->rx_bytes) {
        const uint8_t *p = t->data;
        fprintf(stderr, "[c6-spi] data cmd=0x%02x addr=0x%08x:",
                t->cmd, t->addr);
        for (unsigned i = 0; i < MIN(t->rx_bytes, 16u); i++) {
            fprintf(stderr, " %02x", p[i]);
        }
        fprintf(stderr, "\n");
    }
    qemu_set_irq(s->cs_gpio[0], 1);
    s->dma_int_raw |= SPI_TRANS_DONE;
    esp32c3_spi_update_irq(s);
}


static inline void esp32c3_spi_get_addr(ESP32C3SpiState *s, uint32_t* addr, uint32_t* len)
{
    const uint32_t address = FIELD_EX32(s->mem_addr, SPI_MEM_ADDR, USR_ADDR_VALUE);
    /* SPI Flash expects the address to be sent with MSB first. We make the assumption that
     * the host computer uses a little-endian CPU. */
    *addr = bswap32(address);

    const uint32_t address_len = FIELD_EX32(s->mem_user1, SPI_MEM_USER1, USR_ADDR_BITLEN);
    *len = (address_len + 1) / 8;
}

static inline void esp32c3_spi_get_dummy(ESP32C3SpiState *s, uint32_t* len)
{
    const uint32_t dummy_count = FIELD_EX32(s->mem_user1, SPI_MEM_USER1, USR_DUMMY_CYCLELEN);

    /* Dummy cycles are interpreted as bytes by the emulated SPI Flash. As such, we shall convert
     * our dummy cycles count in bytes, rounding it up. For example:
     * 0 cycles = 0 byte
     * 1 cycle = 1 byte
     * ...
     * 8 cycles = 1 byte
     * 9 cycles = 2 bytes
     * etc..
     */
    *len = (dummy_count + 7) / 8;
}

static void esp32c3_spi_begin_transaction(ESP32C3SpiState *s)
{
    uint8_t dma_buffer[4096];
    uint32_t dma_channel = 0;
    bool dma_tx = s->m5_spi2 && s->gdma &&
        (s->dma_conf & DMA_TX_ENA);
    bool dma_rx = s->m5_spi2 && s->gdma &&
        (s->dma_conf & DMA_RX_ENA);
    ESP32C3SpiTransaction t = {
        .data = s->data_reg
     };

    /* Get the number of bytes to read from the device */
    if (s->mem_user & R_SPI_MEM_USER_USR_MISO_MASK) {
        t.rx_bytes = FIELD_EX32(s->mem_miso_len, SPI_MEM_MISO_DLEN, USR_MISO_DBITLEN);
        t.rx_bytes = (t.rx_bytes + 1) / 8;
    }

    /* and the number of bytes to write to the device */
    if (s->mem_user & R_SPI_MEM_USER_USR_MOSI_MASK) {
        t.tx_bytes = FIELD_EX32(s->mem_mosi_len, SPI_MEM_MOSI_DLEN, USR_MOSI_DBITLEN);
        t.tx_bytes = (t.tx_bytes + 1) / 8;
    }

    /* Get the command and its length, in bytes
     * In theory we should test mem_user's command bit. In practice, if we do, `esptool`
     * cannot write flash successfully and detects an error */
    if (!s->m5_spi2 || (s->mem_user & R_SPI_MEM_USER_USR_COMMAND_MASK)) {
        t.cmd = FIELD_EX32(s->mem_user2, SPI_MEM_USER2, USR_COMMAND_VALUE);
        t.cmd_bytes =
            FIELD_EX32(s->mem_user2, SPI_MEM_USER2, USR_COMMAND_BITLEN);
        t.cmd_bytes = (t.cmd_bytes + 1) / 8;
    }

    /* Get the address and its length, in bytes */
    if (s->mem_user & R_SPI_MEM_USER_USR_ADDR_MASK) {
        esp32c3_spi_get_addr(s, &t.addr, &t.addr_bytes);
        if (t.addr_bytes > 0 && t.addr_bytes <= 4) {
            t.addr = t.addr >> (32 - t.addr_bytes * 8);
        }

        /* Only calculate and include dummy cycles when the USR_DUMMY bit is set! */
        if (s->mem_user & R_SPI_MEM_USER_USR_DUMMY_MASK) {
            esp32c3_spi_get_dummy(s, &t.dummy_bytes);
        }
    }

    /*
     * C6's FREAD_DIO/FREAD_QIO path uses four address bytes followed by a
     * mode byte.  The generic SPI helper only models the address phase, so
     * append the mode byte explicitly when the controller omitted USR_DUMMY.
     */
    if ((t.cmd == 0xbb || t.cmd == 0xeb) && t.dummy_bytes == 0) {
        t.mode_byte = 0;
        t.has_mode_byte = true;
    }

    /*
     * The SSI flash device counts QIO mode/dummy clocks as header bytes.
     * C6 SPI1 uses four address bytes, so none of those bytes represents
     * this header. ISSI consumes three header bytes; Winbond/GigaDevice
     * consume five. Bridge the attached model's header before receiving
     * data, without changing guest registers or the shared SPI2 bus.
     */
    if (!s->m5_spi2 && t.cmd == 0xeb && t.addr_bytes && t.rx_bytes) {
        uint32_t sent_header = t.dummy_bytes + (t.has_mode_byte ? 1 : 0);
        if (sent_header < s->flash_qio_header_bytes) {
            t.extra_dummy_bytes = s->flash_qio_header_bytes - sent_header;
        }
    }

    if (dma_tx &&
        esp_gdma_get_channel_periph(s->gdma, GDMA_SPI2,
                                    ESP_GDMA_OUT_IDX, &dma_channel)) {
        uint32_t requested = t.tx_bytes ? t.tx_bytes : sizeof(dma_buffer);
        uint32_t got = esp_gdma_complete_out_descriptor(
            s->gdma, dma_channel, dma_buffer,
            MIN(requested, sizeof(dma_buffer)));
        t.data = dma_buffer;
        t.tx_bytes = got;
    }

    if (s->m5_spi2 && getenv("M5SW_C6_SPI2_TRACE")) {
        fprintf(stderr,
                "[c6-spi2-xfer] cmd=0x%02x addr_bytes=%u tx=%u rx=%u "
                "user=0x%08x first=%02x dc=%d cs17=%d cs23=%d\n",
                t.cmd, t.addr_bytes, t.tx_bytes, t.rx_bytes, s->mem_user,
                t.tx_bytes ? ((uint8_t *)t.data)[0] : 0,
                esp32_gpio_get_line(16), esp32_gpio_get_line(17),
                esp32_gpio_get_line(23));
    }

    if (getenv("M5SW_SPI_TRACE")) {
        fprintf(stderr,
                "[c6-spi] tx cmd=0x%02x cmd_bytes=%u addr=0x%08x "
                "addr_bytes=%u dummy=%u tx=%u rx=%u usr=0x%08x "
                "mem_addr=0x%08x user1=0x%08x\n",
                t.cmd, t.cmd_bytes, t.addr, t.addr_bytes, t.dummy_bytes,
                t.tx_bytes, t.rx_bytes, s->mem_user, s->mem_addr, s->mem_user1);
    }

    esp32c3_spi_perform_transaction(s, &t);

    if (dma_rx && t.rx_bytes &&
        esp_gdma_get_channel_periph(s->gdma, GDMA_SPI2,
                                    ESP_GDMA_IN_IDX, &dma_channel)) {
        esp_gdma_complete_in_descriptor(
            s->gdma, dma_channel, t.data, t.rx_bytes);
    }
}

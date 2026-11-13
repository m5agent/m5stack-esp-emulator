
static void esp32c3_spi_write(void *opaque, hwaddr addr,
                       uint64_t value, unsigned int size)
{
    ESP32C3SpiState *s = ESP32C3_SPI(opaque);
    uint32_t wvalue = (uint32_t) value;

    if (s->m5_spi2 && getenv("M5SW_C6_SPI2_TRACE")) {
        fprintf(stderr, "[c6-spi2] wr 0x%03" HWADDR_PRIx " = 0x%08x\n",
                addr, wvalue);
    }

#if SPI1_DEBUG
    info_report("[SPI1] Writing 0x%lx = %08lx", addr, value);
#endif

    if (s->m5_spi2) {
        switch (addr) {
        case 0x10:
            s->mem_user = wvalue;
            return;
        case 0x14:
            s->mem_user1 = wvalue;
            return;
        case 0x18:
            s->mem_user2 = wvalue;
            return;
        case 0x1c:
            s->mem_mosi_len = wvalue;
            s->mem_miso_len = wvalue;
            return;
        case 0x20:
            s->c6_misc = wvalue;
            return;
        case 0x24:
            s->c6_din_mode = wvalue;
            return;
        case 0x28:
            s->c6_din_num = wvalue;
            return;
        case 0x2c:
            s->c6_dout_mode = wvalue;
            return;
        case R_SPI_DMA_CONF:
            s->dma_conf = wvalue;
            return;
        }
    }

    switch (addr) {
        case A_SPI_MEM_CMD:
            if ((wvalue & R_SPI_MEM_CMD_USR_MASK) ||
                (s->m5_spi2 && (wvalue & (1u << 24)))) {
                s->dma_int_raw &= ~BIT(0);
                esp32c3_spi_begin_transaction(s);
            } else if (!s->m5_spi2) {
                esp32c3_spi_special_command(s, wvalue);
            }
            /* SPI2 UPDATE latches configuration; it is not a flash command. */
            break;
        case 0x34:
            s->dma_int_ena = wvalue;
            esp32c3_spi_update_irq(s);
            break;
        case 0x38:
            s->dma_int_raw &= ~wvalue;
            esp32c3_spi_update_irq(s);
            break;
        case 0x3c:
            break;
        case 0x44:
            s->dma_int_raw |= wvalue;
            esp32c3_spi_update_irq(s);
            break;
        case A_SPI_MEM_ADDR:
            s->mem_addr = wvalue;
            break;
        case A_SPI_MEM_CTRL:
            s->mem_ctrl = wvalue;
            break;
        case A_SPI_MEM_CTRL1:
            s->mem_ctrl1 = wvalue;
            break;
        case A_SPI_MEM_CTRL2:
            s->mem_ctrl2 = wvalue;
            break;
        case A_SPI_MEM_CLOCK:
            s->mem_clock = wvalue;
            break;
        case A_SPI_MEM_USER:
            s->mem_user = wvalue;
            break;
        case A_SPI_MEM_USER1:
            s->mem_user1 = wvalue;
            break;
        case A_SPI_MEM_USER2:
            s->mem_user2 = wvalue;
            break;
        case A_SPI_MEM_MISO_DLEN:
            s->mem_miso_len = wvalue;
            break;
        case A_SPI_MEM_MOSI_DLEN:
            s->mem_mosi_len = wvalue;
            break;
        case A_SPI_MEM_RD_STATUS:
            s->mem_rd_st = wvalue;
            break;
        case A_SPI_MEM_W0...A_SPI_MEM_W15:
            s->data_reg[(addr - A_SPI_MEM_W0) / sizeof(uint32_t)] = wvalue;
            break;
        case A_SPI_MEM_SUS_STATUS:
            s->mem_sus_st = wvalue;
            break;
        default:
#if SPI1_WARNING
            warn_report("[SPI1] Unsupported write to 0x%lx (%08lx)", addr, value);
#endif
            break;
    }

    if (s->m5_spi2 && addr >= 0x98 && addr < 0xd8) {
        s->data_reg[(addr - 0x98) / sizeof(uint32_t)] = wvalue;
    }

}

static void esp32c3_spi_reset_hold(Object *obj, ResetType type)
{
    ESP32C3SpiState *s = ESP32C3_SPI(obj);
    memset(s->data_reg, 0, ESP32C3_SPI_BUF_WORDS * sizeof(uint32_t));
    s->mem_ctrl1 = FIELD_DP32(s->mem_ctrl1, SPI_MEM_CTRL1, CS_HOLD_DLY_RES, 0x3ff);
    s->mem_clock = FIELD_DP32(s->mem_clock, SPI_MEM_CLOCK, CLKCNT_N, 3);
    s->mem_clock = FIELD_DP32(s->mem_clock, SPI_MEM_CLOCK, CLKCNT_H, 1);
    s->mem_clock = FIELD_DP32(s->mem_clock, SPI_MEM_CLOCK, CLKCNT_L, 3);

    s->mem_user = FIELD_DP32(s->mem_user, SPI_MEM_USER, USR_COMMAND, 1);

    s->mem_user1 = FIELD_DP32(s->mem_user1, SPI_MEM_USER1, USR_ADDR_BITLEN, 23);
    s->mem_user1 = FIELD_DP32(s->mem_user1, SPI_MEM_USER1, USR_DUMMY_CYCLELEN, 7);

    s->mem_user2 = FIELD_DP32(s->mem_user2, SPI_MEM_USER2, USR_COMMAND_BITLEN, 7);
    s->dma_int_ena = 0;
    s->dma_int_raw = 0;
    s->dma_conf = 0;
    s->m5_rx_from_slave = false;
    s->c6_misc = 0;
    s->c6_din_mode = 0;
    s->c6_din_num = 0;
    s->c6_dout_mode = 0;

    /* In case more registers are supported in the future (MEM_MISC, MEM_TX_CRC, ...)
     * update this function with their default values */
}

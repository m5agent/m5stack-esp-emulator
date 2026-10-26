/*
 * SPI-mode SD card protocol model backed by a raw sector image.
 *
 * The model implements the command/data frames used by ESP-IDF's SDSPI host:
 * CMD0/8/16/17/24/55/58/59, ACMD41 and single-block read/write.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "m5stopwatch.h"

#define SD_BLOCK_SIZE 512
#define SD_RESP_SIZE  1024

typedef enum {
    SD_IDLE,
    SD_COMMAND,
    SD_RESPONSE,
    SD_WAIT_DATA,
    SD_WRITE_DATA,
    SD_WRITE_CRC,
} SdSpiMode;

typedef struct M5SpiSdState {
    FILE *image;
    uint64_t image_size;
    SdSpiMode mode;
    uint8_t command[6];
    uint8_t command_pos;
    uint8_t response[SD_RESP_SIZE];
    uint32_t response_pos;
    uint32_t response_len;
    uint32_t sector;
    uint8_t block[SD_BLOCK_SIZE];
    uint32_t block_pos;
    uint8_t cid[16];
    uint8_t csd[16];
    uint8_t crc_pos;
    SdSpiMode next_mode;
    bool app_cmd;
    bool trace;
} M5SpiSdState;

static uint8_t sd_crc7(const uint8_t *data, uint32_t size)
{
    uint8_t crc = 0;
    for (uint32_t i = 0; i < size; i++) {
        for (int bit = 7; bit >= 0; bit--) {
            crc <<= 1;
            if ((crc >> 7) ^ ((data[i] >> bit) & 1)) {
                crc ^= 0x89;
            }
        }
    }
    return crc;
}

static uint16_t sd_crc16(const uint8_t *data, uint32_t size)
{
    uint16_t crc = 0;
    for (uint32_t i = 0; i < size; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
        }
    }
    return (crc >> 8) | (crc << 8);
}

static void sd_set_identity(M5SpiSdState *s, uint64_t size)
{
    uint32_t csize;
    uint32_t sectsize = 63;
    uint32_t wpsize = 255;

    memset(s->cid, 0, sizeof(s->cid));
    s->cid[0] = 0xaa;
    s->cid[1] = 'X';
    s->cid[2] = 'Y';
    memcpy(&s->cid[3], "QEMU!", 5);
    s->cid[8] = 0x01;
    s->cid[9] = 0xde;
    s->cid[10] = 0xad;
    s->cid[11] = 0xbe;
    s->cid[12] = 0xef;
    s->cid[13] = 0x00;
    s->cid[14] = 0x62;
    s->cid[15] = (sd_crc7(s->cid, 15) << 1) | 1;

    if (!size) {
        size = 8 * 1024 * 1024;
    }
    csize = (size >> 18) - 1;
    memset(s->csd, 0, sizeof(s->csd));
    s->csd[0] = 0x00;
    s->csd[1] = 0x26;
    s->csd[3] = 0x32;
    s->csd[4] = 0x5f;
    s->csd[5] = 0x50 | 9;
    s->csd[6] = 0xe0 | ((csize >> 10) & 0x03);
    s->csd[7] = (csize >> 2) & 0xff;
    s->csd[8] = 0x3f | ((csize << 6) & 0xc0);
    s->csd[9] = 0xff;
    s->csd[10] = 0x40 | 0x80 | (sectsize >> 1);
    s->csd[11] = 0x80 | wpsize;
    s->csd[12] = 0x92;
    s->csd[13] = 0x60;
    s->csd[15] = (sd_crc7(s->csd, 15) << 1) | 1;
}

static uint8_t sd_spi_transfer(void *opaque, uint8_t tx);

static const M5SpiSlaveOps sd_spi_ops = {
    .set_cs = NULL,
    .transfer = sd_spi_transfer,
};

static void sd_set_response_lead(M5SpiSdState *s, const uint8_t *data,
                                 uint32_t size, uint32_t lead)
{
    size = MIN(size, sizeof(s->response) - lead);
    memset(s->response, 0xff, lead);
    s->response_len = size + lead;
    if (size) {
        memcpy(&s->response[lead], data, size);
    }
    s->response_pos = 0;
    s->next_mode = SD_IDLE;
    s->mode = size ? SD_RESPONSE : SD_IDLE;
}

static void sd_set_response(M5SpiSdState *s, const uint8_t *data,
                            uint32_t size)
{
    sd_set_response_lead(s, data, size, 1);
}

static void sd_set_read_response(M5SpiSdState *s, const uint8_t *data,
                                 uint32_t size)
{
    sd_set_response_lead(s, data, size, 2);
}

static void sd_set_response_next(M5SpiSdState *s, const uint8_t *data,
                                 uint32_t size, SdSpiMode next)
{
    sd_set_response(s, data, size);
    s->next_mode = next;
}

static void sd_r1(M5SpiSdState *s, uint8_t value)
{
    sd_set_response(s, &value, 1);
}

static uint32_t sd_arg(const uint8_t *cmd)
{
    return ((uint32_t)cmd[1] << 24) | ((uint32_t)cmd[2] << 16) |
           ((uint32_t)cmd[3] << 8) | cmd[4];
}

static void sd_execute(M5SpiSdState *s)
{
    uint8_t cmd = s->command[0] & 0x3f;
    uint32_t arg = sd_arg(s->command);
    bool app_cmd = s->app_cmd;
    uint8_t r7[5] = { 0x01, 0x00, 0x00, 0x01, 0xaa };
    uint8_t r3[5] = { 0x00, 0x00, 0xff, 0x80, 0x00 };
    uint8_t read_resp[SD_BLOCK_SIZE + 4];

    if (s->trace) {
        fprintf(stderr, "[sd-spi] cmd=%u arg=%08x app=%d\n",
                cmd, arg, s->app_cmd);
    }
    if (cmd != 55) {
        s->app_cmd = false;
    }
    switch (cmd) {
    case 0: /* GO_IDLE_STATE */
        sd_r1(s, 0x01);
        break;
    case 1: /* SEND_OP_COND */
        sd_r1(s, 0x00);
        break;
    case 8: /* SEND_IF_COND */
        sd_set_response(s, r7, sizeof(r7));
        break;
    case 9:   /* SEND_CSD */
    case 10:  /* SEND_CID */
    {
        uint8_t data[20];
        const uint8_t *identity = cmd == 9 ? s->csd : s->cid;
        uint16_t crc = sd_crc16(identity, 16);
        data[0] = 0x00;
        data[1] = 0xfe;
        memcpy(&data[2], identity, 16);
        data[18] = crc & 0xff;
        data[19] = crc >> 8;
        sd_set_read_response(s, data, sizeof(data));
        break;
    }
    case 12: /* STOP_TRANSMISSION */
    case 16: /* SET_BLOCKLEN */
    case 59: /* CRC_ON_OFF */
        sd_r1(s, 0x00);
        break;
    case 13: /* SEND_STATUS */
        if (app_cmd) {
            uint8_t status[68];
            uint16_t crc;
            memset(status, 0, sizeof(status));
            status[0] = 0x00;
            status[1] = 0xfe;
            crc = sd_crc16(&status[2], 64);
            status[66] = crc & 0xff;
            status[67] = crc >> 8;
            sd_set_read_response(s, status, sizeof(status));
        } else {
            uint8_t status[2] = { 0x00, 0x00 }; /* R1 + card status */
            sd_set_response(s, status, sizeof(status));
        }
        break;
    case 17: /* READ_SINGLE_BLOCK */
        s->sector = arg / SD_BLOCK_SIZE;
        memset(read_resp, 0xff, sizeof(read_resp));
        read_resp[0] = 0x00;
        read_resp[1] = 0xfe;
        memset(s->block, 0, sizeof(s->block));
        if (s->image) {
            fseeko(s->image, (off_t)s->sector * SD_BLOCK_SIZE, SEEK_SET);
            fread(s->block, 1, sizeof(s->block), s->image);
        }
        memcpy(&read_resp[2], s->block, sizeof(s->block));
        {
            uint16_t crc = sd_crc16(s->block, sizeof(s->block));
            read_resp[SD_BLOCK_SIZE + 2] = crc & 0xff;
            read_resp[SD_BLOCK_SIZE + 3] = crc >> 8;
        }
        sd_set_read_response(s, read_resp, sizeof(read_resp));
        break;
    case 24: /* WRITE_SINGLE_BLOCK */
        s->sector = arg / SD_BLOCK_SIZE;
        s->block_pos = 0;
        s->crc_pos = 0;
        {
            uint8_t r1 = 0x00;
            sd_set_response_next(s, &r1, 1, SD_WAIT_DATA);
        }
        break;
    case 41: /* ACMD41 */
        sd_r1(s, 0x00);
        break;
    case 51: /* ACMD51: SEND_SCR */
        if (app_cmd) {
            uint8_t scr[12] = {
                0x00, 0xfe,             /* R1 + data token */
                0x00, 0x00, 0x00, 0x00, /* SCR structure/version/data status */
                0x00, 0x00, 0x00, 0x00, /* capability bits: 1-bit SPI */
                0x00, 0x00,
                0x00, 0x00,
            };
            uint16_t crc = sd_crc16(&scr[2], 8);
            scr[10] = crc & 0xff;
            scr[11] = crc >> 8;
            sd_set_read_response(s, scr, sizeof(scr));
        } else {
            sd_r1(s, 0x05);
        }
        break;
    case 55: /* APP_CMD */
        s->app_cmd = true;
        sd_r1(s, 0x01);
        break;
    case 58: /* READ_OCR */
        sd_set_response(s, r3, sizeof(r3));
        break;
    default:
        if (s->trace) {
            fprintf(stderr, "[sd-spi] unsupported cmd=%u\n", cmd);
        }
        sd_r1(s, 0x05);
        break;
    }
}

static uint8_t sd_spi_transfer(void *opaque, uint8_t tx)
{
    M5SpiSdState *s = opaque;
    uint8_t out = 0xff;
    uint8_t result;

    switch (s->mode) {
    case SD_RESPONSE:
        out = s->response[s->response_pos++];
        if (s->response_pos >= s->response_len) {
            s->mode = s->next_mode;
            s->next_mode = SD_IDLE;
            s->response_len = 0;
            s->response_pos = 0;
        }
        break;
    case SD_COMMAND:
        s->command[s->command_pos++] = tx;
        if (s->command_pos == sizeof(s->command)) {
            s->command_pos = 0;
            sd_execute(s);
        }
        break;
    case SD_WAIT_DATA:
        if (tx == 0xfe) {
            out = 0xff;
            s->mode = SD_WRITE_DATA;
            s->block_pos = 0;
        }
        break;
    case SD_WRITE_DATA:
        s->block[s->block_pos++] = tx;
        if (s->block_pos == SD_BLOCK_SIZE) {
            s->mode = SD_WRITE_CRC;
            s->crc_pos = 0;
        }
        break;
    case SD_WRITE_CRC:
        if (++s->crc_pos >= 2) {
            if (s->image) {
                fseeko(s->image, (off_t)s->sector * SD_BLOCK_SIZE, SEEK_SET);
                fwrite(s->block, 1, sizeof(s->block), s->image);
                fflush(s->image);
            }
            result = 0x05;
            s->response[0] = result;
            s->response_pos = 0;
            s->response_len = 1;
            s->next_mode = SD_IDLE;
            s->mode = SD_RESPONSE;
        }
        break;
    case SD_IDLE:
    default:
        if (tx == 0xff) {
            out = 0xff;
        } else if ((tx & 0xc0) == 0x40) {
            s->command[0] = tx;
            s->command_pos = 1;
            s->mode = SD_COMMAND;
        }
        break;
    }
    if (s->trace) {
        fprintf(stderr, "[sd-spi] tx=%02x rx=%02x mode=%d\n",
                tx, out, s->mode);
    }
    return out;
}

void m5_spi_sd_attach(DeviceState *spi, int cs_pin)
{
    M5SpiSdState *s = g_new0(M5SpiSdState, 1);
    const char *path = getenv("M5SW_SPI_SD_IMAGE");

    s->trace = getenv("M5SW_SPI_SD_TRACE") != NULL;
    if (path) {
        s->image = fopen(path, "r+b");
        if (s->image) {
            fseeko(s->image, 0, SEEK_END);
            s->image_size = ftello(s->image);
            fseeko(s->image, 0, SEEK_SET);
        }
    }
    sd_set_identity(s, s->image_size);
    esp32s3_gpspi_attach_spi_slave(spi, &sd_spi_ops, s, cs_pin);
}

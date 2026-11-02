/*
 * M5StickT2 (K016-T2) virtual-device probe.
 *
 * This is a tiny freestanding ESP32 image built with the Espressif
 * xtensa-esp-elf toolchain and loaded by QEMU with -kernel.  It drives the
 * same memory-mapped controllers a real firmware uses:
 *   - UART0 FIFO for the probe markers,
 *   - GPIO bit-banged I2C on SDA G21 / SCL G22 for the FLIR Lepton CCI
 *     (0x2A) and the I2C encoder (0x30),
 *   - the classic HSPI controller for the Lepton VoSPI stream (CS G0,
 *     VSYNC G38, RESET G26),
 *   - the classic VSPI controller for the ST7789 135x240 panel
 *     (MOSI G15, SCK G13, CS G5, DC G23, RST G18).
 *
 * The thermal frame is rebuilt from real VoSPI packet payloads received from
 * the sensor model.  Nothing is injected into the frame path by the host; the
 * model's deterministic fixture seed and the QOM counters are the only host
 * inputs, and the host-side oracle rebuilds the same fixture to compare the
 * on-guest digest.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include <stdint.h>

#define UART0_BASE 0x3FF40000u
#define GPIO_BASE  0x3FF44000u
#define SPI2_BASE  0x3FF64000u
#define SPI3_BASE  0x3FF65000u

#define GPIO_OUT_W1TS  0x08u
#define GPIO_OUT_W1TC  0x0Cu
#define GPIO_OUT1_W1TS 0x14u
#define GPIO_OUT1_W1TC 0x18u
#define GPIO_EN_W1TS   0x24u
#define GPIO_EN_W1TC   0x28u
#define GPIO_IN        0x3Cu
#define GPIO_IN1       0x40u

#define SPI_CMD       0x00u
#define SPI_USER      0x1Cu
#define SPI_MOSI_DLEN 0x28u
#define SPI_MISO_DLEN 0x2Cu
#define SPI_USER2     0x24u
#define SPI_W0        0x80u

#define SPI_USER_MISO  (1u << 28)
#define SPI_USER_MOSI  (1u << 27)
#define SPI_CMD_USR    (1u << 18)

#define PIN_I2C_SDA 21
#define PIN_I2C_SCL 22
#define PIN_LEP_CS 0
#define PIN_LEP_VSYNC 38
#define PIN_LEP_RESET 26
#define PIN_LCD_MOSI 15
#define PIN_LCD_SCK 13
#define PIN_LCD_CS 5
#define PIN_LCD_DC 23
#define PIN_LCD_RST 18

#define LEPTON_CCI_ADDR 0x2Au
#define ENCODER_ADDR 0x30u

#define FLIR_W 160
#define FLIR_H 120
#define FLIR_SEGMENTS 4
#define FLIR_PACKETS_PER_SEGMENT 60
#define FLIR_PACKET_BYTES 164

#define LCD_W 135
#define LCD_H 240

static volatile uint32_t *const gpio = (volatile uint32_t *)GPIO_BASE;
static volatile uint32_t *const uart0 = (volatile uint32_t *)UART0_BASE;
static volatile uint32_t *const spi2 = (volatile uint32_t *)SPI2_BASE;
static volatile uint32_t *const spi3 = (volatile uint32_t *)SPI3_BASE;

static const char *hex_digit = "0123456789abcdef";

/* ------------------------------------------------------------------ */
/* Simple string/stdio helpers                                         */
/* ------------------------------------------------------------------ */

void *memset(void *dst, int value, unsigned int len)
{
    uint8_t *p = dst;
    while (len--) {
        *p++ = (uint8_t)value;
    }
    return dst;
}

void *memcpy(void *dst, const void *src, unsigned int len)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    while (len--) {
        *d++ = *s++;
    }
    return dst;
}

static void uart_putc(char c)
{
    *uart0 = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

static void uart_hex32(uint32_t value)
{
    /* Keep this unrolled: on this toolchain a constant-trip count loop is
     * turned into a zero-overhead LOOP whose UART stores behave differently
     * inside the probe's -kernel environment; explicit calls are reliable. */
    uart_puts("0x");
    uart_putc(hex_digit[(value >> 28) & 0xf]);
    uart_putc(hex_digit[(value >> 24) & 0xf]);
    uart_putc(hex_digit[(value >> 20) & 0xf]);
    uart_putc(hex_digit[(value >> 16) & 0xf]);
    uart_putc(hex_digit[(value >> 12) & 0xf]);
    uart_putc(hex_digit[(value >> 8) & 0xf]);
    uart_putc(hex_digit[(value >> 4) & 0xf]);
    uart_putc(hex_digit[value & 0xf]);
}

static void uart_u32(uint32_t value)
{
    char buf[12];
    int pos = 0;
    if (value == 0) {
        uart_putc('0');
        return;
    }
    while (value && pos < (int)sizeof(buf)) {
        buf[pos++] = (char)('0' + value % 10);
        value /= 10;
    }
    while (pos--) {
        uart_putc(buf[pos]);
    }
}

static void uart_u16_hex4(uint32_t value)
{
    uart_putc(hex_digit[(value >> 12) & 0xf]);
    uart_putc(hex_digit[(value >> 8) & 0xf]);
    uart_putc(hex_digit[(value >> 4) & 0xf]);
    uart_putc(hex_digit[value & 0xf]);
}

static void delay_ticks(uint32_t ticks)
{
    for (volatile uint32_t i = 0; i < ticks; i++) {
        __asm__ volatile("" ::: "memory");
    }
}

/* ------------------------------------------------------------------ */
/* GPIO helpers                                                        */
/* ------------------------------------------------------------------ */

static void gpio_enable_out(int pin)
{
    gpio[GPIO_EN_W1TS / 4] = 1u << pin;
}

static void gpio_disable_out(int pin)
{
    gpio[GPIO_EN_W1TC / 4] = 1u << pin;
}

static void gpio_write(int pin, int level)
{
    unsigned reg = pin < 32
        ? (level ? GPIO_OUT_W1TS : GPIO_OUT_W1TC)
        : (level ? GPIO_OUT1_W1TS : GPIO_OUT1_W1TC);
    gpio[reg / 4] = 1u << (pin & 31);
}

static int gpio_read(int pin)
{
    unsigned reg = pin < 32 ? GPIO_IN : GPIO_IN1;
    return (int)((gpio[reg / 4] >> (pin & 31)) & 1);
}

/* ------------------------------------------------------------------ */
/* Bit-banged I2C on G21/G22 (the board's shared 21/22 bus bridge)     */
/* ------------------------------------------------------------------ */

static void i2c_delay(void)
{
    delay_ticks(80);
}

static void sda_drive(int level)
{
    gpio_enable_out(PIN_I2C_SDA);
    gpio_write(PIN_I2C_SDA, level);
    i2c_delay();
}

static void sda_release(void)
{
    gpio_disable_out(PIN_I2C_SDA);
    i2c_delay();
}

static void scl_write(int level)
{
    gpio_enable_out(PIN_I2C_SCL);
    gpio_write(PIN_I2C_SCL, level);
    i2c_delay();
}

static int sda_read(void)
{
    return gpio_read(PIN_I2C_SDA);
}

static void i2c_idle_bus(void)
{
    gpio_enable_out(PIN_I2C_SCL);
    gpio_write(PIN_I2C_SCL, 1);
    sda_drive(1);
    i2c_delay();
}

static void i2c_start(void)
{
    sda_drive(1);
    scl_write(1);
    sda_drive(0);
    scl_write(0);
}

static void i2c_stop(void)
{
    sda_drive(0);
    scl_write(1);
    sda_release();
    i2c_delay();
    i2c_idle_bus();
}

static int i2c_write_byte(uint8_t value)
{
    for (int bit = 7; bit >= 0; bit--) {
        sda_drive((value >> bit) & 1);
        scl_write(1);
        scl_write(0);
    }
    sda_release();
    scl_write(1);
    int ack = sda_read() == 0;
    scl_write(0);
    return ack;
}

static uint8_t i2c_read_byte(int ack)
{
    uint8_t value = 0;
    sda_release();
    for (int bit = 0; bit < 8; bit++) {
        scl_write(1);
        value = (uint8_t)((value << 1) | (sda_read() & 1));
        scl_write(0);
    }
    if (ack) {
        sda_drive(0);
    } else {
        sda_release();
    }
    scl_write(1);
    scl_write(0);
    sda_release();
    return value;
}

/* Returns true when the address was acknowledged. */
static int i2c_begin(uint8_t address)
{
    i2c_start();
    return i2c_write_byte(address);
}

/* ------------------------------------------------------------------ */
/* FLIR Lepton CCI (16-bit register address, 16-bit data words)        */
/* ------------------------------------------------------------------ */

static int cci_write_reg(uint16_t reg, const uint16_t *words, int count)
{
    if (!i2c_begin(LEPTON_CCI_ADDR << 1)) {
        i2c_stop();
        return 0;
    }
    i2c_write_byte((uint8_t)(reg >> 8));
    i2c_write_byte((uint8_t)reg);
    for (int i = 0; i < count; i++) {
        i2c_write_byte((uint8_t)(words[i] >> 8));
        i2c_write_byte((uint8_t)words[i]);
    }
    i2c_stop();
    return 1;
}

static int cci_read_reg(uint16_t reg, uint16_t *words, int count)
{
    if (!i2c_begin(LEPTON_CCI_ADDR << 1)) {
        i2c_stop();
        return 0;
    }
    i2c_write_byte((uint8_t)(reg >> 8));
    i2c_write_byte((uint8_t)reg);
    i2c_stop();
    if (!i2c_begin((LEPTON_CCI_ADDR << 1) | 1)) {
        i2c_stop();
        return 0;
    }
    for (int i = 0; i < count; i++) {
        uint8_t high = i2c_read_byte(1);
        uint8_t low = i2c_read_byte(i + 1 < count);
        words[i] = (uint16_t)((high << 8) | low);
    }
    i2c_stop();
    return 1;
}

static uint16_t cci_command_word(uint16_t command)
{
    uint16_t value = 0;
    cci_write_reg(0x0004, &command, 1);
    return value;
}

/* GET command: write command id, read DATA_LEN and DATA back. */
static int cci_get(uint16_t command, uint16_t *words, int max_words)
{
    uint16_t data_len = 0;
    uint16_t status = 0xffff;
    int words_read;

    if (!cci_write_reg(0x0004, &command, 1)) {
        return -1;
    }
    for (int retry = 0; retry < 100; retry++) {
        if (!cci_read_reg(0x0002, &status, 1)) {
            return -1;
        }
        if ((status & 1u) == 0) {
            break;
        }
    }
    if ((status & 1u) != 0) {
        return -1;
    }
    if (!cci_read_reg(0x0006, &data_len, 1)) {
        return -1;
    }
    words_read = data_len / 2;
    if (words_read > max_words || words_read < 0) {
        words_read = max_words;
    }
    if (words_read > 0) {
        if (!cci_read_reg(0x0008, words, words_read)) {
            return -1;
        }
    }
    return words_read;
}

/* SET command: write REG_DATA_LEN + data words, then the SET command id. */
static int cci_set(uint16_t command, const uint16_t *words, int count)
{
    uint16_t payload[8];
    if (count > 7) {
        count = 7;
    }
    payload[0] = (uint16_t)count;
    for (int i = 0; i < count; i++) {
        payload[i + 1] = words[i];
    }
    if (!cci_write_reg(0x0006, payload, count + 1)) {
        return 0;
    }
    uint16_t set_command = (uint16_t)((command & 0xfffc) | 1);
    return cci_write_reg(0x0004, &set_command, 1);
}

/* ------------------------------------------------------------------ */
/* I2C encoder at 0x30 (official M5-StickT example register protocol)  */
/* ------------------------------------------------------------------ */

static int encoder_read(int *increment, int *switch_state)
{
    uint8_t value = 0;
    uint8_t raw[2];

    *increment = 0;
    *switch_state = 0;
    if (!i2c_begin(ENCODER_ADDR << 1)) {
        i2c_stop();
        return 0;
    }
    i2c_write_byte(0x10);
    i2c_stop();
    if (!i2c_begin((ENCODER_ADDR << 1) | 1)) {
        i2c_stop();
        return 0;
    }
    value = i2c_read_byte(0);
    i2c_stop();
    *switch_state = value;

    if (!i2c_begin(ENCODER_ADDR << 1)) {
        i2c_stop();
        return 0;
    }
    i2c_write_byte(0x00);
    i2c_stop();
    if (!i2c_begin((ENCODER_ADDR << 1) | 1)) {
        i2c_stop();
        return 0;
    }
    raw[0] = i2c_read_byte(1);
    raw[1] = i2c_read_byte(0);
    i2c_stop();
    *increment = (int16_t)((raw[0] << 8) | raw[1]);
    return 1;
}

/* ------------------------------------------------------------------ */
/* Classic SPI controllers                                             */
/* ------------------------------------------------------------------ */

/* The ESP32 SPI FIFO is exposed as 32-bit W registers; byte accesses to the
 * register file are not usable for streaming, so pack/unpack little-endian
 * words explicitly. */
static void spi_prepare(volatile uint32_t *spi, const uint8_t *tx, int tx_len,
                        int rx_len)
{
    for (int k = 0; k < (tx_len + 3) / 4; k++) {
        uint32_t word = 0;
        for (int b = 0; b < 4; b++) {
            int index = k * 4 + b;
            if (index < tx_len) {
                word |= (uint32_t)tx[index] << (b * 8);
            }
        }
        spi[SPI_W0 / 4 + k] = word;
    }
    if (tx_len > 0) {
        spi[SPI_MOSI_DLEN / 4] = (uint32_t)(tx_len * 8 - 1);
    }
    if (rx_len > 0) {
        /*
     * The controller resets with SPI_USER2.COMMAND_BITLEN=4, so a USR
     * transaction would clock one command byte before the data phase; clear
     * it for pure data transfers.
     */
    spi[0x28 / 4] = 0;
    spi[SPI_USER2 / 4] = 0;
    spi[SPI_MISO_DLEN / 4] = (uint32_t)(rx_len * 8 - 1);
    }
    spi[SPI_USER / 4] = (tx_len > 0 ? SPI_USER_MOSI : 0)
                      | (rx_len > 0 ? SPI_USER_MISO : 0);
    spi[SPI_CMD / 4] = SPI_CMD_USR;
}

static void spi_rx(volatile uint32_t *spi, uint8_t *dst, int len)
{
    for (int i = 0; i < len; i++) {
        uint32_t word = spi[SPI_W0 / 4 + i / 4];
        dst[i] = (uint8_t)((word >> ((i & 3) * 8)) & 0xff);
    }
}

static void spi_tx(volatile uint32_t *spi, const uint8_t *src, int len)
{
    spi_prepare(spi, src, len, 0);
}

static void lepton_read_packet(uint8_t *packet)
{
    int remaining = FLIR_PACKET_BYTES;
    int offset = 0;
    while (remaining > 0) {
        int chunk = remaining > 64 ? 64 : remaining;
        spi_prepare(spi2, 0, 0, chunk);
        for (int i = 0; i < chunk; i++) {
            uint32_t word = spi2[SPI_W0 / 4 + i / 4];
            packet[offset + i] = (uint8_t)((word >> ((i & 3) * 8)) & 0xff);
        }
        offset += chunk;
        remaining -= chunk;
    }
}

static void lepton_reset_pulse(void)
{
    gpio_enable_out(PIN_LEP_RESET);
    gpio_write(PIN_LEP_RESET, 1);
    delay_ticks(200000);
    gpio_write(PIN_LEP_RESET, 0);
    delay_ticks(400000);
    gpio_write(PIN_LEP_RESET, 1);
    delay_ticks(200000);
}

/* Wait for a VSYNC low pulse and return after its rising edge. */
static int lepton_wait_vsync(uint32_t timeout)
{
    while (timeout--) {
        if (gpio_read(PIN_LEP_VSYNC) == 0) {
            break;
        }
    }
    if (timeout == 0) {
        return 0;
    }
    timeout = 4000000u;
    while (timeout--) {
        if (gpio_read(PIN_LEP_VSYNC) == 1) {
            return 1;
        }
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* ST7789 panel on VSPI                                                */
/* ------------------------------------------------------------------ */

static uint16_t palette_color(uint32_t value)
{
    /* Simple blue -> green -> red thermal palette, RGB565. */
    uint8_t level = (uint8_t)(value & 0xff);
    uint8_t red = 0, green = 0, blue = 0;

    if (level < 128) {
        blue = (uint8_t)(255 - level * 2);
        green = (uint8_t)(level * 2);
    } else {
        green = (uint8_t)(255 - (level - 128) * 2);
        red = (uint8_t)((level - 128) * 2);
    }
    return (uint16_t)(((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3));
}

static void lcd_cmd(uint8_t command)
{
    gpio_write(PIN_LCD_DC, 0);
    spi_tx(spi3, &command, 1);
}

static void lcd_data(const uint8_t *data, int len)
{
    gpio_write(PIN_LCD_DC, 1);
    while (len > 0) {
        int chunk = len > 64 ? 64 : len;
        spi_tx(spi3, data, chunk);
        data += chunk;
        len -= chunk;
    }
}

static void lcd_data_byte(uint8_t value)
{
    lcd_data(&value, 1);
}

static void lcd_window(uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2)
{
    uint8_t caset[4] = { (uint8_t)(x1 >> 8), (uint8_t)x1,
                         (uint8_t)(x2 >> 8), (uint8_t)x2 };
    uint8_t raset[4] = { (uint8_t)(y1 >> 8), (uint8_t)y1,
                         (uint8_t)(y2 >> 8), (uint8_t)y2 };
    lcd_cmd(0x2A);
    lcd_data(caset, 4);
    lcd_cmd(0x2B);
    lcd_data(raset, 4);
    lcd_cmd(0x2C);
}

static void lcd_init(void)
{
    gpio_enable_out(PIN_LCD_CS);
    gpio_write(PIN_LCD_CS, 0);
    gpio_enable_out(PIN_LCD_DC);
    gpio_enable_out(PIN_LCD_RST);
    gpio_write(PIN_LCD_RST, 0);
    delay_ticks(200000);
    gpio_write(PIN_LCD_RST, 1);
    delay_ticks(200000);

    lcd_cmd(0x01); /* SWRESET */
    delay_ticks(200000);
    lcd_cmd(0x11); /* SLPOUT */
    delay_ticks(200000);
    lcd_cmd(0x3A); /* COLMOD */
    lcd_data_byte(0x55);
    lcd_cmd(0x36); /* MADCTL */
    lcd_data_byte(0x00);
    lcd_cmd(0x21); /* INVON */
    lcd_cmd(0x13); /* NORON */
    lcd_cmd(0x29); /* DISPON */
    delay_ticks(100000);
}

/* Render the 160x120 thermal frame to the visible 135x240 glass area. */
static void lcd_draw_thermal(const uint8_t *raw, uint16_t raw_min,
                             uint16_t raw_max, uint16_t *row_buf)
{
    uint16_t span = (uint16_t)(raw_max - raw_min);
    if (span == 0) {
        span = 1;
    }
    lcd_window(52, 40, 52 + LCD_W - 1, 40 + LCD_H - 1);
    for (int y = 0; y < LCD_H; y++) {
        int src_row = y * FLIR_H / LCD_H;
        for (int x = 0; x < LCD_W; x++) {
            int src_col = x * FLIR_W / LCD_W;
            int index = (src_row * FLIR_W + src_col) * 2;
            uint16_t value = (uint16_t)((raw[index] << 8) | raw[index + 1]);
            uint32_t level = span ? ((uint32_t)(value - raw_min) * 255u) / span
                                  : 0;
            uint16_t color = palette_color(level);
            row_buf[x] = (uint16_t)((color >> 8) | (color << 8));
        }
        uint8_t bytes[LCD_W * 2];
        memcpy(bytes, row_buf, sizeof(bytes));
        lcd_data(bytes, sizeof(bytes));
    }
}

/* ------------------------------------------------------------------ */
/* FNV-1a digest over the VoSPI frame bytes                            */
/* ------------------------------------------------------------------ */

static uint32_t fnv1a(const uint8_t *data, int len)
{
    uint32_t hash = 2166136261u;
    for (int i = 0; i < len; i++) {
        hash ^= data[i];
        hash *= 16777619u;
    }
    return hash;
}

/* ------------------------------------------------------------------ */
/* Main probe                                                          */
/* ------------------------------------------------------------------ */

static uint8_t packet[FLIR_PACKET_BYTES];
static uint8_t frame_bytes[FLIR_W * FLIR_H * 2];
static uint16_t row_pixels[LCD_W];

#define VOPSI_MAX_ERRORS 16

static int receive_segment(uint16_t *raw_min, uint16_t *raw_max,
                           int *errors)
{
    int accepted = 0;
    for (int line = 0; line < FLIR_PACKETS_PER_SEGMENT; line++) {
        lepton_read_packet(packet);
        int segment = (packet[0] >> 4) & 0xf;
        int packet_line = packet[1];
        if (segment < 1 || segment > FLIR_SEGMENTS ||
            packet_line > 59) {
            (*errors)++;
            continue;
        }
        int row = (segment - 1) * 30 + (packet_line >> 1);
        int col = (packet_line & 1) * 80;
        for (int i = 0; i < 80; i++) {
            uint16_t value = (uint16_t)((packet[4 + i * 2] << 8) |
                                        packet[5 + i * 2]);
            int index = (row * FLIR_W + col + i) * 2;
            frame_bytes[index] = packet[4 + i * 2];
            frame_bytes[index + 1] = packet[5 + i * 2];
            if (value < *raw_min) {
                *raw_min = value;
            }
            if (value > *raw_max) {
                *raw_max = value;
            }
        }
        accepted++;
    }
    return accepted;
}

static void print_temp_marker(uint16_t fpa, uint16_t aux)
{
    uart_puts("LEPTON_CCI_TEMP ");
    uart_u32(fpa);
    uart_putc(' ');
    uart_u32(aux);
    uart_puts("\r\n");
}

void probe_main(void)
{
    uart_puts("\r\nSTICKT2_BOOT baremetal-v1\r\n");

    /* Idle both I2C lines high before the first Lepton command. */
    i2c_idle_bus();

    /* Lepton hardware reset, then CCI identification/status commands. */
    lepton_reset_pulse();
    delay_ticks(400000);

    {
        uint16_t words[8];
        int count = cci_get(0x0200, words, 8); /* CMD_SYS_PING (GET) */
        uart_puts("LEPTON_CCI_PING ");
        if (count < 1) {
            uart_puts("fail\r\n");
        } else {
            uart_u16_hex4(words[0]);
            uart_puts("\r\n");
        }
        count = cci_get(0x0208, words, 8); /* FLIR serial number */
        uart_puts("LEPTON_CCI_SERIAL ");
        if (count < 8) {
            uart_puts("fail\r\n");
        } else {
            for (int i = 0; i < 8; i++) {
                uart_u16_hex4(words[i]);
                if (i != 7) {
                    uart_putc(':');
                }
            }
            uart_puts("\r\n");
        }
        uint16_t fpa = 0, aux = 0;
        count = cci_get(0x0214, &fpa, 1); /* FPA temperature */
        if (count < 1) {
            uart_puts("LEPTON_CCI_TEMP fail\r\n");
        }
        count = cci_get(0x0210, &aux, 1); /* AUX temperature */
        print_temp_marker(fpa, aux);

        uint16_t sync_word = 5, delay_word = 3;
        cci_set(0x4854, &sync_word, 1); /* OEM sync mode */
        cci_set(0x4858, &delay_word, 1);
        uart_puts("LEPTON_CCI_SET_OK\r\n");
    }

    /* 20 MHz mode-3-ish VoSPI clock; the model serves on transfer. */
    gpio_enable_out(PIN_LEP_CS);
    gpio_write(PIN_LEP_CS, 0);
    gpio_enable_out(PIN_LEP_RESET);
    gpio_write(PIN_LEP_RESET, 1);
    /* VSYNC pin stays an input. */
    (void)gpio_read(PIN_LEP_VSYNC);

    lcd_init();
    uart_puts("STICKT2_PANEL_INIT 135 240\r\n");

    for (int frame = 0; frame < 3; frame++) {
        uint16_t raw_min = 0xffff, raw_max = 0;
        int frame_errors = 0;
        int frame_ok = 0;
        int segments_seen = 0;

        while (segments_seen < 64) {
            if (!lepton_wait_vsync(40000000u)) {
                uart_puts("VOPSI_VSYNC_TIMEOUT\r\n");
                break;
            }
            int errors = 0;
            int accepted = receive_segment(&raw_min, &raw_max, &errors);
            frame_errors += errors;
            if (accepted == FLIR_PACKETS_PER_SEGMENT) {
                int segment = (packet[0] >> 4) & 0xf;
                segments_seen |= 1 << (segment - 1);
                if (segments_seen == 0xf) {
                    frame_ok = 1;
                    break;
                }
            }
        }

        if (!frame_ok) {
            uart_puts("VOPSI_FRAME fail");
            uart_putc('\r');
            uart_putc('\n');
            break;
        }

        uint32_t digest = fnv1a(frame_bytes, sizeof(frame_bytes));
        uart_puts("VOPSI_FRAME ");
        uart_u32((uint32_t)frame);
        uart_putc(' ');
        uart_u32(FLIR_W);
        uart_putc(' ');
        uart_u32(FLIR_H);
        uart_putc(' ');
        uart_u32(sizeof(frame_bytes));
        uart_putc(' ');
        uart_hex32(digest);
        uart_putc(' ');
        uart_u32(raw_min);
        uart_putc(' ');
        uart_u32(raw_max);
        uart_puts("\r\n");
        uart_puts("VOPSI_FRAME_ERRORS ");
        uart_u32((uint32_t)frame_errors);
        uart_puts("\r\n");

        {
            int increment = 0, switch_state = 0;
            if (encoder_read(&increment, &switch_state)) {
                uart_puts("STICKT2_ENCODER ");
                uart_u32((uint32_t)(increment < 0 ? -increment : increment));
                uart_putc(' ');
                uart_u32((uint32_t)switch_state);
                uart_puts("\r\n");
            } else {
                uart_puts("STICKT2_ENCODER fail\r\n");
            }
        }

        lcd_draw_thermal(frame_bytes, raw_min, raw_max, row_pixels);
        uart_puts("VOPSI_RENDERED ");
        uart_u32((uint32_t)frame);
        uart_puts("\r\n");
        delay_ticks(200000);
    }

    uart_puts("STICKT2_PANEL_OK 135 240\r\n");
    uart_puts("STICKT2_STATUS ok\r\n");
    for (;;) {
        delay_ticks(1000000);
    }
}

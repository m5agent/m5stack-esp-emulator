/*
 * I2C slave models for the M5Stack StopWatch:
 *   M5PM1 PMIC (0x6E), M5IOE1 IO expander (0x4F), CST820 touch (0x15),
 *   BMI270 IMU (0x68), RX8130CE RTC (0x32), ES8311 codec (0x18)
 * Register maps derived from the drivers in M5StopWatch-UserDemo/components.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "hw/i2c/i2c.h"
#include "hw/qdev-properties.h"
#include "qapi/visitor.h"
#include <math.h>
#include "qom/object.h"
#include "m5stopwatch.h"

enum {
    M_GENERIC,
    M_PM1,
    M_IOE1,
    M_CST820,
    M_BMI270,
    M_BMM150,
    M_MPU6886,
    M_RX8130,
    M_PCF8563,
    M_ES8311,
    M_ES7210,
    M_AW88298,
    M_LTR553,
    M_ST25R3916,
    M_AXP192,
    M_AXP2101,
    M_AW9523,
    M_FT5X06,
    M_TCA8418,
    M_PI4IOE,
    M_LM75,
    M_INA226,
    M_INA3221,
    M_SHT40,
    M_SI12T,
    M_LP5562,
    M_BQ27220,
    M_ES8389,
    M_IP2315,
};

typedef struct M5swI2CDev {
    I2CSlave parent_obj;
    char *model_name;
    int model;
    uint8_t regs[256];
    uint8_t ptr;
    bool ptr_set;          /* first byte of a write = register address */
    int64_t rtc_base_seconds; /* host epoch captured at device realize */
    int64_t rtc_offset;    /* seconds added to virtual-clock time */
    bool trace;
    /* live, QOM-settable sensor state (qom-set /machine/bmi270 accel-x 0.5 ...) */
    double accel[3];       /* g   (BMI270 sensor frame) */
    double gyro[3];        /* dps */
    double mag[3];         /* uT */
    int64_t vbat_mv, vin_mv, vinout_mv; /* M5PM1 */
    int64_t battery_level;
    double temperature_c;
    double humidity_pct;
    double bus_voltage_mv;
    double current_ma;
    double shunt_ohms;
    double ina3221_bus_mv[3];
    double ina3221_current_ma[3];
    double ina3221_shunt_ohms;
    uint8_t ina3221_read_index;
    int64_t light_level;
    int64_t proximity_level;
    int64_t aw9523_input_bits;
    int64_t pi4ioe_input_bits;
    int64_t m5ioe1_input_bits;
    bool m5ioe1_pa_enabled;
    int64_t m5pm1_input_bits;
    int64_t pm1_adc1_mv;
    int64_t pm1_adc2_mv;
    int64_t pm1_temperature_c;
    int64_t pm1_wake_source;
    uint8_t pm1_wdt_timeout;
    uint8_t pm1_uid[12];
    double axp192_battery_current_ma;
    int64_t m5ioe1_adc_mv[4];
    int64_t m5ioe1_temp_raw;
    int64_t si12t_touch_bits;
    int64_t lp5562_r_pwm;
    int64_t lp5562_g_pwm;
    int64_t lp5562_b_pwm;
    bool pm1_pa_enabled;
    bool axp192_speaker_enabled;
    bool axp2101_speaker_enabled;
    uint8_t command;
    uint8_t read_start;
    bool charging;         /* M5PM1 G2 CHG_STAT low = charging */
    uint8_t st25_space_b[64];
    uint8_t st25_fifo[512];
    uint32_t st25_fifo_len;
    uint32_t st25_fifo_pos;
    uint8_t st25_tx[64];
    uint32_t st25_tx_len;
    uint8_t st25_mode;
    bool st25_read_space_b;
    uint8_t st25_tag[180];
    uint8_t aw9523_irq_bits;
    uint8_t pi4ioe_irq_bits;
    uint8_t key_event;
    int64_t bq_battery_mv;
    int64_t bq_current_ma;
    int64_t bq_level;
    int64_t bq_design_capacity_mah;
    uint16_t bq_ctrl_word;
    uint8_t bq_ctrl_byte_index;
    uint8_t bq_unseal_matches;
    bool bq_sealed;
    bool bq_unsealed;
} M5swI2CDev;

OBJECT_DECLARE_SIMPLE_TYPE(M5swI2CDev, M5SW_I2C_DEV)

typedef struct M5swIP2315 {
    DeviceState parent_obj;
    bool charging;
    int64_t vbus_mv;
    int64_t ntc_ohms;
} M5swIP2315;

OBJECT_DECLARE_SIMPLE_TYPE(M5swIP2315, M5SW_IP2315)

static M5swI2CDev *g_touch;
static M5swI2CDev *g_ft_touch;
static M5swI2CDev *g_pm1;
static M5swI2CDev *g_axp2101;
static M5swI2CDev *g_axp192;
static M5swI2CDev *g_bmm150;
static M5swI2CDev *g_keyboard;
static M5swI2CDev *g_aw9523;
static M5swI2CDev *g_bq27220;
static uint8_t g_key_events[16];
static unsigned g_key_event_head;
static unsigned g_key_event_count;
static uint8_t g_plc_keys = 0x07;

static uint8_t aw9523_input_read(M5swI2CDev *s, int bank)
{
    uint8_t config = s->regs[0x04 + bank];
    uint8_t external = (s->aw9523_input_bits >> (bank * 8)) & 0xff;
    uint8_t output = s->regs[0x02 + bank];

    return (config & external) | (~config & output);
}

static void aw9523_update_irq(M5swI2CDev *s)
{
    uint8_t level = s->aw9523_irq_bits != 0;

    if (s->parent_obj.address == 0x58) {
        esp32_gpio_force_line(21, !level);
    }
}

static void aw9523_set_input_bits(M5swI2CDev *s, int64_t value)
{
    uint16_t old = s->aw9523_input_bits;
    uint16_t now = value;
    uint16_t changed = old ^ now;
    uint16_t enabled = s->regs[0x06] | (s->regs[0x07] << 8);

    s->aw9523_input_bits = now;
    s->aw9523_irq_bits |= changed & enabled;
    aw9523_update_irq(s);
}

static uint8_t pi4ioe_input_read(M5swI2CDev *s)
{
    uint8_t direction = s->regs[0x03];
    uint8_t external = s->pi4ioe_input_bits;

    /*
     * StamPLC uses P0..P2 for active-low front-panel keys while the
     * remaining inputs are provided by the industrial input bank.
     */
    if (s->parent_obj.address == 0x43) {
        external = (external & 0xf8) | g_plc_keys;
    }
    return external & ~direction;
}

static void pi4ioe_update_irq(M5swI2CDev *s)
{
    if (s->parent_obj.address == 0x43) {
        esp32_gpio_force_line(21, s->pi4ioe_irq_bits == 0);
    }
}

static void pi4ioe_set_input_bits(M5swI2CDev *s, int64_t value)
{
    uint8_t now = value;
    uint8_t default_state = s->regs[0x09];
    uint8_t active;

    s->pi4ioe_input_bits = now;
    active = pi4ioe_input_read(s);
    s->pi4ioe_irq_bits |= (active ^ default_state) & ~s->regs[0x03];
    pi4ioe_update_irq(s);
}

static uint8_t m5ioe1_input_read(M5swI2CDev *s, int bank)
{
    uint16_t mode = s->regs[0x03] | (s->regs[0x04] << 8);
    uint16_t output = s->regs[0x05] | (s->regs[0x06] << 8);
    uint16_t external = s->m5ioe1_input_bits;

    return ((mode & output) | (~mode & external)) >> (bank * 8);
}

static void m5ioe1_set_input_bits(M5swI2CDev *s, int64_t value)
{
    uint16_t old = s->m5ioe1_input_bits;
    uint16_t now = value & 0x3fff;
    uint16_t changed = old ^ now;
    uint16_t enabled = s->regs[0x0d] | (s->regs[0x0e] << 8);
    uint16_t polarity = s->regs[0x0f] | (s->regs[0x10] << 8);
    uint16_t active = (changed & now & polarity)
                      | (changed & ~now & ~polarity);

    s->m5ioe1_input_bits = now;
    s->regs[0x11] |= active & enabled;
    s->regs[0x12] |= (active & enabled) >> 8;
}

void m5sw_pwr_button(int pressed)
{
    if (getenv("M5SW_INPUT_TRACE")) {
        fprintf(stderr, "[pwr-button] pressed=%d pm1=%p axp2101=%p\n",
                pressed, (void *)g_pm1, (void *)g_axp2101);
    }
    if (g_pm1) {
        if (pressed) {
            g_pm1->regs[0x48] |= 0x81;      /* pressed + sticky event */
        } else {
            g_pm1->regs[0x48] &= ~0x01;      /* sticky bit survives release */
        }
        if (pressed) {
            g_pm1->regs[0x42] |= 0x01;      /* IRQ_STATUS3: short press */
        }
    }
    if (g_axp2101 && pressed) {
        g_axp2101->regs[0x49] |= 0x04;      /* AXP2101 short press */
    }
    if (g_axp192 && pressed) {
        g_axp192->regs[0x46] |= 0x02;       /* AXP192 short press */
    }
}
static int g_touch_pressed, g_touch_x, g_touch_y;

void m5sw_touch_set(int pressed, int x, int y)
{
    g_touch_pressed = pressed;
    g_touch_x = x;
    g_touch_y = y;
}

void m5sw_ft_touch_set(int pressed, int x, int y)
{
    m5sw_ft_touch_set_pin(pressed, x, y, 21);
}

void m5sw_ft_touch_set_pin(int pressed, int x, int y, int int_pin)
{
    if (!g_ft_touch) {
        return;
    }
    g_ft_touch->regs[0x02] = pressed ? 1 : 0;
    g_ft_touch->regs[0x03] = (x >> 8) & 0x0f;
    g_ft_touch->regs[0x04] = x & 0xff;
    g_ft_touch->regs[0x05] = (y >> 8) & 0x0f;
    g_ft_touch->regs[0x06] = y & 0xff;
    /*
     * The touch controller owns INT.  Force the external line instead of
     * only changing the pull source: Core2's RTC GPIO path leaves the GPIO
     * output stage enabled even after pinMode(input_pullup), and an external
     * low must still win over that high output latch on an open-drain line.
     */
    esp32_gpio_force_line(int_pin, !pressed);
    if (getenv("M5SW_FT_TRACE")) {
        fprintf(stderr, "[ft5x06-input] pressed=%d x=%d y=%d int_pin=%d\n",
                pressed, x, y, int_pin);
    }
}

void m5sw_keyboard_event(uint8_t event)
{
    if (g_key_event_count == ARRAY_SIZE(g_key_events)) {
        return;
    }
    g_key_events[(g_key_event_head + g_key_event_count) % ARRAY_SIZE(g_key_events)] = event;
    g_key_event_count++;
    if (g_keyboard) {
        g_keyboard->regs[0x02] |= 0x01;  /* INT_STAT: key event */
    }
    esp32_gpio_set_input(11, 0);
}

__attribute__((weak)) void m5sw_ir_rx_start(void)
{
}

void m5sw_plc_key_set(int key, bool pressed)
{
    if (key < 0 || key > 2) {
        return;
    }
    uint8_t bit = 1u << (2 - key);
    if (pressed) {
        g_plc_keys &= ~bit;
    } else {
        g_plc_keys |= bit;
    }
}

static inline uint8_t bcd(int v) { return ((v / 10) << 4) | (v % 10); }
static inline int unbcd(uint8_t v) { return (v >> 4) * 10 + (v & 0xf); }

static uint8_t sht4x_crc8(const uint8_t *data, int size)
{
    uint8_t crc = 0xff;
    for (int i = 0; i < size; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31)
                               : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

static uint16_t encode_be16(double value, double resolution)
{
    int32_t raw = (int32_t)lrint(value / resolution);
    raw = MAX(-32768, MIN(raw, 65535));
    return (uint16_t)raw;
}

static uint16_t axp192_adc12(double value)
{
    int64_t raw = (int64_t)lrint(value);
    return (uint16_t)MAX(0, MIN(raw, 0x0fff));
}

static uint16_t axp192_adc13(double value)
{
    int64_t raw = (int64_t)lrint(value);
    return (uint16_t)MAX(0, MIN(raw, 0x1fff));
}

static uint16_t ina226_u16(M5swI2CDev *s, double value)
{
    int64_t raw = (int64_t)lrint(value);
    return (uint16_t)MAX(0, MIN(raw, 65535));
}

static uint16_t ina3221_u16(double value)
{
    int64_t raw = (int64_t)lrint(value);
    return (uint16_t)MAX(0, MIN(raw, 65535));
}

static uint16_t ina3221_reg16(M5swI2CDev *s, uint8_t reg)
{
    double shunt_mv;

    switch (reg) {
    case 0x00:
        return 0x7127;                         /* continuous all channels */
    case 0x01:
    case 0x03:
    case 0x05: {
        uint32_t channel = (reg - 0x01) / 2;
        shunt_mv = s->ina3221_current_ma[channel]
                   * s->ina3221_shunt_ohms;
        return ina3221_u16(shunt_mv / 0.04);   /* 40 uV/LSB */
    }
    case 0x02:
    case 0x04:
    case 0x06: {
        uint32_t channel = (reg - 0x02) / 2;
        return ina3221_u16(s->ina3221_bus_mv[channel] / 8.0);
    }
    case 0xFE:
        return 0x5449;                         /* TI manufacturer ID */
    case 0xFF:
        return 0x3220;                         /* INA3221 die ID */
    default:
        return 0;
    }
}

static uint16_t ina226_current_raw(M5swI2CDev *s)
{
    uint16_t cal = ((uint16_t)s->regs[0x05] << 8) | s->regs[0x06];
    if (!cal || s->shunt_ohms <= 0.0) {
        return 0;
    }
    double current_lsb = 0.00512 / ((double)cal * s->shunt_ohms);
    return ina226_u16(s, (s->current_ma / 1000.0) / current_lsb);
}

static uint16_t bmm150_raw(double value, bool z_axis)
{
    static const double resolution = 10.0 * 4912.0 / 32760.0;
    int32_t raw = (int32_t)lrint(value / resolution);
    raw = MAX(-8192, MIN(raw, 8191));
    return z_axis ? (uint16_t)((raw << 1) & ~1) : (uint16_t)(raw << 2);
}

static int64_t rtc_virtual_now(M5swI2CDev *s)
{
    return s->rtc_base_seconds
        + qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / NANOSECONDS_PER_SECOND;
}

static void rx8130_fill_time(M5swI2CDev *s)
{
    time_t t = rtc_virtual_now(s) + s->rtc_offset;
    struct tm tm;
    gmtime_r(&t, &tm);
    s->regs[0x10] = bcd(tm.tm_sec);
    s->regs[0x11] = bcd(tm.tm_min);
    s->regs[0x12] = bcd(tm.tm_hour);
    s->regs[0x13] = bcd(tm.tm_wday);
    s->regs[0x14] = bcd(tm.tm_mday);
    s->regs[0x15] = bcd(tm.tm_mon + 1);
    s->regs[0x16] = bcd(tm.tm_year % 100);
}

static void rx8130_time_written(M5swI2CDev *s)
{
    struct tm tm = {0};
    tm.tm_sec = unbcd(s->regs[0x10] & 0x7f);
    tm.tm_min = unbcd(s->regs[0x11] & 0x7f);
    tm.tm_hour = unbcd(s->regs[0x12] & 0x3f);
    tm.tm_mday = unbcd(s->regs[0x14] & 0x3f);
    tm.tm_mon = unbcd(s->regs[0x15] & 0x1f) - 1;
    tm.tm_year = unbcd(s->regs[0x16]) + 100;
    time_t t = timegm(&tm);
    s->rtc_offset = (int64_t)t - rtc_virtual_now(s);
}

static void pcf8563_fill_time(M5swI2CDev *s)
{
    time_t t = rtc_virtual_now(s) + s->rtc_offset;
    struct tm tm;
    gmtime_r(&t, &tm);
    s->regs[0x02] = bcd(tm.tm_sec);
    s->regs[0x03] = bcd(tm.tm_min);
    s->regs[0x04] = bcd(tm.tm_hour);
    s->regs[0x05] = bcd(tm.tm_mday);
    s->regs[0x06] = tm.tm_wday;
    s->regs[0x07] = bcd(tm.tm_mon + 1);
    s->regs[0x08] = bcd(tm.tm_year % 100);
}

static void pcf8563_time_written(M5swI2CDev *s)
{
    struct tm tm = {0};
    tm.tm_sec = unbcd(s->regs[0x02] & 0x7f);
    tm.tm_min = unbcd(s->regs[0x03] & 0x7f);
    tm.tm_hour = unbcd(s->regs[0x04] & 0x3f);
    tm.tm_mday = unbcd(s->regs[0x05] & 0x3f);
    tm.tm_mon = unbcd(s->regs[0x07] & 0x1f) - 1;
    tm.tm_year = unbcd(s->regs[0x08]) + 100;
    time_t t = timegm(&tm);
    s->rtc_offset = (int64_t)t - rtc_virtual_now(s);
}

static void st25_set_fifo(M5swI2CDev *s, const uint8_t *data, uint32_t size)
{
    size = MIN(size, sizeof(s->st25_fifo));
    if (size) {
        memcpy(s->st25_fifo, data, size);
    }
    s->st25_fifo_len = size;
    s->st25_fifo_pos = 0;
}

static void st25_set_fifo_byte(M5swI2CDev *s, uint8_t value)
{
    st25_set_fifo(s, &value, 1);
}

static void st25_init_tag(M5swI2CDev *s)
{
    static const uint8_t uid[4] = { 0xde, 0xad, 0xbe, 0xef };
    static const uint8_t page4[4] = { 'M', '5', 'N', '1' };

    memset(s->st25_tag, 0, sizeof(s->st25_tag));
    memcpy(s->st25_tag, uid, sizeof(uid));
    s->st25_tag[4] = uid[0] ^ uid[1] ^ uid[2] ^ uid[3];
    s->st25_tag[5] = 0x48;
    s->st25_tag[6] = 0x00;
    s->st25_tag[7] = 0x00;
    s->st25_tag[12] = 0xe1;  /* NDEF capability container */
    s->st25_tag[13] = 0x10;
    s->st25_tag[14] = 0x12;  /* NTAG213 user memory */
    s->st25_tag[15] = 0x00;
    memcpy(&s->st25_tag[16], page4, sizeof(page4));
}

static void st25_execute_command(M5swI2CDev *s, uint8_t command)
{
    static const uint8_t atqa[2] = { 0x44, 0x00 };
    static const uint8_t version[10] = {
        0x00, 0x04, 0x04, 0x02, 0x02, 0x01, 0x0b, 0x03, 0x00, 0x00,
    };
    uint8_t response[18] = { 0 };

    switch (command) {
    case 0xc1: /* SET_DEFAULT */
        memset(s->regs, 0, sizeof(s->regs));
        memset(s->st25_space_b, 0, sizeof(s->st25_space_b));
        s->regs[0x3f] = 0x2a;
        st25_set_fifo(s, NULL, 0);
        break;
    case 0xc6: /* TRANSMIT_REQA */
    case 0xc7: /* TRANSMIT_WUPA */
        st25_set_fifo(s, atqa, sizeof(atqa));
        break;
    case 0xc5: /* TRANSMIT_WITHOUT_CRC */
        if (s->st25_tx_len >= 1 && s->st25_tx[0] == 0x93) {
            response[0] = s->st25_tag[0];
            response[1] = s->st25_tag[1];
            response[2] = s->st25_tag[2];
            response[3] = s->st25_tag[3];
            response[4] = s->st25_tag[4];
            st25_set_fifo(s, response, 5);
        }
        break;
    case 0xc4: /* TRANSMIT_WITH_CRC */
        if (s->st25_tx_len >= 2 && s->st25_tx[0] == 0x93) {
            response[0] = 0x00; /* SAK: MIFARE Ultralight / NTAG */
            st25_set_fifo(s, response, 1);
        } else if (s->st25_tx_len >= 1 && s->st25_tx[0] == 0x60) {
            st25_set_fifo(s, version, sizeof(version));
        } else if (s->st25_tx_len >= 2 && s->st25_tx[0] == 0x30) {
            uint32_t base = (s->st25_tx[1] & ~3u) * 4;
            uint32_t available = sizeof(s->st25_tag) - MIN(base,
                                                         sizeof(s->st25_tag));
            uint32_t copy = MIN(available, 16);
            memcpy(response, &s->st25_tag[base], copy);
            st25_set_fifo(s, response, copy + 2);
        } else if (s->st25_tx_len >= 6 && s->st25_tx[0] == 0xa2) {
            uint32_t page = s->st25_tx[1] & 0x3f;
            uint32_t offset = page * 4;
            if (offset + 4 <= sizeof(s->st25_tag)) {
                memcpy(&s->st25_tag[offset], &s->st25_tx[2], 4);
            }
            st25_set_fifo_byte(s, 0x0a);
        } else if (s->st25_tx_len >= 1 && s->st25_tx[0] == 0x50) {
            st25_set_fifo(s, NULL, 0);
        }
        break;
    case 0xdb: /* CLEAR_FIFO */
        st25_set_fifo(s, NULL, 0);
        s->st25_tx_len = 0;
        break;
    default:
        break;
    }
    s->regs[0x1a] = command == 0xc8 ? 0x80 : s->regs[0x1a];
}

static uint8_t dev_read_reg(M5swI2CDev *s, uint8_t r)
{
    switch (s->model) {
    case M_LP5562:
        if (r == 0x04) {
            return s->lp5562_r_pwm;
        }
        if (r == 0x03) {
            return s->lp5562_g_pwm;
        }
        if (r == 0x02) {
            return s->lp5562_b_pwm;
        }
        break;
    case M_IOE1:
        if (r == 0x07) {
            return m5ioe1_input_read(s, 0);
        }
        if (r == 0x08) {
            return m5ioe1_input_read(s, 1) & 0x3f;
        }
        if (r == 0x16 || r == 0x17) {
            int channel = (s->regs[0x15] & 0x03) - 1;
            channel = MAX(0, MIN(channel, 3));
            uint16_t raw = (s->m5ioe1_adc_mv[channel] * 0x0fff
                            + 1650) / 3300;
            return r == 0x16 ? raw & 0xff : raw >> 8;
        }
        if (r == 0x19 || r == 0x1a) {
            return r == 0x19 ? s->m5ioe1_temp_raw & 0xff
                             : (s->m5ioe1_temp_raw >> 8) & 0x0f;
        }
        break;
    case M_CST820:
        if (r <= 0x06) {
            uint8_t b[7] = {0};
            int x = g_touch_x, y = g_touch_y;
            b[1] = 0;                                    /* gesture */
            b[2] = g_touch_pressed ? 1 : 0;              /* finger num */
            b[3] = ((g_touch_pressed ? 2 : 1) << 6) | ((x >> 8) & 0x0f); /* 2=contact,1=up */
            b[4] = x & 0xff;
            b[5] = (y >> 8) & 0x0f;
            b[6] = y & 0xff;
            return b[r];
        }
        break;
    case M_AW9523:
        if (r == 0x00) {
            uint8_t value = aw9523_input_read(s, 0);
            s->aw9523_irq_bits &= 0xff00;
            aw9523_update_irq(s);
            return value;
        }
        if (r == 0x01) {
            uint8_t value = aw9523_input_read(s, 1);
            s->aw9523_irq_bits &= 0x00ff;
            aw9523_update_irq(s);
            return value;
        }
        if (r == 0x10) {
            return 0x23;
        }
        break;
    case M_SI12T:
        if (r == 0x10) {
            return s->si12t_touch_bits & 0xff;
        }
        if (r == 0x11 || r == 0x12) {
            return 0;
        }
        break;
    case M_FT5X06:
        if (r == 0xA3) {
            return 0x51;
        }
        if (r == 0xA6) {
            return 0x10; /* ILI9342C firmware id */
        }
        if (r == 0xA8) {
            return 0x11; /* M5Stack vendor id */
        }
        break;
    case M_TCA8418:
        if (r == 0x03) {
            return g_key_event_count;
        }
        if (r == 0x04 && g_key_event_count) {
            uint8_t event = g_key_events[g_key_event_head];
            g_key_event_head = (g_key_event_head + 1) % ARRAY_SIZE(g_key_events);
            g_key_event_count--;
            if (!g_key_event_count) {
                esp32_gpio_set_input(11, 1);
            }
            return event;
        }
        break;
    case M_PI4IOE:
        if (r == 0x01) {
            uint8_t value = s->regs[r];
            s->regs[r] &= ~0x02;
            return value;
        }
        if (r == 0x0F) {
            return pi4ioe_input_read(s);
        }
        if (r == 0x13) {
            uint8_t value = s->pi4ioe_irq_bits;
            s->pi4ioe_irq_bits = 0;
            pi4ioe_update_irq(s);
            return value;
        }
        break;
    case M_PM1:
        if (r == 0x04) {
            uint8_t value = 0;
            if (s->vin_mv > 1000) {
                value |= BIT(0) | BIT(2);                /* VIN + VBAT node */
            }
            if (s->vinout_mv > 1000 && !(s->regs[0x06] & BIT(3))) {
                value |= BIT(1);                         /* 5VOUT valid */
            }
            return value;
        }
        if (r == 0x12) {
            uint8_t mode = s->regs[0x10];
            uint8_t output = s->regs[0x11];
            uint8_t external = s->m5pm1_input_bits;
            external = (external & ~BIT(2))
                       | (s->charging ? 0 : BIT(2));
            return ((mode & output) | (~mode & external)) & 0x1f;
        }
        if (r == 0x05) {
            return s->pm1_wake_source & 0x7f;
        }
        if (r == 0x28 || r == 0x29) {
            uint16_t raw = s->regs[0x28] | (s->regs[0x29] << 8);
            return r == 0x28 ? raw & 0xff : raw >> 8;
        }
        if (r == 0x2a) {
            return s->regs[r] & ~0x01;
        }
        if (r == 0x48) {
            uint8_t value = s->regs[r];
            s->regs[r] &= ~0x80;
            return value;
        }
        if (r >= 0x22 && r <= 0x27) {
            int64_t v = r < 0x24 ? s->vbat_mv : r < 0x26 ? s->vin_mv : s->vinout_mv;
            v = MAX(0, MIN(v, 65535));
            return (r & 1) ? (v >> 8) & 0xff : v & 0xff;
        }
        if (r >= 0xe0 && r <= 0xeb) {
            return s->pm1_uid[r - 0xe0];
        }
        break;
    case M_AXP192:
        if (r == 0x00) {
            return (s->vin_mv > 1000 ? BIT(5) : 0)
                   | (s->charging ? BIT(2) : 0);
        }
        if (r == 0x01) {
            return s->vbat_mv > 1000 ? BIT(5) : 0;
        }
        if (r == 0x56 || r == 0x57) {
            uint16_t raw = axp192_adc12(s->vin_mv / 1.7);
            return r == 0x56 ? raw >> 4 : raw & 0x0f;
        }
        if (r == 0x58 || r == 0x59) {
            uint16_t raw = axp192_adc13(500.0 / 0.625);
            return r == 0x58 ? raw >> 5 : raw & 0x1f;
        }
        if (r == 0x5A || r == 0x5B) {
            uint16_t raw = axp192_adc12(s->vin_mv / 1.7);
            return r == 0x5A ? raw >> 4 : raw & 0x0f;
        }
        if (r == 0x5C || r == 0x5D) {
            uint16_t raw = axp192_adc13(500.0 / 0.375);
            return r == 0x5C ? raw >> 5 : raw & 0x1f;
        }
        if (r == 0x5E || r == 0x5F) {
            uint16_t raw = axp192_adc12((s->temperature_c + 144.7) * 10.0);
            return r == 0x5E ? raw >> 4 : raw & 0x0f;
        }
        if (r >= 0x70 && r <= 0x72) {
            double power_w = (s->vbat_mv / 1000.0)
                             * (s->axp192_battery_current_ma / 1000.0);
            uint32_t raw = MAX(0, MIN((int64_t)lrint(power_w / 0.00055),
                                      0xffffff));
            int shift = (0x72 - r) * 8;
            return (raw >> shift) & 0xff;
        }
        if (r == 0x78 || r == 0x79) {
            uint16_t raw = axp192_adc12(s->vbat_mv / 1.1);
            return r == 0x78 ? raw >> 4 : raw & 0x0f;
        }
        if (r == 0x7A || r == 0x7B) {
            uint16_t raw = axp192_adc13(
                s->charging ? s->axp192_battery_current_ma / 0.5 : 0);
            return r == 0x7A ? raw >> 5 : raw & 0x1f;
        }
        if (r == 0x7C || r == 0x7D) {
            uint16_t raw = axp192_adc13(
                s->charging ? 0 : s->axp192_battery_current_ma / 0.5);
            return r == 0x7C ? raw >> 5 : raw & 0x1f;
        }
        if (r == 0x7E || r == 0x7F) {
            uint16_t raw = axp192_adc12(s->vinout_mv / 1.4);
            return r == 0x7E ? raw >> 4 : raw & 0x0f;
        }
        break;
    case M_AXP2101:
        if (r == 0x00) {
            return 0x28;  /* battery present + VBUS good */
        }
        if (r == 0x01) {
            return s->charging ? 0x20 : 0;
        }
        if (r == 0xA4) {
            return MAX(0, MIN(s->battery_level, 100));
        }
        if (r == 0x34 || r == 0x35) {
            return r & 1 ? s->vbat_mv & 0xff : (s->vbat_mv >> 8) & 0x3f;
        }
        if (r == 0x38 || r == 0x39 || r == 0x3A || r == 0x3B) {
            return r & 1 ? s->vin_mv & 0xff : (s->vin_mv >> 8) & 0x3f;
        }
        break;
    case M_BMM150:
        if (r == 0x40) {
            return 0x32;
        }
        if (r == 0x48) {
            return 0x01;  /* data ready */
        }
        if (r >= 0x42 && r <= 0x47) {
            int index = (r - 0x42) / 2;
            uint16_t raw = bmm150_raw(s->mag[index], index == 2);
            return (r & 1) ? raw >> 8 : raw & 0xff;
        }
        break;
    case M_MPU6886:
        if (r == 0x75) {
            return 0x19;
        }
        if (r == 0x3A) {
            return 0x01;  /* data ready */
        }
        if (r >= 0x3B && r <= 0x40) {
            int index = (r - 0x3B) / 2;
            uint16_t raw = encode_be16(s->accel[index], 8.0 / 32768.0);
            return (r & 1) ? raw >> 8 : raw & 0xff;
        }
        if (r == 0x41 || r == 0x42) {
            uint16_t raw = encode_be16((s->temperature_c - 25.0) * 326.8, 1.0);
            return r == 0x41 ? raw >> 8 : raw & 0xff;
        }
        if (r >= 0x43 && r <= 0x48) {
            int index = (r - 0x43) / 2;
            uint16_t raw = encode_be16(s->gyro[index], 2000.0 / 32768.0);
            return (r & 1) ? raw >> 8 : raw & 0xff;
        }
        break;
    case M_LM75:
        if (r == 0x00 || r == 0x01) {
            uint16_t raw = encode_be16(s->temperature_c, 1.0 / 256.0);
            return r == 0 ? raw >> 8 : raw & 0xe0;
        }
        break;
    case M_INA226:
        if (s->read_start == 0xFE) {
            return (s->ptr - s->read_start) & 1 ? 0x49 : 0x54;
        }
        if (s->read_start == 0xFF) {
            return (s->ptr - s->read_start) & 1 ? 0x60 : 0x22;
        }
        if (s->read_start == 0x01) {
            uint16_t raw = ina226_u16(
                s, (s->current_ma / 1000.0) * s->shunt_ohms / 2.5e-6);
            return r == 0x01 ? raw >> 8 : raw & 0xff;
        }
        if (s->read_start == 0x02) {
            uint16_t raw = ina226_u16(s, s->bus_voltage_mv / 1.25);
            return r == 0x02 ? raw >> 8 : raw & 0xff;
        }
        if (s->read_start == 0x03) {
            uint16_t cal = ((uint16_t)s->regs[0x05] << 8) | s->regs[0x06];
            double current_lsb = cal && s->shunt_ohms > 0.0
                ? 0.00512 / ((double)cal * s->shunt_ohms) : 0.0;
            double power_lsb = current_lsb * 25.0;
            uint16_t raw = power_lsb
                ? ina226_u16(s, (s->bus_voltage_mv / 1000.0)
                                  * (s->current_ma / 1000.0) / power_lsb)
                : 0;
            return r == 0x03 ? raw >> 8 : raw & 0xff;
        }
        if (s->read_start == 0x04) {
            uint16_t raw = ina226_current_raw(s);
            if (s->trace && r == 0x04) {
                uint16_t cal = ((uint16_t)s->regs[0x05] << 8) | s->regs[0x06];
                fprintf(stderr, "[ina226] state current_ma=%.3f shunt=%.6f cal=%04x raw=%u\n",
                        s->current_ma, s->shunt_ohms, cal, raw);
            }
            return r == 0x04 ? raw >> 8 : raw & 0xff;
        }
        if (s->read_start == 0x05) {
            return r == 0x05 ? s->regs[0x05] : s->regs[0x06];
        }
        break;
    case M_LTR553:
        if (r == 0x86) {
            return 0x92;  /* LTR-553ALS-WA part/revision ID */
        }
        if (r == 0x87) {
            return 0x05;  /* Lite-On manufacturer ID */
        }
        if (r == 0x88 || r == 0x89 || r == 0x8A || r == 0x8B) {
            uint16_t raw = MAX(0, MIN(s->light_level, 65535));
            return (r & 1) ? raw >> 8 : raw & 0xff;
        }
        if (r == 0x8D || r == 0x8E) {
            uint16_t raw = MAX(0, MIN(s->proximity_level, 0x7ff));
            return r == 0x8D ? raw & 0xff : raw >> 8;
        }
        break;
    case M_ST25R3916:
    {
        uint8_t rr = r & 0x3f;
        if (s->read_start == 0x9f) {
            return s->st25_fifo_pos < s->st25_fifo_len
                 ? s->st25_fifo[s->st25_fifo_pos++] : 0;
        }
        if (s->st25_read_space_b) {
            return s->st25_space_b[rr];
        }
        if (rr == 0x3f) {
            return 0x2A;  /* IC type 0x05, revision 0x02 */
        }
        if (rr == 0x31) {
            return 0x10;  /* auxiliary display: OSC_OK */
        }
        if (rr >= 0x1a && rr <= 0x1d) {
            return rr == 0x1a ? 0x80 : 0;
        }
        if (rr == 0x1e || rr == 0x1f) {
            uint32_t count = MIN(s->st25_fifo_len, 0x3ff);
            if (rr == 0x1e) {
                return count & 0xff;
            }
            return ((count >> 8) & 0x03) << 6;
        }
        return s->regs[rr];
    }
    case M_SHT40:
        if (s->command == 0xFD || s->command == 0xF6 || s->command == 0xE0) {
            double t_max = 130.0;
            double t_min = -45.0;
            uint16_t traw = (uint16_t)lrint(
                (s->temperature_c - t_min) * 65535.0 / (t_max - t_min));
            uint16_t hraw = (uint16_t)lrint(
                (s->humidity_pct + 6.0) * 65535.0 / 125.0);
            uint8_t data[6];
            data[0] = traw >> 8;
            data[1] = traw & 0xff;
            data[2] = 0;
            data[3] = hraw >> 8;
            data[4] = hraw & 0xff;
            data[5] = 0;
            if (s->trace) {
                fprintf(stderr,
                        "[sht40] cmd=%02x temp=%.2f hum=%.2f raw=%04x/%04x\n",
                        s->command, s->temperature_c, s->humidity_pct,
                        traw, hraw);
            }
            data[2] = sht4x_crc8(data, 2);
            data[5] = sht4x_crc8(&data[3], 2);
            if (s->trace) {
                fprintf(stderr, "[sht40] data=%02x %02x %02x %02x %02x %02x\n",
                        data[0], data[1], data[2], data[3], data[4], data[5]);
            }
            return data[r % 6];
        }
        if (s->command == 0x89) {
            uint8_t data[6] = { 0x12, 0x34, 0x00, 0x56, 0x78, 0x00 };
            data[2] = sht4x_crc8(data, 2);
            data[5] = sht4x_crc8(&data[3], 2);
            return data[r % 6];
        }
        break;
    case M_BQ27220:
    {
        /*
         * BQ27220 standard commands are 16-bit little-endian words.  Linux
         * reads them with a register write followed by a two-byte read, so
         * the second byte must be derived from read_start rather than from
         * another absolute register address.
         */
        uint16_t word;
        uint8_t offset = r - s->read_start;

        switch (s->read_start) {
        case 0x00:                                      /* Control/status */
            word = s->bq_sealed ? 0x0000 : 0x0000;
            break;
        case 0x06:                                      /* Temperature, 0.1 K */
            word = 2981;
            break;
        case 0x08:                                      /* Voltage, mV */
            word = s->bq_battery_mv;
            break;
        case 0x0a:                                      /* Battery status */
            word = BIT(3);                              /* BATTPRES */
            break;
        case 0x0c:                                      /* Current, mA */
        case 0x14:                                      /* Average current, mA */
            word = (uint16_t)(int16_t)s->bq_current_ma;
            break;
        case 0x10:                                      /* Remaining capacity */
            word = s->bq_level * s->bq_design_capacity_mah / 100;
            break;
        case 0x12:                                      /* Full capacity */
        case 0x3c:                                      /* Design capacity */
            word = s->bq_design_capacity_mah;
            break;
        case 0x28:                                      /* Internal temperature */
            word = 2981;
            break;
        case 0x2a:                                      /* Cycle count */
            word = 0;
            break;
        case 0x2c:                                      /* Relative SOC */
            word = MAX(0, MIN(s->bq_level, 100));
            break;
        case 0x2e:                                      /* State of health */
            word = 100;
            break;
        case 0x30:                                      /* Charging voltage */
            word = 4200;
            break;
        case 0x3a:                                      /* Operation status */
            word = BIT(2) | (s->bq_sealed ? 0x3 : 0x2);
            break;
        default:
            return s->regs[r];
        }
        return offset ? (word >> 8) & 0xff : word & 0xff;
    }
    case M_BMI270:
        if (r >= 0x04 && r <= 0x09 && g_bmm150) {
            int index = (r - 0x04) / 2;
            if (s->regs[0x4D] == 0x40) {
                return 0x32;  /* AUX X LSB register is reused for BMM150 ID probe */
            }
            uint16_t raw = bmm150_raw(g_bmm150->mag[index], index == 2);
            return (r & 1) ? raw >> 8 : raw & 0xff;
        }
        if (r >= 0x0C && r <= 0x17) {                    /* ACC_X..GYR_Z, LSB first */
            int i = (r - 0x0C) / 2;
            double v;
            if (i < 3) {
                v = s->accel[i] * 32768.0 / 8.0;
            } else {
                v = s->gyro[i - 3] * 32768.0 / 2000.0;
            }
            int32_t iv = (int32_t)lrint(v);
            iv = MAX(-32768, MIN(iv, 32767));
            return ((r - 0x0C) & 1) ? ((uint16_t)iv >> 8) : ((uint16_t)iv & 0xff);
        }
        if (r == 0x1D) {                                 /* INT_STATUS_1: acc/gyr drdy */
            return g_bmm150 ? 0xE0 : 0xC0;
        }
        if (r == 0x21) {                                 /* INTERNAL_STATUS */
            return s->regs[0x59] & 1 ? 0x01 : 0x00;      /* init OK after INIT_CTRL=1 */
        }
        if (r == 0x03) {                                 /* STATUS: drdy acc/gyr */
            return 0xC0;
        }
        break;
    case M_ES8389:
        if (r == 0xF1) {                                 /* CSM_STATE1 */
            return 0x0D;                                 /* ES8389_STATE_ON */
        }
        break;
    case M_IP2315:
        if (r == 0xc7) {
            if (!(s->regs[0x01] & BIT(0))) {
                return 0x00;
            }
            return s->charging ? 0x82 : 0x45;
        }
        break;
    default:
        break;
    }
    return s->regs[r];
}

static int dev_event(I2CSlave *i2c, enum i2c_event ev)
{
    M5swI2CDev *s = M5SW_I2C_DEV(i2c);
    if (ev == I2C_START_SEND) {
        s->ptr_set = false;
        s->st25_mode = 0;
        s->st25_read_space_b = false;
        s->bq_ctrl_byte_index = 0;
    } else if (ev == I2C_START_RECV) {
        s->read_start = s->ptr;
        s->ina3221_read_index = 0;
        if (s->model == M_ST25R3916) {
            s->st25_read_space_b = s->st25_mode == 3;
        }
        if (s->model == M_RX8130) {
            rx8130_fill_time(s);
        } else if (s->model == M_PCF8563) {
            pcf8563_fill_time(s);
        }
    } else if (ev == I2C_FINISH) {
        if (s->model == M_RX8130 && s->ptr_set) {
            /* nothing */
        }
    }
    return 0;
}

static uint8_t dev_recv(I2CSlave *i2c)
{
    M5swI2CDev *s = M5SW_I2C_DEV(i2c);
    if (s->model == M_INA3221) {
        uint16_t value = ina3221_reg16(s, s->read_start);
        uint8_t raw = s->ina3221_read_index & 1
                      ? value & 0xff : value >> 8;
        s->ina3221_read_index++;
        if (s->trace) {
            qemu_log("[ina3221] rd16 %02x[%u] -> %02x\n",
                     s->read_start, s->ina3221_read_index - 1, raw);
        }
        return raw;
    }
    uint8_t v = dev_read_reg(s, s->ptr);
    if (s->trace) {
        qemu_log("[%s] rd %02x -> %02x\n", s->model_name, s->ptr, v);
    }
    if (!(s->model == M_ST25R3916 && s->read_start == 0x9f)) {
        s->ptr++;
    }
    if (s->model == M_SHT40 && s->command && s->ptr >= 6) {
        s->command = 0;
        s->ptr = 0;
    }
    return v;
}

static int dev_send(I2CSlave *i2c, uint8_t data)
{
    M5swI2CDev *s = M5SW_I2C_DEV(i2c);
    if (s->model == M_ST25R3916) {
        if (s->trace) {
            qemu_log("[st25r3916] tx mode=%u data=%02x\n",
                     s->st25_mode, data);
        }
        switch (s->st25_mode) {
        case 0:
            if (data == 0xfb) {
                s->st25_mode = 2;
            } else if (data == 0x80) {
                s->st25_tx_len = 0;
                s->st25_mode = 4;
            } else if (data >= 0xc0) {
                st25_execute_command(s, data);
                s->st25_mode = 5;
            } else {
                s->ptr = data;
                s->ptr_set = true;
                s->st25_mode = 1;
            }
            return 0;
        case 1:
            s->regs[s->ptr] = data;
            s->ptr++;
            return 0;
        case 2:
            s->ptr = data & 0x3f;
            s->ptr_set = true;
            s->st25_mode = 3;
            return 0;
        case 3:
            s->st25_space_b[s->ptr & 0x3f] = data;
            s->st25_mode = 0;
            return 0;
        case 4:
            if (s->st25_tx_len < sizeof(s->st25_tx)) {
                s->st25_tx[s->st25_tx_len++] = data;
            }
            return 0;
        default:
            return 0;
        }
    }
    if (s->model == M_SHT40 && !s->ptr_set) {
        s->command = data;
        s->ptr = 0;
        s->ptr_set = true;
        return 0;
    }
    if (!s->ptr_set) {
        s->ptr = data;
        s->ptr_set = true;
        return 0;
    }
    if (s->trace) {
        qemu_log("[%s] wr %02x <- %02x\n", s->model_name, s->ptr, data);
    }
    uint8_t r = s->ptr;
    switch (s->model) {
    case M_BMI270:
        if (r == 0x5E) {          /* INIT_DATA burst: register does not auto-increment */
            return 0;
        }
        if (r == 0x7E && data == 0xB6) {  /* soft reset */
            s->regs[0x7C] = 0x03;
            s->ptr++;
            return 0;
        }
        break;
    case M_TCA8418:
        if (r == 0x02) {          /* INT_STAT is write-one-to-clear */
            s->regs[r] &= ~data;
            s->ptr++;
            return 0;
        }
        break;
    case M_IOE1:
        if (r == 0x07 || r == 0x08) { s->ptr++; return 0; }  /* RO */
        if (r == 0x06) {
            s->m5ioe1_pa_enabled = !!(data & BIT(1));
        } else if (r == 0x15) {
            s->regs[r] = data & 0x83;
        } else if (r == 0x18) {
            s->regs[r] = data & 0x80;
        } else if (r == 0x11 || r == 0x12) {
            s->regs[r] &= data;
            s->ptr++;
            return 0;
        } else if (r == 0x29 && data == 0x3a) {
            memset(s->regs, 0, sizeof(s->regs));
            s->regs[0x00] = 0x34;
            s->regs[0x01] = 0x12;
            s->regs[0x02] = s->parent_obj.address == 0x6f ? 0x04 : 0x01;
            s->regs[0x27] = 3300 & 0xff;
            s->regs[0x28] = 3300 >> 8;
            s->m5ioe1_input_bits = 0x3fff;
            s->ptr++;
            return 0;
        }
        break;
    case M_PM1:
        if (r == 0x05) {
            s->pm1_wake_source &= data;
            s->ptr++;
            return 0;
        }
        if (r == 0x0a) {
            s->pm1_wdt_timeout = data;
        } else if (r == 0x0b && data == 0xa5) {
            s->regs[0x0a] = s->pm1_wdt_timeout;
            s->ptr++;
            return 0;
        } else if (r == 0x28 || r == 0x29 || r == 0x48) {
            s->ptr++;
            return 0;
        } else if (r == 0x2a) {
            unsigned channel = (data >> 1) & 0x07;
            uint16_t raw;
            if (data & 0x01) {
                if (channel == 1) {
                    raw = (s->pm1_adc1_mv * 0x0fff + 1650) / 3300;
                } else if (channel == 2) {
                    raw = (s->pm1_adc2_mv * 0x0fff + 1650) / 3300;
                } else if (channel == 6) {
                    raw = MAX(0, MIN((s->pm1_temperature_c + 40) * 16, 0x0fff));
                } else {
                    raw = 0;
                }
                s->regs[0x28] = raw & 0xff;
                s->regs[0x29] = raw >> 8;
            }
            s->regs[r] = data & ~0x01;
            s->ptr++;
            return 0;
        } else if (r == 0x50) {
            s->regs[r] = data & ~0x40;
            s->ptr++;
            return 0;
        }
        if (r >= 0x40 && r <= 0x42) {
            s->regs[r] &= data;
            s->ptr++;
            return 0;
        }
        if (r == 0x11) {
            s->pm1_pa_enabled = !!(data & 0x08);
        }
        break;
    case M_AXP2101:
        if (r == 0x90) {
            /* Core2 v1.1 uses ALDO3 (bit 3) as the NS4168 enable rail. */
            s->axp2101_speaker_enabled = !!(data & BIT(3));
        }
        if (r == 0x49) {
            s->regs[r] &= ~data;
            s->ptr++;
            return 0;
        }
        break;
    case M_INA3221:
        /* Configuration/limit registers are stored for write/readback. */
        break;
    case M_AXP192:
        if (r == 0x93) {
            s->axp192_speaker_enabled = ((data & 0x06) == 0x06);
        }
        break;
    case M_AW9523:
        if (r == 0x7f) {
            memset(s->regs, 0, sizeof(s->regs));
            s->regs[0x10] = 0x23;
            s->aw9523_irq_bits = 0;
            aw9523_update_irq(s);
            s->ptr++;
            return 0;
        }
        if (r == 0x06 || r == 0x07) {
            s->regs[r] = data;
            aw9523_update_irq(s);
            s->ptr++;
            return 0;
        }
        break;
    case M_PI4IOE:
        if (r == 0x01) {
            if (data & BIT(0)) {
                memset(s->regs, 0, sizeof(s->regs));
                s->regs[0x01] = 0xa2;
                s->regs[0x07] = 0xff;
                s->regs[0x0b] = 0xff;
                s->pi4ioe_irq_bits = 0;
                pi4ioe_update_irq(s);
            } else {
                s->regs[r] = data & 0xfe;
            }
            s->ptr++;
            return 0;
        }
        if (r == 0x0f || r == 0x13) {
            s->ptr++;
            return 0;
        }
        break;
    case M_RX8130:
        s->regs[r] = data;
        if (r >= 0x10 && r <= 0x16) {
            if (r == 0x16) {
                rx8130_time_written(s);
            }
        }
        s->ptr++;
        return 0;
    case M_PCF8563:
        s->regs[r] = data;
        if (r == 0x08) {
            pcf8563_time_written(s);
        }
        s->ptr++;
        return 0;
    case M_LP5562:
        if (r == 0x02) {
            s->lp5562_b_pwm = data;
        } else if (r == 0x03) {
            s->lp5562_g_pwm = data;
        } else if (r == 0x04) {
            s->lp5562_r_pwm = data;
        }
        break;
    case M_BQ27220:
        if (r == 0x00 || r == 0x01) {
            if (s->bq_ctrl_byte_index == 0) {
                s->bq_ctrl_word = data;
                s->bq_ctrl_byte_index = 1;
                s->ptr++;
                return 0;
            }
            s->bq_ctrl_word |= data << 8;
            s->bq_ctrl_byte_index = 0;

            if (s->bq_sealed && s->bq_ctrl_word == 0x8000) {
                if (++s->bq_unseal_matches >= 2) {
                    s->bq_sealed = false;
                    s->bq_unsealed = true;
                    s->bq_unseal_matches = 0;
                }
            } else {
                s->bq_unseal_matches = 0;
                if (s->bq_ctrl_word == 0x0030 && !s->bq_sealed) {
                    s->bq_sealed = true;
                    s->bq_unsealed = false;
                } else if (s->bq_ctrl_word == 0x0041) {
                    s->bq_sealed = false;
                    s->bq_unsealed = true;
                }
            }
            s->ptr++;
            return 0;
        }
        break;
    case M_IP2315:
        if (r == 0x01) {
            s->regs[r] = data & BIT(0);
            s->ptr++;
            return 0;
        }
        break;
    default:
        break;
    }
    s->regs[r] = data;
    s->ptr++;
    return 0;
}

static void prop_get_num(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    visit_type_number(v, name, (double *)op, errp);
}
static void prop_set_num(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    double d;
    if (visit_type_number(v, name, &d, errp)) {
        *(double *)op = d;
    }
}
static void prop_get_i64(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    visit_type_int64(v, name, (int64_t *)op, errp);
}
static void prop_set_i64(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    int64_t d;
    if (visit_type_int64(v, name, &d, errp)) {
        *(int64_t *)op = d;
    }
}
static void prop_get_rtc_time(Object *o, Visitor *v, const char *name,
                              void *op, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(o);
    int64_t value = (int64_t)time(NULL) + s->rtc_offset;
    visit_type_int64(v, name, &value, errp);
}
static void prop_set_rtc_time(Object *o, Visitor *v, const char *name,
                              void *op, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(o);
    int64_t value;
    if (visit_type_int64(v, name, &value, errp)) {
        s->rtc_offset = value - (int64_t)time(NULL);
    }
}
static void rtc_add_properties(M5swI2CDev *s)
{
    object_property_add(OBJECT(s), "rtc-offset", "int",
                        prop_get_i64, prop_set_i64, NULL,
                        &s->rtc_offset);
    object_property_add(OBJECT(s), "unix-time", "int",
                        prop_get_rtc_time, prop_set_rtc_time, NULL, NULL);
}
static void prop_get_u8(Object *o, Visitor *v, const char *name, void *op,
                        Error **errp)
{
    visit_type_uint8(v, name, (uint8_t *)op, errp);
}
static void prop_set_key_event(Object *o, Visitor *v, const char *name,
                               void *op, Error **errp)
{
    uint8_t value;

    if (visit_type_uint8(v, name, &value, errp)) {
        *(uint8_t *)op = value;
        if (getenv("M5SW_I2C_TRACE")) {
            fprintf(stderr, "[tca8418] inject key-event=%02x\n", value);
        }
        m5sw_keyboard_event(value);
    }
}

static void prop_set_ir_rx_start(Object *o, Visitor *v, const char *name,
                                 void *op, Error **errp)
{
    uint8_t value;

    if (visit_type_uint8(v, name, &value, errp) && value) {
        m5sw_ir_rx_start();
    }
}
static void prop_set_aw9523_input(Object *o, Visitor *v, const char *name,
                                  void *op, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(o);
    int64_t value;

    if (visit_type_int64(v, name, &value, errp)) {
        aw9523_set_input_bits(s, value & 0xffff);
    }
}
static void prop_set_pi4ioe_input(Object *o, Visitor *v, const char *name,
                                  void *op, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(o);
    int64_t value;

    if (visit_type_int64(v, name, &value, errp)) {
        pi4ioe_set_input_bits(s, value & 0xff);
    }
}
static void prop_set_m5ioe1_input(Object *o, Visitor *v, const char *name,
                                  void *op, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(o);
    int64_t value;

    if (visit_type_int64(v, name, &value, errp)) {
        m5ioe1_set_input_bits(s, value);
    }
}
static void prop_set_m5pm1_input(Object *o, Visitor *v, const char *name,
                                 void *op, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(o);
    int64_t value;

    if (visit_type_int64(v, name, &value, errp)) {
        uint8_t old = s->m5pm1_input_bits;
        uint8_t now = value & 0x1f;
        s->m5pm1_input_bits = now;
        s->regs[0x40] |= (old ^ now) & 0x1f;
    }
}
static void prop_get_bool(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    visit_type_bool(v, name, (bool *)op, errp);
}
static void prop_set_bool(Object *o, Visitor *v, const char *name, void *op, Error **errp)
{
    bool d;
    if (visit_type_bool(v, name, &d, errp)) {
        *(bool *)op = d;
    }
}

static void ip2315_apply_state(M5swIP2315 *s)
{
    int64_t current_ma;

    if (!g_bq27220) {
        return;
    }
    current_ma = llabs(g_bq27220->bq_current_ma);
    if (!current_ma) {
        current_ma = 250;
    }
    /*
     * Linux bq27xxx derives power_supply status from the signed current:
     * positive is charging and negative is discharging.
     */
    g_bq27220->bq_current_ma = s->charging ? current_ma : -current_ma;
}

static void ip2315_set_charging(Object *obj, Visitor *v,
                                const char *name, void *opaque,
                                Error **errp)
{
    M5swIP2315 *s = M5SW_IP2315(obj);
    bool value;

    if (visit_type_bool(v, name, &value, errp)) {
        s->charging = value;
        ip2315_apply_state(s);
    }
}

static void ip2315_get_charging(Object *obj, Visitor *v,
                                const char *name, void *opaque,
                                Error **errp)
{
    M5swIP2315 *s = M5SW_IP2315(obj);

    visit_type_bool(v, name, &s->charging, errp);
}

static void ip2315_get_vbus(Object *obj, Visitor *v,
                            const char *name, void *opaque,
                            Error **errp)
{
    M5swIP2315 *s = M5SW_IP2315(obj);

    visit_type_int64(v, name, &s->vbus_mv, errp);
}

static void ip2315_set_vbus(Object *obj, Visitor *v,
                            const char *name, void *opaque,
                            Error **errp)
{
    M5swIP2315 *s = M5SW_IP2315(obj);

    visit_type_int64(v, name, &s->vbus_mv, errp);
}

static void ip2315_get_ntc(Object *obj, Visitor *v,
                           const char *name, void *opaque,
                           Error **errp)
{
    M5swIP2315 *s = M5SW_IP2315(obj);

    visit_type_int64(v, name, &s->ntc_ohms, errp);
}

static void ip2315_set_ntc(Object *obj, Visitor *v,
                           const char *name, void *opaque,
                           Error **errp)
{
    M5swIP2315 *s = M5SW_IP2315(obj);

    visit_type_int64(v, name, &s->ntc_ohms, errp);
}

static void ip2315_realize(DeviceState *dev, Error **errp)
{
    ip2315_apply_state(M5SW_IP2315(dev));
}

static void ip2315_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = ip2315_realize;
    dc->user_creatable = true;
    object_class_property_add(klass, "charging", "bool",
                              ip2315_get_charging, ip2315_set_charging,
                              NULL, NULL);
    object_class_property_add(klass, "vbus-mv", "int",
                              ip2315_get_vbus, ip2315_set_vbus,
                              NULL, NULL);
    object_class_property_add(klass, "ntc-ohms", "int",
                              ip2315_get_ntc, ip2315_set_ntc,
                              NULL, NULL);
}

static const TypeInfo ip2315_info = {
    .name = TYPE_M5SW_IP2315,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(M5swIP2315),
    .class_init = ip2315_class_init,
};

static void dev_realize(DeviceState *dev, Error **errp)
{
    M5swI2CDev *s = M5SW_I2C_DEV(dev);
    const char *m = s->model_name ? s->model_name : "generic";
    memset(s->regs, 0, sizeof(s->regs));
    s->rtc_base_seconds = time(NULL);
    s->trace = getenv("M5SW_I2C_TRACE") != NULL;
    if (!strcmp(m, "m5pm1")) {
        s->model = M_PM1;
        s->regs[0x00] = 0x50;   /* device id (little-endian 0x2050) */
        s->regs[0x01] = 0x20;
        s->regs[0x02] = 0x01;   /* hw rev */
        s->regs[0x03] = 'A';    /* sw rev */
        s->regs[0x20] = 3300 & 0xff; s->regs[0x21] = 3300 >> 8;   /* VREF mV */
        s->regs[0x22] = 4000 & 0xff; s->regs[0x23] = 4000 >> 8;   /* VBAT 4.0 V */
        s->regs[0x24] = 5000 & 0xff; s->regs[0x25] = 5000 >> 8;   /* VIN 5.0 V (USB) */
        s->regs[0x26] = 5000 & 0xff; s->regs[0x27] = 5000 >> 8;
        s->regs[0x28] = 0x00; s->regs[0x29] = 0x08;               /* ADC ~2/3 scale */
        s->regs[0x2a] = 0;
        s->regs[0x12] = 0x04;   /* GPIO_IN: CHG_STAT (G2) high = not charging */
        s->vbat_mv = 4000; s->vin_mv = 5000; s->vinout_mv = 5000; s->charging = false;
        s->m5pm1_input_bits = 0x1f;
        s->pm1_adc1_mv = 1650;
        s->pm1_adc2_mv = 1200;
        s->pm1_temperature_c = 25;
        s->pm1_wake_source = 0;
        s->pm1_wdt_timeout = 0;
        for (int i = 0; i < 12; i++) {
            s->pm1_uid[i] = 0x50 + i;
        }
        object_property_add(OBJECT(s), "vbat-mv", "int", prop_get_i64, prop_set_i64, NULL, &s->vbat_mv);
        object_property_add(OBJECT(s), "vin-mv", "int", prop_get_i64, prop_set_i64, NULL, &s->vin_mv);
        object_property_add(OBJECT(s), "vinout-mv", "int", prop_get_i64, prop_set_i64, NULL, &s->vinout_mv);
        object_property_add(OBJECT(s), "charging", "bool", prop_get_bool, prop_set_bool, NULL, &s->charging);
        object_property_add(OBJECT(s), "gpio-input-bits", "int", prop_get_i64,
                            prop_set_m5pm1_input, NULL,
                            &s->m5pm1_input_bits);
        object_property_add(OBJECT(s), "adc1-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->pm1_adc1_mv);
        object_property_add(OBJECT(s), "adc2-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->pm1_adc2_mv);
        object_property_add(OBJECT(s), "temperature-c", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->pm1_temperature_c);
        object_property_add(OBJECT(s), "wake-source", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->pm1_wake_source);
        object_property_add(OBJECT(s), "pa-enabled", "bool", prop_get_bool, NULL, NULL, &s->pm1_pa_enabled);
        g_pm1 = s;
    } else if (!strcmp(m, "ip2315")) {
        s->model = M_IP2315;
        s->regs[0x01] = BIT(0);   /* charger enable */
        s->charging = false;
        object_property_add(OBJECT(s), "charging", "bool",
                            prop_get_bool, prop_set_bool, NULL,
                            &s->charging);
    } else if (!strcmp(m, "m5ioe1")) {
        s->model = M_IOE1;
        s->regs[0x00] = 0x34; s->regs[0x01] = 0x12;   /* UID */
        s->regs[0x02] = 0x01;                          /* FW rev */
        s->regs[0x27] = 3300 & 0xff; s->regs[0x28] = 3300 >> 8;
        s->m5ioe1_input_bits = 0x3fff;
        s->m5ioe1_adc_mv[0] = 1650;
        s->m5ioe1_temp_raw = 850;
        object_property_add(OBJECT(s), "input-bits", "int", prop_get_i64,
                            prop_set_m5ioe1_input, NULL,
                            &s->m5ioe1_input_bits);
        object_property_add(OBJECT(s), "adc1-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[0]);
        object_property_add(OBJECT(s), "adc2-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[1]);
        object_property_add(OBJECT(s), "adc3-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[2]);
        object_property_add(OBJECT(s), "adc4-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[3]);
        object_property_add(OBJECT(s), "pa-enabled", "bool", prop_get_bool,
                            NULL, NULL, &s->m5ioe1_pa_enabled);
    } else if (!strcmp(m, "cst820")) {
        s->model = M_CST820;
        s->regs[0xA7] = 0xB7;   /* chip id */
        s->regs[0xA8] = 0x01;
        s->regs[0xA9] = 0x01;   /* firmware ver */
        g_touch = s;
    } else if (!strcmp(m, "bmi270")) {
        s->model = M_BMI270;
        s->regs[0x00] = 0x24;   /* CHIP_ID */
        s->regs[0x7C] = 0x03;   /* PWR_CONF default */
        s->accel[2] = 1.0;      /* lying flat: +1 g on Z */
        static const char *an[] = { "accel-x", "accel-y", "accel-z" };
        static const char *gn[] = { "gyro-x", "gyro-y", "gyro-z" };
        for (int i = 0; i < 3; i++) {
            object_property_add(OBJECT(s), an[i], "number", prop_get_num, prop_set_num, NULL, &s->accel[i]);
            object_property_add(OBJECT(s), gn[i], "number", prop_get_num, prop_set_num, NULL, &s->gyro[i]);
        }
    } else if (!strcmp(m, "bmm150")) {
        s->model = M_BMM150;
        s->regs[0x40] = 0x32;
        s->regs[0x48] = 0x01;
        static const char *props[] = { "mag-x", "mag-y", "mag-z" };
        for (int i = 0; i < 3; i++) {
            object_property_add(OBJECT(s), props[i], "number",
                                prop_get_num, prop_set_num, NULL, &s->mag[i]);
        }
        g_bmm150 = s;
    } else if (!strcmp(m, "mpu6886")) {
        s->model = M_MPU6886;
        s->regs[0x75] = 0x19;
        s->accel[2] = 1.0;
        s->temperature_c = 25.0;
        static const char *aprops[] = { "accel-x", "accel-y", "accel-z" };
        static const char *gprops[] = { "gyro-x", "gyro-y", "gyro-z" };
        for (int i = 0; i < 3; i++) {
            object_property_add(OBJECT(s), aprops[i], "number",
                                prop_get_num, prop_set_num, NULL, &s->accel[i]);
            object_property_add(OBJECT(s), gprops[i], "number",
                                prop_get_num, prop_set_num, NULL, &s->gyro[i]);
        }
    } else if (!strcmp(m, "lm75")) {
        s->model = M_LM75;
        s->temperature_c = 25.0;
        object_property_add(OBJECT(s), "temperature-c", "number",
                            prop_get_num, prop_set_num, NULL, &s->temperature_c);
    } else if (!strcmp(m, "ina226")) {
        s->model = M_INA226;
        s->bus_voltage_mv = 5000.0;
        s->current_ma = 500.0;
        s->shunt_ohms = 0.005;
        s->regs[0x00] = 0x45; s->regs[0x01] = 0x27;
        s->regs[0x05] = 0x0c; s->regs[0x06] = 0x80;
        object_property_add(OBJECT(s), "bus-voltage-mv", "number",
                            prop_get_num, prop_set_num, NULL, &s->bus_voltage_mv);
        object_property_add(OBJECT(s), "current-ma", "number",
                            prop_get_num, prop_set_num, NULL, &s->current_ma);
        object_property_add(OBJECT(s), "shunt-ohms", "number",
                            prop_get_num, prop_set_num, NULL, &s->shunt_ohms);
    } else if (!strcmp(m, "ina3221")) {
        s->model = M_INA3221;
        s->ina3221_bus_mv[0] = 5000.0;
        s->ina3221_bus_mv[1] = 3300.0;
        s->ina3221_bus_mv[2] = 5000.0;
        s->ina3221_current_ma[0] = 500.0;
        s->ina3221_current_ma[1] = 200.0;
        s->ina3221_current_ma[2] = 100.0;
        s->ina3221_shunt_ohms = 0.010;
        static const char *ina_bus_props[] = {
            "bus1-mv", "bus2-mv", "bus3-mv"
        };
        static const char *ina_current_props[] = {
            "current1-ma", "current2-ma", "current3-ma"
        };
        for (int i = 0; i < 3; i++) {
            object_property_add(OBJECT(s), ina_bus_props[i], "number",
                                prop_get_num, prop_set_num, NULL,
                                &s->ina3221_bus_mv[i]);
            object_property_add(OBJECT(s), ina_current_props[i], "number",
                                prop_get_num, prop_set_num, NULL,
                                &s->ina3221_current_ma[i]);
        }
        object_property_add(OBJECT(s), "shunt-ohms", "number",
                            prop_get_num, prop_set_num, NULL,
                            &s->ina3221_shunt_ohms);
    } else if (!strcmp(m, "ltr553")) {
        s->model = M_LTR553;
        s->light_level = 320;
        s->proximity_level = 64;
        object_property_add(OBJECT(s), "light-level", "int",
                            prop_get_i64, prop_set_i64, NULL, &s->light_level);
        object_property_add(OBJECT(s), "proximity-level", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->proximity_level);
    } else if (!strcmp(m, "st25r3916")) {
        s->model = M_ST25R3916;
        s->regs[0x3F] = 0x2A;
        st25_init_tag(s);
    } else if (!strcmp(m, "sht40")) {
        s->model = M_SHT40;
        s->temperature_c = 25.0;
        s->humidity_pct = 50.0;
        object_property_add(OBJECT(s), "temperature-c", "number",
                            prop_get_num, prop_set_num, NULL, &s->temperature_c);
        object_property_add(OBJECT(s), "humidity-pct", "number",
                            prop_get_num, prop_set_num, NULL, &s->humidity_pct);
    } else if (!strcmp(m, "si12t")) {
        s->model = M_SI12T;
        s->regs[0x08] = 0x22;
        s->regs[0x09] = 0x07;
        object_property_add(OBJECT(s), "touch-bits", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->si12t_touch_bits);
    } else if (!strcmp(m, "lp5562")) {
        s->model = M_LP5562;
        s->regs[0x00] = 0x00;
        s->regs[0x01] = 0x00;
        object_property_add(OBJECT(s), "red-pwm", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->lp5562_r_pwm);
        object_property_add(OBJECT(s), "green-pwm", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->lp5562_g_pwm);
        object_property_add(OBJECT(s), "blue-pwm", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->lp5562_b_pwm);
    } else if (!strcmp(m, "bq27220")) {
        s->model = M_BQ27220;
        s->bq_battery_mv = 4000;
        s->bq_current_ma = 250;
        s->bq_level = 87;
        s->bq_design_capacity_mah = 1750;
        object_property_add(OBJECT(s), "battery-mv", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->bq_battery_mv);
        object_property_add(OBJECT(s), "current-ma", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->bq_current_ma);
        object_property_add(OBJECT(s), "battery-level", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->bq_level);
        object_property_add(OBJECT(s), "design-capacity-mah", "int",
                            prop_get_i64, prop_set_i64, NULL,
                            &s->bq_design_capacity_mah);
        g_bq27220 = s;
    } else if (!strcmp(m, "es8389")) {
        /*
         * ES8389 has an 8-bit register map at I2C 0x10.  The open-source
         * Linux and ESP codec drivers use the same FD/FE identity registers;
         * FE is checked as 0x89 by Espressif's ESP codec layer.  CSM_STATE1
         * reports the powered/on state expected after codec initialization.
         */
        s->model = M_ES8389;
        s->regs[0xFD] = 0x83;
        s->regs[0xFE] = 0x89;
        s->regs[0xF1] = 0x0D;
    } else if (!strcmp(m, "rx8130")) {
        s->model = M_RX8130;
        s->regs[0x1E] = 0x00;
        s->regs[0x1D] = 0x00;
        rtc_add_properties(s);
    } else if (!strcmp(m, "pcf8563")) {
        s->model = M_PCF8563;
        rtc_add_properties(s);
    } else if (!strcmp(m, "es8311")) {
        s->model = M_ES8311;
        s->regs[0xFD] = 0x83;   /* CHIP ID1 */
        s->regs[0xFE] = 0x11;   /* CHIP ID2 */
        s->regs[0xFF] = 0x00;   /* version */
    } else if (!strcmp(m, "es7210")) {
        s->model = M_ES7210;
    } else if (!strcmp(m, "aw88298")) {
        s->model = M_AW88298;
    } else if (!strcmp(m, "axp192")) {
        s->model = M_AXP192;
        s->regs[0x03] = 0x03;   /* AXP192 chip ID */
        s->regs[0x00] = 0x28;
        s->regs[0x33] = 0x08;
        s->vbat_mv = 4000;
        s->vin_mv = 5000;
        s->vinout_mv = 5000;
        s->temperature_c = 25.0;
        s->charging = true;
        s->battery_level = 87;
        s->axp192_battery_current_ma = 300.0;
        object_property_add(OBJECT(s), "vbat-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->vbat_mv);
        object_property_add(OBJECT(s), "vin-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->vin_mv);
        object_property_add(OBJECT(s), "vinout-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->vinout_mv);
        object_property_add(OBJECT(s), "temperature-c", "number",
                            prop_get_num, prop_set_num, NULL,
                            &s->temperature_c);
        object_property_add(OBJECT(s), "charging", "bool", prop_get_bool,
                            prop_set_bool, NULL, &s->charging);
        object_property_add(OBJECT(s), "battery-level", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->battery_level);
        object_property_add(OBJECT(s), "battery-current-ma", "number",
                            prop_get_num, prop_set_num, NULL,
                            &s->axp192_battery_current_ma);
        object_property_add(OBJECT(s), "speaker-enabled", "bool",
                            prop_get_bool, NULL, NULL,
                            &s->axp192_speaker_enabled);
        g_axp192 = s;
    } else if (!strcmp(m, "axp2101")) {
        s->model = M_AXP2101;
        s->regs[0x03] = 0x4A;   /* chip id required by AXP2101_Class::begin */
        s->regs[0x00] = 0x28;   /* battery present + VBUS good */
        s->regs[0x01] = 0x20;   /* charging */
        s->regs[0x18] = 0x06;
        s->regs[0x90] = 0xBF;
        s->regs[0x49] = 0;
        s->vbat_mv = 4000;
        s->vin_mv = 5000;
        s->charging = true;
        s->battery_level = 87;
        object_property_add(OBJECT(s), "vbat-mv", "int", prop_get_i64, prop_set_i64, NULL, &s->vbat_mv);
        object_property_add(OBJECT(s), "vin-mv", "int", prop_get_i64, prop_set_i64, NULL, &s->vin_mv);
        object_property_add(OBJECT(s), "charging", "bool", prop_get_bool, prop_set_bool, NULL, &s->charging);
        object_property_add(OBJECT(s), "battery-level", "int", prop_get_i64, prop_set_i64, NULL, &s->battery_level);
        object_property_add(OBJECT(s), "speaker-enabled", "bool",
                            prop_get_bool, NULL, NULL,
                            &s->axp2101_speaker_enabled);
        g_axp2101 = s;
    } else if (!strcmp(m, "aw9523")) {
        s->model = M_AW9523;
        s->regs[0x10] = 0x23;   /* M5GFX CoreS3 identity */
        s->regs[0x04] = 0xff;
        s->regs[0x05] = 0xff;
        s->regs[0x06] = 0xff;
        s->regs[0x07] = 0xff;
        s->aw9523_input_bits = 0xffff;
        object_property_add(OBJECT(s), "input-bits", "int", prop_get_i64,
                            prop_set_aw9523_input, NULL,
                            &s->aw9523_input_bits);
        g_aw9523 = s;
    } else if (!strcmp(m, "ft5x06")) {
        s->model = M_FT5X06;
        s->regs[0xA3] = 0x51;
        s->regs[0xA6] = 0x10;
        s->regs[0xA8] = 0x11;
        s->regs[0x02] = 0;
        g_ft_touch = s;
    } else if (!strcmp(m, "tca8418")) {
        s->model = M_TCA8418;
        s->regs[0x03] = 0;
        s->regs[0x04] = 0;
        object_property_add(OBJECT(s), "key-event", "uint8",
                            prop_get_u8, prop_set_key_event, NULL,
                            &s->key_event);
        object_property_add(OBJECT(s), "ir-rx-start", "uint8",
                            prop_get_u8, prop_set_ir_rx_start, NULL,
                            &s->key_event);
        g_keyboard = s;
        esp32_gpio_set_input(11, 1);  /* active-low IRQ idles high */
    } else if (!strcmp(m, "pi4ioe")) {
        s->model = M_PI4IOE;
        s->regs[0x01] = 0xa2;
        s->regs[0x07] = 0xff;
        s->regs[0x0b] = 0xff;
        s->pi4ioe_input_bits = 0xff;
        object_property_add(OBJECT(s), "input-bits", "int", prop_get_i64,
                            prop_set_pi4ioe_input, NULL,
                            &s->pi4ioe_input_bits);
    } else if (!strcmp(m, "gc0308")) {
        s->model = M_GENERIC;
        s->regs[0x00] = 0x9B;
    } else if (!strcmp(m, "m5ioe1_v4")) {
        s->model = M_IOE1;
        s->regs[0x00] = 0x34;
        s->regs[0x01] = 0x12;
        s->regs[0x02] = 0x04;
        s->regs[0x27] = 3300 & 0xff;
        s->regs[0x28] = 3300 >> 8;
        s->m5ioe1_input_bits = 0x3fff;
        s->m5ioe1_adc_mv[0] = 1650;
        s->m5ioe1_temp_raw = 850;
        object_property_add(OBJECT(s), "input-bits", "int", prop_get_i64,
                            prop_set_m5ioe1_input, NULL,
                            &s->m5ioe1_input_bits);
        object_property_add(OBJECT(s), "adc1-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[0]);
        object_property_add(OBJECT(s), "adc2-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[1]);
        object_property_add(OBJECT(s), "adc3-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[2]);
        object_property_add(OBJECT(s), "adc4-mv", "int", prop_get_i64,
                            prop_set_i64, NULL, &s->m5ioe1_adc_mv[3]);
    } else {
        s->model = M_GENERIC;
    }
}

static Property dev_props[] = {
    DEFINE_PROP_STRING("model", M5swI2CDev, model_name),
    DEFINE_PROP_END_OF_LIST(),
};

static void dev_reset(DeviceState *dev)
{
    M5swI2CDev *s = M5SW_I2C_DEV(dev);

    if (s->model == M_TCA8418) {
        g_key_event_head = 0;
        g_key_event_count = 0;
        esp32_gpio_set_input(11, 1);
    }
}

static void dev_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    I2CSlaveClass *k = I2C_SLAVE_CLASS(klass);
    dc->realize = dev_realize;
    device_class_set_legacy_reset(dc, dev_reset);
    k->event = dev_event;
    k->recv = dev_recv;
    k->send = dev_send;
    device_class_set_props(dc, dev_props);
}

static const TypeInfo dev_info = {
    .name = TYPE_M5SW_I2C_DEV,
    .parent = TYPE_I2C_SLAVE,
    .instance_size = sizeof(M5swI2CDev),
    .class_init = dev_class_init,
};

static void dev_register(void)
{
    type_register_static(&dev_info);
    type_register_static(&ip2315_info);
}
type_init(dev_register)

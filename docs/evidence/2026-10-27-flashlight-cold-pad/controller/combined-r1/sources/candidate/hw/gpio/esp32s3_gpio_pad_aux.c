/*
 * ESP32-S3 retained RTC pad ownership and MMIO storage.
 *
 * This intentionally does not synthesize RTC waveforms, held pad levels,
 * sleep entry, power-domain transitions, or USB pad ownership. Such owners
 * withdraw ordinary digital GPIO observations until their source is known.
 * Register definitions: ESP32-S3 TRM v1.8, chapters 6/10; ESP-IDF commit
 * 735507283d5b2f9fb363a1901172dbd9e847945d, esp32s3 rtc_io_reg.h and
 * rtc_cntl_reg.h. BQL serializes storage and observer notifications.
 */
#include "qemu/osdep.h"
#include "hw/gpio/esp32s3_gpio_pad_aux.h"

#define RTCIO_SIZE              0x400
#define RTCIO_WORDS             (RTCIO_SIZE / sizeof(uint32_t))
#define RTCIO_DATA_MASK         0xfffffc00u
#define RTCIO_PAD_FIRST         0x84
#define RTCIO_PAD_MUX_SEL       (1u << 19)

#define CNTL_STATE0             0x18
#define CNTL_PWC                0x88
#define CNTL_DIG_ISO            0x94
#define CNTL_PAD_HOLD           0xd8
#define CNTL_DIG_PAD_HOLD       0xdc
#define CNTL_SLEEP_REQUEST      (1u << 31)
#define CNTL_RTC_FORCE_HOLD     (1u << 21)
#define CNTL_RTC_FORCE_PD       (1u << 18)
#define CNTL_RTC_FORCE_ISO      (1u << 4)
#define CNTL_DIG_FORCE_HOLD     (1u << 15)
#define CNTL_DIG_PAD_FORCE_ISO  (1u << 13)
#define CNTL_DIG_AUTOHOLD_CLEAR (1u << 10)
#define CNTL_DIG_AUTOHOLD_STATE (1u << 9)
/* Force isolation of the digital wrapper/CPU/peripheral domain or core.
 * These unmodeled transitions cannot establish a digital pad's source.
 */
#define CNTL_DIG_SOURCE_ISO     ((1u << 30) | (1u << 26) | \
                                 (1u << 24) | (1u << 8))

typedef struct RtcCntlWord {
    hwaddr offset;
    uint32_t reset;
    uint32_t rw_mask;
    uint32_t ro_mask;
} RtcCntlWord;

static const RtcCntlWord cntl_words[] = {
    { CNTL_STATE0,       0x00000000, 0xe0400000, 0x10000000 },
    { CNTL_PWC,          0x00000925, 0x003c0fff, 0x00000000 },
    { CNTL_DIG_ISO,      0xaa805080, 0xffc0f980, 0x00000200 },
    { CNTL_PAD_HOLD,     0x00000000, 0x003fffff, 0x00000000 },
    { CNTL_DIG_PAD_HOLD, 0x00000000, 0xffffffff, 0x00000000 },
};

typedef struct Esp32s3GpioPadAux {
    Esp32GpioState *gpio;
    MemoryRegion iomem;
    uint32_t rtcio[RTCIO_WORDS];
    uint32_t cntl[G_N_ELEMENTS(cntl_words)];
    /* A request is not proof of sleep entry or recovery. The unimplemented
     * power FSM cannot re-establish pad provenance by clearing that request.
     * Only a new VM/GPIO owner starts a fresh power-on provenance domain.
     */
    bool power_history_unknown;
} Esp32s3GpioPadAux;

static Esp32s3GpioPadAux *pad_aux;

static bool aux_active(void)
{
    return pad_aux &&
           esp32_gpio_get_controller(true) == pad_aux->gpio;
}

static int cntl_index(hwaddr addr)
{
    for (unsigned i = 0; i < G_N_ELEMENTS(cntl_words); i++) {
        if (cntl_words[i].offset == addr) {
            return i;
        }
    }
    return -1;
}

static uint32_t cntl_value(hwaddr addr)
{
    int index = cntl_index(addr);
    assert(index >= 0);
    return pad_aux->cntl[index];
}

uint32_t esp32s3_gpio_pad_aux_blockers(Esp32GpioState *gpio, unsigned pin)
{
    uint32_t blocks = 0;

    if (!aux_active() || pad_aux->gpio != gpio) {
        return ESP32S3_PAD_AUX_UNBOUND;
    }
    if (pad_aux->power_history_unknown) {
        blocks |= ESP32S3_PAD_AUX_POWER_REQUEST;
    }
    /* No USB ownership/injection hook is provided by this auxiliary model.
     * Even a GPIO IO_MUX setting is not proof that USB released these pads.
     */
    if (pin == 19 || pin == 20) {
        blocks |= ESP32S3_PAD_AUX_USB_UNOBSERVED;
    }
    if (cntl_value(CNTL_DIG_ISO) & CNTL_DIG_SOURCE_ISO) {
        blocks |= ESP32S3_PAD_AUX_ISOLATION;
    }
    if (pin <= 21) {
        if (pad_aux->rtcio[(RTCIO_PAD_FIRST + 4 * pin) / 4] &
            RTCIO_PAD_MUX_SEL) {
            blocks |= ESP32S3_PAD_AUX_RTC_MUX;
        }
        /* The RTC hold bank also owns these pads while their mux is DIGITAL. */
        if ((cntl_value(CNTL_PAD_HOLD) & (1u << pin)) ||
            (cntl_value(CNTL_PWC) & CNTL_RTC_FORCE_HOLD)) {
            blocks |= ESP32S3_PAD_AUX_RTC_HOLD;
        }
        if (cntl_value(CNTL_PWC) & (CNTL_RTC_FORCE_PD | CNTL_RTC_FORCE_ISO)) {
            blocks |= ESP32S3_PAD_AUX_ISOLATION;
        }
    } else if (pin >= 26 && pin <= 48) {
        uint32_t iso = cntl_value(CNTL_DIG_ISO);
        /* FORCE_UNHOLD defaults to 1. It must not mask an independent
         * per-pad hold, whose public IDF setter only writes this bank.
         * AUTOHOLD_EN is configuration; only actual state would own a pad.
         */
        if ((cntl_value(CNTL_DIG_PAD_HOLD) & (1u << (pin - 21))) ||
            (iso & (CNTL_DIG_FORCE_HOLD | CNTL_DIG_AUTOHOLD_STATE))) {
            blocks |= ESP32S3_PAD_AUX_DIGITAL_HOLD;
        }
        if (iso & CNTL_DIG_PAD_FORCE_ISO) {
            blocks |= ESP32S3_PAD_AUX_ISOLATION;
        }
    }
    return blocks;
}

bool esp32s3_gpio_pad_aux_cntl_read(hwaddr addr, uint32_t *value)
{
    int index = cntl_index(addr);

    if (!value || index < 0 || !aux_active()) {
        return false;
    }
    /* WO strobes never latch or read back; RO bits are model-owned. */
    *value = pad_aux->cntl[index];
    return true;
}

bool esp32s3_gpio_pad_aux_cntl_write(hwaddr addr, uint32_t value)
{
    Esp32GpioPadSnapshot before[54];
    int index = cntl_index(addr);

    if (index < 0 || !aux_active()) {
        return false;
    }
    esp32_gpio_capture_pads(pad_aux->gpio, before);
    pad_aux->cntl[index] = (value & cntl_words[index].rw_mask) |
        (pad_aux->cntl[index] & cntl_words[index].ro_mask);
    if (addr == CNTL_DIG_ISO && (value & CNTL_DIG_AUTOHOLD_CLEAR)) {
        pad_aux->cntl[index] &= ~CNTL_DIG_AUTOHOLD_STATE;
    }
    if ((addr == CNTL_STATE0 && (value & CNTL_SLEEP_REQUEST)) ||
        (addr == CNTL_PWC && (value & CNTL_RTC_FORCE_PD))) {
        pad_aux->power_history_unknown = true;
    }
    esp32_gpio_notify_pads(pad_aux->gpio, before, ESP32_GPIO_PAD_OVERRIDE);
    return true;
}

bool esp32s3_gpio_pad_aux_cntl_read_access(hwaddr addr, unsigned size,
                                         uint64_t *value)
{
    uint32_t word;
    unsigned byte = addr & 3;

    if (!value || !esp32s3_gpio_pad_aux_cntl_read(addr & ~(hwaddr)3, &word)) {
        return false;
    }
    *value = 0;
    if ((size == 1 || size == 2 || size == 4) && byte + size <= 4) {
        uint32_t mask = size == 4 ? UINT32_MAX : (1u << (8 * size)) - 1;
        *value = (word >> (8 * byte)) & mask;
    }
    return true;
}

bool esp32s3_gpio_pad_aux_cntl_write_access(hwaddr addr, unsigned size,
                                          uint64_t value)
{
    hwaddr aligned = addr & ~(hwaddr)3;
    uint32_t word;
    unsigned byte = addr & 3;

    if (!esp32s3_gpio_pad_aux_cntl_read(aligned, &word)) {
        return false;
    }
    if ((size == 1 || size == 2 || size == 4) && byte + size <= 4) {
        uint32_t mask = size == 4 ? UINT32_MAX : (1u << (8 * size)) - 1;
        mask <<= 8 * byte;
        word = (word & ~mask) | (((uint32_t)value << (8 * byte)) & mask);
        esp32s3_gpio_pad_aux_cntl_write(aligned, word);
    }
    return true;
}

static bool rtcio_alias(hwaddr addr, hwaddr *target, bool *set)
{
    switch (addr) {
    case 0x04: case 0x10: case 0x1c:
        *target = addr - 4;
        *set = true;
        return true;
    case 0x08: case 0x14: case 0x20:
        *target = addr - 8;
        *set = false;
        return true;
    default:
        return false;
    }
}

static uint64_t rtcio_read(void *opaque, hwaddr addr, unsigned size)
{
    Esp32s3GpioPadAux *s = opaque;
    hwaddr target;
    bool set;

    if ((addr & 3) || addr >= RTCIO_SIZE ||
        rtcio_alias(addr, &target, &set)) {
        return 0;
    }
    /* RTC_GPIO_IN has no modeled RTC input plane. Its reset storage is not
     * evidence of a low physical pad: RTC mux ownership always blocks that.
     */
    return s->rtcio[addr / 4];
}

static void rtcio_write(void *opaque, hwaddr addr, uint64_t value,
                        unsigned size)
{
    Esp32s3GpioPadAux *s = opaque;
    Esp32GpioPadSnapshot before[54];
    hwaddr target;
    bool set;
    uint32_t v = value;

    if ((addr & 3) || addr >= RTCIO_SIZE || addr == 0x24) {
        return;
    }
    esp32_gpio_capture_pads(s->gpio, before);
    if (rtcio_alias(addr, &target, &set)) {
        v &= RTCIO_DATA_MASK;
        if (set) {
            s->rtcio[target / 4] |= v;
        } else {
            s->rtcio[target / 4] &= ~v;
        }
    } else {
        if (addr == 0x00 || addr == 0x0c || addr == 0x18) {
            v &= RTCIO_DATA_MASK;
        } else if (addr == 0x1fc) {
            v &= 0x0fffffffu;
        }
        s->rtcio[addr / 4] = v;
    }
    esp32_gpio_notify_pads(s->gpio, before, ESP32_GPIO_PAD_OVERRIDE);
}

static const MemoryRegionOps rtcio_ops = {
    .read = rtcio_read,
    .write = rtcio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4,
    .valid.max_access_size = 4,
};

void esp32s3_gpio_pad_aux_init(Esp32GpioState *gpio, MemoryRegion *sys_mem,
                              hwaddr rtcio_base)
{
    static const uint32_t pad_reset[22] = {
        0x50000000, 0x48000000, 0x50000000, 0x48000000,
        0x50000000, 0x50000000, 0x48000000, 0x40000000,
        0x40000000, 0x40000000, 0x40000000, 0x40000000,
        0x40000000, 0x40000000, 0x40000000, 0x40000000,
        0x40000000, 0x40000000, 0x40000000, 0x50000000,
        0x50000000, 0x50000000,
    };
    Esp32GpioPadSnapshot before[54];
    Esp32s3GpioPadAux *s;

    assert(gpio && sys_mem);
    if (pad_aux && pad_aux->gpio == gpio) {
        return;
    }
    esp32_gpio_capture_pads(gpio, before);
    s = g_new0(Esp32s3GpioPadAux, 1);
    s->gpio = gpio;
    for (unsigned i = 0; i < G_N_ELEMENTS(pad_reset); i++) {
        s->rtcio[(RTCIO_PAD_FIRST + 4 * i) / 4] = pad_reset[i];
    }
    s->rtcio[0x1fc / 4] = 0x02101180;
    for (unsigned i = 0; i < G_N_ELEMENTS(cntl_words); i++) {
        s->cntl[i] = cntl_words[i].reset;
    }
    memory_region_init_io(&s->iomem, OBJECT(gpio), &rtcio_ops, s,
                          "esp32s3.rtcio-pad-storage", RTCIO_SIZE);
    memory_region_add_subregion_overlap(sys_mem, rtcio_base, &s->iomem, 0);
    pad_aux = s;
    esp32_gpio_notify_pads(gpio, before, ESP32_GPIO_PAD_OVERRIDE);
}

#pragma once

#include "hw/sysbus.h"
#include "hw/hw.h"
#include "hw/registerfields.h"

#define TYPE_ESP32_GPIO "esp32.gpio"
#define ESP32_GPIO(obj)             OBJECT_CHECK(Esp32GpioState, (obj), TYPE_ESP32_GPIO)
#define ESP32_GPIO_GET_CLASS(obj)   OBJECT_GET_CLASS(Esp32GpioClass, obj, TYPE_ESP32_GPIO)
#define ESP32_GPIO_CLASS(klass)     OBJECT_CLASS_CHECK(Esp32GpioClass, klass, TYPE_ESP32_GPIO)

REG32(GPIO_STRAP, 0x0038)

#define ESP32_STRAP_MODE_FLASH_BOOT 0x12
#define ESP32_STRAP_MODE_UART_BOOT  0x0f

typedef struct Esp32GpioState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    MemoryRegion iomux;
    qemu_irq irq;
    uint32_t strap_mode;
} Esp32GpioState;

typedef struct Esp32GpioClass {
    SysBusDeviceClass parent_class;
} Esp32GpioClass;

bool esp32_gpio_matrix_i2c_pins(unsigned controller, bool s3, int *sda, int *scl);
int esp32_gpio_matrix_out_signal(int pin, bool s3);
int esp32_gpio_matrix_in_pin(unsigned signal, bool s3);

/* Nominal pad observations. Require BQL; callbacks must not mutate GPIO. */

#include "qapi/error.h"

#define ESP32_GPIO_PAD_SOURCE_GPIO             (1u << 0)
#define ESP32_GPIO_PAD_SOURCE_EXTERNAL         (1u << 1)
#define ESP32_GPIO_PAD_SOURCE_FORCE            (1u << 2)
#define ESP32_GPIO_PAD_SOURCE_BOARD_UP         (1u << 3)
#define ESP32_GPIO_PAD_SOURCE_BOARD_DOWN       (1u << 4)
#define ESP32_GPIO_PAD_SOURCE_IOMUX_UP         (1u << 5)
#define ESP32_GPIO_PAD_SOURCE_IOMUX_DOWN       (1u << 6)
#define ESP32_GPIO_PAD_SOURCE_LEGACY_FALLBACK   (1u << 7)

#define ESP32_GPIO_PAD_BLOCK_MUX               (1u << 0)
#define ESP32_GPIO_PAD_BLOCK_PERIPHERAL_DATA   (1u << 1)
#define ESP32_GPIO_PAD_BLOCK_PERIPHERAL_OE     (1u << 2)
#define ESP32_GPIO_PAD_BLOCK_OVERRIDE          (1u << 3)
#define ESP32_GPIO_PAD_BLOCK_FLOATING          (1u << 4)
#define ESP32_GPIO_PAD_BLOCK_CONFLICT          (1u << 5)
#define ESP32_GPIO_PAD_BLOCK_RESET_UNKNOWN     (1u << 6)

#define ESP32_GPIO_PAD_CHANGE_LEVEL            (1u << 0)
#define ESP32_GPIO_PAD_CHANGE_KNOWN            (1u << 1)
#define ESP32_GPIO_PAD_CHANGE_SOURCE           (1u << 2)
#define ESP32_GPIO_PAD_CHANGE_DRIVE            (1u << 3)
#define ESP32_GPIO_PAD_CHANGE_ROUTE            (1u << 4)
#define ESP32_GPIO_PAD_CHANGE_IOMUX            (1u << 5)
#define ESP32_GPIO_PAD_CHANGE_EXTERNAL         (1u << 6)
#define ESP32_GPIO_PAD_CHANGE_FORCE            (1u << 7)
#define ESP32_GPIO_PAD_CHANGE_OD               (1u << 8)
#define ESP32_GPIO_PAD_CHANGE_BIAS             (1u << 9)
#define ESP32_GPIO_PAD_CHANGE_RESET            (1u << 10)
#define ESP32_GPIO_PAD_CHANGE_RECEIVER         (1u << 11)
#define ESP32_GPIO_PAD_CHANGE_LATCH            (1u << 12)
#define ESP32_GPIO_PAD_CHANGE_ENABLE           (1u << 13)

typedef struct Esp32GpioPadObserver Esp32GpioPadObserver;
typedef struct Esp32GpioBoardBias Esp32GpioBoardBias;

typedef enum Esp32GpioPadCause {
    ESP32_GPIO_PAD_OUT, ESP32_GPIO_PAD_ENABLE, ESP32_GPIO_PAD_DRIVER,
    ESP32_GPIO_PAD_ROUTE, ESP32_GPIO_PAD_EXTERNAL, ESP32_GPIO_PAD_FORCE,
    ESP32_GPIO_PAD_DIRECT_OD, ESP32_GPIO_PAD_RESET, ESP32_GPIO_PAD_IOMUX,
    ESP32_GPIO_PAD_BIAS_ADD, ESP32_GPIO_PAD_BIAS_REMOVE,
    ESP32_GPIO_PAD_OVERRIDE,
} Esp32GpioPadCause;

typedef enum Esp32GpioBias {
    ESP32_GPIO_BIAS_PULL_UP, ESP32_GPIO_BIAS_PULL_DOWN,
} Esp32GpioBias;

typedef enum Esp32GpioOdOrigin {
    ESP32_GPIO_OD_RESET, ESP32_GPIO_OD_PAD_DRIVER, ESP32_GPIO_OD_DIRECT,
} Esp32GpioOdOrigin;

/* source_mask: GPIO_DRIVE, EXTERNAL, FORCE, BOARD_UP, BOARD_DOWN,
 * IOMUX_UP, IOMUX_DOWN, LEGACY_FALLBACK. Compatible sources may coexist.
 * blocker_mask: MUX_UNSUPPORTED, PERIPHERAL_DATA, PERIPHERAL_OE,
 * SLEEP_OR_OVERRIDE_UNMODELED, FLOATING_DEFAULT, SOURCE_CONFLICT.
 * Named constants will be uint32_t bits in the implementation header.
 */
typedef enum Esp32GpioMuxPath {
    ESP32_GPIO_MUX_GPIO_MATRIX,
    ESP32_GPIO_MUX_GPIO_ALIAS,
    ESP32_GPIO_MUX_OTHER_UNMODELED,
    ESP32_GPIO_MUX_UNRESOLVED,
} Esp32GpioMuxPath;

typedef struct Esp32GpioPadSnapshot {
    unsigned pin;
    bool s3;
    uint64_t controller_generation; /* Lifetime identity, not a physical ID. */
    uint64_t epoch;                 /* Incremented only by controller reset. */
    uint64_t revision;              /* This pin's meaningful committed facts. */
    int64_t at_ns;                  /* QEMU_CLOCK_VIRTUAL commit time. */
    bool level, known, conflict;
    bool receiver_level, receiver_known; /* IN receiver; distinct from pad. */
    uint32_t source_mask, blocker_mask, override_mask;
    bool out_latch, enable_reg;
    uint16_t out_sel;
    bool out_inv, oen_sel, oen_inv;
    bool oe_known, oe, drive_known, drive_level;
    bool open_drain, pad_driver_reg;
    Esp32GpioOdOrigin od_origin;    /* Last actual effective-OD writer. */
    bool iomux_valid;              /* Implemented pin/register, not a guess. */
    uint8_t mcu_sel;
    Esp32GpioMuxPath mux_path;      /* Per-pin function map, not mcu_sel==1. */
    bool fun_ie, fun_pu, fun_pd, slp_sel, filter_en;
    bool pull_config_known;
    bool external_seen, external_level;
    bool force_enabled, force_level;
    unsigned bias_up_count, bias_down_count;
} Esp32GpioPadSnapshot;

typedef struct Esp32GpioPadEvent {
    Esp32GpioPadCause cause;
    uint32_t change_mask;           /* Actual changed facts, not a write mask. */
    uint64_t commit_sequence;       /* Total order, including nested commits. */
    Esp32GpioPadSnapshot before, after;
} Esp32GpioPadEvent;

typedef void (*Esp32GpioPadObserverFn)(void *opaque,
                                     const Esp32GpioPadEvent *event);

/* Borrowed current controller, matching the active singleton layout.
 * NULL on absent/mismatching controller; never aliases another SoC layout.
 */
Esp32GpioState *esp32_gpio_get_controller(bool s3);
/* Pure read. Invalid pin/controller returns false, not a fabricated low. */
bool esp32_gpio_pad_snapshot(Esp32GpioState *s, unsigned pin,
                             Esp32GpioPadSnapshot *snapshot);
/* Atomically register and return the current baseline in initial_out.
 * Registration makes NO callback and supplies NO synthetic pad edge.
 * Callback event memory is borrowed for the synchronous call only.
 */
Esp32GpioPadObserver *esp32_gpio_observe_pad(
    Esp32GpioState *s, unsigned pin, Esp32GpioPadObserverFn cb, void *opaque,
    Esp32GpioPadSnapshot *initial_out, Error **errp);
void esp32_gpio_unobserve_pad(Esp32GpioPadObserver *observer);
/* One separately owned passive board bias. Multiple conflicting passive
 * biases resolve unknown; do not silently overwrite external_input storage.
 * Owner identity is opaque, never dereferenced; caller removes on unrealize.
 */
Esp32GpioBoardBias *esp32_gpio_add_board_bias(
    Esp32GpioState *s, unsigned pin, Esp32GpioBias bias,
    const void *owner, Error **errp);
void esp32_gpio_remove_board_bias(Esp32GpioBoardBias *bias);

/* Internal bridges for controller-owned auxiliary MMIO writers only. */
void esp32_gpio_capture_pads(Esp32GpioState *s,
                            Esp32GpioPadSnapshot before[54]);
void esp32_gpio_notify_pads(Esp32GpioState *s,
                           const Esp32GpioPadSnapshot before[54],
                           Esp32GpioPadCause cause);

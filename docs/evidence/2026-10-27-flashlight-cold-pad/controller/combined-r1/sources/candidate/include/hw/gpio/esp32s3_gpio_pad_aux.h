#ifndef HW_GPIO_ESP32S3_GPIO_PAD_AUX_H
#define HW_GPIO_ESP32S3_GPIO_PAD_AUX_H

#include "hw/gpio/esp32_gpio.h"

/* Unmodeled owners withdraw digital-pad qualification; they are not levels. */
#define ESP32S3_PAD_AUX_RTC_MUX        (1u << 0)
#define ESP32S3_PAD_AUX_RTC_HOLD       (1u << 1)
#define ESP32S3_PAD_AUX_DIGITAL_HOLD   (1u << 2)
#define ESP32S3_PAD_AUX_POWER_REQUEST  (1u << 3)
#define ESP32S3_PAD_AUX_ISOLATION      (1u << 4)
#define ESP32S3_PAD_AUX_USB_UNOBSERVED (1u << 5)
#define ESP32S3_PAD_AUX_UNBOUND        (1u << 6)

/* A new GPIO owner's RTC domain starts at documented power-on defaults.
 * Ordinary digital GPIO reset must not clear this retained RTC storage.
 * Call under BQL, after GPIO realization and before guest execution.
 */
void esp32s3_gpio_pad_aux_init(Esp32GpioState *gpio, MemoryRegion *sys_mem,
                              hwaddr rtcio_base);
uint32_t esp32s3_gpio_pad_aux_blockers(Esp32GpioState *gpio, unsigned pin);

/* RTC_CNTL relative offsets, only the five previously unimplemented words.
 * Return false for other words or before an auxiliary owner is bound.
 * Writes capture pads, commit storage, then notify under BQL.
 */
bool esp32s3_gpio_pad_aux_cntl_read(hwaddr addr, uint32_t *value);
bool esp32s3_gpio_pad_aux_cntl_write(hwaddr addr, uint32_t value);
/* Bus adapters retain the rest of a word on subword writes. Cross-word or
 * invalid-width accesses to an owned word are consumed without mutation.
 */
bool esp32s3_gpio_pad_aux_cntl_read_access(hwaddr addr, unsigned size,
                                         uint64_t *value);
bool esp32s3_gpio_pad_aux_cntl_write_access(hwaddr addr, unsigned size,
                                          uint64_t value);

#endif

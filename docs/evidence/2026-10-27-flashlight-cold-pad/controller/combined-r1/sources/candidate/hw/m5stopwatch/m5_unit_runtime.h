#ifndef M5_UNIT_RUNTIME_H
#define M5_UNIT_RUNTIME_H
#include "hw/qdev-core.h"
#include "hw/i2c/i2c.h"
#include "qapi/error.h"
#define TYPE_M5_UNIT "m5-unit-attachment"
#define TYPE_M5_UNIT_I2C "m5-unit-i2c"
#define MAX_UNIT_PORTS 8

typedef enum { UNIT_BUTTON, UNIT_RELAY, UNIT_ENV_III, UNIT_EXTRA, UNIT_GPIO, UNIT_RELAY2 } UnitKind;
typedef struct M5Unit {
    DeviceState parent_obj;
    UnitKind kind;
    char *unit_id;
    int yellow, white;
    bool pressed;
    bool s3;
    double temperature_c, humidity_pct, pressure_pa;
    uint64_t transactions, read_bytes, written_bytes, input_events;
    uint64_t output_transitions;
    int previous_output;
    int relay2_previous[2];
    uint64_t relay2_transitions[2];
    I2CBus *bus;
} M5Unit;
OBJECT_DECLARE_SIMPLE_TYPE(M5Unit, M5_UNIT)


bool m5_unit_extra_supported(const char *unit_id);
void m5_unit_extra_realize(M5Unit *unit, Error **errp);
bool m5_unit_sensor_supported(const char *unit_id);
void m5_unit_sensor_realize(M5Unit *unit, Error **errp);
bool m5_unit_controls_supported(const char *unit_id);
void m5_unit_controls_realize(M5Unit *unit, Error **errp);
bool m5_unit_gpio_supported(const char *id);
void m5_unit_gpio_realize(M5Unit *unit, bool s3, Error **errp);
void m5_unit_gpio_initial_complete(M5Unit *unit);
uint16_t m5_unit_adc_sample(unsigned adc, unsigned channel, unsigned atten, bool s3, uint16_t fallback);
void m5_unit_pwm_observe(bool s3, unsigned channel, uint32_t timer, uint32_t duty, uint32_t conf);
void m5_unit_rmt_tx(unsigned channel, const uint32_t *symbols, unsigned count, double tick_hz);
void m5_unit_rmt_rx_arrived(void);
unsigned m5_unit_rmt_rx(unsigned channel, uint32_t *symbols, unsigned capacity, double tick_hz);
struct ESPUARTState;
void m5_unit_uart_tx(struct ESPUARTState *uart, uint8_t byte);
#endif

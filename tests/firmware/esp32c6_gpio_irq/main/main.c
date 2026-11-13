/* Actual ESP-IDF GPIO driver ISR probe. No direct ISR calls or pending writes. */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "driver/gpio.h"
#include "driver/i2c.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/gpio_reg.h"
#include "soc/soc.h"

#ifdef CONFIG_GPIO_IRQ_PROBE_NESSO
#define PROBE_PIN GPIO_NUM_3
#else
#define PROBE_PIN GPIO_NUM_9
#endif

static volatile uint32_t hits;
static volatile gpio_int_type_t active_type;

static void gpio_isr(void *unused)
{
    (void)unused;
    hits++;
    /* A held level would correctly keep interrupting. The application masks
     * it until the main task acknowledges/releases the external source. */
    if (active_type == GPIO_INTR_LOW_LEVEL || active_type == GPIO_INTR_HIGH_LEVEL) {
        gpio_intr_disable(PROBE_PIN);
    }
}

#ifdef CONFIG_GPIO_IRQ_PROBE_NESSO
static void source_write(uint8_t reg, uint8_t value)
{
    uint8_t data[] = {reg, value};
    ESP_ERROR_CHECK(i2c_master_write_to_device(I2C_NUM_0, 0x43, data,
                    sizeof(data), pdMS_TO_TICKS(500)));
}
static uint8_t source_read(uint8_t reg)
{
    uint8_t value;
    ESP_ERROR_CHECK(i2c_master_write_read_device(I2C_NUM_0, 0x43, &reg, 1,
                    &value, 1, pdMS_TO_TICKS(500)));
    return value;
}
static void source_init(void)
{
    const i2c_config_t config = {
        .mode = I2C_MODE_MASTER, .sda_io_num = GPIO_NUM_10,
        .scl_io_num = GPIO_NUM_8, .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE, .master.clk_speed = 100000,
    };
    ESP_ERROR_CHECK(i2c_param_config(I2C_NUM_0, &config));
    ESP_ERROR_CHECK(i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0));
    source_write(0x03, 0); /* All primary expander pins are inputs for this probe. */
    source_write(0x09, 3); /* A/B idle high; press is the away transition. */
    source_write(0x11, 0); /* Do not mask primary expander input events. */
    (void)source_read(0x13);
}
#endif

static void snapshot(const char *stage)
{
    printf("C6_GPIO_IRQ stage=%s pin=%d hits=%" PRIu32
           " level=%d raw=%08" PRIx32 " cpu=%08" PRIx32 "\n",
           stage, PROBE_PIN, hits, gpio_get_level(PROBE_PIN),
           REG_READ(GPIO_STATUS_REG), REG_READ(GPIO_PCPU_INT_REG));
    fflush(stdout);
}

void app_main(void)
{
#ifdef CONFIG_GPIO_IRQ_PROBE_NESSO
    source_init();
#endif
    const gpio_config_t config = {
        .pin_bit_mask = 1ULL << PROBE_PIN, .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE, .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&config));
    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    ESP_ERROR_CHECK(gpio_isr_handler_add(PROBE_PIN, gpio_isr, NULL));
    ESP_ERROR_CHECK(gpio_intr_disable(PROBE_PIN));
    snapshot("READY");
    char line[48];
    while (true) {
        if (!fgets(line, sizeof(line), stdin)) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        unsigned type;
        if (sscanf(line, "arm %u", &type) == 1 && type >= 1 && type <= 5) {
            ESP_ERROR_CHECK(gpio_intr_disable(PROBE_PIN));
            active_type = (gpio_int_type_t)type;
            ESP_ERROR_CHECK(gpio_set_intr_type(PROBE_PIN, active_type));
            ESP_ERROR_CHECK(gpio_intr_enable(PROBE_PIN));
            snapshot("ARMED");
        } else if (strncmp(line, "disable", 7) == 0) {
            ESP_ERROR_CHECK(gpio_intr_disable(PROBE_PIN));
            snapshot("DISABLED");
        } else if (strncmp(line, "ack", 3) == 0) {
#ifdef CONFIG_GPIO_IRQ_PROBE_NESSO
            printf("C6_GPIO_SOURCE_ACK status=%02x\n", source_read(0x13));
#else
            puts("C6_GPIO_SOURCE_ACK external_release_required");
#endif
            snapshot("ACK");
        } else if (strncmp(line, "reset", 5) == 0) {
            puts("C6_GPIO_IRQ_RESET_REQUEST");
            fflush(stdout);
            esp_restart();
        } else if (strncmp(line, "snap", 4) == 0) {
            snapshot("SNAPSHOT");
        } else {
            puts("C6_GPIO_IRQ_BAD_COMMAND");
            fflush(stdout);
        }
    }
}

#include <Arduino.h>
#include "esp_task_wdt.h"
#include "esp_intr_alloc.h"
#include "esp_timer.h"
#include "soc/interrupts.h"

static volatile uint32_t *const tg = (volatile uint32_t *)0x60008000;
static volatile uint32_t *const pcr = (volatile uint32_t *)0x60096000;
static volatile int64_t fired;
static void IRAM_ATTR alarm(void *) {
    fired = esp_timer_get_time();
    tg[0x64/4] = 0x50d83aa1;
    tg[0x48/4] = 0;
    tg[0x7c/4] = 2;
}
static int64_t begin(unsigned hold0, unsigned hold1, bool interrupt1) {
    tg[0x64/4] = 0x50d83aa1;
    tg[0x48/4] = 0;
    tg[0x7c/4] = 2;
    pcr[0x44/4] = 1u << 22;
    tg[0x4c/4] = 20000u << 16;
    tg[0x50/4] = hold0;
    tg[0x54/4] = hold1;
    tg[0x58/4] = hold0;
    tg[0x5c/4] = hold1;
    tg[0x70/4] |= 2;
    fired = 0;
    int64_t started = esp_timer_get_time();
    tg[0x48/4] = (1u << 31) | (1u << 22) | (interrupt1 ? 1u << 27 : 0);
    tg[0x60/4] = 1;
    return started;
}
void setup() {
    Serial.begin(115200);
    delay(100);
    esp_err_t error = esp_task_wdt_deinit();
    if (error != ESP_OK && error != ESP_ERR_INVALID_STATE) {
        Serial.printf("OFF_SETUP_FAIL deinit=%x\n", error);
        return;
    }
    intr_handle_t handle = nullptr;
    if (esp_intr_alloc(ETS_TG0_WDT_LEVEL_INTR_SOURCE, ESP_INTR_FLAG_IRAM,
                       alarm, nullptr, &handle) != ESP_OK) return;
    Serial.println("OFF_PROBE_READY");
    for (unsigned index = 0; index < 2; index++) {
        unsigned hold = 1-index;
        Serial.printf("OFF_BEGIN hold=%u\n", hold);
        int64_t started = begin(hold, hold, false);
        delay(50);
        bool pass = !fired && tg[0x50/4] == hold;
        tg[0x48/4] = 0;
        Serial.printf("OFF_LIVE hold=%u elapsed_us=%lld result=%s\n", hold,
                      (long long)(esp_timer_get_time()-started), pass ? "PASS" : "FAIL");
    }
    int64_t started = begin(200, 300, true);
    while (!fired && esp_timer_get_time()-started < 1000000) delay(1);
    int64_t elapsed = fired ? fired-started : -1;
    tg[0x48/4] = 0;
    Serial.printf("OFF_TO_INT elapsed_us=%lld expected_us=250000 result=%s\n",
                  (long long)elapsed, elapsed >= 230000 && elapsed <= 270000 ? "PASS" : "FAIL");
    Serial.println("OFF_PROBE_DONE");
}
void loop() { delay(100); }

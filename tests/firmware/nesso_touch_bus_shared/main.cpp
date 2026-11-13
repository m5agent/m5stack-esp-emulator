#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <M5GFX.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <cstdio>
#include <cassert>

static M5GFX display;
static TaskHandle_t input_task;
static TaskHandle_t drawing_task;
static uint32_t cycle;
static volatile uint32_t sample_count;
static volatile int sample_x;
static volatile int sample_y;

static void input_reader(void*) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        lgfx::touch_point_t point{};
        const auto start_count = display.getStartCount();
        const unsigned count = display.getTouchRaw(&point, 1);
        sample_count = count;
        sample_x = count ? point.x : -1;
        sample_y = count ? point.y : -1;
        printf("TOUCH_SAMPLE cycle=%lu held_start_count=%lu count=%u x=%d y=%d\n",
               (unsigned long)cycle, (unsigned long)start_count,
               count, (int)sample_x, (int)sample_y);
        fflush(stdout);
        xTaskNotifyGive(drawing_task);
    }
}

void setup() {
    assert(display.init());
    assert(SPI.bus() != nullptr);
    printf("ARDUINO_SPI_HANDLE_PRESENT=1\n");
    display.setRotation(0);
    assert(display.getBoard() == lgfx::board_t::board_ArduinoNessoN1);
    assert(display.touch());
    const auto cfg = display.touch()->config();
    printf("PROBE_READY board=%d touch_bus_shared=%d panel_bus_shared=%d touch_sda=%d touch_scl=%d\n",
           (int)display.getBoard(), (int)cfg.bus_shared,
           (int)display.getPanel()->config().bus_shared, cfg.pin_sda, cfg.pin_scl);
    fflush(stdout);
    display.fillScreen(0x001040);
    display.setTextColor(0xffffff);
    display.setCursor(2, 2);
    display.print("SPI + I2C touch");
    drawing_task = xTaskGetCurrentTaskHandle();
    assert(xTaskCreate(input_reader, "InputHandler", 4096, nullptr, 2, &input_task) == pdPASS);
    delay(1000);
}

void loop() {
    ++cycle;
    display.startWrite();
    // Preserve real display ownership while the higher-priority input task
    // exercises Panel_Device::getTouchRaw and the real I2C controller.
    xTaskNotifyGive(input_task);
    assert(ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000)) == 1);
    display.endWrite();
    assert(display.getStartCount() == 0);
    display.fillRect(0, 30, 135, 28, (cycle & 1) ? 0x003000 : 0x005000);
    display.setCursor(2, 34);
    display.printf("cycle %lu", (unsigned long)cycle);
    if (sample_count) display.fillCircle(sample_x, sample_y, 4, 0xffcc00);
    printf("OWNER_RELEASE_OK cycle=%lu start_count=%lu\n", (unsigned long)cycle,
           (unsigned long)display.getStartCount());
    fflush(stdout);
    delay(250);
}

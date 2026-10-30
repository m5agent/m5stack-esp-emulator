// Diagnostic firmware, not a replacement for the user's application.
#include <Arduino.h>
#include <M5StackChan.h>
#include <esp_timer.h>

#ifndef SCREEN_BLOCKED_CONTROL
#define SCREEN_BLOCKED_CONTROL 0
#endif

static constexpr const char* NONCE = "stackchan-screen-motion-20261030-v3";
static uint32_t readyAt, lastTargetAt, lastSampleAt, lastLoopAt, maxLoopGap;
static uint32_t pressedCount, releasedCount, touchSequence, updateCount;
static uint32_t lastUpdateAt, lastUpdateGap, maxUpdateGap, lastUpdateCost;
static uint32_t lastDrawCost, lastReportCost, lastMotionCommandCost;
static int targetYaw, targetPitch, leg;
static bool moving, blockedDone, wasDown;
static uint8_t rawFt[5];
static bool rawFtOk, previousRawDown;
static const char* phase = "idle";

static void render() {
    // Keep the observation UI below a large SPI redraw. Counts and timing stay
    // in serial; only the 8x8 real-guest status block changes while polling.
    static bool rendered, renderedDown;
    if (rendered && renderedDown == wasDown) return;
    const int64_t start = esp_timer_get_time();
    M5StackChan.Display().fillRect(8, 60, 8, 8, wasDown ? TFT_GREEN : TFT_BLUE);
    lastDrawCost = (uint32_t)(esp_timer_get_time() - start);
    rendered = true;
    renderedDown = wasDown;
}

static void report(const char* kind, int x = -1, int y = -1) {
    // Do not put synchronous UART ReadPos traffic in touch telemetry. The
    // independent same-guest QOM snapshot is the actual-shaft witness.
    const int64_t start = esp_timer_get_time();
    Serial.printf("{\"nonce\":\"%s\",\"kind\":\"%s\",\"mode\":%d,"
                  "\"phase\":\"%s\",\"ms\":%lu,\"sequence\":%lu,"
                  "\"down\":%s,\"xy\":[%d,%d],\"presses\":%lu,\"releases\":%lu,"
                  "\"updates\":%lu,\"max_loop_gap_ms\":%lu,"
                  "\"last_update_gap_ms\":%lu,\"max_update_gap_ms\":%lu,\"update_cost_us\":%lu,"
                  "\"ft_read_ok\":%s,\"ft_count\":%d,\"ft_xy\":[%d,%d],\"ft_irq\":%d,"
                  "\"draw_cost_us\":%lu,\"previous_report_cost_us\":%lu,\"motion_command_cost_us\":%lu,"
                  "\"target_ddeg\":[%d,%d]}\n",
                  NONCE, kind, SCREEN_BLOCKED_CONTROL, phase,
                  (unsigned long)millis(), (unsigned long)touchSequence,
                  wasDown ? "true" : "false", x, y,
                  (unsigned long)pressedCount, (unsigned long)releasedCount,
                  (unsigned long)updateCount, (unsigned long)maxLoopGap,
                  (unsigned long)lastUpdateGap, (unsigned long)maxUpdateGap,
                  (unsigned long)lastUpdateCost, rawFtOk ? "true" : "false",
                  rawFt[0] & 0x0f, ((rawFt[1] & 0x0f) << 8) | rawFt[2],
                  ((rawFt[3] & 0x0f) << 8) | rawFt[4], digitalRead(21),
                  (unsigned long)lastDrawCost, (unsigned long)lastReportCost,
                  (unsigned long)lastMotionCommandCost, targetYaw, targetPitch);
    lastReportCost = (uint32_t)(esp_timer_get_time() - start);
}

static void target(int yaw, int pitch, int speed) {
    targetYaw = yaw;
    targetPitch = pitch;
    const int64_t start = esp_timer_get_time();
    M5StackChan.Motion.move(yaw, pitch, speed);
    lastMotionCommandCost = (uint32_t)(esp_timer_get_time() - start);
    lastTargetAt = millis();
    report("target");
}

void setup() {
    Serial.begin(115200);
    delay(100);
    M5StackChan.begin();
    M5StackChan.Motion.setAutoAngleSyncEnabled(false);
    M5StackChan.Motion.setAutoTorqueReleaseEnabled(false);
    M5StackChan.Motion.setTorqueEnabled(true);
    auto& d = M5StackChan.Display();
    d.setRotation(1);
    d.setTextSize(1);
    d.setTextColor(TFT_WHITE, TFT_BLACK);
    d.fillScreen(TFT_BLACK);
    d.setCursor(8, 8);
    d.print("Screen + servo: live FT6336U");
    render();
    Serial.printf("{\"nonce\":\"%s\",\"kind\":\"identity\",\"mode\":%d,"
                  "\"board\":%d,\"touch_enabled\":%s,\"width\":%d,\"height\":%d,"
                  "\"rotation\":%d,\"screen_controller\":\"FT6336U\","
                  "\"top_sensor\":\"Si12T-not-the-screen\"}\n",
                  NONCE, SCREEN_BLOCKED_CONTROL, (int)M5.getBoard(),
                  M5.Touch.isEnabled() ? "true" : "false",
                  d.width(), d.height(), d.getRotation());
    readyAt = lastSampleAt = lastLoopAt = lastUpdateAt = millis();
    report("ready");
}

void loop() {
    const uint32_t now = millis();
    maxLoopGap = max(maxLoopGap, now - lastLoopAt);
    lastLoopAt = now;
    // Read the actual controller through the guest's original I2C API. This
    // passive register observation neither injects input nor supplies M5.Touch.
    rawFtOk = M5.In_I2C.readRegister(0x38, 0x02, rawFt, sizeof(rawFt), 400000);
    const bool rawDown = rawFtOk && (rawFt[0] & 0x0f);
    const bool rawChanged = rawDown != previousRawDown;
    previousRawDown = rawDown;
    const uint32_t updateAt = millis();
    lastUpdateGap = updateAt - lastUpdateAt;
    maxUpdateGap = max(maxUpdateGap, lastUpdateGap);
    lastUpdateAt = updateAt;
    const int64_t updateStart = esp_timer_get_time();
    M5StackChan.update();
    lastUpdateCost = (uint32_t)(esp_timer_get_time() - updateStart);
    ++updateCount;
    const auto detail = M5.Touch.getDetail();
    const bool down = detail.isPressed();
    if (rawChanged) report(rawDown ? "ft_down" : "ft_up");
    if (down != wasDown) {
        wasDown = down;
        ++touchSequence;
        if (down) ++pressedCount;
        else ++releasedCount;
        report(down ? "screen_down" : "screen_up", detail.x, detail.y);
        render();
    }

    if (!moving && now - readyAt >= 20000) {
        moving = true;
        phase = "moving";
        render();
        target(350, 100, 250);
    }
    if (moving && now - lastTargetAt >= 2400) {
        ++leg;
        target((leg & 1) ? -350 : 350, (leg & 1) ? 250 : 100, 250);
    }
    if (SCREEN_BLOCKED_CONTROL && !blockedDone && now - readyAt >= 40000) {
        blockedDone = true;
        phase = "blocked";
        target(-400, 300, 100);
        render();
        report("blocked_begin");
        // Deliberate negative control: a real blocking application section,
        // like the official Dance example's interval delays, omits M5.update.
        // FreeRTOS still schedules the BSP's independent motion task.
        delay(6000);
        report("blocked_end");
        phase = "moving_after_block";
        render();
        lastTargetAt = millis();
    }
    if (now - lastSampleAt >= 500) {
        lastSampleAt = now;
        report("sample", detail.x, detail.y);
    }
    delay(5);
}

/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include <Arduino.h>
#include <M5StackChan.h>
#include <Preferences.h>
static const char* DIAG_NONCE = "sc-dance-release-20261029-e2f3b02d-v1";
static const char* DIAG_VARIANT = "torque_explicit_idle_release";
static void dance_diag(const char* phase, int frame_index = -1)
{
    const auto angles = M5StackChan.Motion.getCurrentAngles();
    const auto& touch = M5StackChan.TouchSensor.getIntensities();
    Serial.printf("DANCE_DIAG nonce=%s variant=%s phase=%s t=%lu frame=%d yaw_ddeg=%d pitch_ddeg=%d touch=%u,%u,%u\n",
                  DIAG_NONCE, DIAG_VARIANT, phase, (unsigned long)millis(), frame_index,
                  angles.x, angles.y, touch[0], touch[1], touch[2]);
}


/**
 * @brief
 * Angle unit: 10 = 1 degrees, Speed range: 0~1000
 * Range X: -1280 ~ 1280 (-128° ~ 128°), Range Y: 0 ~ 900 (0° ~ 90°)
 *
 */
struct Keyframe_t {
    int x             = 0;
    int y             = 0;
    int speed         = 500;
    uint32_t interval = 0;
};

/* Move around */
std::vector<Keyframe_t> dance_1 = {
    {0, 0, 500, 1000},      // Home, 1s
    {600, 200, 800, 500},   // Left, fast
    {-600, 200, 800, 500},  // Right, fast
    {600, 200, 800, 500},   // Left, fast
    {-600, 200, 800, 500},  // Right, fast
    {0, 800, 900, 400},     // Look Up
    {0, 0, 900, 400},       // Look Down
    {0, 800, 900, 400},     // Look Up
    {0, 0, 900, 400},       // Look Down
    {800, 700, 700, 500},   // Top Left
    {-800, 700, 700, 500},  // Top Right
    {800, 700, 700, 500},   // Top Left
    {-800, 700, 700, 500},  // Top Right
    {0, 0, 500, 1000}       // Back Home
};

/* Shake */
std::vector<Keyframe_t> dance_2 = {
    {0, 0, 500, 1000},    // Home
    {300, 0, 750, 250},   // Shake Left
    {-300, 0, 750, 250},  // Shake Right
    {300, 0, 750, 250},   // Shake Left
    {-300, 0, 750, 250},  // Shake Right
    {300, 0, 750, 250},   // Shake Left
    {-300, 0, 750, 250},  // Shake Right
    {0, 0, 500, 1000}     // Back Home
};

/* Nod */
std::vector<Keyframe_t> dance_3 = {
    {0, 0, 500, 1000},   // Home
    {0, 350, 900, 250},  // Nod Up
    {0, 0, 900, 250},    // Nod Down
    {0, 350, 900, 250},  // Nod Up
    {0, 0, 900, 250},    // Nod Down
    {0, 350, 900, 250},  // Nod Up
    {0, 0, 900, 250},    // Nod Down
    {0, 0, 500, 500}     // Back Home
};

std::vector<std::vector<Keyframe_t>*> dances = {
    &dance_1,
    &dance_2,
    &dance_3,
};

static int dance_index = 0;
static bool diag_waiting_release = true;

void setup()
{
    /* Init StackChan */
    Serial.begin(115200);
    M5StackChan.begin();

    /* Setup display */
    M5StackChan.Display().setTextSize(2);
    M5StackChan.Display().setTextScroll(true);
    M5StackChan.Display().setTextColor(TFT_YELLOW);
    M5StackChan.Display().printf("> Touch the top to start\n");
    M5StackChan.Display().setTextColor(TFT_GREENYELLOW);

    // Disable auto angle sync for smooth and continuous movement
    M5StackChan.Motion.setAutoAngleSyncEnabled(false);
    Preferences servo_nvs;
    servo_nvs.begin("servo", true);
    Serial.printf("DANCE_DIAG nonce=%s variant=%s zero_pos_1=%d zero_pos_2=%d\n", DIAG_NONCE, DIAG_VARIANT,
                  servo_nvs.getInt("zero_pos_1", -1), servo_nvs.getInt("zero_pos_2", -1));
    servo_nvs.end();
    // Diagnostic behavior change: keep torque enabled across idle and original dance delays.
    // This is not the unmodified official Dance example and does not establish physical servo semantics.
    M5StackChan.Motion.setAutoTorqueReleaseEnabled(false);
    M5StackChan.Motion.setTorqueEnabled(true);
    dance_diag("ready");

}

void loop()
{
    M5StackChan.update();
    // Observe only the real SDK update consuming release; retain every original dance and delay.
    const auto& diag_touch = M5StackChan.TouchSensor.getIntensities();
    if (diag_waiting_release && diag_touch[0] == 0 && diag_touch[1] == 0 && diag_touch[2] == 0) {
        dance_diag("idle_release");
        diag_waiting_release = false;
    }
    if (M5StackChan.TouchSensor.wasPressed()) {
        diag_waiting_release = true;
        dance_diag("top_pressed");
        delay(200);

        /* Perform dance */
        M5StackChan.Display().printf("> Dance #%d!\n", dance_index + 1);
        int frame_index = 0;
        for (const auto& frame : *dances[dance_index]) {
            Serial.printf("DANCE_DIAG nonce=%s variant=%s phase=target dance=%d frame=%d x=%d y=%d speed=%d interval=%lu\n", DIAG_NONCE, DIAG_VARIANT, dance_index+1, frame_index, frame.x, frame.y, frame.speed, (unsigned long)frame.interval);
            M5StackChan.Motion.move(frame.x, frame.y, frame.speed);
            delay(frame.interval);
            dance_diag("frame_end", frame_index++);
        }
        M5StackChan.Display().printf("> Finished!\n");
        dance_diag("finished");

        /* Next dance */
        dance_index = (dance_index + 1) % dances.size();

        M5StackChan.Display().setTextColor(TFT_YELLOW);
        M5StackChan.Display().printf("> Touch the top to start\n");
        M5StackChan.Display().setTextColor(TFT_GREENYELLOW);
    }

    delay(100);
}

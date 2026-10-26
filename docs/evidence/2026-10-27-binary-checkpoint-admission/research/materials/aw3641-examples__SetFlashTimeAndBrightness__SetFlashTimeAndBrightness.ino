#include <M5Stack.h>
#include <M5GFX.h>

#define FLASH_EN_PIN 26

M5GFX display;
M5Canvas canvas(&display);

uint8_t flash_brightness_time = 0;

void unit_flash_init(void)
{
    pinMode(FLASH_EN_PIN, OUTPUT);
    digitalWrite(FLASH_EN_PIN, LOW);
}

// 0: Flashlight off
// 1: 100% brightness + 220ms
// 2: 90% brightness + 220ms
// 3: 80% brightness + 220ms
// 4: 70% brightness + 220ms
// 5: 60% brightness + 220ms
// 6: 50% brightness + 220ms
// 7: 40% brightness + 220ms
// 8: 30% brightness + 220ms
// 9: 100% brightness + 1.3s
// 10: 90% brightness + 1.3s
// 11: 80% brightness + 1.3s
// 12: 70% brightness + 1.3s
// 13: 60% brightness + 1.3s
// 14: 50% brightness + 1.3s
// 15: 40% brightness + 1.3s
// 16: 30% brightness + 1.3s
void unit_flash_set_brightness(uint8_t brightness)
{
    if ((brightness >= 1) && (brightness <= 16)) {
        for (int i = 0; i < brightness; i++) {
            digitalWrite(FLASH_EN_PIN, LOW);
            delayMicroseconds(4);
            digitalWrite(FLASH_EN_PIN, HIGH);
            delayMicroseconds(4);
        }
    } else {
        digitalWrite(FLASH_EN_PIN, LOW);
    }
}

void setup()
{
    M5.begin(true, false, true, true);
    display.begin();
    canvas.setTextDatum(MC_DATUM);
    canvas.setColorDepth(8);
    canvas.setFont(&fonts::efontCN_14);
    canvas.setTextSize(2);
    canvas.createSprite(display.width(), display.height());

    unit_flash_init();
}

void loop()
{
    canvas.fillSprite(BLACK);
    canvas.setTextSize(2);
    canvas.setTextColor(ORANGE);
    canvas.drawString("M5Unit Flashlight", 160, 10);
    canvas.setTextColor(WHITE);
    switch (flash_brightness_time) {
        case 0:
            canvas.drawString("Off", 150, 100);
            break;
        case 1:
            canvas.drawString("100% brightness+220ms", 150, 100);
            break;
        case 2:
            canvas.drawString("90% brightness+220ms", 150, 100);
            break;
        case 3:
            canvas.drawString("80% brightness+220ms", 150, 100);
            break;
        case 4:
            canvas.drawString("70% brightness+220ms", 150, 100);
            break;
        case 5:
            canvas.drawString("60% brightness+220ms", 150, 100);
            break;
        case 6:
            canvas.drawString("50% brightness+220ms", 150, 100);
            break;
        case 7:
            canvas.drawString("40% brightness+220ms", 150, 100);
            break;
        case 8:
            canvas.drawString("30% brightness+220ms", 150, 100);
            break;
        case 9:
            canvas.drawString("100% brightness+1.3s", 150, 100);
            break;
        case 10:
            canvas.drawString("90% brightness+1.3s", 150, 100);
            break;
        case 11:
            canvas.drawString("80% brightness+1.3s", 150, 100);
            break;
        case 12:
            canvas.drawString("70% brightness+1.3s", 150, 100);
            break;
        case 13:
            canvas.drawString("60% brightness+1.3s", 150, 100);
            break;
        case 14:
            canvas.drawString("50% brightness+1.3s", 150, 100);
            break;
        case 15:
            canvas.drawString("40% brightness+1.3s", 150, 100);
            break;
        case 16:
            canvas.drawString("30% brightness+1.3s", 150, 100);
            break;

        default:
            break;
    }

    canvas.drawString("level", 70, 220);
    canvas.drawString("off", 160, 220);
    canvas.drawString("on", 250, 220);
    canvas.pushSprite(0, 0);

    M5.update();
    if (M5.BtnA.wasPressed()) {
        flash_brightness_time++;
        if (flash_brightness_time > 16) {
            flash_brightness_time = 1;
        }
    } else if (M5.BtnB.wasPressed()) {
        flash_brightness_time = 0;
        unit_flash_set_brightness(0);
    } else if (M5.BtnC.wasPressed()) {
        unit_flash_set_brightness(flash_brightness_time);
    }
}
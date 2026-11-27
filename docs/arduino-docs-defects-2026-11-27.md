# Arduino documentation defects for handoff

The file and line numbers refer to the English docs checkout at `7219cc9286c39b463da84053deee40bc234625db`. Paths in the table are relative to `static/en/arduino/`. The two AtomS3 LCD presets and AtomS3 Lite reuse the same button example.

| Board and case | Docs file and lines | Observed defect |
| --- | --- | --- |
| AtomS3 and AtomS3 Lite · button | `m5atoms3/button.md:12–14,20,24` | The setup omits `Serial.begin()` while the documented press and release messages use Serial. |
| AtomS3 · IMU | `m5atoms3/imu.md:10–12,33,35` | The example prints acceleration and gyro values without starting Serial. |
| StickS3 · m5pm1-1 | `m5sticks3/m5pm1.md:154,175` | Wire assigns I2C0 to GPIO47/48. The PM1 poll in `M5.update()` remaps those same pins to I2C1 and the later Wire operation fails. |
| StickS3 · m5pm1-2 | `m5sticks3/m5pm1.md:236,270` | Same Wire and PM1 pin-routing conflict. |
| StickS3 · m5pm1-3 | `m5sticks3/m5pm1.md:343,396` | Same Wire and PM1 pin-routing conflict. |
| StickS3 · wakeup-1 | `m5sticks3/wakeup.md:32` | The pinned `timerSleep(5)` path arms the ESP RTC and cuts ESP power through PM1. The sketch leaves the PM1 timer unarmed. |
| StickS3 · wakeup-2 | `m5sticks3/wakeup.md:80,100` | The PM1 poll remaps Wire's GPIO47/48, so the later PM1 Wire operation fails. |
| StopWatch · m5pm1_m5ioe1-6 | `stopwatch/m5pm1_m5ioe1.md:726–727,758–762` | The demo requests a tone or speaker initialization after dropping the amplifier or codec supply. The observed speaker-enable callback restores the rails before PCM plays. |
| StamPLC · display | `m5stamplc/display.md:25` | The example uses `Display` as a field. The pinned StamPLC API exposes `Display()`. |
| StackChan · nfc-2 | `stackchan/nfc.md:230,264` | The default touch-button height is zero. Raw touch Y ends at 239 and the BtnA region starts at 240. |
| PaperMono · nfc-4 | `papermono/nfc.md:817–818,858` | The emulation setup reaches `units.begin()` before enabling NFC power on IOE1 GPIO4. |
| PaperColor · ir_nec | `papercolor/ir_nec.md:19,115–116` | `begin(DISABLE_LED_FEEDBACK)` selects a one-argument overload with the pinned IRremote library. The feedback path drives the RGB LED alias on the same GPIO48 used for NEC. |
| PaperColor · sht40 | `papercolor/sht40.md:69,84` | Sensor access uses Wire on the pins that `M5.update()` routes to the internal controller. |
| Atom Echo · EchoRest | `m5atomecho/program.md:40,81` | The linked M5Atom 0.1.3 example fails compilation because `WiFiClient` is undeclared at `examples/Echo/EchoRest/BaiduRest.cpp:175`. |
| Atom Echo · PlayMusic | `m5atomecho/program.md:82` | The linked example fails under the pinned package at M5Atom 0.1.3 `src/utility/LED_DisPlay.h:62` and `src/utility/LED_DisPlay.cpp:198` because `boolean` is unavailable in that translation unit. |
| Atom Echo · RecordPlay | `m5atomecho/program.md:83` | Same compile error at M5Atom 0.1.3 `src/utility/LED_DisPlay.h:62` and `src/utility/LED_DisPlay.cpp:198`. |
| Basic v2.7 · IMU | `m5core/imu.md:1,5,9` | The example inventory assigned the Gray sketch to Basic. The page identifies Gray and already states that Basic lacks an IMU. |
| Arduino Nesso N1 · power-1 | `arduino_nesso_n1/power.md:46–47` | The example assigns the board's Boolean `isCharging()` result to `m5::Power_Class::is_charging_t`. |
| StickC · pwm-1 | `m5stickc/pwm.md:31,35` | The example uses the Arduino-ESP32 2.x LEDC setup and attachment APIs with the pinned 3.x package. |
| StickC · pwm-2 | `m5stickc/pwm.md:63–64` | Same removed LEDC APIs. |
| StickC · sh200q_m5stickc-1 | `m5stickc/sh200q_m5stickc.md:23` | M5StickC 0.3.0 does not expose `I2C_Read_NBytes` on the IMU class. |
| StickC · sh200q_m5stickc-2 | `m5stickc/sh200q_m5stickc.md:37,50` | The example passes integer pointers to `getGyroData()`, which expects float pointers in the pinned library. |
| StickC · sh200q_m5stickc-3 | `m5stickc/sh200q_m5stickc.md:68,81` | The example passes integer pointers to `getAccelData()`, which expects float pointers in the pinned library. |
| StickC · system_m5stickc-1 | `m5stickc/system_m5stickc.md:51–56` | The standalone sketch omits `loop()` and fails linking. |
| StickC Plus2 · button | `m5stickc_plus2/button.md:33,36` | The example calls `BtnPWR`. M5StickCPlus2 1.0.1 exposes `BtnC`. |
| Tab5 · speaker-1 | `m5tab5/speaker.md:15` | The original starts with `##include`. The corrected build replayed successfully. |

The two LIBRARY-DEFECT results are StickC temperature decode at M5StickC 0.3.0 `src/utility/MPU6886.cpp:208–212` and StickC Plus buzzer attach and channel-to-pin routing at M5StickCPlus 0.1.1 `src/utility/Speaker.cpp:14,31,55`.

## AtomU and Atom Echo stock UIFlow2 v2.5.4

The GitHub release images reach UART0 REPL after the offline launcher aborts.
Boot option `1` imports `M5Things` from `startup/headless.py`, and the module is
absent from these images. The separately hashed M5Burner AtomU catalog image
`UIFlow2.0 AtomU` v0.1 also identifies itself as v2.5.4. It includes
`M5Things` and passed offline launcher, REPL, button, RGB and microphone
checks. Atom Echo's GitHub v2.5.4 image passed REPL, button, RGB, microphone
and speaker checks after the launcher abort. These were standalone
esp32sim virtual-device checks.

[Stock receiver report and image identities](https://github.com/m5agent/agent-work-logs/blob/3b0ec43e686f08040ef7e39caddba854a1ca7a6b/records/esp32sim/2026-11-27-lx6a-stock-receivers/report.md#candidate-text-for-the-main-repository)
· [Startup import](https://github.com/m5stack/uiflow-micropython/blob/e437118892520ba987c2d930a2428db1cab65ab1/m5stack/modules/startup/headless.py#L11)
· [Official release](https://github.com/m5stack/uiflow-micropython/releases/tag/2.5.4)

[Integration report and per-case evidence](https://github.com/m5agent/agent-work-logs/tree/6806ff46edbe0a5d3c7a28059ca1e6b0adbd6d2e/records/esp32sim/2026-11-27-lx6b-integration)

# StickC Plus2 display and input probe

This probe targets the official StickC Plus2 UIFlow2 v2.5.3 firmware and the
independent `m5stickcplus2` machine. It renders a 135×240 RGB pattern and records
the real M5Unified A, B and power-button states, driven through GPIO37, GPIO39
and GPIO35. After A is pressed, pixel (3, 3) is green.

Functional execution must use a dedicated Device Service session. The probe's
presence and a passing source/registry check do not establish a runtime PASS.
Audio, infrared, ADC battery telemetry and power hold/wake behavior need their
own device-local evidence. This board's official build disables LVGL.

API references: the official UIFlow2 Display and Button documentation, and
the existing `sticks3_ui_test` initialization/update pattern. Hardware sources:
[StickC Plus2](https://docs.m5stack.com/en/core/M5StickC%20PLUS2), the
[official board configuration](https://github.com/m5stack/uiflow-micropython/tree/50e440780492aa847378c7d3477ab912f7063bac/m5stack/boards/M5STACK_StickC_PLUS2)
and the pinned M5Unified/M5GFX submodules of UIFlow2 v2.5.3.

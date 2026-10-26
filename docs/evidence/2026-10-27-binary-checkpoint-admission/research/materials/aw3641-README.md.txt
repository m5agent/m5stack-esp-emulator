# M5Unit-FLASHLIGHT

## Overview

### SKU:U152

Unit FlashLight is an output unit with a built-in flashlight, containing an AW3641E driver and a white LED with a color temperature of 5000 ~ 5700K. There is a mode selection switch on the internal PCB that allows you to choose between flash mode and constant light mode, using a GPIO input interface. It can be used as a flash source or for lighting applications.

## Related Link

- [Document & Datasheet - M5Unit-FlashLight](https://docs.m5stack.com/en/unit/FlashLight)

## License

- [M5Unit-FlashLight - MIT](LICENSE)

---

## M5UnitUnified

Library for M5Stack flashlight unit using [M5UnitUnified](https://github.com/m5stack/M5UnitUnified).
M5UnitUnified is a library for unified handling of various M5 units products.

### Supported units
- UnitFlashLight (SKU:U152) — AW3641E 1-wire flash LED driver

### Include file
```cpp
#include <M5UnitUnifiedFLASHLIGHT.h>
```

### Required Libraries:
- [M5UnitUnified](https://github.com/m5stack/M5UnitUnified)
- [M5Utility](https://github.com/m5stack/M5Utility)
- [M5HAL](https://github.com/m5stack/M5HAL)

### Support via [PbHub](https://docs.m5stack.com/en/unit/pbhub_1.1)

|Unit|Support|Note|
|---|---|---|
|UnitFlashLight|NG|1-wire EN pulse protocol requires µs-level timing (T_HI/T_LO 0.75–10 µs) that cannot be met over PbHub's I2C hop|

See also [M5Unit-HUB](https://github.com/m5stack/M5Unit-HUB)

### Mode selection switch (`S1`)

UnitFlashLight (U152) has an on-board **mode selection switch** (silkscreen `S1`, SPDT type)
that selects between Flash and Torch mode by wiring the AW3641E FLASH pin to +5V or GND.
**The switch is not connected to the host MCU and cannot be read from software.** Flip it
on the PCB before powering the unit:

- **Flash side**: use `unit.flash(Brightness, duration_ms)` — short pulsed flash (<= 220 ms)
- **Torch side**: use `unit.torch(duration_ms)` — steady ~214 mA illumination (<= 1.3 s)

### Examples
See also [examples/UnitUnified](examples/UnitUnified)

### For Arduino IDE settings
`FlashDemo` runs in one of two modes (Flash / Torch). Choose the mode by
uncommenting the corresponding `#define` in the sketch, or by passing it
as a compile option. The physical `S1` switch on the PCB must be set to
match the selected mode.

- FlashDemo
```cpp
// *************************************************************
// Default: Flash mode (S1 = Flash side).
// Uncomment to run the Torch demo instead (S1 = Torch side).
// *************************************************************
// #define USE_TORCH_DEMO
```

### Doxygen document
[GitHub Pages](https://m5stack.github.io/M5Unit-FLASHLIGHT/)

If you want to generate documents on your local machine, execute the following command

```
bash docs/doxy.sh
```

It will output it under docs/html  
If you want to output Git commit hashes to html, do it for the git cloned folder.

#### Required
- [Doxygen](https://www.doxygen.nl/)
- [Git](https://git-scm.com/) (Output commit hash to html)

# C6 GPIO interrupt delivery

Reviewed: `2026-11-14`. Work in progress: actual-C host controls pass; runtime
build, ESP-IDF guest ISR and original UIFlow guest callback are **NOT RUN**.
No service or browser runtime inherits this patch before its separate rollout.

The patch models ordinary GPIO source 30: pad changes set raw `STATUS`, each
pin's `INT_ENA` bit 0 gates the `PCPU_INT` view, and their OR drives the existing
interrupt matrix. Five `INT_TYPE` modes, W1TS/W1TC, configuration changes and
interrupt reset are covered. GPIO pin edge detection produces a latched level
at the matrix input; it does not require a new edge-triggered PLIC model.

NMI/source 31 delivery, sleep/wakeup, input synchronizer/filter timing, physical
electrical behavior and BMI270 interrupt generation are **NOT IMPLEMENTED by
this patch**. The NMI pending view remains separate from the ordinary CPU output.
The existing FT touch held-level source is exercised, not FT6336 trigger-pulse
timing. Neither an ISR probe nor old display/IMU polling results close those gaps.

## Fixed source contract

The upstream QEMU base is `febae182e132e4055529be423a818225ebddaa3a`.
The fixture is the postimage of the ordered 25 patch inputs at repository
`a5990e720a8c79310456bf5868141f4cfd50afe8`; its provenance binds every copied
file and prior patch. Bootstrap adds `0024-c6-gpio-interrupt-delivery.patch`.
The old runtime SHA
`80d92a6c6c68137a7813b8b7c519725aac350258078d9b244098eaabf82f63bf`
is a baseline, not a binary containing this change.

The register and driver references are fixed ESP-IDF v5.5.4:

- [GPIO register definitions](https://github.com/espressif/esp-idf/blob/v5.5.4/components/soc/esp32c6/register/soc/gpio_reg.h)
- [GPIO HAL accessors](https://github.com/espressif/esp-idf/blob/v5.5.4/components/hal/esp32c6/include/hal/gpio_ll.h)
- [GPIO ISR dispatch](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_driver_gpio/src/gpio.c)
- [Public GPIO API](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32c6/api-reference/peripherals/gpio.html)

## Actual-C host controls

Requires Python 3.12+, Git and a C compiler supporting address/undefined-behavior
sanitizers. No QEMU build, firmware, local runtime cache or guest is required:

```sh
python3 platform/tests/test_c6_gpio_irq_patch.py
python3 platform/tests/test_c6_nesso_pi4ioe_irq_patch.py
python3 -m unittest discover -s platform/tests -p 'test_bootstrap_c6_runtime.py'
```

The first command verifies fixture hashes, forward/reverse patch application,
and compiles the actual before/after GPIO and board-I2C callback bodies with only
host/QOM declarations stubbed. The board source is unchanged by this patch.
It records 45 observations covering five triggers, disabled capture/routing,
old pending enable, NMI separation, W1TC level reassertion, multiple pending
pins, type changes, reset, normal output/open-drain resolution, real PI4IOE/FT
shared pad arbitration and the default opt-out path used by other subclasses.
The preimage must retain specific failing IRQ observations. GPIO3 is not
replaced by a host callback that jumps directly to a guest ISR.

This proves controller C behavior, not guest CPU execution, physical timing,
bus timing or ISR scheduling. The output observer's number 30 is a test label;
only the later QEMU run exercises the actual machine/matrix/CPU connection.

## Build prerequisites and lane coordination

Use a new owned source/build directory; never update the preserved old runtime.
The canonical entry is:

```sh
python3 scripts/bootstrap-c6-runtime.py --source-dir .work/c6-gpio-irq-source --jobs 2
```

It replays all ordered patches, checks source receipts, and builds only
`riscv32-softmmu`. It needs the compiler, Ninja, pkg-config, GLib, pixman, slirp,
libgcrypt and libgpg-error. Record the resulting source, runtime and ROM hashes.
This command has not yet been run for this work; coordinate the heavy CPU lane
before building. No Xtensa or browser-WASM binary is rebuilt or requalified.

## Independent ESP-IDF guest probe

Build against ESP-IDF v5.5.4 with its pinned RISC-V toolchain. The default probe
uses NanoC6 GPIO9; the Nesso build uses shared GPIO3 and public hardware-I2C
transactions to primary PI4IOE address `0x43` on SDA10/SCL8.

```sh
idf.py -C tests/firmware/esp32c6_gpio_irq -B build-nano set-target esp32c6 build
idf.py -C tests/firmware/esp32c6_gpio_irq -B build-nesso \
  -D SDKCONFIG=sdkconfig.nesso.generated \
  -D SDKCONFIG_DEFAULTS='sdkconfig.defaults;sdkconfig.nesso' set-target esp32c6 build
```

Load each compatible merged image in a dedicated Device Service session and
retain build/firmware hashes separately. The source calls `gpio_config`,
`gpio_install_isr_service` and `gpio_isr_handler_add`; only that ISR increments
`hits`. It accepts UART lines `arm 1` (rising), `arm 2` (falling), `arm 3` (both),
`arm 4` (low), `arm 5` (high), `disable`, `ack`, `snap` and `reset`.
`snap` observes raw/CPU pending and the real callback count. For held-level modes
the ISR masks the pin to prevent a legitimate interrupt storm; main-task `ack`
acknowledges the external PI4IOE through I2C, and the harness releases/reenables
the source explicitly. No probe writes pending registers or calls its ISR.

Use marker-ordered input, not a blind fixed-time sequence. Wait for `READY`,
then each `ARMED`/`DISABLED` marker before injecting the documented board input.
Run the identical script against old and new runtimes. Required guest controls:

1. Disabled source input changes the pad and leaves `hits` unchanged.
2. Falling/rising/both modes increment on the corresponding real transitions;
   repeated held inputs do not manufacture extra edge callbacks.
3. A real low/high source invokes the registered ISR. Acknowledge, release and
   rearm permit a new callback; the two level polarities are checked separately.
4. Nesso primary PI4IOE and touch share the pad: acknowledging one active source
   cannot release another. Reading live button state is not interrupt evidence.
5. Guest `reset` produces a second fresh `READY`; repeat the first callback.
   A software restart and a full service-session cold boot are distinct cases.

The host controls cover raw pending/mask/ack corner cases that a public driver
may intentionally clear during setup. Do not bypass that driver to force a
guest result. Keep driver semantics explicit in each observation.

## Original UIFlow2 firmware probe

Original Nesso UIFlow2 v2.5.3 image:
`fcbd588fa92bcd24c8d4ba8fcd8837b8df64a6d5be72771e520c1ed84af88c7a`
(16,773,120 bytes). Use its original executable/partitions with only the
`uiflow/` files injected into VFS (`0x820000`, size `0x7df000`, 16 MiB flash).
Bind original BIN SHA, resulting composed-image SHA and preserved executable
partition hashes. Do not describe the VFS-modified image as byte-identical BIN.

The bundled UIFlow documentation defines `Pin`/I2C; its short Pin page omits
IRQ. The [MicroPython Pin API](https://docs.micropython.org/en/v1.25.0/library/machine.Pin.html)
and the actual ESP32 `machine_pin.c` driver were consulted for `handler` and
`trigger`; the exact original firmware must still prove the calls at runtime.
Do not fall back to polling or manually invoking a callback if an API fails.

`main.py` imports a dedicated `irq_probe` module and returns to the guest REPL.
Use the same session to call `irq_probe.arm('falling')`, apply an actual board
button/touch input, and call `irq_probe.snapshot()`. `hits` changes only in the
real `Pin.irq` callback. `acknowledge_source()` reads the actual I2C status;
`disable()` removes the IRQ callback. Test rising/both, disabled negative,
held-edge quiet, source ack/rearm and a fresh reset in marker order. Level-mode
storm handling is exercised by the independent IDF probe, not imitated here.
Do not run `M5.update()` alongside this fixture: it could acknowledge the same
shared board source before the explicit control reads it.

Request each session's ZIP before stop, stop with `purge=0`, verify lease/guest
cleanup, and preserve old failures separately. Original Mesh/Bruce UI regressions
can establish non-regression only; they cannot replace these actual ISR tests.

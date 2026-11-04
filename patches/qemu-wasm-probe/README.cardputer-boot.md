# Cardputer-ADV G0 / Boot input (`0029`)

This browser build layer follows `0028` in the independent WASM source lock.
It does not change the native bootstrap, guest firmware, keyboard decoder,
timers or watchdogs. **WASM build and guest button validation are NOT RUN**
until the new source lock is built and exercised.

The original guest driver is M5Unified commit
[`8530f5377d782e4a25a6c482de2e71c3f75ca8eb`](https://github.com/m5stack/M5Unified/blob/8530f5377d782e4a25a6c482de2e71c3f75ca8eb/src/M5Unified.cpp#L3304).
Its Cardputer/Cardputer-ADV path configures GPIO0 as input and reads its
active-low value as BtnA. The G0 switch is separate from the 56-key TCA8418
matrix; mapping it to the keyboard's QKeyCode A would exercise the wrong path.

The patch explicitly wires the board panel's `key-a-pin` to GPIO0 and starts
it released. QKeyCode F12 is a dedicated transport carrier for that switch
only when the panel is a keyboard board explicitly wired to GPIO0. Its press
and release enter the existing ESP GPIO controller. Other keys still call
the original matrix helper; its source bytes and FIFO ordering are unchanged.
F12 must not be added to the 56-key keyboard's admitted matrix key list.

The browser profile requires the exact patch path and SHA in the actual
runtime's `source.patches`. Both the host and engine check this before startup;
an old cache must fail closed rather than silently discard a G0 input. This
source requirement is not evidence that a new runtime or guest has passed.

Preimage and postimage identities:

| File | Before SHA-256 | After SHA-256 |
| --- | --- | --- |
| `hw/m5stopwatch/m5_spi_panel.c` | `838695ca92b319b516ad43bd22ea4fe0be8b23dce6ba046bd542b7d5577ed26c` | `2b0eda9d99e64122a69a9ffa5c868a4fb86726d2504f87b162d54c7f6a22e786` |
| `hw/m5stopwatch/m5cardputeradv.c` | `b7b0b1f5e212d7de275e8f2db4c657a19b3c5615b634abe9008f092761847934` | `718c8d152df07eef12f2c2ad0429bbff24a8dd0e611cc097b48783442a04dba0` |

The checkout-only C test replays the source lock's preceding layers into a
separate Git root, verifies both preimages, applies/reverses this patch and
checks the postimages against the lock. It compiles the real keyboard input
branch, unchanged matrix helpers and board configuration statements with
host GPIO/FIFO observations. The old source must fail the missing GPIO0
wiring control; the new source must preserve every other QKeyCode and invalid
boundary while delivering active-low G0 edges without FIFO events.

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_cardputer_boot_button_patch test_cardputer_keyboard_qcode_patch \
  test_bootstrap_qemu_browser_runtime
node platform/tests/test_public_qemu_profiles.mjs
node platform/tests/test_public_qemu_execution.mjs
```

These controls are host C/JavaScript validation. Browser acceptance must use a
fresh owned WASM build and the same firmware's original BtnA API, keyboard
FIFO checks, framebuffer observations and normal Worker cleanup.

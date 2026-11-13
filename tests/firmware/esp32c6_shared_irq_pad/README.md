# Nesso shared interrupt pad

Patch 0023 corrects the modeled PI4IOE input/status path and combines its
active-low output with the modeled touch source on GPIO3. The
[official schematic](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1198/DK001-sche_02.png)
wires the button expander at 0x43 to SYS_IRQ; the 0x44 expander is not connected
to this line. The relevant protocol is
[PI4IOE5V6408 DS40583 Rev 3-5](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1219/PI4IOE5V6408ZTAEX.pdf),
pages 9–12. The fixed schematic SHA256 is
`c054f406cf7a710da56d74c38020171cf78741a29f07ea113aed4647146c987a`;
the datasheet SHA256 is
`4ad734bac333c2a2c76f6af406a6a4337a446fac4ad068de1415a7c96cce6706`.

Only an external input transition from its configured default to the opposite
state latches status. Masking gates the interrupt output but preserves status;
outputs do not generate new status. Reading 0x13 clears that source, while
reading 0x0f does not. A held non-default input does not immediately relatch.
Clearing or resetting one source cannot release the shared pad while the
other modeled source remains active. The 0x44 expander never drives GPIO3.

Configuration writes do not synthesize input transitions or new latched
status. Mask and direction writes can change the interrupt pad level by gating
already pending state. The model preserves
already latched status across direction changes, gates its output while the
pin is an output, and clears it on status read or software reset. The precise
silicon behavior for a direction change with previously latched status is not
specified in the cited material and has not been measured; this preservation
rule is an explicit modeling choice. Default-state changes likewise establish
the comparison for subsequent external changes without inventing a transition.

This is controller-to-pad validation. The current GPIO force-line path does
not deliver CPU interrupt-matrix status; this change does not claim CPU ISR
dispatch. BMI270 interrupt generation and FT6336 interrupt pulse/configuration
timing are also not implemented by this change. The shared line combines only
the touch state and PI4IOE pending source already modeled by the board.

The old runtime's actual HP I2C0/FIFO, QMP input and GPIO input-register
control reproduced nine failures among 17 observations. The new runtime
passes all 17. Independent actual-C controls also pass with Clang and GCC;
these are separate from guest execution. The fixed
[controller and board evidence](https://github.com/m5agent/m5stack-esp-emulator/blob/f3c10994dd7ae406542ef91123ec2e54aae653fb/tests/firmware/esp32c6_nesso_pi4ioe_irq/shared-pad-evidence-summary.json)
retains the negative controls and the initial unsupported qtest-accelerator
attempt; its successful board run uses normal TCG and a two-instruction SRAM
wait fixture.

The [fresh-runtime record](final-runtime-summary.json) binds the 25-patch
recipe at `60f13e41933a6664b8be2720d1feef7451dcc0c3`, canonical QEMU
`febae182e132e4055529be423a818225ebddaa3a`, runtime
`80d92a6c6c68137a7813b8b7c519725aac350258078d9b244098eaabf82f63bf`,
and Device Service source `4a5d28e6d4764ec78c0621aed0e0527080597486`.
All 1,273 QEMU objects were freshly built; reused dependency libraries are
explicitly distinguished from QEMU objects. The ROM, all 25 patches and 52
source postimages are pinned by the receipt and bounded record.

Original BINs used separate Device Service sessions. Mesh ran for 150.382
seconds: A held for 1.2 seconds entered the LoRa region menu; a normal short A
advanced Back to US; natural display sleep and B wake retained that selection.
Bruce ran for 150.393 seconds: touch selected Clock from WiFi, and one requested
reset restored the WiFi page after filesystem remount. Full ZIP serial showed
one Mesh boot and two Bruce boots corresponding to power-on and the requested
reset, without fatal markers. Exact retained frames were visually inspected.
These are UI, input and stability results, not wireless application or RF PASS.

NanoC6 Honeypot separately ran for 180.011 seconds without injected input.
The original configuration output was exactly 153 bytes after the 461-byte
boot prefix, with independent UART and USB logs and one boot per channel.
The five [USB](../esp32c6_usb_serial_jtag/README.md) and
[TSF/identity](../esp32c6_tsf_identity/README.md) controls passed: 257-byte TX,
197-byte RX and acknowledgment, original UIFlow2 REPL, six TSF observations,
and two independent identities stable across reset. Raw identity values and
fingerprints are not published. The separate 802.15.4 register readback remains
an expected failure. The checked-in Nesso peripherals and LoRa controller
regressions also passed; they do not establish radio transmission.

A further, independent 90.012-second Honeypot session supplied the new-runtime
API and three-page read-only observation. The browser completed before ZIP
export and stop. It is separate from the original 180-second run: the first
UI borrow reached that earlier owner only after it had stopped, and its
preflight infrastructure failure is retained. The detailed [browser response
and frame audit](https://github.com/m5agent/m5stack-esp-emulator/blob/27a1706ba1500cde7cd0e77beb479515b0beb164/tests/firmware/esp32c6_usb_serial_jtag/serial-channel-ui/final-v3/summary.json)
is separate: 18 API chunks, 13 page responses and nine reviewed screenshots.
No firmware input was injected.

Every original/probe result checks actual runtime identity, unchanged app
partition bytes, same-session ZIP before stop, and Flash/lease/process cleanup.
Reproduce the bounded original runs through Device Service with the firmware
hashes and inputs in the record; do not substitute an arbitrary uploaded
application with a direct-QEMU regression. A rebuild may have a new binary
hash and needs its own run identity. The joint matrix, main delivery and
resident rollout are separate gates and are not granted by this record.

The earlier B-change expectation remains a retained failure in the
[pre-correction record](../esp32c6_usb_serial_jtag/pre-shared-irq-runtime-summary.json).
The [exact original BIN audit](mesh-button-reader-summary.json) now establishes
that this image directly reads live input 0x0f and tracks both A and B. It does
not match the older public fork's status-gated, A-only polling implementation;
that fork's hypothetical release defect must not be attributed to this BIN.
Physical hardware and browser-WASM remain NOT RUN.

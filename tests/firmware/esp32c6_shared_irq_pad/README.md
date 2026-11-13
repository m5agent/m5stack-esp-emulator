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

Configuration writes do not create synthetic pad edges. The model preserves
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

The old runtime's actual HP I2C0/FIFO plus QMP input and GPIO input-register
control reproduces the missing assertion and incorrect shared-line release.
Candidate host C controls and fresh-runtime positive observations are separate
evidence. A fresh build with the committed ordered recipe and affected original
firmware runs must complete before this candidate receives runtime acceptance.

The earlier Mesh B-change expectation is unrelated: the original BIN responds
to a 1.2-second A hold with Home Action and to a short A with selection advance.
That same-BIN observation is retained in the
[pre-correction record](../esp32c6_usb_serial_jtag/pre-shared-irq-runtime-summary.json).
Its polling driver may rely on different edge assumptions; subsequent original
firmware results must be reported as observed, without restoring incorrect
controller behavior to make an application pass. Physical hardware and
browser-WASM are NOT RUN.

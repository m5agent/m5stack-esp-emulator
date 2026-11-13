# StackChan application rebuild controls

The original UserDemo 1.6.0 and StackChan-GPT 1.8.11 images contain an ESP-IDF
I2C ISR that notifies the waiter before copying the final RX bytes. A caller on
the other core can return and reuse its stack while the ISR still writes to it.
The public-source controls here apply only the official
[09fb236c fix](https://github.com/espressif/esp-idf/commit/09fb236cda71a7f67a33631a907b738dc41cba22)
to each image's SDK source. They do not alter the original BIN or the emulator's
interrupt timing, watchdogs, FIFO or I2C transaction completion semantics.

| Application | Public source | Original SDK source |
| --- | --- | --- |
| UserDemo 1.6.0 | [94856a77876255ceee36f2a7ffae40f572eeb1f2](https://github.com/m5stack/StackChan/tree/94856a77876255ceee36f2a7ffae40f572eeb1f2/firmware) | [v5.5.4 / 735507283d5b2f9fb363a1901172dbd9e847945d](https://github.com/espressif/esp-idf/tree/735507283d5b2f9fb363a1901172dbd9e847945d) |
| GPT 1.8.11 | [28529cdcf535bc345bd47cf21a618397663fa081](https://github.com/j15marti/StackChan-GPT/tree/28529cdcf535bc345bd47cf21a618397663fa081/firmware) | [c00874869b4a4f451e91c783da1de26ef61df58d](https://github.com/espressif/esp-idf/tree/c00874869b4a4f451e91c783da1de26ef61df58d) |

The GPT GitHub release BIN digest exactly matches the original M5Burner image.
Neither public repository/release supplied its matching ELF/map. UserDemo's
public v1.6.0 sync explicitly excludes private authentication. Public-source
rebuilds therefore have independent firmware/ELF identities and do not establish
bit-identical reproduction of the original release or private cloud behavior.

Use separate clean application and IDF clones at the commits above, including
IDF submodules. Install each SDK's declared tools and Python environment. The
recorded toolchains are GCC 14.2.0 (`esp-14.2.0_20260121`) for UserDemo and GCC
15.2.0 (`esp-15.2.0_20251204`) for GPT. Initialize the application's Git
dependencies at [these exact commits](application-source-pins.json); apply the
application's existing `firmware/patches/xiaozhi-esp32.patch` to its xiaozhi
checkout. Keep `firmware/dependencies.lock` byte-identical to the pinned source.
Do not silently accept package updates from a fresh dependency solve.

For a positive control, apply the vendored upstream patch to the IDF clone:

```sh
git -C "$idf_checkout" apply --check "$fixture/upstream-09fb236c.patch"
git -C "$idf_checkout" apply "$fixture/upstream-09fb236c.patch"
```

For the unpatched negative control, use a separate IDF checkout with no patch.
With that SDK environment exported, configure and build:

```sh
idf.py -C "$app_checkout/firmware" -DIDF_TARGET=esp32s3 -B "$build_dir" reconfigure
ninja -C "$build_dir" -j2 lang_header
ninja -C "$build_dir" -j2
```

Run the project's existing `lang_header` target first: the initial parallel
UserDemo build exposed a missing dependency edge and failed on
`assets/lang_config.h`; running that target fixed build ordering without an
application source change. A fresh GPT solve initially selected four newer
managed packages. Restoring the source lock and reconfiguring downloaded the
locked versions; the final build's lock and application tracked source remained
unchanged. An incomplete local partial-clone dependency checkout was repaired
before configuring; it is not a firmware defect.

Merge **every** offset/file pair from `flasher_args.json`, including bootloader,
partition table, otadata and `generated_assets.bin`, with the same SDK's esptool
and recorded flash settings (`dio`, `80m`, `16MB`). Preserve the rebuilt ELF/map
and all source, lock, patch and firmware hashes in private artifact storage.
Build timestamps, dependency metadata and the SDK `-dirty` version suffix make
newly rebuilt bytes distinct. The suffix in these controls also reflects local
submodule-cache links; the only tracked SDK C-source delta is the vendored patch.

Upload the merged image through a dedicated Device Service lease. Enable
`M5SW_FT_TRACE=1`, use the pinned runtime from the evidence summary, and retain
serial, raw frame samples, input receipts and `/machine/scs_servo.state` QOM
observations from that same lease. Request evidence before stopping with
`purge=0&retain_flash=0`.

The collection runner takes explicit image and runtime identities and leaves its
raw output at `REVIEW` until frames and protocol observations are checked:

```sh
python3 tests/firmware/s3_i2c_lifetime/run_application.py \
  --api "$owned_api/api/v1" --token-file "$owned_token_file" \
  --bin "$merged_bin" --sha256 "$merged_sha256" --runtime-bin "$qemu_binary" \
  --out "$ignored_output" --seconds 360 \
  --touch-at 20:85:187 --touch-at 180:160:120 \
  --touch-at 185:292:118 --touch-at 190:26:118
```

A repeated boot is a failure of uninterrupted uptime even when no panic string
appears. The recorded final positive cases used this same sampling/API sequence
with manually reviewed action timing; their exact collection/action-script
hashes are retained in the evidence summary. The checked-in runner additionally
makes the repeated-boot rejection explicit.

At the visible Welcome page, tap Skip at `(85,187)`. Observe the official
launcher, then leave it idle: its source creates the moving DVD-style screensaver
after 30 seconds. Collect raw frames every 10 seconds for at least 330 seconds
of uninterrupted runtime, with no second boot, panic or reset. Touch wakes the
screensaver; subsequent taps at `(292,118)` and `(26,118)` select adjacent launcher
pages. Verify the visible labels, controller press/release coordinates, serial
startup marker and continued UART servo protocol counters. A changing PNG file
alone is insufficient: check decoded pixels and review the frames.

Do not open AVATAR without network setup for this stability control. The official
application intentionally requests setup and a warm reboot in that state. That
exploratory attempt is retained separately and does not count as uninterrupted
uptime. Native UART servo packets establish protocol behavior only; no mechanical,
RF, optical, electrical or original-BIN hardware result is claimed.

The upstream maintainer's [ESP32-S3 hardware reproduction](https://github.com/espressif/esp-idf/issues/19050#issuecomment-5567444628)
is independent evidence of the SDK race, not our physical test of either original
application. Merely upgrading to v5.5.6 is not the asserted fix; acceptance here
is tied to the actual notify-after-RX source change and executed new artifacts.

## Recorded result

[The bounded evidence summary](application-evidence-2026-11-13.json) records
both patched public-source builds at 360 seconds, one boot each, 37 raw-frame
samples and 30 distinct decoded pixel hashes each. Actual touch-controller
press/release events wake and navigate the official launcher. UART servo packet
counts reach 32,122 and 31,980 respectively with no rejected packets. Both leases
were stopped after collecting their evidence ZIPs.

On the same pinned native runtime, the untouched original UserDemo BIN panics
within the 50-second sample and the untouched GPT BIN within the 110-second
sample. The independently rebuilt unpatched UserDemo source also panics within
the 120-second sample. These are observed sampling bounds, not deterministic
crash deadlines. All three negative leases were preserved and stopped. The new
builds pass this scoped experiment; neither original BIN is declared repaired.

# Firmware review and runtime evidence

Last reviewed: `2026-10-29`

This directory stores committed evidence for firmware normalization, static
review and public-firmware runtime tests. The evidence files are snapshots, not
the implementation or the test runner.

Implementation lives under `platform/tools/` and contract tests live under
`platform/tests/`. The public firmware matrix runner is
`platform/tools/user_firmware_matrix.py`.

Common checks:

```bash
PYTHONPATH=platform/tools python3 -m unittest \
  platform/tests/test_firmware_manifest.py \
  platform/tests/test_firmware_analysis.py \
  platform/tests/test_firmware_filesystems.py \
  platform/tests/test_firmware_static_review.py \
  platform/tests/test_user_firmware_matrix.py
```

The historical cross-vendor snapshot records 18 non-baseline samples on six
S3/C6 devices; the combined current selection adds three public Core2 images,
for 21 non-baseline samples on seven devices. Its `PARTIAL` results are not all
simulator defects:
`runtime_model_gap`, missing application frame, absent input response,
serial-only devices and fatal post-frame evidence retain separate reasons.
The original C6 software-reset chip-id gap has a separate fix evidence snapshot;
that firmware now reaches the ordinary `fatal_after_application_frame` path
without a `runtime_model_gap`. The C6 Zigbee gap remains open:
`c6_zigbee_thread_sim/run_feasibility.py` observed bidirectional 802.15.4
frames from source-built switch/light examples, but commissioning/join did not
complete.

## Core2 UIFlow2 startup

[`core2_startup/`](core2_startup/README.md) replays the public Core2 display,
Widgets, LVGL and offline WLAN startup paths through visible Device Service
sessions, with pinned stock executable bytes and retained-history checks.
It does not replace private full-application or legacy UIFlow1 validation.

## Core2 for AWS ATECC608

[`core2_atecc608/`](core2_atecc608/README.md) drives the public Core2 for AWS
factory image through three visible Device Service sessions. The `0085` QEMU
patch implements the ATECC608 wake/Read/Info/CRC path with a deterministic
locked test config and fixes the classic ESP32 DMA link-start/DC command phase.
Each run must reach `atecc608: ok: 60 02` and a nonempty frame, then stop with
`purge=0` while retaining evidence. Production key material, ECDSA signing,
electrical behavior and hardware validation remain separate.

## Core2 8 MiB PSRAM bank switch

[`core2_psram_himem/`](core2_psram_himem/) builds a small ESP-IDF firmware that
remaps two distinct upper PSRAM blocks through the same virtual MMU window and
verifies both after remap. Three independent Device Service leases pass with
QOM memory `8,388,608 B`, himem capacity `4,456,448 B`, reserve `262,144 B` and
no mismatch markers:
[`evidence-2026-10-25-core2-himem-bank-switch-3x.json`](core2_psram_himem/evidence-2026-10-25-core2-himem-bank-switch-3x.json).

This is virtual-device validation of the DRAM1 MMU data path, not physical
PSRAM or cache timing.

Filesystem inventories include a per-file `permission_policy`. FAT directory
attributes are recorded without treating them as POSIX access control;
LittleFS and SPIFFS explicitly report that Unix mode bits are absent. Runtime
permission/ACL enforcement inside the guest remains `NOT RUN`.

Device Service API `1.51.0` separately provides an operator-owned service
runtime ACL for serial/input/reset, program execute/interrupt/read, package
paths and flash reads. Real HTTP validation is recorded in
[`evidence-2026-10-29-runtime-acl.json`](evidence-2026-10-29-runtime-acl.json)
with the runner at [`runtime_acl/run_test.py`](runtime_acl/run_test.py).
This service policy is not firmware-authored filesystem permission proof and
does not sandbox arbitrary native code.

Required/optional capability consistency is covered by
[`evidence-2026-10-25-capability-required-optional-consistency.json`](evidence-2026-10-25-capability-required-optional-consistency.json):
overlap is rejected, unsupported required capability rejects the manifest, and
unsupported or unknown optional capabilities remain structured warnings.
The later
[`evidence-2026-10-26-unknown-required-capability-fail-closed.json`](evidence-2026-10-26-unknown-required-capability-fail-closed.json)
supersedes the earlier unknown-required warning behavior. On the same public
StickS3 SHA, an unknown required capability returns `REJECTED` and CLI exit
code `1` for both merged and WebBurner inputs; an unknown optional capability
remains a warning. The same evidence also imports the same WebBurner content
from two differently named package roots and requires equal `manifest_id`
while allowing the output artifact filenames to differ. The probe is
[`unknown_required_capability/run_test.py`](unknown_required_capability/run_test.py).

Hand-edited manifest policy is covered by
[`manifest_policy/run_test.py`](manifest_policy/run_test.py) and
[`evidence-2026-10-26-manifest-policy-fail-closed.json`](evidence-2026-10-26-manifest-policy-fail-closed.json):
the root `capabilities` object and its `required`/`optional` arrays are
mandatory, signed-image status cannot be understated while signature blocks
remain, eFuse security fields use strict enums, key-digest mismatch and
image secure-version rollback are rejected.

WebBurner package selection and ZIP path policy are covered by
[`webburner_import_policy/run_test.py`](webburner_import_policy/run_test.py) and
[`evidence-2026-10-26-webburner-import-policy.json`](evidence-2026-10-26-webburner-import-policy.json):
raw dot segments, duplicate/casefold-colliding ZIP entries, directory-prefix
collisions and symlinks are rejected; ambiguous
manifest/sdkconfig/eFuse/flasher/SBOM resources fail closed; an actual
`sdkconfig` takes explicit precedence over `sdkconfig.defaults`; and
multi-build WebBurner packages select exactly one build matching the target
SoC.

Image capability observations are recorded in
[`evidence-2026-10-25-image-capability-observation.json`](evidence-2026-10-25-image-capability-observation.json).
The public StickS3 Weather image contains low-confidence WiFi and display
signatures; required WiFi passes while required camera remains a structured
StickS3 mismatch. Missing/undeclared observations produce review warnings and
do not become runtime capability proof.

The real WebBurner result layout is captured in
[`evidence-2026-10-25-webburner-capability-display.json`](evidence-2026-10-25-webburner-capability-display.json):
it shows sdkconfig capabilities, image observations, scan coverage and warning
codes separately.

WebBurner `parts[]` may declare `size`, SHA-256, SHA-1, MD5 or an equivalent
`integrity` object. The importer recomputes each declaration and rejects
mismatches, malformed digests, conflicting duplicate declarations and unknown
integrity fields before composition. Successful segments record only the
verified algorithm names and a weak-digest flag. This detects accidental
corruption; it is not a publisher signature, source-authenticity proof,
secure-boot execution or hardware result:
[`evidence-2026-10-25-webburner-part-integrity.json`](evidence-2026-10-25-webburner-part-integrity.json).

Security-evidence conflicts have a separate static regression:
[`evidence-2026-10-25-security-evidence-conflicts.json`](evidence-2026-10-25-security-evidence-conflicts.json).
It covers config/eFuse disagreement, secure-boot mode mismatch and missing key
purposes without claiming that a package-supplied eFuse summary is authentic.

Secure Boot v2 image evidence now parses up to three signature blocks at
4 KiB-aligned bootloader/application boundaries, validates block magic,
version, CRC32 and the embedded SHA-256/SHA-384 image digest, and records the
embedded public-key digest. Synthetic RSA-PSS and ECDSA P-192/P-256/P-384
signature mathematics are verified against block-embedded public keys. When a
package includes an `espefuse` summary, `security.trust_root.comparison`
separately records digest match, mismatch or unavailable evidence. The summary
is self-asserted, so `security.trust_root.status` remains `not-verified`; no
live eFuse read or ROM/bootloader verification executes.
`security.anti_rollback` separately compares application `secure_version` with
the summary's `SECURE_VERSION` and warns when the image is below the declared
minimum. Both comparisons remain `not-verified`. This is static image
self-consistency, not a hardware secure-boot PASS.
The current tool-hash-bound run after mandatory capability and security
evidence hardening is
[`evidence-2026-10-26-secure-boot-image-manifest-policy-v2.json`](evidence-2026-10-26-secure-boot-image-manifest-policy-v2.json);
the preceding
[`evidence-2026-10-26-secure-boot-image-security-preflight.json`](evidence-2026-10-26-secure-boot-image-security-preflight.json)
and
[`evidence-2026-10-26-secure-boot-image.json`](evidence-2026-10-26-secure-boot-image.json)
are retained for their earlier tool hashes;
the earlier
[`evidence-2026-10-25-secure-boot-image.json`](evidence-2026-10-25-secure-boot-image.json)
remains as a historical checkpoint.

Security preflight now checks every available evidence layer rather than only
the aggregate `security.secure_boot` / `security.flash_encryption` field.
sdkconfig, signed-image status and package-provided eFuse claims cannot be
hidden by setting the aggregate to `unknown`. Missing security fields, invalid
enums, invalid signature evidence and unmodeled enabled chains are rejected.
The static probe and evidence are
[`security_preflight/run_test.py`](security_preflight/run_test.py) and
[`evidence-2026-10-26-firmware-security-preflight-fail-closed.json`](evidence-2026-10-26-firmware-security-preflight-fail-closed.json).
This remains compatibility validation, not runtime trust or live eFuse proof.

The four current public CDN artifacts refreshed on `2026-10-25` are bound in
[`evidence-2026-10-25-refreshed-public-artifacts-static.json`](evidence-2026-10-25-refreshed-public-artifacts-static.json).
That checkpoint is `STATIC_PASS / FUNCTIONAL_NOT_RUN`; its functional axis is
superseded by the later Device Service run below.

The same four artifacts passed the full manifest importer in
[`evidence-2026-10-25-refreshed-public-artifacts-manifest.json`](evidence-2026-10-25-refreshed-public-artifacts-manifest.json).
Manifest PASS does not mean a clean review: all four require human review and
the record itself does not assert functional behavior.

The refreshed bytes were then executed through Device Service in
[`evidence-2026-10-25-refreshed-four-functional-sd-mbr`](evidence-2026-10-25-refreshed-four-functional-sd-mbr/).
Results are `3 PASS / 1 PARTIAL / 0 FAIL`: XiaoZhi reaches its Wi-Fi
provisioning UI, EDC Book reaches its launch screen, CrossPoint reaches its
recent-books menu when a deterministic FAT32+MBR SD image is mounted, and
OpenAI Voice Assistant remains black under the matrix's UI/input rule.
The SD image is generated by `platform/tools/sd_image.py`, copied into the
session, re-hashed and mounted writable; the source artifact is never mounted
directly. Final screenshots and full frame/serial/storage digests are retained
in the evidence JSON.

The OpenAI black-frame cause is recorded separately in
[`evidence-2026-10-25-openai-nvs-precondition.json`](evidence-2026-10-25-openai-nvs-precondition.json).
The public 24 KiB NVS partition is erased and the app reads
`config/wifi_ssid`, `config/wifi_password` and `config/openaikey`.
`platform/tools/nvs_image.py` generates deterministic NVSv2 fixtures, and
Device Service applies a fixture only to the session Flash copy after checking
the firmware partition label, offset and size. An open-AP fixture reaches
association, DHCP, `api.openai.com` DNS and TCP/443. A non-empty-password
fixture completes WPA2-PSK four-way/EAPOL, pairwise CCMP RX, DHCP, DNS and
TCP/443; a wrong-password control is rejected at M2 MIC and retries without
DHCP. Real credentials, Realtime/audio, cloud success, WPA3, group-key
multicast, physical WPA2 and hardware remain `NOT RUN`.

The matrix can now apply the same evidence to a SHA-bound `network-first`
expectation instead of treating the absence of a UI frame as the primary
application verdict.
[`evidence-2026-10-25-network-first-review-expectation.json`](evidence-2026-10-25-network-first-review-expectation.json)
binds the public BIN, expectation digest, isolated NVS fixture and finalized
network evidence in one result key. Plaintext WiFi passwords are rejected in
the expectation file; only a password environment-variable name is allowed.

The earlier
[`refreshed-four-functional`](evidence-2026-10-25-refreshed-four-functional/)
checkpoint is retained as the `2 PASS / 2 PARTIAL` no-storage control. Its
CrossPoint `runtime_fixture_gap` is not firmware FAIL and is superseded by the
SD-mounted run.

The live resume/force-refresh path is retained in
[`evidence-2026-10-25-public-resume-refresh-live.json`](evidence-2026-10-25-public-resume-refresh-live.json).
It uses public metadata and downloads only; no Device Service session was
created.

Packages that include source files also receive a bounded SPDX header scan.
Source path hashes and declarations are eligible for license policy, while
generated code, absent third-party sources and legal review remain out of
scope.

The API and WebBurner accept explicit required/optional hardware capabilities.
The same normalization and mismatch contract applies to CLI and HTTP imports:
aliases are canonicalized, declarations are bounded and a target without a
required capability returns a structured manifest rejection. An unknown
required capability also fails closed because the checker cannot establish
that the target supports it. Declarations are operator-provided; they do not
prove that every firmware code path uses the declared peripheral.

High-confidence WiFi, Bluetooth and PSRAM build flags from package
`sdkconfig` are recorded separately as `capabilities.detected`. When sdkconfig
is absent, allowlisted image tokens are recorded as low-confidence
`capabilities.observed`. A target profile missing either detected or observed
capability receives a warning rather than an automatic rejection; strict
rejection remains tied to explicit required capabilities.

Radio build flags retain their protocol boundary in
[`evidence-2026-10-25-radio-capability-detection.json`](evidence-2026-10-25-radio-capability-detection.json):
Classic Bluetooth and Zigbee/802.15.4 are detected separately from the
generic BLE flag, without claiming runtime use.

For the Core2 public-firmware runtime gap, the 2026-10-24 trace recorded a
successful AXP2101 chip-id read followed by an unacknowledged address-`0x51`
transaction on controller 0. The 2026-10-25 follow-up proved that the old board
model exposed RTC only on controller 1. Patch `0031` now routes both controller
register blocks to the single physical GPIO21/22 bus and attaches each slave
once; AXP, RTC and INA transactions ACK on the same image, the prior I2C error
is absent, and the existing UIFlow2 Core2 device group passes. The same
legacy image still reaches an independent interrupt-WDT boundary with a black
frame, so `RUNTIME-03` stays open for that later failure.

`0032-esp32-timg-wdt-trace.patch` adds a default-off `M5SW_TIMG_TRACE=1`
channel for watchdog reset/config/feed/arm/timeout events. A default
single-session control kept feeding TG0/TG1 for more than 285 seconds;
consecutive four-session batches produced interrupt-WDT failures at varying
CPUs and PCs in five of eight leases. Explicit thread and icount controls did
not fix the path and sometimes triggered TG hardware resets earlier. The
evidence therefore classifies the remaining boundary as timing-sensitive
pending a guest code-point diagnosis, not as another fixed I2C or PMIC device
gap.

The later minimal [`core2_flash_ipc`](core2_flash_ipc/) probe first proved that
the flash-read data path could execute while an intermittent interrupt-WDT
remained. IRQ-ring evidence then captured the timer ISR writing
`CCOMPARE == CCOUNT`; the old unsigned subtraction scheduled `2^32` ticks and
deferred the next timer interrupt by roughly 26.8 seconds. Patch `0034` arms
that equal deadline for the next cycle without changing other wraparound
semantics. After the business-only fix, the probe's first-boot gate passed in
trace-enabled and trace-disabled controls. Exact counts, hashes and
accelerator variants are in
[`evidence-2026-10-26-core2-ccompare-equal-deadline.json`](core2_flash_ipc/evidence-2026-10-26-core2-ccompare-equal-deadline.json).

An earlier probe revision placed a 4096-byte local buffer on a 4096-byte task
stack; its stack overflow caused the previously reported spinlock assertion.
That run is explicitly invalidated in
[`evidence-2026-10-26-core2-flash-ipc-wdt.json`](core2_flash_ipc/evidence-2026-10-26-core2-flash-ipc-wdt.json).
The corrected evidence supports the flash-read data path and closes the minimal
probe's timer-starvation reproduction. It does not close legacy UIFlow:
TG0 stage-1 system reset, reset CPU PC `0` and a black frame remain in the same
public firmware path. Later WDT liveness and WDT-off late-state controls are
required before assigning a cause; the minimal-probe timer must not be inherited
as the legacy root cause.

The earlier QIO/cross-core diagnostics are recorded in
[`evidence-2026-10-26-core2-qio-crosscore-diagnostic.json`](evidence-2026-10-26-core2-qio-crosscore-diagnostic.json)
as `DIAGNOSTIC_ONLY`. Patch `0035` fixes a verified TIMG mask-semantics bug
where a raw WDT status raised the level IRQ while `INT_ENA.WDT` was clear; the
same legacy image still reset after that fix. A temporary QIO direct-read path
matched the SSI byte stream for sampled transactions, but later rebuilds did
not reproduce its older REPL observation and the path bypasses the SSI/m25p80
phase machine. Patch `0036` adds a stateful batch interface: m25p80 accelerates
only `STATE_READ`, the generic fallback remains per-byte equivalent, and the
sampled batches matched exactly. The Core2 UIFlow2 device group and the
shared-controller full matrix passed. Normal-WDT legacy still reset; with WDT
disabled, the bounded observation was insufficient to reach setup text or
REPL. Cross-core state tracing showed
the flash-operation and reason flags repeatedly completing, moving the working
hypothesis from permanent handshake deadlock to aggregate synchronous
Flash/cache-handoff throughput. Normal-WDT application startup, non-empty frame
and physical hardware remain unproven.

See
[`evidence-2026-10-26-core2-ssi-transfer-buf.json`](evidence-2026-10-26-core2-ssi-transfer-buf.json).

`0037` adds a unified virtual-time/CPU/PC trace across cross-core, DPORT, SSI,
UART and TIMG events. Early normal-WDT runs placed the last TG1 feed exactly
800 ms before stage-0 timeout; the final timeout PC changed between runs, and
a 1 ms dual-PC control kept the same gap but reset earlier. The initial
different-version ELF mapping to UART ISR/MicroPython VM was later rejected by
a same-VMA public-BIN byte audit; all three CPU0 windows differ. The PC sampler
is intentionally off by default because it changes scheduling. The BIN-bound
cluster is consistent with a cross-core Flash/cache-disable handoff, but its
function name remains unbound.
`0038` adds a virtual-time `SIGSTOP` control without PC sampling. At 14.800 s
the sampled PCs are not fixed; at 15.301 s they converge on CPU0
`0x40087980` and CPU1 `0x40084484`, matching a Flash block/cache-handshake
source pattern in the public BIN.
`0039` adds exact-time CPU/handoff/cache/SSI/cross-core state dumps. A
14.8/15.3/15.9-second sweep observed CPU0 waiting while CPU1 continued through
different PCs; cache, SSI transaction and cross-core counters kept increasing.
`0040` adds a default-off BIN-bound PC list for the four complete/can-start
setters. The first normal-WDT boot reached stage-0 timeout at `5.913935 s`,
then reset at `15.914787 s`, after roughly 4,376 completed handoff cycles.
This rejects the simple permanent-handoff-deadlock explanation. A zero
changed-page host-flush skip control still reset with the same black frame and
was not retained.
[`run_wdt_liveness.py`](core2_handoff_trace/run_wdt_liveness.py) disables PC
tracing and runs three isolated 18-second TIMG controls. Each observed a masked
TG0 stage-0 timeout at about `5.91 s`, then a TG0 stage-1 reset at about
`15.91 s`. TG1 completed 6,618-6,807 feeds, stayed within a 10.410 ms maximum
inter-feed interval and fed within 1.779-4.271 ms of reset; no TG1 timeout
occurred. The earlier 800 ms gap is therefore `NOT_REPRODUCED` in the current
configuration.
WDT-off 45/120-second pauses now bracket the later failure. Flash and SSI
counters stop changing at about 44 seconds; CPU0 remains in `waiti` idle at
`0x4026306e`, while CPU1 spins at `0x40100049`. CPU1 holds `A2+24=1` and
`A10+28=0`. `0041` dumps A0-A15, PS, selected object pointers and an optional
bounded stack window. BIN-bound analysis identifies the loop as LVGL
`lv_refr_vdb_flush`: a valid double-buffered `lv_disp_buf_t` has
`flushing=1`, and the display driver has `wait_cb=null`. `0042` adds the
optional object-word dump and a partial SPI `TRANS_DONE/TRANS_INTEN` IRQ
model. Display `flush_cb` executes, but the completion callback and
`lv_disp_flush_ready` are not observed. At that point the boundary was the
SPI interrupt/queue completion chain, not an unknown flag/object.

[`core2_spi_irq_remap/`](core2_spi_irq_remap/) isolates one part of that
chain with a 16-byte ESP-IDF SPI3 queue transaction. It reproduces a guest
that raises the SPI level before writing the final interrupt-matrix mapping.
The old matrix model only forwarded level edges, so the queued transaction
timed out without a guest callback. Patch `0064` recomputes outputs for
pending input levels and models `SPI_SLAVE.TRANS_DONE/TRANS_INTEN`; the same
firmware is pre-fix `FAIL` and fixed `3/3 PASS`. Legacy UIFlow still does not
reach the display completion or a non-empty frame, so this does not close
`RUNTIME-03`.

`0065-xtensa-high-priority-irq-cooperative-yield.patch` supersedes the earlier
"permanent handoff deadlock not proven" wording. The fixed double wait was
reproducible under single-thread TCG: a large icount slice let the sender clear
the previous completion flags and start the next DPORT handoff before the peer
level-4 handler observed it. The patch tracks active level-4/5 handlers, yields
after the handler publishes its start flag with `memw`, and yields when the
sender returns through `retw`; RFI and reset clear the active state. Five
independent first attempts reached the same early-state boundary at about
`5 s`, with no fixed old CPU0/CPU1 wait. Guest instructions, virtual time and
IRQ levels are unchanged.

`0066-esp32-classic-rmt-legacy.patch` replaces the unimplemented
`0x3ff56000` RMT region with eight channels, registers, 2 KiB RMTMEM,
`conf0.mem_size`, memory-mode TX, threshold refill, `TX_END`, INTMATRIX source
47 and bounded symbol capture. Without it, Neopixel initialization read
`mem_size=0`, reported `RMT translator buffer create fail`, and raised
`OSError: Error initializing Neopixel interface`. The fixed trace captures four
channel-7 transmissions of 49 symbols, and the same legacy Serial reaches
`BOARD NAME`/`APIKEY`.

The final runtime still reproduces `TG0WDT_SYS_RESET`: stage-0 timeout at
`7.249439902 s`, stage-1 at `17.249439902 s`, and first reset at
`17.249530334 s`. The WDT-off 68-second state reaches `APIKEY` but captures a
302-byte black 320x240 PNG. These results keep `RUNTIME-03` open for the
post-`APIKEY` display/application path.

Earlier WDT-disabled `sample=1024` and trace-off controls produced the same
banner-only serial hash before the classic RMT model existed; those snapshots
remain historical and do not describe the final `APIKEY` state. The reusable
summarizer and evidence are in
[`core2_handoff_trace/`](core2_handoff_trace/). The unbound local-ELF PC
symbolization is retained as separate metadata so rerunning the summarizer does
not silently reintroduce it.

Known emulator capability gaps are maintained in
[the runtime model-gap register](../../docs/runtime-model-gap-register.md).
Current overall status and unfinished work must be read from
[project status](../../docs/project-status.md) and
[project backlog](../../docs/project-backlog.md), not inferred from an older
evidence date.

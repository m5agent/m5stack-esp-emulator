# Firmware review and runtime evidence

Last reviewed: `2026-10-26`

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
permission/ACL enforcement remains `NOT RUN`.

Required/optional capability consistency is covered by
[`evidence-2026-10-25-capability-required-optional-consistency.json`](evidence-2026-10-25-capability-required-optional-consistency.json):
overlap is rejected, unsupported required capability rejects the manifest, and
unsupported or unknown optional capabilities remain structured warnings.

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
required capability returns a structured manifest rejection. Declarations are
operator-provided; they do not prove that every firmware code path uses the
declared peripheral.

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
`TG0WDT_SYS_RESET`/`TG1WDT_SYS_RESET`, reset CPU PC `0` and a black frame remain
in the same public firmware path, so interrupt-WDT timing and aggregate
Flash/cache-handoff progress remain the next investigation boundary.

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

Patch `0037` adds a unified virtual-time/CPU/PC trace across cross-core, DPORT,
SSI, UART and TIMG events. Two normal-WDT runs both placed the last TG1 feed
exactly 800 ms before stage-0 timeout; the final timeout PC changed between
runs. A 1 ms dual-PC control kept the same gap but reset earlier. The initial
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
WDT-disabled `sample=1024` and trace-off produced the same banner-only serial
hash. The reusable summarizer and evidence are in
[`core2_handoff_trace/`](core2_handoff_trace/). The unbound local-ELF PC
symbolization is retained as separate metadata so rerunning the summarizer does
not silently reintroduce it.

Known emulator capability gaps are maintained in
[the runtime model-gap register](../../docs/runtime-model-gap-register.md).
Current overall status and unfinished work must be read from
[project status](../../docs/project-status.md) and
[project backlog](../../docs/project-backlog.md), not inferred from an older
evidence date.

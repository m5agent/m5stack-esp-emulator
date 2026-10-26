# CoreS3 Unit Web cohort, QEMU a8fe / worker generation 7

This interrupted cohort has 20 complete outer case reports: **16 PASS and
4 FAIL** (TVOC, PIR, Dual Button and Key). Angle's child runner then failed
QMP startup and retained its raw controller/browser/ZIP evidence, while its
outer wrapper was interrupted. The remaining six cases were NOT RUN: Light,
Buzzer, Fan, IR, RS485 and HUB. The [attempt summary](attempt-summary.json)
records every case, failure, missing wrapper, original-report hash and the
outer exit code 143. This directory contains the 16 selected passing case
records; failed and interrupted raw evidence is retained internally.

Only the outer batch process was suspended. The active Angle child completed
its evidence ZIP and stop path; the API had zero active sessions before the
outer batch was terminated. Failed or unrun cases require separately labelled
new sessions and explicit selection, with their own worker generation and
tool fingerprints. This cohort must not be reported as one 27-case PASS.

Every passing report independently binds its visible CoreS3 Device Service
session, firmware SHA, direct live PID/executable SHA, sampled and reconfirmed
worker generation 7, original pre-stop evidence ZIP, guest/controller result,
actual product DOM and real HTTP input/readback record. The runtime executable
SHA256 is
`a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`.
The pre-stop ZIPs are copied byte for byte; sessions retain history with
`purge=0`. No firmware or ROM binary is included. `tool-sources/`, per-case
`artifact_sha256` and `SHA256SUMS` preserve the frozen executed tool versions.

The original bridge waited only for available QOM data before asserting that
an input was enabled. TVOC/PIR/Dual Button reached available data while the
page was still booting. A later bridge revision waits for the real product
session to be running and the actual control to be enabled; its independent
supplemental results are separate from this interrupted attempt. Key and
Angle instead failed QMP startup; their original failures remain unchanged.

Controller functionality, panel presentation and model-component bindings
are separate evidence levels. Missing or unconfirmed axis, switch,
LED-location and count-to-angle bindings remain panel presentation. Fan
activity does not establish RPM or a mechanical model. These are virtual
device results. Physical hardware, RF, mechanical, optical, acoustic and
electrical equivalence are NOT RUN.

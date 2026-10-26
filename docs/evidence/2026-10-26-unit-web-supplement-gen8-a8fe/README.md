# CoreS3 Unit Web supplemental sessions, QEMU a8fe / generation 8

All 11 independently created supplemental cases PASS: TVOC, PIR, Dual Button,
Key, Angle, Light, Buzzer, Fan, IR, RS485 and HUB. The [summary](summary.json)
retains the complete runner output; the process exited 0. These sessions cover
failed, interrupted or unrun cases in the separately retained generation-7
attempt. They do not turn that earlier attempt into one all-PASS 27-case run.
The final explicit selection combines its 16 passing cases with these 11.

Each case binds the same session/firmware/ZIP between guest/controller and
actual product-browser evidence. Its live PID executable hash is
`a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`,
with worker generation 8 sampled and reconfirmed directly. Tool snapshots
capture the revised readiness bridge and Linux/macOS executable resolver.
The raw controller report also binds the revised profile builder in
`runner_sha256`; service startup serialization is recorded in the separate
[worker generation receipt](../unit-service-generation8-20261026.json).
Inputs wait for the real product running state, available Unit data and the
actual enabled control. No product API functions or data-plane values are
replaced. Evidence ZIPs were requested before stop, copied byte for byte,
and history retained with `purge=0`. Firmware/ROM binaries are not included.

IR is explicitly `custom-guest-ir-callback-root-patch`, with the original and
patched driver hashes retained. Its PASS applies only to that opt-in guest
wrapper. The originally published callback/GC path remains partial.
Fan reports PWM activity with RPM 0; this is not a measured mechanical model.
Missing or unconfirmed physical component bindings remain panel output.
All results are virtual-device evidence. Hardware, RF, acoustic, optical,
mechanical and electrical equivalence are NOT RUN.

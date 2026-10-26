# Final real browser / guest feedback validation

2026-10-26: Button, Key RGB and Fan activity **PASS** on the same final frozen
QEMU `1880891da692de06612aa0a10b2026c0209875f4641e837df29dc818bb3ac81d`.
Each test creates its own visible Device Service lease, loads the real
`platform/web/sessions.html` product page, and uses the actual UnitPanel,
ModelDeviceShell and HTTP APIs. The only browser instrumentation appends a
reference to existing private module objects for observation; no function,
controller response, input request or firmware observation is replaced.

- Button: real DOM hold/release reaches the same guest (`UNIT_BUTTON 0/1`),
  QOM pressed/input-level, model button travel and native framebuffer.
- Key: real DOM hold/release additionally causes official guest RMT writes.
  Packed QOM RGB `0x123456` / `0x2468ac` becomes the same shell LED color and
  the observed-output RGB swatch; no browser key-to-color rule exists.
- Fan: observed positive PWM enables qualitative rotor activity; zero PWM and
  terminal state stop it. The graphical cadence is independent of duty and
  frequency, with no RPM written or shaft-speed/electromechanical claim.
  The source model's default assembly is a bare circular shaft; the optional
  60mm propeller is not enabled. Static screenshots have limited visibility of
  shaft rotation, so movement/stopping is asserted from the same scene joint's
  changing/stable angle, alongside real controller state and guest serial.

Each report fingerprints the exact product/test source, records page errors
and checks, and retains native/browser screenshots, serial and a pre-stop ZIP.
Button/Key also exercise the actual SessionVisual WebGL resource-limit path:
old shell disposal, Unit detach, generic preview, remount and real frame
restoration. Input traces contain only the user's down/up requests; readback
and remount do not echo input.

All sessions were stopped with `purge=0`; history retains their metadata,
serial and last frame. Key and Fan have additional `runtime-provenance.json`
records from live session PID → executable → SHA256. The frozen service
provenance at this root and the final controls' worker-generation record bind
these results to the final runtime. No firmware/ROM image is committed.

These are reproducible **virtual-device/browser** cases, not hardware tests
and not blanket acceptance of all 27 Unit paths or uncalibrated bindings.

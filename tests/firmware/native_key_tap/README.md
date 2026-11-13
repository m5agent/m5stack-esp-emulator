# Native Device Service automatic key taps

The [bounded evidence](evidence-summary.json) records virtual-device validation
of the unchanged JIGGLER image on `stickc-plus2`, using the production Device
Service input route and the pinned, uninstrumented native runtime. All three
automatic inputs produced visible application changes: B short press displayed
the mouse-not-ready message, A short press paused the application, and B long
press opened settings. The 100-second observation had no watchdog panic or
reboot. Both application partitions matched the original bytes on readback.

To reproduce with the exact runtime and original firmware hashes in the summary:

1. Start an isolated Device Service, import the original merged BIN, and create
   a `stickc-plus2`, `runtime=qemu` session with default `icount` shift 5. Keep
   the watchdogs enabled. Verify the actual process runtime and initial Flash.
2. On boot, send explicit key `c` down, followed by up after approximately
   1.6 host seconds. This startup action retains physical edge semantics.
3. Observe the original home screen before testing application buttons. Send
   `{"kind":"key","key":"b","hold_seconds":0.1,"settle_seconds":0}`, then
   observe the mouse-not-ready screen. Send the same request for key `a` and
   observe the paused state. Finally send key `b` with `hold_seconds:2` and
   observe settings. Preserve each request, timing receipt and resulting frame.
4. Read back the application partitions, save serial and the evidence ZIP before
   stopping with `purge=0`, then verify Flash, lease and owned-process cleanup.

The [input API](../../../docs/device-service-api.md#inject-input) defines
`hold_seconds` in guest virtual time for independent QMP key sessions. The
default is 450 ms; the range is 1 ms to 5 s. QEMU's existing keyboard queue
orders these taps and inserts an equal release gap. Responses say `queued`,
which does not establish application completion. Soft reset does not cancel
that queue; VM termination destroys it.

Managed Preview default taps remain synchronous and host-timed so Run replacement
cannot inherit future queued input. NanoC6 retains its existing GPIO-button
behavior. Both reject an explicit key `hold_seconds`. Browser down/up controls
and pointer/touch/drag timing are unchanged. This evidence does not close the
separate JIGGLER auto-icount watchdog failure or establish Bluetooth HID/RF
operation, browser-WASM behavior, or physical timing.

Host controls exercise the actual production QMP helper, invalid durations,
explicit edges, ACL/state rejection, Preview admission and Run draining, NanoC6
compatibility and QMP failure handling:

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_device_input_validation test_preview_service test_device_service \
  test_runtime_acl
```

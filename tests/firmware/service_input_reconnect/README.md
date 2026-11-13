# Native input after a QMP connection error

`DeviceSession._qmp_call()` closes and clears a failed connection. Native key,
touch, longpress and drag commands must use that same command boundary, including
its lazy reconnect, process checks and error translation. A cached `None` must
not become an HTTP 500 or a falsely accepted input.

The regression is covered in `platform/tests/test_device_service.py`:

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_device_service.DeviceServiceUnitTests.test_input_reconnects_after_qom_error_and_preserves_pointer_sequence \
  test_device_service.DeviceServiceUnitTests.test_input_transport_failure_is_not_recorded_as_accepted \
  test_device_service.DeviceServiceUnitTests.test_physical_key_down_and_up_are_distinct_qmp_events \
  test_device_service.DeviceServiceUnitTests.test_sticks3_capture_taps_are_timed_by_the_guest_clock
```

For the same-path **virtual-device validation**, create an owned Device Service
StackChan lease with the firmware and runtime hashes in the evidence summary.
The image is an independent build of public UserDemo v1.6.0 plus the official
ESP-IDF I2C lifetime fix; it is not the original M5Burner image. At the visible
Welcome page, query a deliberately absent QOM property through
`GET /api/v1/sessions/<lease>/qom?path=/machine&property=definitely-missing-input-regression`.
Expect `503 qmp_error`. Then send `POST /api/v1/sessions/<lease>/input`:

```json
{"kind":"touch","x":85,"y":187,"settle_seconds":1}
```

The result must be accepted, the guest must log `startup skipped`, and the raw
frame must change from Welcome to the AI.AGENT launcher. Request the evidence ZIP
before stopping with `purge=0&retain_flash=0`. The fixture retains the preceding
500 negative control separately. This establishes input recovery, not complete
application stability, cloud connectivity or physical touch behavior.

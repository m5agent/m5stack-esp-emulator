# Original protocol and system APIs

`run_protocols.py` prepares an uploaded LittleFS probe and executes it only
through a visible Device Service session. HTTP/TCP/UDP, MQTT and Modbus peers
listen on owned loopback ports; guest traffic traverses the actual WiFi runtime.
The TLS fixture generates a disposable test certificate/key in the ignored run
directory and independently authenticates the guest certificate. No production
credentials or external EzData account are required or tested.

```sh
PYTHONPATH=.work/py312 python3.12 tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:8788 --group tls --token-file "$M5_TOKEN_FILE" \
  --out-dir .work/api-sweep/tls-new
```

Groups include `http`, `tls`, `sockets`, `easysocket`, `network`, `mqtt`,
`modbus`, `modbus-rtu`, `ezdata`, `espnow`, `espnow-native`, `audio-player`,
`audio-recorder`, `ble-nus`, `ble-client`, `m5ble-server` and `m5ble-client`.
RTU uses the CoreS3 RS485 Unit on Port A; a peer verifies actual UART TX bytes
and CRC before injecting a response through the Unit RX FIFO. It is not admitted
on Cardputer-ADV. An empty ESPNow queue, accepted encryption key or configured
peer table does not prove ESPNow packet/IRQ delivery.

The default base is always the device-matrix reference. Stock S3 internal-BT
firmware cannot inherit a UART H4 test build result. The BLE groups may use
explicit compatible HCI test images, following the board-specific UART build
configuration in `../unified_cores3/README.md` and
`../unified_cardputer/README.md`:

```sh
PYTHONPATH=.work/py312 python3.12 tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api http://127.0.0.1:8788 --group ble-client --device cores3 \
  --base-image cores3=/path/to/cores3-hci-test.bin \
  --expected-base-sha256 cores3=EXACT_SHA256 \
  --token-file "$M5_TOKEN_FILE" --out-dir .work/api-sweep/hci-client-new
```

Both original frozen SDKs and controller traffic still execute in this lane;
`firmware_lane=hci-offload-test-firmware` prevents merging it into stock results.
The owned peripheral requires a genuine guest CCCD subscription before sending
notifications. It never force-sends an unrequested notification to hide a client
SDK subscription defect. Central checks require the complete ACK, and negotiate
ATT MTU when its payload exceeds the default notification capacity. A call that
begins without returning before the session deadline is recorded as `TIMED_OUT`;
earlier completed methods retain their independent evidence and cleanup proof.

`probe_system_runtime.py` exercises native FAT/LittleFS using an ordinary RAM
block-device input, actual flash file operations, TCP select/poll and queued
callbacks. RAM VFS results describe filesystem algorithms, not an SD controller.
`verify_audio_wrappers.py --run RUN_DIRECTORY` independently checks retained
recorder PCM/WAV frequency, format and duration. Explicit 48 kHz diagnostic input
stays separate from the default service microphone fixture.

`summarize_system_results.py` joins source declarations, actual guest exports and
behavior by device. It merges documented/import/result aliases, includes native
and inherited members, keeps all subcases from the latest run, and never grants
PASS from a recipe, import or state-only observation. Candidate source, alternate
firmware and explicit diagnostic input are excluded from stock results. String
member lists have unknown callability until typed reflection supplies it; they
must not inflate the count of known executable methods. All raw serial, Flash,
PCM, keys, peer logs and ZIPs stay in ignored run storage.

`compact_system_results.py` preserves every joined API/device/status/reason and
selected execution receipt through shared pools and run-length encoded slots.
Its source inventory hash and API-order hash make omissions or slot reordering
detectable. Non-callable exports remain `INVENTORY_ONLY`; known-callable
`NOT_RUN`, `ERROR`, state-only and model boundaries retain their exact statuses.
A complete functional receipt requires source, firmware, runtime and ZIP SHA256
plus stopped-process evidence. Earlier incomplete receipts cannot acquire PASS.
The reason pool uses lossless zlib/UTF-8 JSON encoding to stay within the 64 KiB
per-summary evidence budget. Expand it for per-API review:

```sh
python3.12 tests/uiflow2/api_sweep/compact_system_results.py \
  --expand docs/evidence/2026-10-27-uiflow2-api-sweep/system-protocol-status.json \
  --out /tmp/m5-system-protocol-api-status.json
```

The public compact file contains all 5,624 source/runtime inventory slots on
each board, including optional accessories, hardware-lane entries and constants.
Its zero known-callable `NOT_RUN` count applies only to the system/communication
scope, and does not mean every inventory row or every behavioral case passed.

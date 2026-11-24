# review-sta control firmware

These ESP-IDF v5.5.4 images are the per-board controls for the `review-sta`
qemu-wifi profile ([#238](https://github.com/m5agent/m5stack-esp-emulator/issues/238)).
They use the stock Wi-Fi driver and lwIP. The fixed fixture endpoints are in
[`main/review_contract.h`](main/review_contract.h); change the Device Service
fixture and this header together.

| Mode | Behavior | Expected review result |
| --- | --- | --- |
| `good` | Join `M5-REVIEW` with WPA2-PSK, then DNS, NXDOMAIN, HTTP GET/POST, TCP, UDP, MQTT | `PASS` |
| `wrong` | Same AP with a wrong passphrase, at most 3 connection attempts | `FAIL` with `wifi_auth_failed`, no DHCP |
| `setup` | Wait for a 1.5 s hold of the board's active-low button B, then join and run DNS + HTTP GET | `PARTIAL` without input; `PASS` after the setup input |
| `offline` | Never starts Wi-Fi; prints three ticks | `NOT_USED`, never `PARTIAL` |

Every operation prints one line, for example
`REVIEW_CTRL HTTP_GET ok=1 status=200 path=/review/status`, and each run
finishes with `REVIEW_CTRL RESULT <PASS|FAIL|NO_LEASE|NO_SETUP|OFFLINE>`.
These lines are firmware diagnostics. The review verdict must come from the
fixture's observed events and the pcap, not from the serial text.

## Fixture contract

Station: SSID `M5-REVIEW`, passphrase `review-pass-v1`, WPA2-PSK threshold.
The `wrong` image uses `review-wrong-v1`. DHCP must hand out a lease with the
gateway and DNS server at `10.0.2.2`; the images do not hard-code DNS.

| Operation | Target | Exact exchange |
| --- | --- | --- |
| DNS A | `review.test` | must resolve to `10.0.2.2` |
| DNS negative | `absent.test` | must fail to resolve |
| HTTP GET | `10.0.2.2:80` `/review/status`, Host `review.test` | `200`, body `REVIEW_OK\n` with `Content-Length` |
| HTTP POST | `10.0.2.2:80` `/review/config`, body `{"probe":1}` | `200`, body `{"ok":true}` with `Content-Length` |
| TCP | `10.0.2.2:19193` | send `M5TCP\x00\x01`, receive `ACK-M5TCP\x00\x01` |
| UDP | `10.0.2.2:19090` | send `M5UDP\x00\x02`, receive `ACK-M5UDP\x00\x02` |
| MQTT 3.1.1 | `10.0.2.2:1883`, client `review-ctrl` | CONNECT → CONNACK rc 0 → QoS 0 PUBLISH `review/ctrl` `hello` → DISCONNECT |

HTTP responses are parsed by `Content-Length`; the fixture does not have to
close the connection.

## Images

| Label | Chip | Flash | Mode | Setup GPIO |
| --- | --- | --- | --- | --- |
| `s3-8mb-{good,wrong,offline}` | ESP32-S3 | 8 MiB | Cardputer, Cardputer-ADV, StickS3 | |
| `s3-16mb-{good,wrong,offline}` | ESP32-S3 | 16 MiB | StopWatch, PaperDIY, PaperS3 | |
| `sticks3-setup-b` | ESP32-S3 | 8 MiB | setup | GPIO12 |
| `stopwatch-setup-b` | ESP32-S3 | 16 MiB | setup | GPIO1 |
| `paperdiy-setup-b` | ESP32-S3 | 16 MiB | setup | GPIO3 |
| `classic-8mb-{good,wrong,offline}` | ESP32 | 8 MiB | StickC Plus2 | |
| `classic-16mb-{good,wrong,offline}` | ESP32 | 16 MiB | Core2 | |
| `stickcplus2-setup-b` | ESP32 | 8 MiB | setup | GPIO39 |
| `core2-setup-b` | ESP32 | 16 MiB | setup | GPIO39 |

The setup GPIOs are the button-B lines that the board machines drive from the
QMP `b` key (StickS3 `key-b-pin` 12, StopWatch `PIN_KEYB` 1, PaperDIY line 3,
StickC Plus2 GPIO39). The Core2 entry has no physical button B GPIO; its
buttons are touch areas, so `core2-setup-b` is only a build check and must not
be used as a setup-required control. Cardputer boards and PaperS3 have no
button B and have no setup image.

## Build

```sh
export IDF_PATH=<esp-idf v5.5.4>
export IDF_PYTHON_ENV_PATH=<idf python env>
export PATH="$IDF_PYTHON_ENV_PATH/bin:<xtensa-esp-elf>/bin:$PATH"
tests/network/review_sta_controls/build.sh <out-dir>
# one target: ONLY=s3-8mb-good tests/network/review_sta_controls/build.sh <out-dir>
```

The script writes merged images `review-ctrl-<label>.bin`, the matching ELF
and a build log per target. Keep the outputs in ignored storage; commit only
their SHA-256 values with the run evidence.

## Run the controls

Start a dedicated Device Service on an agent-owned port with its own
`--state-dir` and `--api-token-file`. Then pass a JSON list of
`{"device", "mode", "image"}` cases, where `mode` is `good`, `bad` (the
`wrong` image), `setup`, `setup-skip` or `offline`:

```sh
python3 tests/network/review_sta_controls/run_matrix.py \
  --base http://127.0.0.1:<port> --token-file <token-file> \
  --cases <cases.json> --out <ignored-dir> --timeout 45
```

Each case imports the image, creates a `qemu-wifi` `review-sta` session,
waits for the observation window, reads `/network`, frame, serial and the
evidence ZIP, stops with `purge=0` and re-reads `/network` for the finalized
pcap isolation. `setup` sends the board's `b` button hold after the
`REVIEW_CTRL SETUP_WAIT` marker; `setup-skip` uses the same image without the
input and must end `PARTIAL`. `results.json` holds bounded summaries; ZIPs stay
in the output directory.

This is virtual-device validation tooling. It does not cover physical RF,
WPA3, enterprise authentication, TLS or real cloud services.

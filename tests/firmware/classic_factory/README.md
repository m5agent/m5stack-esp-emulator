# Classic factory startup regressions

These are native Device Service virtual-device results for the unchanged public
Atom-Lite and Atom-Matrix factory BINs. They are not hardware measurements.
The bounded summary retains failing controls and incomplete Matrix acceptance.

Use a dedicated Device Service with a fresh canonical native runtime including
`qemu-unit-runtime/0021`; upload the original merged BIN, create a `qemu` session,
retain serial and `/device-state`, send `key:a` down/up through `/input`, and
compare GPIO input with actual RMT LED frames. Observe at least 120 seconds;
request `/evidence` before deleting with `purge=0&retain_flash=0`.

The classic accelerator policy supplies `M5SW_ICOUNT_MAX_PERCPU_NS=10000`.
`M5_CORE2_ICOUNT_MAX_PERCPU_NS=0` is the existing host-policy opt-out. A zero
setting is a diagnostic negative control, not the accepted factory profile.

The final integrated-main retest includes classic eFuse provisioning and a
fresh runtime. Two original Atom-Lite cold starts each ran for over 121 seconds
and produced button-driven RMT output. The complete serial streams were read
with API pagination, rather than checking only the first 262 KiB. Original
Atom-Matrix still triggers a WiFi watchdog, so issue #221 remains open.
Earlier-service failures and the unmerged offline-MAC experiment remain in the
summary; later passing runs do not erase them.


## WiFi follow-up: original Atom Matrix, 2026-11-13

The original SHA-256 `24892fcf5d5f8c97ee30a5ffb4fec166dca1c254cc6f54861af28abc8732ba2f`
was rerun through Device Service with native patch `0188`. The baseline had
omitted the MAC entirely in plain `qemu`; with an explicitly configured NIC it
could scan but exhausted its RX descriptor chain before authentication. The
missing NEXT/LAST cursor registers prevented the guest from recycling buffers.
After restoring those registers and classic CCMP RX, the unchanged image
completed scan, WPA2 authentication, DHCP, DNS and a real HTTP transaction.

The factory image fixes its AP credentials and requests
`http://example.com/index.html`. The observed HTTP status is **404**, also
confirmed independently against that public URL. The guest correctly prints
`[HTTP] HTTP code not ok`; no HTTP 200 is fabricated to produce a factory PASS.
The earlier offline-MAC `Wifi scan start` stop is not by itself a scan hang:
the original scan task records an error and deletes itself when no AP is found.

LED acceptance remains **PARTIAL** here: RMT produces 128-symbol transactions,
but the 25-LED endpoint requires 600 symbols and records incomplete frames.
The WiFi result does not close that separate controller/driver investigation or
claim physical RF behavior. Bounded results are in `wifi-rx-summary.json`.


Reproduce with an agent-owned service/runtime, the exact public BIN and the
factory test AP credentials held in `M5_TEST_WIFI_PASSWORD` (do not log or commit
them):

```sh
python3 tests/firmware/classic_factory/run_matrix_original.py \
  --service "$DEVICE_SERVICE_URL" --token-file "$DEVICE_SERVICE_TOKEN_FILE" \
  --firmware "$ATOM_MATRIX_ORIGINAL_BIN" --wifi-ssid "$FACTORY_AP_SSID" \
  --out-dir "$EVIDENCE_DIRECTORY" --seconds 130
```

Exit status validates scan, an actual HTTP response, watchdog/abort absence and
button edges. `factory_http_pass` and `led_frames` remain separate results;
a transport PASS does not upgrade a 404 or incomplete LED frame to factory PASS.

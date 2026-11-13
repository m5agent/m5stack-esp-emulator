# NanoC6 serial-channel API and page validation

The [bounded summary](summary.json) records **virtual-device validation** of
one original Honeypot BIN through a dedicated native Device Service session.
At source `10c826b832b78c9bc42e9f788bd3e595584978ae`, the plain NanoC6 launch
path attaches a separate USB Serial-JTAG log and uses the same fixed
instruction-counted clock as the existing StickS3 USB capture path:
`-accel tcg,thread=single -icount shift=5,align=off,sleep=off`.
The condition follows the actual third serial-endpoint branch; HCI, unified,
Wi-Fi, Nesso and alternate console-index configurations keep their policies.
There is no firmware-hash special case or application modification.

The original BIN SHA-256 is
`4184ffc6b56f1742a926845d782f3b65c37246490cc6d3e1bfa067bff7b0c381`;
the native runtime SHA-256 is
`8df537142dd8e8231f7d201772176f6460fdbe46a80b812e7796d213373b8b8d`.
The 180.008-second run used the production service directly, without a launch
wrapper, HMP observer, application input or additional runtime build. Both
application regions remained unchanged. Each serial channel had one ROM
banner and no observed fatal marker. The USB log contained the complete
153-byte, four-CRLF application suffix after the same 461-byte UART prefix.

## API and page result

Eighteen API responses, read in 64-byte chunks, matched the corresponding
channel bytes in the same session's final evidence ZIP. The channels retain
independent offsets and are never concatenated for display or boot counting.
On the public workbench, Sessions and Observatory pages, selecting
`console → usb-serial-jtag → console` showed the complete application output
only in USB and resumed the console cursor without mixing streams. Thirteen
page responses were independently checked against the final ZIP. All served
tool and page source bytes matched the frozen Git object.

This was **two page-observation attempts on one continuously running guest**:

1. Public workbench and Sessions passed. Observatory displayed its complete
   USB output, but the external browser harness received an empty body while
   reading its JSON response; that attempt remains `INFRA_FAILED`.
2. Only Observatory was repeated, using a read-only `fetch` response clone to
   record the body. The original response, product source and guest remained
   unchanged. Its complete output, return to console and offsets passed.

Both browser contexts closed. An independent visual review confirmed all nine
final screenshots; Observatory retains its existing bounded tail display.
Screenshots and raw logs contain original firmware configuration fields, so
only their hashes are published. The owner exported the ZIP before stopping
the session; Flash, lease, native process and owned service were released.

## Reproduce the same path

Use the source, original BIN and native runtime hashes above with an isolated
Device Service. Upload the original BIN, create a plain `nanoc6` / `qemu`
session and verify its actual native process arguments. Do not inject a
button or modify its application. Read both explicit channels using
`GET /api/v1/sessions/{id}/serial?channel=console&offset=0&limit=64` and the
corresponding `channel=usb-serial-jtag` request. Continue each stream from its
own `next_offset` and compare every returned chunk with that stream's log.
The application suffix must be exactly 153 bytes with SHA-256
`957653a047aacb4f6c16b22209ba72edc5e5ae941ff7fd744992c3c297d9f3c6`.

Attach the same running session to each native-service page and perform the
three channel selections above. Record the actual requests, selector state,
rendered text and screenshots. Export evidence before `purge=0` stop, then
verify terminal state and resource release. See the
[serial API contract](../../../../docs/device-service-api.md) for access and
channel-availability rules. No browser-WASM result follows from these pages.

## Limits and retained failures

The serial interface and page scope passes; the complete firmware application
remains **PARTIAL**. AP association, HTTP, honeypot network behavior, radio
calibration and physical RF were not validated. The logs still contain PHY
calibration-mismatch and PLL-calibration-timeout diagnostics; they are not
converted into a claim of complete application readiness.

Earlier plain-clock startup failures, truncated output and diagnostic runs
remain separate retained evidence. The later clock control and production
run do not erase them. USB fixed-endpoint model tests, full platform checks,
resident deployment and broader firmware acceptance have their own evidence.

# Core2 legacy deviceCfg WiFi overlay

Date: 2026-10-30

Status: `PARTIAL`; the legacy WiFi configuration fixture is implemented and
validated, while `RUNTIME-03` remains `OPEN`.

## Result

The public `UIFlow_Core2 v1.15.4` image stores its legacy configuration in the
`config` partition, not in the separate `wifi` partition:

- `config`: offset `0xbfe000`, size `0x1000`, valid legacy `deviceCfg` JSON;
- `wifi`: offset `0xbff000`, size `0x1000`, erased with `0xff`.

`platform/tools/legacy_device_config.py` now recognizes only the classic
four-key schema plus its two-byte big-endian length and one-byte checksum. For
a Core2 `runtime=qemu-wifi` session, the Device Service writes the requested
SSID/password into that document on the session-isolated Flash copy before
QEMU starts. A different partition layout or schema remains byte-for-byte
unchanged.

The service records `legacy_wifi_config_applied`, the base and effective Flash
SHA256 values, the partition offset/size, the hashed SSID, whether a password
was supplied and the entry count. It does not record the raw SSID or password.

## Validation lanes

### Service overlay

The standard QEMU binary
`54e7a7f7cd0ff6f5a1d6343c06563388f49c2b0abbca4cafb850876e57ed1254`
accepted the original normalized firmware
`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`.
The session event reported one changed entry and the following effective
Flash:

- effective Flash SHA256:
  `b30f3014b75f762f50be3284010502e047b3bd0494b0f0b72a673c2756baffd7`
- config partition SHA256:
  `6d5f7fb3eca7fb7823f32053f8efd2c7885645a524cc71d10b1b67a0c22d108d`
- SSID SHA256:
  `4118a1151b34a6715fdbaf8e2afb6c2ca61b2c492e1f3091204a7d5e226c9658`
- password supplied: `false`

This lane proves the service boundary and retains a blank frame after 43
seconds. It is not a guest functional PASS.

### Same effective Flash, real WiFi UI

The service-produced effective Flash was also executed as an explicit
diagnostic image under WDT-disabled diagnostic controls. The guest rendered the
real legacy WiFi screen rather than a host-injected frame:

- `320x240`;
- `75,373` nonblack pixels;
- `305` colors;
- PNG SHA256
  `df9ba1849edb7742f7b5672ff14fdfc97a2f351cd5a96b0f429ef9e22dfbf4c3`.

The visible screen contains `Wi-Fi Connect`, `Connecting to myssid` and the
Core2 `v1.15.4` title. This confirms that the selected legacy configuration
enters the real `wifiCfg`/menu path.

### Default watchdog control

With the same overlay and a diagnostic QEMU containing the product TIMG fix,
serial reached:

```text
BOARD NAME: M5STACK-CORE2
APIKEY: 7621FAE2
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
```

The next failure is still:

```text
Guru Meditation Error: Core 0 panic'ed
(Cache disabled but cached memory region accessed)
```

The frame remains blank. The failure is therefore independent of the config
partition and remains an interrupt/cache-handoff runtime issue.

## Verification

- legacy config focused tests: `7/7 PASS`;
- platform full suite: `1,596` run, `1,595 PASS + 1 skip`;
- Device API inventory contract: `1/1 PASS`;
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  `PASS`;
- Python compileall and `git diff --check`: `PASS`;
- malformed checksum/schema and non-legacy Flash remain unchanged;
- overlay is scoped to `Core2 + qemu-wifi`;
- a repeated overlay is idempotent and emits no raw credentials;
- the service event includes base/effective Flash identity.

## Boundary

This is virtual-device validation only. It does not prove DHCP, access-point
association, Internet access, RF behavior, physical cache/PSRAM timing or any
electrical result. It does not close `RUNTIME-03`: stable normal-watchdog
startup, setup/REPL and a nonblank completed application frame remain open.

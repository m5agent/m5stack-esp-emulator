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

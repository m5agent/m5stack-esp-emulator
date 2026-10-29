# Core2 post-reset teardown

Date: `2026-10-29`

## Result

`PASS` for virtual-device `CORE2-02` teardown while guest reset is in flight.
This does not establish physical hardware, RF controller equivalence or
physical cache/PSRAM timing.

`run_service_teardown.py --stop-mode after-reset --attempts 3` completed three
consecutive leases. Each attempt:

1. reached `UNIFIED_CORE2_READY`;
2. captured visible frame, 32-node QOM, WiFi/public DNS/HTTP, external NUS
   GATT, serial, pcap and evidence ZIP;
3. issued guest `system_reset`;
4. verified the session and the same QEMU PID remained `running` while reboot
   was in flight;
5. stopped the session and observed `stopped`/no error, terminated HTTP and BLE
   companions, reaped BLE/QEMU PIDs and released the worker lease;
6. created the next lease successfully.

Every attempt passed the same 23 checks. Native-HCI health was `45/45`, with
36 events, 9 ACLs and zero HLI errors, reset, panic or queue depth.

Inputs were hashed before the first lease and did not drift:

- firmware SHA256: `c3eaa35b9c41204cc6337e30b1d81f60bf06eab2d747f3547af5d8b8ba0ea99f`
- matching ELF: `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49`
- QEMU: `54e7a7f7cd0ff6f5a1d6343c06563388f49c2b0abbca4cafb850876e57ed1254`

Machine evidence:
[`evidence-2026-10-29-core2-post-reset-stop-recovery-3x.json`](../../../tests/uiflow2/core2_native_hci/evidence-2026-10-29-core2-post-reset-stop-recovery-3x.json).

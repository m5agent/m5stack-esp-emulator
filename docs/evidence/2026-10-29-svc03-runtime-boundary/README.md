# 2026-10-29: Device Service runtime boundary and Core2 unified stability

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

This milestone contains two service-side changes:

1. `SVC-03` moved the stateless QEMU runtime memory policy, PSRAM mismatch
   check, private runtime environment set and runtime environment redaction
   helper from `device_service.py` to `device_service_runtime.py`.
   `device_service.py` keeps same-object compatibility re-exports.
2. Unified profile startup now uses the session readiness budget instead of a
   fixed 20-second QOM setup limit. Core2 unified profiles default to 180
   seconds, and the external BLE peer waits ten seconds after subscription
   before writing. The reconnect workload bound was recalibrated for that
   write delay.

The second change removes two independent service-side false failures:

- Core2 could reach the requested unified image but be stopped by the fixed
  20-second profile-QOM window before its slower guest emitted
  `UNIFIED_CORE2_IO_CONFIG_READY`;
- a unified guest could accept the peer write and execute the Python receive
  handler while its BLE transmit path had not settled, leaving the peer to
  report `notification timeout` and eventually disconnect the guest.

The ten-second settle interval is a service scheduling boundary. It does not
change guest firmware, HCI packet contents, BLE RF behavior or controller
semantics.

## Core2 unified evidence

The final run used the repository's documented composition:

- firmware: `tests/uiflow2/unified_core2/make_image.py`;
- build: `build-M5STACK_Core2`;
- runtime: `qemu-unified`, profile `core2-native-hci`;
- QEMU: `tcg,thread=single,tb-size=128`
  and `icount shift=5,align=off,sleep=off`.

Three independent `/api/v1` leases completed `3/3 PASS`. Every lease passed:

- the generated PNG frame;
- a 32-node QOM snapshot with 8 MiB effective PSRAM;
- WiFi DHCP and controlled HTTP;
- public IPv4 DNS and HTTP;
- external Bumble NUS discovery, subscription, write and exact
  `ACK:M5_CORE2_UNIFIED` notification;
- native HLI `45/45`, 36 C2H events, 9 C2H ACLs, zero HLI errors, empty
  HLI/meta queues, zero dropped packets and zero TX queue depth;
- pcap and evidence ZIP collection;
- stop, history retention, worker lease release and QEMU/companion cleanup.

The same write-delay change also passed three independent leases on the prior
QEMU runtime used for comparison. This distinguishes the service scheduling
fix from a single QEMU binary's incidental timing.

| Identity | SHA256 |
| --- | --- |
| composed firmware | `c3eaa35b9c41204cc6337e30b1d81f60bf06eab2d747f3547af5d8b8ba0ea99f` |
| matching ELF | `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49` |
| final QEMU | `568079f3b9e818ef1cc29b9e7cd1c5c036af19196668a12174ed79ec96c262ed` |
| `device_service.py` | `ca42bf183b8cbac31be71d987a9c544561d5b868911f597a109e61f8ebf33627` |
| `device_service_runtime.py` | `8a7f348ee2af46b1ee107a1db6acd38203555b01e3b498729b7441fe6e210ba6` |
| `ble_runtime_limits.py` | `30148f7f3df98fd930a8ee35ed61ec0f6fe6baed3b7a026cea757e34072ea385` |
| runner | `a3b6429ce28d657bc773a0e33c93ed51ff44789bcb362919dadc1c7793856640` |

All three frames were 3,888 bytes with SHA256
`fa98d48fc9fd2a18e78fbf327374ae1725a473dc7cad7bc81418895ac8c96c33`.

| Run | Evidence ZIP SHA256 | Serial SHA256 | Peer log SHA256 |
| --- | --- | --- | --- |
| 1 | `bb9b65b2d72076d542e0dd71efbd6af6bf504d0d1e672963c5b0e4b013c28863` | `6916ba268229a184c2fa14ddf86427d9ad020fea07f3b6a8b1d9b37b9b60532c` | `7f2ea2feea78c1699c86beeeffdc326e6f1ecd47910566dce24fbe9aa5333409` |
| 2 | `dc052cf5c903b5978114c53ee41144085eefed1b0fc4b29398a4bbd1da168959` | `a404faa5acdfbe62bd265892c3b163c62b5404dc9fe2be423c87f46b90dd057f` | `0672dabb237865e3deef4335380a03b56158138bfc0c92c20540764d965d12f2` |
| 3 | `5655f9c7760455198da35ddbda2c35915ae187736f84e51b276b289055b52da6` | `6eae16e3f64623a90bef9dd31840bf6a90b520805d696a53adbb74bea9ac7a74` | `34cc4cf78fd5ccf3b3d88c9c23b82fc44bbcef4b8ed3c895d641545cfd01fc8d` |

## Regression

- `test_device_service_runtime.py`: `6/6 PASS`;
- Device Service matching tests: `142/142 PASS`;
- full platform suite: `1581 PASS + 1 skip`;
- runtime coverage, peripheral catalog, QEMU profiles and project snapshot:
  PASS;
- Ruff `E9/F`, compileall and `git diff --check`: PASS.

## Reproduction

Build the documented unified image and run the existing service runner:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_core2/make_image.py \
  --base platform/.cache/firmware/core2/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_Core2 \
  --littlefs .work/uiflow-core2-2.5.3/tools/littlefs/prebuilt/littlefs2 \
  --out /tmp/core2-unified.bin

python3 tests/uiflow2/core2_native_hci/run_service_5x.py \
  --image /tmp/core2-unified.bin \
  --elf .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_Core2/micropython.elf \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 3 --concurrency 1 --timeout 180 \
  --out-dir /tmp/core2-unified-service
```

## Boundaries

This is virtual-device validation. It does not establish physical hardware,
RF, antenna, BLE security/pairing, coexistence, electrical or physical timing
behavior. It does not close Core2 legacy UIFlow `RUNTIME-03`. The result is
bound to the firmware, ELF, QEMU, runner and service hashes above.

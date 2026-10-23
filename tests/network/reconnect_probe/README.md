# StickS3 reconnect probe

Last reviewed: `2026-10-24`

This UIFlow2 VFS replaces only `boot.py`/`main.py` in the validated StickS3
test image. It performs:

1. scan and association;
2. DHCP and controlled HTTP `/before`;
3. guest WLAN disconnect;
4. a five-second air gap during which the host may issue QMP link-down;
5. re-association and a second DHCP lease;
6. controlled HTTP `/after`.

Build the image from the validated unified app:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/m5-sticks3-unified-public.bin \
  --machine m5sticks3 \
  --files-dir tests/network/reconnect_probe \
  --vfs-offset 0x641000 \
  --vfs-size 0x1BE000 \
  --flash-size 0x800000 \
  --expected-size 135x240 \
  --efuse-pkg-version 1 \
  --out-dir /tmp/m5-reconnect-probe \
  --build-only
```

Create a Device Service `runtime=qemu-wifi` lease with
`profile=uiflow2-sticks3-wifi`, then poll the serial endpoint until
`RECONNECT DISCONNECTED`. Issue:

```bash
curl -sS -H 'Content-Type: application/json' -d '{"action":"down"}' \
  "$BASE/api/v1/sessions/$SID/network-fault"

# after at least two seconds
curl -sS -H 'Content-Type: application/json' -d '{"action":"up"}' \
  "$BASE/api/v1/sessions/$SID/network-fault"
```

The expected terminal marker is `RECONNECT RESULT: PASSED`. The host HTTP
fixture must log both `/before` and `/after`; the retained pcap summary should
show two DHCP exchanges and two TCP flows to the controlled endpoint.

This is simulation-only evidence. It proves application disconnect and
recovery over the OpenMAC/QEMU network data plane, not physical AP loss, RF
timing, WPA2/WPA3 security or DHCP server failure behavior.

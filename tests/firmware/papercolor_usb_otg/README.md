# PaperColor factory USB device enumeration

Use an owned Device Service and the canonical native runtime including 0180.
Supply the unmodified public PaperColor_Factory_Code BIN (M5Burner firmware
`1897200000000000148`). The runner checks its SHA-256, uploads the original
bytes and exercises the guest TinyUSB endpoint-zero path immediately after
attachment, within the first cold-boot epoch.

```sh
python3 tests/firmware/papercolor_usb_otg/run_test.py \
  --api "$OWNED_SERVICE_API" --token-file "$OWNED_TOKEN_FILE" \
  --bin "$ORIGINAL_FACTORY_BIN" --out "$IGNORED_EVIDENCE_DIR"
```

The checks include device/configuration descriptors, device address,
configuration selection/readback and MSC GET_MAX_LUN. The pinned firmware
exposes one MSC interface, so CDC is not an applicable class transfer; the
[StickS3 probe](../sticks3_usb_otg/README.md) separately covers CDC and bulk I/O.
This probe covers the buffer-DMA control-transfer path and records every virtual
host packet. It does not claim MSC block reads/writes, physical USB or a stable
factory application: a later Wi-Fi/task-priority assertion remains separate.
Evidence is requested before stop, with session history retained.

# Core2 legacy dual-SPI display probe

This fixture keeps the public UIFlow `v1.15.4` `/flash/boot.py` SD-card setup
and appends a legacy `m5stack` LCD drawing sequence. It exercises the same
ESP32 display controller and panel sink paths used by the public startup UI.

Pack this `boot.py` together with the original VFS assets using the UIFlow
`tools/littlefs/prebuilt/littlefs2` packer:

```bash
tools/littlefs/prebuilt/littlefs2 \
  -c -b core2 \
  -i /path/to/original-flash-assets-with-probe-boot \
  -o /path/to/vfs.bin \
  -s 0x6de000
```

Splice the generated `0x6de000` payload into a copy of the public, padded
16 MiB image at `0x520000`.

Expected serial markers:

```text
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
CORE2_LEGACY_DISPLAY_PROBE_DONE
```

The frame must contain the `CORE2 LEGACY` / `PANEL ROUTING` text and green
rectangle. Run this through the Device Service `runtime=qemu-wifi` lane with
WDT disabled only as a diagnostic control. Reaching the probe marker while
the same firmware remains on the normal-WDT reset path does not close
`RUNTIME-03`.

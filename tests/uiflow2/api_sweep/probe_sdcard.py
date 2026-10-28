"""Exercise the real SPI SD block path and the official hardware mount closure.

The host provides a disposable, FAT-formatted session-isolated SD artifact.
Writes apply to that artifact only. CoreS3 pins are from M5Unified's SPI
pin table; Cardputer-ADV uses the existing device-local SD matrix pins.
"""
import json
import os
import M5
from machine import Pin, SDCard
from hardware import SDCard as mount_sd

M5.begin()
if "Cardputer" in os.uname().machine:
    pins = (40, 14, 39, 12)
else:
    pins = (36, 37, 35, 4)
kwargs = dict(slot=3, width=1, sck=Pin(pins[0]), mosi=Pin(pins[1]),
              miso=Pin(pins[2]), cs=Pin(pins[3]), freq=1000000)
try:
    import sd_fixture_config as config
except ImportError:
    config = None
block_count = getattr(config, "BLOCK_COUNT", 1)
file_pattern_bytes = getattr(config, "FILE_PATTERN_BYTES", 256)
format_disk = getattr(config, "FORMAT_DISK", False)
assert 1 <= block_count <= 8 and 1 <= file_pattern_bytes <= 65536
try:
    card = SDCard(**kwargs)
    expected = bytes((i * 7 + 0x31) & 255 for i in range(512 * block_count))
    actual = bytearray(len(expected))
    wrote = card.writeblocks(4096, expected)
    read = card.readblocks(4096, actual)
    assert wrote and read and bytes(actual) == expected
    print("HARDWARE_SD_BLOCK_PASS " + json.dumps({"sector": 4096, "bytes": len(expected), "info": card.info()}))
    if format_disk:
        os.VfsFat.mkfs(card)
        print("HARDWARE_SD_FORMAT_PASS")
    card.deinit()
    mounted = mount_sd(**kwargs)
    assert mounted is None
    payload = b"M5EMU_SD_FILE_ORACLE_20261027\n" + bytes((i * 7 + 0x31) & 255 for i in range(file_pattern_bytes))
    with open("/sd/api-sweep.bin", "wb") as handle:
        assert handle.write(payload) == len(payload)
    os.sync()
    with open("/sd/api-sweep.bin", "rb") as handle:
        restored = handle.read()
    assert restored == payload
    assert "api-sweep.bin" in os.listdir("/sd")
    # Unmount/remount to exclude an open file or VFS-only read cache oracle.
    mount_sd(**kwargs)
    with open("/sd/api-sweep.bin", "rb") as handle:
        assert handle.read() == payload
    print("HARDWARE_API " + json.dumps({"api": "hardware.SDCard", "status": "API_ASSERTION_PASS",
        "value": {"raw_block_roundtrip": True, "raw_block_bytes": len(expected), "formatted_by_guest": format_disk, "mounted_file_bytes": len(payload), "remount_readback": True},
        "detail": "Disposable isolated SD: native SPI block roundtrip, optional guest format, official mount closure, distinct file write, sync, unmount/remount and exact readback; fixture config defines transfer scope."}))
except Exception as error:
    print("HARDWARE_API " + json.dumps({"api": "hardware.SDCard", "status": "FAIL", "error": repr(error)}))
print("HARDWARE_SD_DONE")

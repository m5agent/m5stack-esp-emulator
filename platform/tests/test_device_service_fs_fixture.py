from hashlib import md5, sha256
import importlib.util
import struct
import unittest

from device_service_errors import ServiceError
from device_service_fs_fixture import parse_fs_fixture, plan_fs_fixture
from firmware_analysis import analyze_esp_image
from firmware_filesystems import inventory_data_partition
from firmware_manifest import canonical_json_sha256
from test_firmware_analysis import build_image, build_spiffs_volume


APP_OFFSET = 0x10000
DATA_OFFSET = 0x30000


def _unsigned_esp_image(chip, *, uiflow=False):
    data = bytearray(build_image(chip))
    if uiflow:
        data[48:80] = b"V2.5.3".ljust(32, b"\0")
        data[80:112] = b"micropython".ljust(32, b"\0")
        data.extend(b"UIFLOW2\0_uiflow_run_main")
        struct.pack_into("<I", data, 28, len(data) - 32)
    data[23] = 1
    checksum = 0xEF
    for byte in data[32:]:
        checksum ^= byte
    data.extend(bytes((15 - len(data)) % 16))
    data.append(checksum)
    return bytes(data) + sha256(data).digest()


def _part(label, kind, subtype, offset, size, flags=0):
    return struct.pack("<HBBII16sI", 0x50AA, kind, subtype, offset, size, label.encode(), flags)


def _firmware(volume, *, subtype=0x83, label="storage", flags=0, extra=b"", chip=9, uiflow=False):
    data = bytearray(b"\xff" * (DATA_OFFSET + len(volume)))
    boot = _unsigned_esp_image(chip)
    boot_offset = 0x1000 if chip == 0 else 0
    data[boot_offset:boot_offset + len(boot)] = boot
    app = _unsigned_esp_image(chip, uiflow=uiflow)
    data[APP_OFFSET:APP_OFFSET + len(app)] = app
    table = _part("factory", 0, 0, APP_OFFSET, DATA_OFFSET - APP_OFFSET)
    table += _part(label, 1, subtype, DATA_OFFSET, len(volume), flags) + extra
    table += b"\xeb\xeb" + bytes(14) + md5(table).digest()
    data[0x8000:0x8000 + len(table)] = table
    data[DATA_OFFSET:] = volume
    return bytes(data)


def _plan(firmware, fixture, *, label="storage", fmt="littlefs", chip=9, **kwargs):
    default = {"firmware_sha256": sha256(firmware).hexdigest(), "expected_chip_id": chip,
               "bootloader_offset": 0x1000 if chip == 0 else 0}
    default.update(kwargs)
    return plan_fs_fixture(
        firmware, fixture,
        {"image_artifact_id": sha256(fixture).hexdigest(), "partition_label": label, "format": fmt},
        **default,
    )


def _littlefs_file(*, blocks=6, block_size=4096, content=b"review fixture\n"):
    import littlefs

    context = littlefs.UserContext(buffer=bytearray(b"\xff" * (block_size * blocks)))
    fs = littlefs.LittleFS(context=context, block_size=block_size, block_count=blocks, mount=False)
    fs.format()
    fs.mount()
    with fs.open("/fixture.txt", "wb") as handle:
        handle.write(content)
    fs.unmount()
    return bytes(context.buffer)


class FsFixturePlannerTests(unittest.TestCase):
    def test_parses_explicit_format_label_and_lowercase_digest_only(self):
        self.assertEqual(parse_fs_fixture(None), {})
        fields = {"format": "littlefs", "partition_label": "storage", "image_artifact_id": "b" * 64}
        self.assertEqual(parse_fs_fixture(fields), fields)
        for override in (
            {"format": "fat"}, {"file_dir": "."}, {"partition_label": ""},
            {"partition_label": "a\x00b"}, {"partition_label": "\ud800"},
            {"partition_label": "虚拟文件系统名称"}, {"image_artifact_id": "B" * 64},
        ):
            with self.subTest(override=override), self.assertRaises(ServiceError) as raised:
                parse_fs_fixture({**fields, **override})
            self.assertEqual((raised.exception.code, raised.exception.status), ("invalid_fs_fixture", 400))

    def test_binds_requested_hashes_before_inventory(self):
        base, fixture = _firmware(b"\xff" * 8192), b"\xff" * 8192
        with self.assertRaises(ServiceError) as raised:
            _plan(base, fixture, firmware_sha256="0" * 64)
        self.assertEqual(raised.exception.code, "fs_fixture_firmware_mismatch")
        with self.assertRaises(ServiceError) as raised:
            plan_fs_fixture(base, fixture, {
                "format": "littlefs", "partition_label": "storage", "image_artifact_id": "0" * 64
            }, firmware_sha256=sha256(base).hexdigest(), expected_chip_id=9, bootloader_offset=0)
        self.assertEqual(raised.exception.code, "fs_fixture_artifact_mismatch")

    def test_duplicate_label_overlap_and_wrong_partition_type_reject(self):
        base, fixture = _firmware(b"\xff" * 8192), b"\xff" * 8192
        for firmware, label, code in (
            (_firmware(fixture, extra=_part("storage", 1, 0x83, 0x9000, 0x1000)),
             "storage", "fs_fixture_partition_not_unique"),
            (_firmware(fixture, extra=_part("collision", 1, 0x83, DATA_OFFSET, 0x1000)),
             "storage", "fs_fixture_invalid_layout"),
            (base, "factory", "fs_fixture_partition_unsupported"),
            (base, "missing", "fs_fixture_partition_not_unique"),
        ):
            with self.subTest(code=code), self.assertRaises(ServiceError) as raised:
                _plan(firmware, fixture, label=label)
            self.assertEqual(raised.exception.code, code)

    def test_wrong_size_file_format_flags_or_chip_fail_closed(self):
        fixture = b"\xff" * 8192
        base = _firmware(fixture)
        for firmware, payload, code, options in (
            (base, fixture[:-1], "fs_fixture_invalid_size", {}),
            (base, fixture, "fs_fixture_invalid_image", {}),
            (base, fixture, "fs_fixture_partition_unsupported", {"fmt": "spiffs"}),
            (_firmware(fixture, flags=2), fixture, "fs_fixture_partition_unsupported", {}),
            (_firmware(fixture, flags=1), fixture, "fs_fixture_secure_firmware", {}),
            (base, fixture, "fs_fixture_invalid_layout", {"chip": 13}),
            (base, fixture, "fs_fixture_invalid_layout", {"bootloader_offset": 0x1000}),
        ):
            with self.subTest(code=code, options=options), self.assertRaises(ServiceError) as raised:
                _plan(firmware, payload, **options)
            self.assertEqual(raised.exception.code, code)

    def test_signature_trailers_and_security_metadata_fail_closed(self):
        fixture = b"\xff" * 8192
        base = bytearray(_firmware(fixture))
        image = analyze_esp_image(base, APP_OFFSET)
        trailer = APP_OFFSET + ((image["image_end"] - APP_OFFSET + 16) & ~15) + 32
        base[trailer:trailer + 4] = b"\xe7\x02\0\0"
        with self.assertRaises(ServiceError) as raised:
            _plan(bytes(base), fixture)
        self.assertEqual(raised.exception.code, "fs_fixture_secure_firmware")
        base[trailer:trailer + 4] = b"\xff" * 4
        for security in (
            {"secure_boot_config": "v1"}, {"flash_encryption": "enabled"},
            {"efuse_summary": {"secure_boot": "v2"}},
            {"secure_boot_image": {"status": "not-found", "images": [{"status": "not-found", "candidate_count": 1}]}},
        ):
            with self.subTest(security=security), self.assertRaises(ServiceError) as raised:
                _plan(bytes(base), fixture, security=security)
            self.assertEqual(raised.exception.code, "fs_fixture_secure_firmware")

    def test_declared_security_ambiguity_is_distinct_from_absent_metadata(self):
        fixture = build_spiffs_volume(multi_index=True)
        base = _firmware(fixture, subtype=0x82)
        plan = _plan(base, fixture, fmt="spiffs")
        self.assertEqual(plan, _plan(base, fixture, fmt="spiffs", security={
            "secure_boot": "disabled",
            "flash_encryption": "not-indicated",
            "efuse": "not-included",
            "efuse_summary": None,
        }))
        ambiguous = (
            {"secure_boot": "unknown"},
            {"flash_encryption": "unknown"},
            {"secure_boot_config": None},
            {"flash_encryption_config": "unknown"},
            {"efuse": "unknown"},
            {"efuse": "summary-included", "efuse_summary": None},
            {"efuse_summary": {}},
            {"efuse_summary": {"secure_boot": "disabled", "flash_encryption": "unknown"}},
        )
        for security in ambiguous:
            with self.subTest(security=security), self.assertRaises(ServiceError) as raised:
                _plan(base, fixture, fmt="spiffs", security=security)
            self.assertEqual((raised.exception.code, raised.exception.status), ("fs_fixture_secure_firmware", 409))

    def test_spiffs_requires_existing_geometry_and_matching_fixture(self):
        base_volume = build_spiffs_volume(multi_index=True, obj_name_len=64)
        fixture = build_spiffs_volume(multi_index=True, obj_name_len=32)
        size = max(len(base_volume), len(fixture))
        base_volume, fixture = base_volume.ljust(size, b"\xff"), fixture.ljust(size, b"\xff")
        for volume, code in (
            (base_volume, "fs_fixture_geometry_mismatch"),
            (b"\xff" * size, "fs_fixture_unverified_geometry"),
        ):
            with self.subTest(code=code), self.assertRaises(ServiceError) as raised:
                _plan(_firmware(volume, subtype=0x82), fixture, fmt="spiffs")
            self.assertEqual(raised.exception.code, code)
        plan = _plan(_firmware(fixture, subtype=0x82), fixture, fmt="spiffs")
        self.assertEqual(plan["geometry"]["object_name_len"], 32)
        self.assertGreater(plan["file_bytes"], 0)
        self.assertNotIn("files", plan)

    def test_spiffs_optional_inventory_budget_limits_file_reads(self):
        fixture = build_spiffs_volume(multi_index=True)
        parsed = inventory_data_partition(
            fixture, {"offset": 0, "size": len(fixture), "subtype": 0x82}, max_file_bytes=1
        )
        self.assertEqual((parsed["status"], parsed["total_file_bytes"]), ("PARTIAL", 0))


@unittest.skipUnless(importlib.util.find_spec("littlefs"), "littlefs-python is unavailable")
class LittleFSFixturePlannerTests(unittest.TestCase):
    def test_exact_size_littlefs_is_reused_without_mutation(self):
        fixture = _littlefs_file()
        for chip in (0, 9):
            with self.subTest(chip=chip):
                firmware = _firmware(b"\xff" * len(fixture), chip=chip)
                plan = _plan(firmware, fixture, chip=chip)
                self.assertEqual(plan["offset"], DATA_OFFSET)
                self.assertEqual(plan["base_flash_sha256"], sha256(firmware).hexdigest())
                self.assertEqual(plan["base_partition_sha256"], sha256(firmware[DATA_OFFSET:]).hexdigest())
                self.assertEqual(plan["fixture_sha256"], sha256(fixture).hexdigest())
                self.assertEqual(plan["geometry"], {"block_size": 4096, "block_count": 6})
                self.assertEqual((plan["file_count"], plan["file_bytes"]), (1, len(b"review fixture\n")))
                self.assertEqual(plan, _plan(firmware, fixture, chip=chip))
                self.assertEqual(plan["plan_sha256"], canonical_json_sha256({
                    k: v for k, v in plan.items() if k != "plan_sha256"
                }))

    def test_legacy_vfs_requires_an_exact_ui_flow_fingerprint_and_existing_fs(self):
        fixture = _littlefs_file()
        base_volume = _littlefs_file(content=b"prior")
        plan = _plan(_firmware(base_volume, subtype=0x81, label="vfs", uiflow=True), fixture, label="vfs")
        self.assertEqual(plan["subtype"], 0x81)
        self.assertNotEqual(plan["base_partition_sha256"], plan["fixture_sha256"])
        for base, code in (
            (_firmware(base_volume, subtype=0x81, label="vfs"), "fs_fixture_partition_unsupported"),
            (_firmware(b"\xff" * len(base_volume), subtype=0x81, label="vfs", uiflow=True), "fs_fixture_unverified_geometry"),
        ):
            with self.subTest(code=code), self.assertRaises(ServiceError) as raised:
                _plan(base, fixture, label="vfs")
            self.assertEqual(raised.exception.code, code)

    def test_littlefs_requires_full_partition_geometry(self):
        base = _firmware(b"\xff" * 6 * 4096)
        with self.assertRaises(ServiceError) as raised:
            _plan(base, _littlefs_file(blocks=3, block_size=8192))
        self.assertEqual(raised.exception.code, "fs_fixture_unverified_geometry")

    def test_littlefs_optional_inventory_budget_limits_file_reads(self):
        fixture = _littlefs_file(content=b"abcdef")
        parsed = inventory_data_partition(
            fixture, {"offset": 0, "size": len(fixture), "subtype": 0x83}, max_file_bytes=5
        )
        self.assertEqual((parsed["status"], parsed["total_file_bytes"]), ("PARTIAL", 0))

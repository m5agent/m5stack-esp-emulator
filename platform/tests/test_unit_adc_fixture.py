"""Host calibration contracts; these tests never start firmware or QEMU."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import unit_adc_fixture as adc


ROOT = Path(__file__).resolve().parents[2]


class UnitAdcFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = adc.FIXTURE.read_bytes()
        cls.fixture = adc.load_fixture(raw=cls.raw)

    def apply_host_buffer(self, image=None, *, raw=None):
        """Isolate bit-level contracts from the separately tested app admission."""
        if image is None:
            image = bytearray(4096)
        with patch.object(adc, "verify_firmware"):
            return adc.apply_s3_adc_calibration(
                image, backend="qemu-esp32s3", firmware=b"host-test-only",
                fixture_raw=self.raw if raw is None else raw,
            )

    @staticmethod
    def encode(fixture):
        return json.dumps(fixture).encode("utf-8")

    def test_exact_field_locations_and_cross_block_attenuation(self):
        expected = {
            "BLK_VERSION_MAJOR": (2, 128, 2),
            "ADC1_INIT_CODE_ATTEN0": (2, 149, 8),
            "ADC1_INIT_CODE_ATTEN1": (2, 157, 6),
            "ADC1_INIT_CODE_ATTEN2": (2, 163, 6),
            "ADC1_INIT_CODE_ATTEN3": (2, 169, 6),
            "ADC2_INIT_CODE_ATTEN0": (2, 175, 8),
            "ADC2_INIT_CODE_ATTEN1": (2, 183, 6),
            "ADC2_INIT_CODE_ATTEN2": (2, 189, 6),
            "ADC2_INIT_CODE_ATTEN3": (2, 195, 6),
            "ADC1_CAL_VOL_ATTEN0": (2, 201, 8),
            "ADC1_CAL_VOL_ATTEN1": (2, 209, 8),
            "ADC1_CAL_VOL_ATTEN2": (2, 217, 8),
            "ADC1_CAL_VOL_ATTEN3": (2, 225, 8),
            "ADC2_CAL_VOL_ATTEN0": (2, 233, 8),
            "ADC2_CAL_VOL_ATTEN1": (2, 241, 7),
            "ADC2_CAL_VOL_ATTEN2": (2, 248, 7),
            "ADC2_CAL_VOL_ATTEN3": (1, 186, 6),
        }
        actual = {f["name"]: (f["block"], f["bit_start"], f["bit_count"]) for f in self.fixture["fields"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.fixture["fields"]), 17)
        self.assertIs(self.fixture["hardware_validation"], False)

    def test_unsigned_difference_decoding_matches_sar_reference(self):
        expected = {"adc1": [3664, 2785, 1989, 1123], "adc2": [3664, 2785, 1989, 1123]}
        self.assertEqual(adc.decoded_reference_digital(self.fixture), expected)
        self.assertEqual(self.fixture["sar_profile"]["reference_digital"], expected)

    def test_python_oracle_matches_all_official_c_vectors(self):
        vectors = self.fixture["numeric_oracle"]["test_vectors"]
        self.assertEqual(len(vectors), 80)
        self.assertEqual({(v["adc_unit"], v["attenuation"]) for v in vectors}, {(u, a) for u in (1, 2) for a in range(4)})
        for v in vectors:
            with self.subTest(**v):
                self.assertEqual(adc.expected_read_uv(v["raw_12bit"], attenuation=v["attenuation"], adc_unit=v["adc_unit"], fixture=self.fixture), v["read_uv"])

    def test_official_c_harness_reproduces_frozen_vectors(self):
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("host C compiler unavailable; frozen-vector Python check still runs")
        oracle = self.fixture["numeric_oracle"]
        source = ROOT / oracle["host_harness_path"]
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), oracle["host_harness_sha256"])
        with tempfile.TemporaryDirectory(prefix="m5-adc-oracle-") as temp:
            binary = Path(temp) / "adc-reference-oracle"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Werror", str(source), "-o", str(binary)], check=True, capture_output=True, timeout=30)
            result = subprocess.run([str(binary)], check=True, text=True, capture_output=True, timeout=10)
        actual = [tuple(map(int, line.split())) for line in result.stdout.splitlines()]
        expected = [(v["adc_unit"], v["attenuation"], v["raw_12bit"], v["read_uv"]) for v in oracle["test_vectors"]]
        self.assertEqual(actual, expected)

    def test_non_calibration_bits_are_preserved_across_entire_buffer(self):
        image = bytearray((i * 73 + 29) % 256 for i in range(4096))
        allowed = bytearray(4096)
        for field in self.fixture["fields"]:
            start = {0: 0, 1: 24, 2: 48}[field["block"]] * 8 + field["bit_start"]
            for bit in range(field["bit_count"]):
                byte, offset = divmod(start + bit, 8)
                allowed[byte] |= 1 << offset
                image[byte] &= ~(1 << offset)
        before = bytes(image)
        receipt = self.apply_host_buffer(image)
        for i, (old, new, mask) in enumerate(zip(before, image, allowed)):
            self.assertEqual((old ^ new) & ~mask, 0, f"outside whitelist at byte {i}")
        self.assertEqual(image[:24], before[:24])
        self.assertEqual(image[24:30], before[24:30])
        for field in self.fixture["fields"]:
            self.assertEqual(adc.field_value(image, field), field["value"])
        self.assertIs(receipt["identity_or_security_fields_changed"], False)

    def test_late_conflict_cannot_leave_partially_written_efuse(self):
        image = bytearray(4096)
        last = self.fixture["fields"][-1]
        self.assertEqual(last["name"], "ADC2_CAL_VOL_ATTEN2")
        bit = 48 * 8 + 248
        image[bit // 8] |= 1 << (bit % 8)
        before = bytes(image)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.apply_host_buffer(image)
        self.assertEqual(image, before)

    def test_apply_is_idempotent(self):
        image = bytearray(4096)
        first = self.apply_host_buffer(image)
        before = bytes(image)
        second = self.apply_host_buffer(image)
        self.assertEqual(image, before)
        self.assertEqual(first, second)

    def test_frozen_bytes_never_read_default_file_and_hash_same_bytes(self):
        frozen = self.raw + b"\n "
        with patch.object(Path, "read_bytes", side_effect=AssertionError("disk read after fixture freeze")):
            self.assertEqual(adc.load_fixture(raw=frozen), self.fixture)
            receipt = self.apply_host_buffer(raw=frozen)
        self.assertEqual(receipt["fixture_sha256"], hashlib.sha256(frozen).hexdigest())
        self.assertEqual(receipt["source"], "session-frozen-fixture")
        self.assertEqual(receipt["status"], "applied")
        self.assertIs(receipt["hardware_validation"], False)

    def test_wrong_backend_buffer_type_and_size_fail_without_mutation(self):
        for backend, image in (("qemu-esp32", bytearray(4096)), ("qemu-esp32s3", bytes(4096)), ("qemu-esp32s3", bytearray(4095))):
            with self.subTest(backend=backend, buffer_type=type(image), length=len(image)):
                before = bytes(image)
                with self.assertRaisesRegex(ValueError, "4096-byte"):
                    adc.apply_s3_adc_calibration(image, backend=backend, firmware=b"unknown", fixture_raw=self.raw)
                self.assertEqual(image, before)

    def test_unknown_firmware_and_copied_metadata_are_rejected(self):
        # A copied/self-declared ELF hash cannot stand in for application bytes.
        unknown = b"fake descriptor " + self.fixture["firmware_binding"]["app_elf_sha256"].encode()
        image = bytearray(4096)
        with self.assertRaisesRegex(ValueError, "application bytes"):
            adc.apply_s3_adc_calibration(image, backend="qemu-esp32s3", firmware=unknown, fixture_raw=self.raw)
        self.assertEqual(image, bytes(4096))

    def test_byte_binding_accepts_only_changes_outside_app(self):
        fixture = copy.deepcopy(self.fixture)
        code = b"synthetic host-only application" * 8
        fixture["firmware_binding"].update(application_offset=32, application_segment_bytes=len(code), application_segment_sha256=hashlib.sha256(code).hexdigest())
        image = b"n" * 32 + code + b"vfs fixture"
        adc.verify_firmware(image, fixture)
        adc.verify_firmware(b"s" * 32 + code + b"changed vfs/nvs contents", fixture)
        changed = bytearray(image)
        changed[33] ^= 1
        for image in (bytes(changed), image[:-12], bytearray(image)):
            with self.assertRaises(ValueError):
                adc.verify_firmware(image, fixture)

    def test_malicious_field_layout_cannot_target_identity_or_security(self):
        for key, value in (("block", 0), ("bit_start", 0), ("bit_count", 7), ("block", True), ("value", True), ("name", "MAC_FACTORY")):
            fixture = copy.deepcopy(self.fixture)
            fixture["fields"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                adc.load_fixture(raw=self.encode(fixture))
        fixture = copy.deepcopy(self.fixture)
        fixture["fields"].append(copy.deepcopy(fixture["fields"][0]))
        with self.assertRaises(ValueError):
            adc.load_fixture(raw=self.encode(fixture))

    def test_invalid_fixture_encoding_layout_metadata_and_binding_fail(self):
        for raw in (b"[]", b"null", b"{}", b"\xff", "not bytes", bytearray(self.raw)):
            with self.subTest(raw_type=type(raw)), self.assertRaises(ValueError):
                adc.load_fixture(raw=raw)
        for section, key, value in (
            (None, "schema_version", True), (None, "hardware_validation", True),
            ("sar_profile", "maximum_raw", 65535), ("sar_profile", "reference_voltage_mv", 1100),
            ("firmware_binding", "application_offset", -1), ("firmware_binding", "application_segment_bytes", 0),
            ("firmware_binding", "application_segment_sha256", "not-a-hash"),
        ):
            fixture = copy.deepcopy(self.fixture)
            (fixture if section is None else fixture[section])[key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                adc.load_fixture(raw=self.encode(fixture))

    def test_mismatched_references_and_init_offset_fail_atomically(self):
        for name, value in (("ADC1_CAL_VOL_ATTEN3", 222), ("ADC1_INIT_CODE_ATTEN0", 1)):
            fixture = copy.deepcopy(self.fixture)
            next(field for field in fixture["fields"] if field["name"] == name)["value"] = value
            image = bytearray(4096)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.apply_host_buffer(image, raw=self.encode(fixture))
            self.assertEqual(image, bytes(4096))

    def test_expected_input_uses_real_raw_expansion_and_idf_curve(self):
        result = adc.expected_ideal_input(1250)
        self.assertEqual((result["raw_12bit"], result["read_u16"], result["read_uv"]), (1651, 26422, 1232000))
        for value in (3100, 3300, 1e308):
            result = adc.expected_ideal_input(value)
            self.assertEqual((result["raw_12bit"], result["read_u16"], result["read_uv"]), (4095, 65535, 2912000))

    def test_invalid_oracle_inputs_are_rejected(self):
        for raw in (-1, 4096, True, 1.5, "330", None):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                adc.expected_read_uv(raw)
        for key, values in (("attenuation", (-1, 4, True, 3.0)), ("adc_unit", (0, 3, True, "1"))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    adc.expected_read_uv(100, **{key: value})
        for value in (-1, True, None, "1250", float("nan"), float("inf"), 10**500):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValueError):
                adc.expected_ideal_input(value)

    def test_cardputer_fixture_uses_its_own_s3_application_binding(self):
        cardputer = adc.load_fixture(path=adc.CARDPUTER_FIXTURE)
        self.assertEqual(cardputer["id"], "esp32s3-cardputer-ideal-adc-v1")
        self.assertEqual(cardputer["backend"], "qemu-esp32s3")
        self.assertIs(cardputer["hardware_validation"], False)
        self.assertEqual(
            cardputer["firmware_binding"]["reference_sha256"],
            "a3961c8eda7358771c8e06c9160648e87ada973d23c6f71c9939b76fa973bed9",
        )
        self.assertEqual(
            cardputer["firmware_binding"]["application_segment_sha256"],
            "b5cc34b9fb1487d027b09b8b2cd9cab460b3349dff7245c163e88f45be778e53",
        )
        self.assertNotEqual(
            cardputer["firmware_binding"],
            self.fixture["firmware_binding"],
        )

        code = b"cardputer-application-bytes" * 8
        cardputer["firmware_binding"].update(
            application_offset=32,
            application_segment_bytes=len(code),
            application_segment_sha256=hashlib.sha256(code).hexdigest(),
        )
        image = b"n" * 32 + code + b"session-vfs"
        adc.verify_firmware(image, cardputer)
        changed = bytearray(image)
        changed[32] ^= 1
        with self.assertRaises(ValueError):
            adc.verify_firmware(bytes(changed), cardputer)


if __name__ == "__main__":
    unittest.main()

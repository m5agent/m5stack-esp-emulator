"""SPI SD fixtures use session-owned disks rather than inherited host paths."""
import unittest
from unittest import mock

import device_service_specs
from device_service_errors import ServiceError
import test_plain_qemu_audio as audio_tests


class PlainQemuStorageTests(unittest.TestCase):
    setUp = audio_tests.PlainQemuAudioTests.setUp
    tearDown = audio_tests.PlainQemuAudioTests.tearDown
    session = audio_tests.PlainQemuAudioTests.session

    def test_selected_boards_route_only_their_owned_sd_image(self):
        paths = []
        for device in ("cores3", "cardputer", "cardputer-adv", "core2", "papers3"):
            with self.subTest(device=device):
                session = self.session(device)
                self.assertTrue(session.spec.has_sd_card)
                session.storage_config = {"sd_image_artifact_id": "a" * 64}
                environment = {"M5SW_SPI_SD_IMAGE": "/another/session/private-disk.img"}
                session._qemu_storage_environment(environment)
                self.assertEqual(environment["M5SW_SPI_SD_IMAGE"], str(session.sd_card_image))
                self.assertEqual(session.sd_card_image.parent, session.dir)
                paths.append(environment["M5SW_SPI_SD_IMAGE"])
        self.assertEqual(len(set(paths)), len(paths))

    def test_no_fixture_cannot_inherit_a_host_spi_disk(self):
        for device in ("cores3", "cardputer", "cardputer-adv", "core2", "papers3", "paperdiy", "atoms3r"):
            with self.subTest(device=device):
                environment = {"M5SW_SPI_SD_IMAGE": "/host/private-disk.img"}
                self.session(device)._qemu_storage_environment(environment)
                self.assertNotIn("M5SW_SPI_SD_IMAGE", environment)

    def test_paperdiy_rechecks_native_card_detect_model_when_wiring_media(self):
        session = self.session("paperdiy")
        session.storage_config = {"sd_image_artifact_id": "a" * 64}
        env = {"M5SW_SPI_SD_IMAGE": "/host/private-disk.img"}
        with mock.patch.object(device_service_specs, "qemu_has_qom_property", return_value=False) as probe:
            with self.assertRaises(ServiceError) as error:
                session._qemu_storage_environment(env)
            self.assertEqual(error.exception.code, "storage_not_supported")
            self.assertNotIn("M5SW_SPI_SD_IMAGE", env)
            probe.return_value = True
            session._qemu_storage_environment(env)
            self.assertEqual(env["M5SW_SPI_SD_IMAGE"], str(session.sd_card_image))


if __name__ == "__main__":
    unittest.main()

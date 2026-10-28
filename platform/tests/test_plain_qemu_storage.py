"""SPI SD fixtures use session-owned disks rather than inherited host paths."""
import unittest

import test_plain_qemu_audio as audio_tests


class PlainQemuStorageTests(unittest.TestCase):
    setUp = audio_tests.PlainQemuAudioTests.setUp
    tearDown = audio_tests.PlainQemuAudioTests.tearDown
    session = audio_tests.PlainQemuAudioTests.session

    def test_selected_boards_route_only_their_owned_sd_image(self):
        paths = []
        for device in ("cores3", "cardputer-adv"):
            with self.subTest(device=device):
                session = self.session(device)
                self.assertTrue(session.spec.has_sd_card)
                session.storage_config = {"sd_image_artifact_id": "a" * 64}
                environment = {"M5SW_SPI_SD_IMAGE": "/another/session/private-disk.img"}
                session._qemu_storage_environment(environment)
                self.assertEqual(environment["M5SW_SPI_SD_IMAGE"], str(session.sd_card_image))
                self.assertEqual(session.sd_card_image.parent, session.dir)
                paths.append(environment["M5SW_SPI_SD_IMAGE"])
        self.assertNotEqual(*paths)

    def test_no_fixture_cannot_inherit_a_host_spi_disk(self):
        for device in ("cores3", "cardputer-adv", "atoms3r"):
            with self.subTest(device=device):
                environment = {"M5SW_SPI_SD_IMAGE": "/host/private-disk.img"}
                self.session(device)._qemu_storage_environment(environment)
                self.assertNotIn("M5SW_SPI_SD_IMAGE", environment)


if __name__ == "__main__":
    unittest.main()

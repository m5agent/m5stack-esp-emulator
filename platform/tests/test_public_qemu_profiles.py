from pathlib import Path
import shutil
import subprocess
import unittest


class PublicQemuProfileContracts(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_profiles(self):
        result = subprocess.run(
            ["node", "--experimental-default-type=module", str(Path(__file__).with_suffix(".mjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

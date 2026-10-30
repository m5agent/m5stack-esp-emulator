import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("agent_skill_distribution", ROOT / "platform/tools/agent_skills.py")
distribution = importlib.util.module_from_spec(spec)
spec.loader.exec_module(distribution)


class AgentSkillPackagesTests(unittest.TestCase):
    def test_archives_are_deterministic_complete_and_executable_after_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            expected = distribution.skill_files()
            first = distribution.package_skills(temp / "one")
            second = distribution.package_skills(temp / "two")
            self.assertEqual([r["sha256"] for r in first], [r["sha256"] for r in second])
            for receipt in first:
                name = receipt["name"]
                with zipfile.ZipFile(receipt["path"]) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(set(archive.namelist()),
                                     {f"{name}/{p}" for p in expected[name]} | {f"{name}/SHA256SUMS"})
                    for path, value in expected[name].items():
                        self.assertEqual(archive.read(f"{name}/{path}"), value)
                    checksums = archive.read(f"{name}/SHA256SUMS").decode().splitlines()
                    for row in checksums:
                        digest, path = row.split("  ", 1)
                        self.assertEqual(hashlib.sha256(archive.read(f"{name}/{path}")).hexdigest(), digest)
                    archive.extractall(temp / "standalone")
                script = next(p for p in expected[name] if p.startswith("scripts/") and p.endswith(".py"))
                completed = subprocess.run([sys.executable, "-I", str(temp / "standalone" / name / script), "--help"],
                                           cwd=temp, capture_output=True, text=True, timeout=10)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("usage:", completed.stdout)

    def test_unlisted_operator_files_are_never_packaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "skills", root / "skills")
            config = root / "skills/m5stack-esp-emulator/config.local.json"
            config.write_text('{"token":"synthetic-not-for-distribution"}')
            (config.parent / ".env").write_text("SECRET=synthetic-not-for-distribution\n")
            for receipt in distribution.package_skills(root / "out", root):
                with zipfile.ZipFile(receipt["path"]) as archive:
                    self.assertFalse(any("local.json" in p or p.endswith("/.env") for p in archive.namelist()))
                    self.assertNotIn(b"synthetic-not-for-distribution", b"".join(archive.read(p) for p in archive.namelist()))

    def test_manifest_cannot_opt_in_private_or_external_files(self):
        for unsafe in ["config.local.json", "../outside.py", ".env", "firmware.bin"]:
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                shutil.copytree(ROOT / "skills", root / "skills")
                catalog = root / "skills/catalog.json"
                value = json.loads(catalog.read_text())
                value["skills"][0]["files"].append(unsafe)
                catalog.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    distribution.skill_files(root)

    def test_manifest_rejects_symbolic_link_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "skills", root / "skills")
            script = root / "skills/m5stack-esp-emulator/scripts/emulator.py"
            outside = root / "external.py"
            script.rename(outside)
            script.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlink"):
                distribution.skill_files(root)


if __name__ == "__main__":
    unittest.main()

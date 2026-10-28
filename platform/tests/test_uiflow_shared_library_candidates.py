"""Verify reviewed shared-library corrections against the pinned SDK source."""
import asyncio
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".work/uiflow-core2-2.5.3"
SWEEP = ROOT / "tests/uiflow2/api_sweep"
sys.path.insert(0, str(SWEEP))

from prepare_uiflow_library_candidates import prepare


class UUID:
    def __init__(self, value):
        if isinstance(value, (bytes, bytearray)):
            self.raw = bytes(value)
        elif value <= 0xFFFF:
            self.raw = int(value).to_bytes(2, "little")
        else:
            self.raw = int(value).to_bytes(4, "little")

    def __bytes__(self):
        return self.raw


def load(path, package=None):
    namespace = {"__name__": "candidate"}
    if package is not None:
        namespace["__package__"] = package
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
    return namespace


@unittest.skipUnless(SOURCE.is_dir(), "pinned UIFlow source checkout is not available")
class SharedLibraryCandidateTests(unittest.TestCase):
    def setUp(self):
        bluetooth = types.ModuleType("bluetooth")
        bluetooth.UUID = UUID
        micropython = types.ModuleType("micropython")
        micropython.const = lambda value: value
        micropython.schedule = lambda *_args: None
        self.previous = {
            name: sys.modules.get(name)
            for name in ("bluetooth", "micropython")
        }
        sys.modules["bluetooth"] = bluetooth
        sys.modules["micropython"] = micropython

    def tearDown(self):
        for name, previous in self.previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def test_ble_uuid32_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ble"
            receipt = prepare("ble-uuid32", SOURCE, output)
            self.assertEqual(len(receipt["files"]), 2)
            for row in receipt["files"]:
                module = load(output / row["guest_file"])
                decoded = module["decode_services"](
                    b"\x05\x05\x78\x56\x34\x12"
                )
                self.assertEqual([bytes(value).hex() for value in decoded], ["78563412"])

    def test_modbus_transform_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "modbus"
            receipt = prepare("modbus-transform", SOURCE, output)
            module = load(output / receipt["files"][0]["guest_file"])
            tcp = module["ModbusTCPFrame"](
                transaction_id=7,
                unit_id=1,
                func_code=3,
                register=0,
                length=2,
            )
            frame = module["ModbusRTUFrame"].transform_frame(tcp)
            self.assertEqual(bytes(frame.get_frame()).hex(), "010300000002c40b")

    def test_modbus_async_candidate_uses_socket_receive(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "modbus-async"
            receipt = prepare("modbus-async", SOURCE, output)
            source_path = output / receipt["files"][0]["guest_file"]
            previous_path = list(sys.path)
            sys.path.insert(0, str(SOURCE / "m5stack/libs/modbus"))
            try:
                module = load(source_path, "modbus")
                client_socket, peer_socket = socket.socketpair()
                try:
                    client_socket.setblocking(False)
                    peer_response = b"\x00\x01\x00\x00\x00\x05\x01\x03\x02\x10\xe1"
                    peer_socket.sendall(peer_response)
                    client = object.__new__(module["ModbusTCPClient"])
                    client.sock = client_socket
                    state, response = asyncio.run(
                        client._send_async(
                            b"\x00\x01\x00\x00\x00\x06\x01\x03\x00\x00\x00\x02",
                            timeout=100,
                        )
                    )
                    self.assertTrue(state)
                    self.assertEqual(response, peer_response)
                finally:
                    client_socket.close()
                    peer_socket.close()
            finally:
                sys.path[:] = previous_path

    def test_tls_epoch_patch_is_rebound_to_the_current_release_source(self):
        manifest = json.loads(
            (ROOT / "patches/uiflow2-api/0010-mbedtls-epoch.json").read_text()
        )
        source = SOURCE / manifest["path"]
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            manifest["preimage_sha256"],
        )
        patch = ROOT / "patches/uiflow2-api/0010-mbedtls-epoch.patch"
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / manifest["path"]
            work.parent.mkdir(parents=True)
            work.write_bytes(source.read_bytes())
            subprocess.run(
                ["patch", "-d", temporary, "-p1", "--batch", "--forward", "-i", str(patch)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(
                hashlib.sha256(work.read_bytes()).hexdigest(),
                manifest["candidate_sha256"],
            )

    def test_draw_pixel_candidate_is_transactionally_bound(self):
        manifest = json.loads(
            (ROOT / "patches/uiflow2-api/0024-display-draw-pixel-transaction.json").read_text()
        )
        source = SOURCE / manifest["path"]
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            manifest["preimage_sha256"],
        )
        patch = ROOT / "patches/uiflow2-api/0024-display-draw-pixel-transaction.patch"
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / manifest["path"]
            work.parent.mkdir(parents=True)
            work.write_bytes(source.read_bytes())
            subprocess.run(
                ["patch", "-d", temporary, "-p1", "--batch", "--forward", "-i", str(patch)],
                check=True,
                capture_output=True,
            )
            candidate = work.read_text()
            self.assertEqual(
                hashlib.sha256(work.read_bytes()).hexdigest(),
                manifest["candidate_sha256"],
            )
            self.assertIn("gfx->startWrite();\n    gfx->drawPixel", candidate)
            self.assertIn("gfx->endWrite();\n    return mp_const_none", candidate)


if __name__ == "__main__":
    unittest.main()

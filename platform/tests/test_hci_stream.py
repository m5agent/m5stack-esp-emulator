#!/usr/bin/env python3
from __future__ import annotations

import unittest

from hci_stream import HciStreamParser


class HciStreamParserTests(unittest.TestCase):
    def test_parses_commands_events_and_acl_across_chunks(self) -> None:
        parser = HciStreamParser()
        reset = bytes.fromhex("01030c00")
        command_complete = bytes.fromhex("040e0401030c00")
        acl = bytes.fromhex("0201200900050004000411001100")

        self.assertEqual(parser.feed(reset[:2]), [])
        self.assertEqual(
            parser.feed(reset[2:] + command_complete[:2]),
            [reset],
        )
        self.assertEqual(
            parser.feed(command_complete[2:] + acl[:4]),
            [command_complete],
        )
        self.assertEqual(parser.feed(acl[4:]), [acl])
        self.assertEqual(parser.buffer, b"")

    def test_rejects_unknown_packet_type(self) -> None:
        parser = HciStreamParser()
        with self.assertRaisesRegex(ValueError, "unsupported HCI packet type"):
            parser.feed(b"\xff")

    def test_waits_for_full_acl_payload(self) -> None:
        parser = HciStreamParser()
        acl = bytes.fromhex("02012008000102030405060708")
        self.assertEqual(parser.feed(acl[:-1]), [])
        self.assertEqual(parser.feed(acl[-1:]), [acl])


if __name__ == "__main__":
    unittest.main(verbosity=2)

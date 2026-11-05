"""Pure Preview request-context policy tests; no socket or guest launch."""
from email.message import Message
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from preview_request_context import tokenless_preview_local_control


class PreviewRequestContextTests(unittest.TestCase):
    def allowed(self, *, host="127.0.0.1:8123", origin=None, site=None,
                server=("127.0.0.1", 8123), peer=("127.0.0.1", 53123),
                method="POST", secure=False, extra=()):
        headers = Message()
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        if site is not None:
            headers["Sec-Fetch-Site"] = site
        for key, value in extra:
            headers[key] = value
        return tokenless_preview_local_control(server_address=server, client_address=peer,
                                               headers=headers, method=method, secure=secure)

    def test_same_origin_browser_and_explicit_local_cli(self):
        for values in [
            {},
            {"origin": "http://127.0.0.1:8123", "site": "same-origin"},
            {"origin": "http://127.0.0.1:8123"},
            {"method": "GET", "site": "same-origin"},
            {"site": "same-origin"},
            {"method": "GET", "site": "none"},
            {"host": "localhost:8123", "origin": "http://localhost:8123"},
            {"host": "LOCALHOST:8123", "origin": "http://localhost:8123"},
            {"host": "[::1]:8123", "origin": "http://[::1]:8123",
             "server": ("::1", 8123, 0, 0), "peer": ("::1", 54321, 0, 0)},
            {"host": "127.0.0.2:8123", "server": ("127.0.0.2", 8123)},
            {"host": "[::ffff:127.0.0.1]:8123", "server": ("::ffff:127.0.0.1", 8123),
             "peer": ("::ffff:127.0.0.1", 54321)},
            {"host": "localhost", "server": ("127.0.0.1", 80), "origin": "http://localhost"},
            {"host": "localhost", "server": ("127.0.0.1", 443), "origin": "https://localhost", "secure": True},
        ]:
            with self.subTest(values=values):
                self.assertTrue(self.allowed(**values))

    def test_socket_bind_and_peer_must_both_be_loopback(self):
        for values in [
            {"server": ("0.0.0.0", 8123)}, {"server": ("::", 8123, 0, 0)},
            {"server": ("192.0.2.1", 8123)}, {"peer": ("192.0.2.2", 8123)},
            {"peer": ("::ffff:192.0.2.2", 8123)}, {"server": ("localhost", 8123)},
            {"peer": ("localhost", 8123)}, {"server": ()}, {"peer": ()},
            {"server": ("::1%lo0", 8123)},
        ]:
            with self.subTest(values=values):
                self.assertFalse(self.allowed(**values))

    def test_host_is_single_literal_loopback_and_actual_listener_port(self):
        for host in [None, "", "evil.example:8123", "foo.localhost:8123", "localhost.:8123",
                     "192.0.2.1:8123", "0.0.0.0:8123", "127.0.0.1:8124", "127.0.0.1",
                     "127.0.0.1:bad", "127.0.0.1:65536", "user@127.0.0.1:8123",
                     "127.0.0.1:8123/path", "127.0.0.1:8123?", "127.0.0.1:8123#",
                     "127.0.0.1:8123,evil.example", "127.0.0.1:8123\\evil",
                     "127.0.0.1:8123 ", "127.0.0.1:\t8123", "[::1]:bad", "[::1%lo0]:8123",
                     "127.1:8123", "2130706433:8123", "0x7f000001:8123", "lоcalhost:8123"]:
            with self.subTest(host=host):
                self.assertFalse(self.allowed(host=host))
        self.assertFalse(self.allowed(extra=(("Host", "127.0.0.1:8123"),)))

    def test_origin_must_be_exact_nonopaque_origin_not_an_arbitrary_url(self):
        for origin in ["null", "", "https://127.0.0.1:8123", "http://localhost:8123",
                       "http://127.0.0.1:8124", "http://evil.example:8123", "file://",
                       "http://127.0.0.1:8123/", "http://127.0.0.1:8123?",
                       "http://127.0.0.1:8123#", "http://user@127.0.0.1:8123",
                       "http://127.0.0.1:8123 http://evil.example", "http://127.0.0.1:8123\\",
                       "http://[::1", "http://127.0.0.1:bad"]:
            with self.subTest(origin=origin):
                self.assertFalse(self.allowed(origin=origin))
        self.assertFalse(self.allowed(origin="http://127.0.0.1:8123",
                                      extra=(("Origin", "http://127.0.0.1:8123"),)))

    def test_cross_site_metadata_and_missing_origin_browser_context_are_rejected(self):
        for site in ["cross-site", "same-site", "none", "unknown", "same-origin,cross-site", ""]:
            with self.subTest(site=site):
                self.assertFalse(self.allowed(site=site))
        self.assertFalse(self.allowed(origin="http://127.0.0.1:8123", site="cross-site"))
        self.assertFalse(self.allowed(site="same-origin", extra=(("Sec-Fetch-Site", "same-origin"),)))
        self.assertFalse(self.allowed(extra=(("Sec-Fetch-Mode", "cors"),)))

    def test_forwarded_headers_cannot_supply_or_override_local_context(self):
        proxy = (("Forwarded", "for=127.0.0.1;host=127.0.0.1:8123;proto=http"),
                 ("X-Forwarded-Host", "127.0.0.1:8123"), ("X-Forwarded-For", "127.0.0.1"))
        self.assertFalse(self.allowed(host="evil.example:8123", extra=proxy))
        self.assertFalse(self.allowed(peer=("192.0.2.1", 12345), extra=proxy))
        self.assertFalse(self.allowed(server=("0.0.0.0", 8123), extra=proxy))
        self.assertTrue(self.allowed(extra=proxy), "proxy assertions do not change a genuine direct local request")


if __name__ == "__main__":
    unittest.main()

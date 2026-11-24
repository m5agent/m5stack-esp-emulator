"""Request parsing for the portable `review-sta` qemu-wifi profile (#238).

The profile runs one guest against a per-session userspace peer on a Unix
socketpair. No host IP socket, namespace, root or packet filter is involved,
so the same request is admissible on macOS and Linux workers.
"""
from __future__ import annotations

import ipaddress
import re

from device_service_errors import ServiceError

PROFILE = "review-sta"
ISOLATION = "userspace-fixture-only"
# Exact native board machines admitted for review-sta. A board is listed only
# after its control firmware set has a same-runtime virtual-device result.
BOARDS = {
    "cardputer": ("m5cardputer", "misc.esp32s3.wifi"),
    "cardputer-adv": ("m5cardputeradv", "misc.esp32s3.wifi"),
    "sticks3": ("m5sticks3", "misc.esp32s3.wifi"),
    "stopwatch": ("m5stopwatch", "misc.esp32s3.wifi"),
    "paperdiy": ("m5paperdiy", "misc.esp32s3.wifi"),
    "papers3": ("m5papers3", "misc.esp32s3.wifi"),
    "core2": ("m5core2", "misc.esp32_wifi"),
    "stickc-plus2": ("m5stickcplus2", "misc.esp32_wifi"),
}
# Capability families the emulator cannot serve with an in-session peer.
EXTERNAL_DEPENDENCIES = {
    "wifi_rf_attack": "deauth, evil twin, beacon spam and monitor-mode RF need a physical radio environment",
    "lora_peer": "LoRa/Meshtastic needs a real or modeled remote radio peer",
    "nfc_card": "NFC/RFID needs a physical card or tag",
    "infrared_target": "IR transmit needs a physical receiver such as a TV",
    "phone_provisioning": "captive-portal provisioning by a real phone or app",
    "usb_host": "BadUSB/HID injection needs a real USB host",
    "internet_service": "arbitrary Internet/TLS cloud endpoints are outside the fixture-only network",
}


def board_nic(spec) -> str | None:
    entry = BOARDS.get(spec.id)
    if (entry is None or spec.machine != entry[0] or spec.service_kind != "qemu"
            or spec.backend not in ("qemu-esp32s3", "qemu-esp32lx6")):
        return None
    return entry[1]
GATEWAY = ipaddress.IPv4Address("10.0.2.2")
LEASE = ipaddress.IPv4Address("10.0.2.15")
SECURITIES = ("open", "wpa2-psk")
FIXTURE_KINDS = ("dhcp", "dns", "http", "tcp", "udp", "mqtt")
ASSERTION_TYPES = (
    "wifi_auth", "dhcp_lease", "dns_query", "tcp_connect",
    "http_request", "udp_exchange", "mqtt_connect", "mqtt_publish",
)
SETUP_KINDS = ("button", "keyboard", "chord", "touch", "key", "wait")
MAX_ROUTES = 16
MAX_BODY = 4096
MAX_HEX = 1024
MAX_SETUP = 12
MAX_ASSERTIONS = 16
RESERVED_TCP_PORTS = frozenset({80, 1883})
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PATH = re.compile(r"^/[\x21-\x7e]{0,200}$")
_TOPIC = re.compile(r"^[\x21-\x7e]{1,128}$")


def _bad(message: str) -> ServiceError:
    return ServiceError("invalid_network", message, 400)


def _hostname(value: object, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 253:
        raise _bad(f"{field} must be a DNS name")
    name = value.lower().rstrip(".")
    if not all(_LABEL.match(label) for label in name.split(".")):
        raise _bad(f"{field} must be a DNS name")
    return name


def _hex(value: object, field: str) -> str:
    if (not isinstance(value, str) or not value or len(value) % 2
            or len(value) > MAX_HEX or not re.fullmatch(r"[0-9a-fA-F]+", value)):
        raise _bad(f"{field} must be 1-{MAX_HEX // 2} hex-encoded bytes")
    return value.lower()


def _port(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise _bad(f"{field} must be a TCP/UDP port")
    return value


def _only(value: dict, allowed: set[str], field: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise _bad(f"{field} has unsupported fields: {', '.join(sorted(extra))}")


def _dns(value: object) -> dict:
    if value is True:
        value = {}
    if not isinstance(value, dict):
        raise _bad("network.fixtures.dns must be true or an object")
    _only(value, {"A"}, "network.fixtures.dns")
    records = value.get("A", {})
    if not isinstance(records, dict) or len(records) > 32:
        raise _bad("network.fixtures.dns.A must map at most 32 names")
    answers = {}
    for name, address in records.items():
        host = _hostname(name, "network.fixtures.dns.A name")
        # Only the in-session peer is reachable. Any other answer would be a
        # destination the fixture cannot serve, so it is rejected up front.
        if address != str(GATEWAY):
            raise ServiceError("fixture_rejected", f"DNS answer for {host} must be {GATEWAY}", 400)
        answers[host] = str(GATEWAY)
    return {"A": answers}


def _http(value: object) -> dict:
    if not isinstance(value, dict):
        raise _bad("network.fixtures.http must be an object")
    _only(value, {"port", "routes"}, "network.fixtures.http")
    port = _port(value.get("port", 80), "network.fixtures.http.port")
    routes = value.get("routes", [])
    if not isinstance(routes, list) or not 1 <= len(routes) <= MAX_ROUTES:
        raise _bad(f"network.fixtures.http.routes must have 1-{MAX_ROUTES} entries")
    parsed, seen = [], set()
    for index, route in enumerate(routes):
        field = f"network.fixtures.http.routes[{index}]"
        if not isinstance(route, dict):
            raise _bad(f"{field} must be an object")
        _only(route, {"method", "path", "status", "body", "content_type"}, field)
        method = route.get("method", "GET")
        path = route.get("path")
        status = route.get("status", 200)
        body = route.get("body", "")
        content_type = route.get("content_type", "text/plain")
        if method not in ("GET", "POST", "PUT", "DELETE", "HEAD"):
            raise _bad(f"{field}.method is unsupported")
        if not isinstance(path, str) or not _PATH.match(path):
            raise _bad(f"{field}.path must be an absolute printable path")
        if type(status) is not int or not 100 <= status <= 599:
            raise _bad(f"{field}.status must be an HTTP status")
        if not isinstance(body, str) or len(body.encode()) > MAX_BODY:
            raise _bad(f"{field}.body must be at most {MAX_BODY} bytes")
        if not isinstance(content_type, str) or not re.fullmatch(r"[\x21-\x7e ]{1,100}", content_type):
            raise _bad(f"{field}.content_type is invalid")
        if (method, path) in seen:
            raise _bad(f"{field} duplicates {method} {path}")
        seen.add((method, path))
        parsed.append({"method": method, "path": path, "status": status,
                       "body": body, "content_type": content_type})
    return {"port": port, "routes": parsed}


def _exchange(value: object, field: str, default_port: int) -> dict:
    if not isinstance(value, dict):
        raise _bad(f"{field} must be an object")
    _only(value, {"port", "request_hex", "response_hex"}, field)
    return {"port": _port(value.get("port", default_port), f"{field}.port"),
            "request_hex": _hex(value.get("request_hex"), f"{field}.request_hex"),
            "response_hex": _hex(value.get("response_hex"), f"{field}.response_hex")}


def _mqtt(value: object) -> dict:
    if value is True:
        value = {}
    if not isinstance(value, dict):
        raise _bad("network.fixtures.mqtt must be true or an object")
    _only(value, {"port", "topics"}, "network.fixtures.mqtt")
    topics = value.get("topics", ["#"])
    if (not isinstance(topics, list) or not 1 <= len(topics) <= 16
            or any(not isinstance(t, str) or not _TOPIC.match(t) for t in topics)):
        raise _bad("network.fixtures.mqtt.topics must list 1-16 topic filters")
    return {"port": _port(value.get("port", 1883), "network.fixtures.mqtt.port"), "topics": topics}


def _setup_inputs(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_SETUP:
        raise _bad(f"network.setup_inputs must have at most {MAX_SETUP} entries")
    steps = []
    for index, step in enumerate(value):
        field = f"network.setup_inputs[{index}]"
        if not isinstance(step, dict) or step.get("kind") not in SETUP_KINDS:
            raise _bad(f"{field}.kind must be one of {', '.join(SETUP_KINDS)}")
        if step["kind"] == "wait":
            _only(step, {"kind", "seconds", "serial_marker"}, field)
            seconds = step.get("seconds", 1)
            marker = step.get("serial_marker")
            if type(seconds) not in (int, float) or not 0 < seconds <= 60:
                raise _bad(f"{field}.seconds must be within (0, 60]")
            if marker is not None and (not isinstance(marker, str) or not 1 <= len(marker) <= 200):
                raise _bad(f"{field}.serial_marker must be a short string")
            steps.append({"kind": "wait", "seconds": float(seconds),
                          **({"serial_marker": marker} if marker else {})})
        else:
            # Board-specific fields are validated by the same input path used
            # for /input at execution time, against the running guest.
            steps.append(dict(step))
    return steps


def _assertions(value: object, fixtures: dict) -> list[dict]:
    if value is None:
        value = [{"type": "wifi_auth"}, {"type": "dhcp_lease"}]
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ASSERTIONS:
        raise _bad(f"network.assertions must have 1-{MAX_ASSERTIONS} entries")
    parsed = []
    for index, item in enumerate(value):
        field = f"network.assertions[{index}]"
        if not isinstance(item, dict) or item.get("type") not in ASSERTION_TYPES:
            raise _bad(f"{field}.type must be one of {', '.join(ASSERTION_TYPES)}")
        kind = item["type"]
        allowed = {"type"} | {
            "dns_query": {"name"}, "tcp_connect": {"port"}, "udp_exchange": {"port"},
            "http_request": {"method", "path", "status"}, "mqtt_publish": {"topic"},
        }.get(kind, set())
        _only(item, allowed, field)
        row = {"type": kind}
        if "name" in item:
            row["name"] = _hostname(item["name"], f"{field}.name")
        if "port" in item:
            row["port"] = _port(item["port"], f"{field}.port")
        if "method" in item:
            if item["method"] not in ("GET", "POST", "PUT", "DELETE", "HEAD"):
                raise _bad(f"{field}.method is unsupported")
            row["method"] = item["method"]
        if "path" in item:
            if not isinstance(item["path"], str) or not _PATH.match(item["path"]):
                raise _bad(f"{field}.path must be an absolute printable path")
            row["path"] = item["path"]
        if "status" in item:
            if type(item["status"]) is not int or not 100 <= item["status"] <= 599:
                raise _bad(f"{field}.status must be an HTTP status")
            row["status"] = item["status"]
        if "topic" in item:
            if not isinstance(item["topic"], str) or not _TOPIC.match(item["topic"]):
                raise _bad(f"{field}.topic is invalid")
            row["topic"] = item["topic"]
        needs = {"dns_query": "dns", "http_request": "http", "udp_exchange": "udp",
                 "mqtt_connect": "mqtt", "mqtt_publish": "mqtt"}.get(kind)
        if needs and needs not in fixtures:
            raise _bad(f"{field} requires network.fixtures.{needs}")
        parsed.append(row)
    return parsed


def parse_review_sta(value: dict, *, nic: str) -> dict:
    allowed = {"profile", "ssid", "password", "security", "wifi_ssid", "wifi_password", "wifi_auth",
               "fixtures", "setup_inputs", "assertions", "timeout_seconds", "capture_pcap", "network_code"}
    _only(value, allowed, "network")
    ssid = value.get("ssid", value.get("wifi_ssid", "M5-REVIEW"))
    security = value.get("security", value.get("wifi_auth", "open"))
    password = value.get("password", value.get("wifi_password", ""))
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32:
        raise _bad("network.ssid must be 1-32 bytes")
    if security not in SECURITIES:
        raise ServiceError("unsupported_wifi_security", "review-sta supports open or wpa2-psk", 409)
    if security == "wpa2-psk":
        if not isinstance(password, str) or not 8 <= len(password.encode()) <= 63:
            raise _bad("network.password must be 8-63 bytes for wpa2-psk")
    else:
        password = ""
    if value.get("capture_pcap", True) is not True:
        raise _bad("review-sta always captures pcap; capture_pcap must be true")
    timeout = value.get("timeout_seconds", 90)
    if type(timeout) not in (int, float) or not 10 <= timeout <= 300:
        raise _bad("network.timeout_seconds must be between 10 and 300")
    network_code = value.get("network_code", "unknown")
    if network_code not in ("unknown", "present", "absent"):
        raise _bad("network.network_code must be unknown, present or absent")
    raw = value.get("fixtures", {"dhcp": True})
    if not isinstance(raw, dict):
        raise _bad("network.fixtures must be an object")
    _only(raw, set(FIXTURE_KINDS), "network.fixtures")
    if raw.get("dhcp", True) is not True:
        raise ServiceError("fixture_rejected", "review-sta requires the DHCP fixture", 400)
    fixtures: dict = {"dhcp": True}
    if "dns" in raw:
        fixtures["dns"] = _dns(raw["dns"])
    if "http" in raw:
        fixtures["http"] = _http(raw["http"])
    if "tcp" in raw:
        fixtures["tcp"] = _exchange(raw["tcp"], "network.fixtures.tcp", 19193)
    if "udp" in raw:
        fixtures["udp"] = _exchange(raw["udp"], "network.fixtures.udp", 19090)
        if fixtures["udp"]["port"] in (53, 67, 68):
            raise ServiceError("fixture_rejected", "UDP fixture port collides with DHCP/DNS", 400)
    if "mqtt" in raw:
        fixtures["mqtt"] = _mqtt(raw["mqtt"])
    tcp_ports = [fixtures[k]["port"] for k in ("http", "tcp", "mqtt") if k in fixtures]
    if len(tcp_ports) != len(set(tcp_ports)):
        raise ServiceError("fixture_rejected", "TCP fixtures must use distinct ports", 400)
    return {
        "profile": PROFILE, "net_mode": "unix-socketpair", "nic": nic,
        "capture_pcap": True, "http_fixture": False,
        "wifi_ssid": ssid, "wifi_password": password, "wifi_auth": security,
        "fixtures": fixtures, "setup_inputs": _setup_inputs(value.get("setup_inputs")),
        "assertions": _assertions(value.get("assertions"), fixtures),
        "timeout_seconds": float(timeout), "network_code": network_code,
        "isolation": ISOLATION, "host_egress": "deny",
    }


def capability(spec, *, backend_ready: bool) -> dict:
    """Stable, review-facing network capability for one device (#238)."""
    nic = board_nic(spec) if backend_ready and spec.supported else None
    base = {"schema_version": 1, "external_dependencies": EXTERNAL_DEPENDENCIES}
    if nic is None:
        reason = ("backend_unavailable" if spec.supported and not backend_ready and spec.id in BOARDS
                  else "no_review_sta_model")
        return {**base, "network": "unsupported", "review_sta": None, "reason": reason}
    return {**base, "network": "supported", "review_sta": {
        "runtime": "qemu-wifi", "profile": PROFILE, "nic": nic,
        "network_isolation": ISOLATION, "host_egress": "deny",
        "requires_linux_namespace": False, "pcap": True,
        "security": list(SECURITIES), "fixtures": list(FIXTURE_KINDS),
        "setup_input_kinds": list(SETUP_KINDS), "assertion_types": list(ASSERTION_TYPES),
        "gateway": str(GATEWAY), "lease": str(LEASE),
        "max_timeout_seconds": 300, "statuses": ["PASS", "FAIL", "PARTIAL", "NOT_USED"],
        "failure_codes": ["wifi_auth_failed", "dhcp_timeout", "dns_failed", "tcp_refused",
                          "http_status", "no_network_activity", "wifi_scan_only", "fixture_rejected",
                          "host_egress_denied"],
    }}

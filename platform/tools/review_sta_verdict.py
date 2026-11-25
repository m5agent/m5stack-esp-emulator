"""Turn review-sta peer events, AP trace and pcap into a stable verdict.

Status semantics (#238):
- PASS: every required assertion was observed.
- FAIL: an explicit network failure (auth, DHCP, DNS, TCP, HTTP, fixture).
- PARTIAL: the Wi-Fi driver ran (or only scanned) but the station never joined.
- NOT_USED: the window closed with no station activity and the controller saw
  no driver initialisation (`wifi_initialized` false), or the image has no
  Wi-Fi stack. `reason` says which; the reviewer decides whether an unused
  network is acceptable for the claim.
- RUNNING: the window is still open and no verdict is final yet.
"""
from __future__ import annotations

import ipaddress
import re

from review_sta_config import GATEWAY, LEASE

FAILURE_CODES = (
    "wifi_auth_failed", "dhcp_timeout", "dns_failed", "tcp_refused", "http_status",
    "fixture_rejected", "host_egress_denied", "no_network_activity", "wifi_scan_only",
)
_TRACE = re.compile(r"\[esp32s3-wifi\] WPA: (.*)")
_AUTH_FAIL = ("EAPOL 2/4 MIC mismatch", "EAPOL 4/4 MIC mismatch")
_AUTH_OK = "WPA2-PSK ready"
# Signatures of an ESP-IDF / Arduino Wi-Fi stack in the application image.
WIFI_STACK_SIGNATURES = (b"net80211", b"wifi firmware version", b"esp_wifi_init", b"wpa_supplicant")


def firmware_has_wifi_stack(image: bytes) -> bool:
    return any(signature in image for signature in WIFI_STACK_SIGNATURES)


def wifi_auth_events(stderr_text: str, security: str, leased: bool) -> list[dict]:
    """Derive auth events from the controller's WPA trace, never from guest text."""
    lines = [m.group(1) for m in _TRACE.finditer(stderr_text)]
    events = []
    failures = sum(any(sig in line for sig in _AUTH_FAIL) for line in lines)
    if security == "wpa2-psk":
        if any(_AUTH_OK in line for line in lines):
            events.append({"type": "wifi_auth", "security": security, "status": "PASS",
                           "source": "controller-wpa-trace"})
        if failures:
            events.append({"type": "wifi_auth", "security": security, "status": "FAIL",
                           "code": "wifi_auth_failed", "reason": "EAPOL MIC mismatch",
                           "attempts": failures, "source": "controller-wpa-trace"})
    elif leased:
        # Open networks have no handshake; a lease on the controller path is
        # the first proof that association completed.
        events.append({"type": "wifi_auth", "security": "open", "status": "PASS",
                       "source": "dhcp-after-association"})
    return events


def radio_events(stdout_text: str) -> list[dict]:
    """Station management requests the AP model actually received."""
    events = []
    probes = stdout_text.count("QEMU: Received probe request!")
    auths = stdout_text.count("QEMU: Received authentication request!")
    assocs = stdout_text.count("QEMU: Received association request!")
    if probes:
        events.append({"type": "wifi_scan", "probe_requests": probes, "status": "OBSERVED",
                       "source": "controller-ap-model"})
    if auths or assocs:
        events.append({"type": "wifi_assoc", "auth_requests": auths, "assoc_requests": assocs,
                       "status": "OBSERVED", "source": "controller-ap-model"})
    return events


# Controller trace lines that only appear after the guest driver programmed
# the Wi-Fi MAC DMA rings (ESP32-S3 NIC, `M5SW_S3_WIFI_TRACE`). They come from
# the NIC model, never from guest serial text or image strings.
DRIVER_MARKERS = ("[esp32s3-wifi] RX DMA base=", "[esp32s3-wifi] TX DMA outlink=")


def _matches(assertion: dict, event: dict) -> bool:
    kind = assertion["type"]
    if kind == "wifi_auth":
        return event["type"] == "wifi_auth"
    if kind == "dhcp_lease":
        return event["type"] == "dhcp_lease"
    if kind == "dns_query":
        return event["type"] == "dns_query" and event.get("name") == assertion.get("name", event.get("name"))
    if kind == "tcp_connect":
        port = assertion.get("port")
        return event["type"] == "tcp_connect" and (port is None or event.get("dst") == f"{GATEWAY}:{port}")
    if kind == "udp_exchange":
        port = assertion.get("port")
        return event["type"] == "udp_exchange" and (port is None or event.get("dst") == f"{GATEWAY}:{port}")
    if kind == "http_request":
        return (event["type"] == "http_request"
                and all(event.get(k) == assertion[k] for k in ("method", "path") if k in assertion))
    if kind == "mqtt_connect":
        return event["type"] == "mqtt_connect"
    if kind == "mqtt_publish":
        return event["type"] == "mqtt_publish" and event.get("topic") == assertion.get("topic", event.get("topic"))
    return False


def _event_passed(assertion: dict, event: dict) -> bool:
    if assertion["type"] == "http_request":
        expected = assertion.get("status")
        return event.get("result") == "PASS" and (expected is None or event.get("status") == expected)
    return event.get("status") == "PASS"


def _host(endpoint) -> str | None:
    if not isinstance(endpoint, str):
        return None
    return endpoint.rpartition(":")[0] if endpoint.count(":") == 1 else endpoint


def _pcap_isolation(capture: dict) -> dict:
    """Station traffic must stay between the lease and the fixture gateway.

    The capture also sees frames the guest emits on its own behalf, for
    example a firmware SoftAP (192.168.4.1) announcing mDNS. Those never leave
    the socketpair and are reported as `guest_local`, not as egress. Only a
    unicast destination outside the fixture, reached from the station lease
    or the gateway, counts against isolation.
    """
    if capture.get("status") != "PASS" or not isinstance(capture.get("flows"), list):
        return {"status": "UNAVAILABLE"}
    station = {str(GATEWAY), str(LEASE)}
    outside, guest_local = set(), set()
    for flow in capture["flows"]:
        source, destination = _host(flow.get("source")), _host(flow.get("destination"))
        if source is None or destination is None:
            continue
        try:
            dst = ipaddress.IPv4Address(destination)
            src = ipaddress.IPv4Address(source)
        except ValueError:
            continue
        broadcast = (dst.is_multicast or destination == "255.255.255.255" or src.is_unspecified
                     or dst.is_unspecified)
        if source in station and not broadcast and destination not in station:
            outside.add(destination)
        elif destination in station and source not in station and not src.is_unspecified:
            outside.add(source)
        elif source not in station and not src.is_unspecified:
            guest_local.add(source)
    return {"status": "PASS" if not outside else "FAIL",
            "flows": len(capture["flows"]), "non_fixture_addresses": sorted(outside)[:16],
            "guest_local_sources": sorted(guest_local)[:16],
            "capture_sha256": (capture.get("input") or {}).get("sha256")}


def evaluate(config: dict, peer: dict, *, stderr_text: str, capture: dict,
             window_closed: bool, firmware_wifi_stack: bool | None, stdout_text: str = "",
             wifi_initialized: bool | None = None) -> dict:
    events = [dict(e) for e in peer.get("events", []) if isinstance(e, dict)]
    leased = any(e["type"] == "dhcp_lease" for e in events)
    auth = wifi_auth_events(stderr_text, config["wifi_auth"], leased)
    radio = radio_events(stdout_text)
    events = radio + auth + events
    joined = any(e["type"] == "wifi_assoc" for e in radio)
    scanned_only = bool(radio) and not joined
    attempted = bool(auth) or joined or any(
        e["type"] not in ("setup_input", "wifi_scan") for e in events)
    rows, failures, reason = [], [], None
    if radio and wifi_initialized is False:
        # A management frame reached the AP model, so the driver did run.
        wifi_initialized = True
    for assertion in config["assertions"]:
        matched = [e for e in events if _matches(assertion, e)]
        passed = [e for e in matched if _event_passed(assertion, e)]
        if passed:
            rows.append({**assertion, "status": "PASS", "observed": len(passed)})
        elif matched:
            code = next((e.get("code") for e in matched if e.get("code")), "fixture_rejected")
            rows.append({**assertion, "status": "FAIL", "code": code, "observed": len(matched)})
            failures.append(code)
        else:
            rows.append({**assertion, "status": "PENDING" if not window_closed else "NOT_OBSERVED"})
    auth_failed = any(e["type"] == "wifi_auth" and e["status"] == "FAIL" for e in events) and not leased
    if auth_failed and "wifi_auth_failed" not in failures:
        failures.insert(0, "wifi_auth_failed")
    egress_denied = any(e["type"] == "egress_denied" for e in events)
    isolation = _pcap_isolation(capture)
    if isolation["status"] == "FAIL" or egress_denied:
        failures.append("host_egress_denied")
    if window_closed and attempted and not leased and not auth_failed:
        failures.append("dhcp_timeout")
    for row in rows:
        if row["status"] == "NOT_OBSERVED" and attempted and leased:
            row["status"] = "FAIL"
            row["code"] = {"dns_query": "dns_failed", "http_request": "http_status",
                           "tcp_connect": "tcp_refused"}.get(row["type"], "fixture_rejected")
            failures.append(row["code"])
    if all(row["status"] == "PASS" for row in rows) and not failures:
        status = "PASS"
    elif failures and (window_closed or auth_failed or egress_denied
                       or any(r["status"] == "FAIL" for r in rows)):
        status = "FAIL"
    elif not window_closed:
        status = "RUNNING"
    elif not attempted:
        # `wifi_initialized` is True/False when the NIC trace was observable and
        # None when this NIC has no driver-level signal (classic ESP32).
        if firmware_wifi_stack is False or config.get("network_code") == "absent":
            status, reason = "NOT_USED", "no_wifi_stack"
        elif wifi_initialized is False:
            status, reason = "NOT_USED", "wifi_not_initialized"
        else:
            status, reason = "PARTIAL", None
    else:
        status = "FAIL"
    codes = list(dict.fromkeys(failures))
    if status == "NOT_USED" and reason is None:
        reason = "no_wifi_stack"
    if status == "PARTIAL" and not scanned_only and wifi_initialized:
        reason = "wifi_initialized_no_scan"
    if status == "PARTIAL":
        # A scan without a join usually means the firmware found no saved or
        # matching network and is waiting for user setup.
        codes = ["no_network_activity"] + (["wifi_scan_only"] if scanned_only else [])
    data_plane = ("PASS" if leased and status == "PASS" else
                  "FAIL" if status == "FAIL" else
                  "NOT_USED" if status == "NOT_USED" else "PARTIAL")
    # What the firmware tried to reach beyond the fixture. A review can record
    # these as external dependencies; they are never served or forwarded.
    external = {
        "dns_names": sorted({e.get("name") for e in events
                             if e["type"] == "dns_query" and e.get("code") == "dns_failed" and e.get("name")})[:32],
        "destinations": sorted({e.get("dst") for e in events
                                if e["type"] == "egress_denied" and e.get("dst")})[:32],
    }
    return {"status": status, "data_plane": data_plane, "failure_codes": codes,
            "external_requests": external, "station_joined": leased,
            "wifi_initialized": wifi_initialized, "reason": reason,
            "events": events, "assertions": rows, "pcap_isolation": isolation,
            "ipv4": str(LEASE) if leased else None,
            "firmware_wifi_stack": firmware_wifi_stack}

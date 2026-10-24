#!/usr/bin/env python3
"""Prove that the public OpenAI sample requires an external NVS config."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "platform/tools"

sys.path.insert(0, str(TOOLS))

from fetch_firmware import resolve_community_firmware  # noqa: E402
from firmware_analysis import analyze_firmware  # noqa: E402
from nvs_image import create_string_nvs_image  # noqa: E402
from user_firmware_matrix import ServiceClient  # noqa: E402

FIRMWARE_ID = "1897200000000000358"
DEVICE_ID = "atoms3r"
PUBLIC_VERSION = "v1.0"
EXPECTED_SOURCE_SHA256 = (
    "b3597fcabbff57c98618caa8754af84745e9eac35b2868ab3c4cb0935b7c59b3"
)
OPEN_NVS_SHA256 = (
    "14f0acc47e1e1bef7e19d29c90febd0fe3707599fd8fc42eeb14dd27cfc26e5d"
)
SECURE_NVS_SHA256 = (
    "ab16f2a1842e40addce0ba26209595fef98d1b3f31113512375d5cfad70fe2bd"
)
WRONG_NVS_SHA256 = (
    "444486b388235e5f4bcf8c6e34590d78ebcf19baf1cff521fbf593ddeb41dddf"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_nvs_partition(analysis: dict, label: str = "nvs") -> dict:
    partitions = analysis.get("partition_table", {}).get("partitions", [])
    partition = next(
        (
            row
            for row in partitions
            if row.get("type") == 1
            and row.get("subtype") == 2
            and row.get("label") == label
        ),
        None,
    )
    if not isinstance(partition, dict):
        raise RuntimeError(f"firmware has no NVS partition {label!r}")
    return partition


def wait_for_session(
    client: ServiceClient,
    session_id: str,
    *,
    timeout: float,
) -> tuple[dict, list[str]]:
    states: list[str] = []
    deadline = time.monotonic() + timeout
    snapshot: dict[str, Any] = {}
    while time.monotonic() < deadline:
        snapshot = client.get(f"sessions/{session_id}")
        state = str(snapshot.get("state") or "")
        if not states or states[-1] != state:
            states.append(state)
        if state in {"running", "failed", "stopped"}:
            return snapshot, states
        time.sleep(0.2)
    return snapshot, states


def serial_text(client: ServiceClient, session_id: str) -> str:
    payload = client.get(
        f"sessions/{session_id}/serial?offset=0&limit=65536"
    )
    return str(payload.get("data") or "")


def pcap_facts(network: dict) -> dict:
    capture = network.get("packet_capture")
    capture = capture if isinstance(capture, dict) else {}
    dns = capture.get("dns")
    dns = dns if isinstance(dns, dict) else {}
    flows = capture.get("flows")
    flows = flows if isinstance(flows, list) else []
    return {
        "packets": capture.get("packets"),
        "dns_queries": list(dns.get("queries") or []),
        "tcp_443_flows": sum(
            1
            for flow in flows
            if isinstance(flow, dict)
            and flow.get("protocol") == "TCP"
            and str(flow.get("destination") or "").endswith(":443")
        ),
        "capture_sha256": (capture.get("input") or {}).get("sha256"),
    }


def run_case(
    client: ServiceClient,
    *,
    firmware_id: str,
    fixture_path: Path,
    name: str,
    ready_marker: str,
    timeout: float,
    qemu_wifi_auth: str,
    qemu_wifi_password: str,
    observe_after_running: float = 0.0,
) -> dict:
    fixture = client.upload(fixture_path, fixture_path.name)
    created = client.post(
        "sessions",
        {
            "device_id": DEVICE_ID,
            "firmware_id": firmware_id,
            "runtime": "qemu-wifi",
            "ttl_seconds": 180,
            "ready_timeout_seconds": timeout,
            "ready_marker": ready_marker,
            "network": {
                "profile": "generic-observe",
                "expected_markers": [ready_marker],
                "attempts": 1,
                "capture_pcap": True,
                "wifi_ssid": "myssid",
                "wifi_password": qemu_wifi_password,
                "wifi_auth": qemu_wifi_auth,
            },
            "nvs": {
                "partition_label": "nvs",
                "image_artifact_id": fixture["artifact_id"],
            },
        },
    )
    session_id = str(created["session_id"])
    try:
        snapshot, states = wait_for_session(
            client,
            session_id,
            timeout=timeout + 15,
        )
        if (
            observe_after_running > 0
            and snapshot.get("state") == "running"
        ):
            time.sleep(observe_after_running)
        serial = serial_text(client, session_id)
        stopped = client.delete(f"sessions/{session_id}?purge=0")
        final = client.get(f"sessions/{session_id}")
        final_serial = serial_text(client, session_id)
        if final_serial:
            serial = final_serial
        logs = client.get(
            f"sessions/{session_id}/logs?offset=0&limit=1048576"
        )
        qemu_stderr = str(logs.get("qemu_stderr") or "")
        network = final.get("network")
        network = network if isinstance(network, dict) else {}
        return {
            "name": name,
            "session_id": session_id,
            "fixture_sha256": fixture["sha256"],
            "states": states,
            "reached_running": "running" in states,
            "final_state": final.get("state"),
            "final_error": final.get("error"),
            "nvs": final.get("nvs"),
            "flash": final.get("flash"),
            "serial_bytes": len(serial.encode()),
            "serial_sha256": sha256_bytes(serial.encode()),
            "qemu_stderr_bytes": len(qemu_stderr.encode()),
            "qemu_stderr_sha256": sha256_bytes(qemu_stderr.encode()),
            "markers": {
                marker: marker in serial
                for marker in (
                    "NVS: WiFi SSID: myssid",
                    "NVS: OpenAI Key: test-openai-key-not-secret",
                    "authmode threshold changes from OPEN to WPA2",
                    "retry to connect to the AP",
                    "wifi:connected with myssid",
                    "got ip:",
                    "Error perform http request",
                )
            },
            "runtime_markers": {
                marker: marker in qemu_stderr
                for marker in (
                    "EAPOL 1/4 sent",
                    "EAPOL 2/4 verified",
                    "EAPOL 3/4 sent",
                    "EAPOL 4/4 verified; WPA2-PSK ready",
                    "EAPOL 2/4 MIC mismatch",
                    "deauthenticate station reason=15",
                    "CCMP RX decrypted",
                )
            },
            "network_status": network.get("status"),
            "network_checks": network.get("checks"),
            "pcap": pcap_facts(network),
            "stop_state": stopped.get("state"),
        }
    finally:
        try:
            current = client.get(f"sessions/{session_id}")
            if current.get("state") not in {"stopped", "failed"}:
                client.delete(f"sessions/{session_id}?purge=0")
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--service-url",
        default="http://127.0.0.1:8787",
    )
    parser.add_argument("--firmware", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.cache_dir or args.out_dir / "cache"
    firmware_path = args.firmware
    download = None
    if firmware_path is None:
        destination = (
            cache_dir / "community" / f"{FIRMWARE_ID}.bin"
        )
        download = resolve_community_firmware(
            FIRMWARE_ID,
            destination,
            api_base="https://burner.m5stack.com",
            device_slug=DEVICE_ID,
            force=True,
            analyze=False,
            expected_chip_id_value=None,
        )
        firmware_path = destination
    firmware_data = firmware_path.read_bytes()
    firmware_sha = sha256_bytes(firmware_data)
    if firmware_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            f"OpenAI firmware bytes changed: {firmware_sha}"
        )
    analysis = analyze_firmware(firmware_path, expected_chip_id_value=0x9)
    partition = find_nvs_partition(analysis)
    nvs_offset = int(partition["offset"])
    nvs_size = int(partition["size"])
    blank_nvs = firmware_data[nvs_offset : nvs_offset + nvs_size]
    if blank_nvs != b"\xff" * nvs_size:
        raise RuntimeError("public firmware NVS partition is not erased")

    open_fixture = args.out_dir / "open-qemu-ap.nvs.bin"
    secure_fixture = args.out_dir / "wpa2-qemu-ap.nvs.bin"
    wrong_fixture = args.out_dir / "wrong-password.nvs.bin"
    create_string_nvs_image(
        open_fixture,
        partition_size=nvs_size,
        namespaces={
            "config": {
                "wifi_ssid": "myssid",
                "wifi_password": "",
                "openaikey": "test-openai-key-not-secret",
            }
        },
    )
    create_string_nvs_image(
        secure_fixture,
        partition_size=nvs_size,
        namespaces={
            "config": {
                "wifi_ssid": "myssid",
                "wifi_password": "mypassword",
                "openaikey": "test-openai-key-not-secret",
            }
        },
    )
    create_string_nvs_image(
        wrong_fixture,
        partition_size=nvs_size,
        namespaces={
            "config": {
                "wifi_ssid": "myssid",
                "wifi_password": "wrongpass",
                "openaikey": "test-openai-key-not-secret",
            }
        },
    )
    open_sha = sha256_bytes(open_fixture.read_bytes())
    secure_sha = sha256_bytes(secure_fixture.read_bytes())
    wrong_sha = sha256_bytes(wrong_fixture.read_bytes())
    if (
        open_sha != OPEN_NVS_SHA256
        or secure_sha != SECURE_NVS_SHA256
        or wrong_sha != WRONG_NVS_SHA256
    ):
        raise RuntimeError("NVS fixture encoder output changed")

    client = ServiceClient(args.service_url, timeout=120)
    base = client.upload(firmware_path, f"{DEVICE_ID}-{FIRMWARE_ID}.bin")
    firmware = client.post(
        "firmware",
        {
            "device_id": DEVICE_ID,
            "kind": "merged",
            "artifact_id": base["artifact_id"],
        },
    )
    secure = run_case(
        client,
        firmware_id=firmware["firmware_id"],
        fixture_path=secure_fixture,
        name="wpa2-fixture-against-qemu-wpa2-ap",
        ready_marker="got ip:",
        timeout=30,
        qemu_wifi_auth="wpa2-psk",
        qemu_wifi_password="mypassword",
        observe_after_running=8,
    )
    wrong = run_case(
        client,
        firmware_id=firmware["firmware_id"],
        fixture_path=wrong_fixture,
        name="wrong-password-rejected-by-qemu-wpa2-ap",
        ready_marker="retry to connect to the AP",
        timeout=20,
        qemu_wifi_auth="wpa2-psk",
        qemu_wifi_password="mypassword",
        observe_after_running=3,
    )
    open_run = run_case(
        client,
        firmware_id=firmware["firmware_id"],
        fixture_path=open_fixture,
        name="open-fixture-against-open-qemu-ap",
        ready_marker="got ip:",
        timeout=30,
        qemu_wifi_auth="open",
        qemu_wifi_password="",
        observe_after_running=8,
    )

    dns_queries = open_run["pcap"]["dns_queries"]
    secure_dns_queries = secure["pcap"]["dns_queries"]
    checks = {
        "source_sha_binding": firmware_sha == EXPECTED_SOURCE_SHA256,
        "nvs_partition_is_blank_in_public_binary": (
            blank_nvs == b"\xff" * nvs_size
        ),
        "fixture_encoder_matches_esp_idf_generator": (
            open_sha == OPEN_NVS_SHA256
            and secure_sha == SECURE_NVS_SHA256
            and wrong_sha == WRONG_NVS_SHA256
        ),
        "secure_fixture_loads_nvs_config": secure["markers"][
            "NVS: WiFi SSID: myssid"
        ],
        "secure_fixture_exposes_wpa2_threshold": secure["markers"][
            "authmode threshold changes from OPEN to WPA2"
        ],
        "secure_fixture_completes_4_way_handshake": all(
            secure["runtime_markers"][marker]
            for marker in (
                "EAPOL 1/4 sent",
                "EAPOL 2/4 verified",
                "EAPOL 3/4 sent",
                "EAPOL 4/4 verified; WPA2-PSK ready",
            )
        ),
        "secure_fixture_associates": secure["markers"][
            "wifi:connected with myssid"
        ],
        "secure_fixture_reaches_dhcp": secure["markers"]["got ip:"],
        "secure_fixture_receives_ccmp_data": secure["runtime_markers"][
            "CCMP RX decrypted"
        ],
        "secure_fixture_resolves_api_openai_com": (
            "api.openai.com." in secure_dns_queries
        ),
        "secure_fixture_makes_tcp_443_attempt": (
            secure["pcap"]["tcp_443_flows"] > 0
        ),
        "secure_fixture_attempts_https": (
            secure["markers"]["Error perform http request"]
        ),
        "wrong_password_m2_mic_is_rejected": (
            wrong["runtime_markers"]["EAPOL 2/4 MIC mismatch"]
        ),
        "wrong_password_is_deauthenticated": (
            wrong["runtime_markers"]["deauthenticate station reason=15"]
        ),
        "wrong_password_retries_without_dhcp": (
            wrong["markers"]["retry to connect to the AP"]
            and not wrong["markers"]["wifi:connected with myssid"]
            and not wrong["markers"]["got ip:"]
        ),
        "open_fixture_loads_nvs_config": open_run["markers"][
            "NVS: WiFi SSID: myssid"
        ],
        "open_fixture_associates": open_run["markers"][
            "wifi:connected with myssid"
        ],
        "open_fixture_reaches_dhcp": open_run["markers"]["got ip:"],
        "open_fixture_resolves_api_openai_com": (
            "api.openai.com." in dns_queries
        ),
        "open_fixture_makes_tcp_443_attempt": (
            open_run["pcap"]["tcp_443_flows"] > 0
        ),
        "open_fixture_attempts_https": (
            open_run["markers"]["Error perform http request"]
        ),
        "session_isolated_nvs_overlay": all(
            isinstance(run["nvs"], dict)
            and run["nvs"].get("session_isolated_overlay") is True
            and run["nvs"].get("source_artifact_modified") is False
            and run["nvs"].get("base_flash_sha256")
            != run["nvs"].get("effective_flash_sha256")
            for run in (secure, wrong, open_run)
        ),
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-openai-first-boot-nvs-precondition",
        "date": "2026-10-25",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "functional_status": "PARTIAL",
        "scope": "virtual-device-validation-not-hardware",
        "source": {
            "firmware_id": FIRMWARE_ID,
            "name": "OpenAI Voice Assistant For AtomS3R",
            "version": PUBLIC_VERSION,
            "sha256": firmware_sha,
            "bytes": len(firmware_data),
            "download": download,
        },
        "nvs_partition": {
            "label": partition["label"],
            "offset": nvs_offset,
            "size": nvs_size,
            "public_binary_sha256": sha256_bytes(blank_nvs),
            "public_binary_erased": blank_nvs == b"\xff" * nvs_size,
        },
        "fixtures": {
            "open_qemu_ap": {
                "sha256": open_sha,
                "wifi_auth": "open",
            },
            "wpa2_qemu_ap": {
                "sha256": secure_sha,
                "wifi_auth": "wpa2-psk",
            },
            "wrong_password": {
                "sha256": wrong_sha,
                "wifi_auth": "wpa2-psk",
            },
            "values_are_synthetic": True,
        },
        "checks": checks,
        "secure_run": secure,
        "wrong_password_run": wrong,
        "open_run": open_run,
        "classification": {
            "nvs_precondition": (
                "CONFIRMED_EXTERNAL_CONFIGURATION_REQUIRED"
            ),
            "frame_result": (
                "NOT_APPLICABLE_TO_NVS_ROOT_CAUSE; the firmware does not "
                "provide a provisioning or error UI before network success"
            ),
            "qemu_wifi_security": (
                "PASS: WPA2-PSK 4-way handshake, pairwise CCMP RX, DHCP, "
                "DNS and TCP/443; wrong password fails at M2 MIC"
            ),
            "cloud_function": "NOT RUN: no real OpenAI credential is used",
        },
        "not_claimed": [
            "real OpenAI account or Realtime API session",
            "voice audio input/output or WebRTC media behavior",
            "WPA2/WPA3 association on physical hardware",
            "WPA2 group-key multicast delivery",
            "an on-device UI requirement",
            "physical hardware or RF validation",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

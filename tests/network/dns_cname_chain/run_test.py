#!/usr/bin/env python3
"""Exercise bounded CNAME chains in the controlled DNS fixture."""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import struct
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

import network_sandbox


def dns_query(name: str, qtype: int = 1) -> bytes:
    qname = (
        b"".join(
            bytes([len(label)]) + label.encode("ascii") for label in name.split(".")
        )
        + b"\0"
    )
    return (
        struct.pack("!HHHHHH", 0x5A17, 0x0100, 1, 0, 0, 0)
        + qname
        + struct.pack("!HH", qtype, 1)
    )


def udp_query(port: int, name: str, qtype: int) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(2)
        client.sendto(dns_query(name, qtype), ("127.0.0.1", port))
        response, _ = client.recvfrom(4096)
        return response


def expect_sandbox_error(
    label: str,
    *,
    records: dict,
    domain_records: dict,
    cname_records: dict,
    expected: str,
) -> dict:
    try:
        network_sandbox.ControlledDns(
            host="127.0.0.1",
            port=0,
            records=records,
            domain_records=domain_records,
            cname_records=cname_records,
            log_path=None,
        )
    except network_sandbox.SandboxError as error:
        message = str(error)
        return {
            "label": label,
            "status": "REJECTED",
            "error_match": expected in message,
            "error": message,
        }
    return {
        "label": label,
        "status": "UNEXPECTED_PASS",
        "error_match": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="m5-dns-cname-") as temporary:
        log_path = Path(temporary) / "dns.json"
        dns = network_sandbox.ControlledDns(
            host="127.0.0.1",
            port=0,
            records={
                "origin.example.test": "203.0.113.10",
            },
            domain_records={
                "service.example.test": "198.51.100.20",
            },
            cname_records={
                "api.example.test": "edge.example.test",
                "edge.example.test": "origin.example.test",
                "public.service.example.test": "origin.service.example.test",
            },
            log_path=log_path,
        )
        dns.start()
        port = dns.socket.getsockname()[1]
        try:
            address_response = udp_query(
                port,
                "api.example.test",
                1,
            )
            cname_response = udp_query(
                port,
                "api.example.test",
                5,
            )
            suffix_response = udp_query(
                port,
                "public.service.example.test",
                1,
            )
            denied_response = udp_query(
                port,
                "denied.example.test",
                1,
            )
        finally:
            dns.close()
        requests = json.loads(log_path.read_text())

    negatives = [
        expect_sandbox_error(
            "cycle",
            records={"origin.example.test": "203.0.113.10"},
            domain_records={},
            cname_records={
                "a.example.test": "b.example.test",
                "b.example.test": "a.example.test",
            },
            expected="cycle detected",
        ),
        expect_sandbox_error(
            "uncontrolled-terminal",
            records={"origin.example.test": "203.0.113.10"},
            domain_records={},
            cname_records={"alias.example.test": "outside-zone.test"},
            expected="uncontrolled name",
        ),
        expect_sandbox_error(
            "exact-owner-conflict",
            records={"same.example.test": "203.0.113.10"},
            domain_records={},
            cname_records={"same.example.test": "origin.example.test"},
            expected="conflicts with an exact A/AAAA record",
        ),
        expect_sandbox_error(
            "suffix-owner-conflict",
            records={},
            domain_records={"same.example.test": "203.0.113.10"},
            cname_records={"same.example.test": "origin.example.test"},
            expected="conflicts with a domain suffix answer",
        ),
    ]
    try:
        network_sandbox.validate_cname_record_bindings(
            {"escape.other.test": "origin.allowed.test"},
            exact_hosts=("origin.allowed.test",),
            allowed_hosts=("origin.allowed.test",),
            allowed_domains=("allowed.test",),
        )
    except network_sandbox.SandboxError as error:
        unauthorized_alias = {
            "status": "REJECTED",
            "error_match": "must be covered by" in str(error),
            "error": str(error),
        }
    else:
        unauthorized_alias = {
            "status": "UNEXPECTED_PASS",
            "error_match": False,
        }

    checks = {
        "a_query_includes_two_cnames_and_address": (
            struct.unpack_from("!H", address_response, 6)[0] == 3
            and str(ipaddress.ip_address(address_response[-4:])) == "203.0.113.10"
        ),
        "cname_query_returns_two_links": (
            struct.unpack_from("!H", cname_response, 6)[0] == 2
        ),
        "domain_suffix_terminal_resolves": (
            struct.unpack_from("!H", suffix_response, 6)[0] == 2
            and str(ipaddress.ip_address(suffix_response[-4:])) == "198.51.100.20"
            and requests[2].get("rule") == "suffix:service.example.test"
        ),
        "unknown_name_is_nxdomain": (
            struct.unpack_from("!H", denied_response, 6)[0] == 0
            and struct.unpack_from("!H", denied_response, 2)[0] & 0x000F == 3
        ),
        "log_records_chain_and_terminal": (
            requests[0].get("cname_terminal") == "origin.example.test"
            and len(requests[0].get("cname_chain", [])) == 2
        ),
        "cycle_rejected": negatives[0]["error_match"],
        "uncontrolled_terminal_rejected": negatives[1]["error_match"],
        "exact_owner_conflict_rejected": negatives[2]["error_match"],
        "suffix_owner_conflict_rejected": negatives[3]["error_match"],
        "unauthorized_alias_rejected": unauthorized_alias["error_match"],
    }
    evidence = {
        "schema_version": 1,
        "kind": "controlled-dns-cname-chain",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation": "resolver-data-plane validation",
        "fixture": {
            "exact_record": "origin.example.test",
            "exact_address": "203.0.113.10",
            "domain_suffix": "service.example.test",
            "cname": [
                "api.example.test -> edge.example.test",
                "edge.example.test -> origin.example.test",
            ],
            "suffix_cname": (
                "public.service.example.test -> origin.service.example.test"
            ),
        },
        "checks": checks,
        "dns_log": requests,
        "negative_cases": negatives + [unauthorized_alias],
        "not_claimed": [
            "guest firmware DNS lifecycle",
            "full Linux namespace isolation",
            "public DNS or DNSSEC",
            "DNS rebinding or malicious resolver safety",
            "physical RF or hardware validation",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

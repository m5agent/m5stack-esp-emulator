#!/usr/bin/env python3
"""Redacted static review helpers for normalized ESP firmware images."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

MAX_STRINGS = 200_000
MAX_STRING_LENGTH = 8_192
MAX_FINDINGS = 256
MAX_URLS = 256
MAX_ENCODED_BLOBS = 128
MAX_SBOM_BYTES = 8 << 20

URL_RE = re.compile(
    r"(?:https?|wss?|mqtts?|ftps?)://[^\s\"'<>]{1,2048}",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
BEARER_RE = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}",
    re.IGNORECASE,
)
CREDENTIAL_RE = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|password|passwd|secret)"
    r"\s*[:=]\s*[^\s\"']{8,}",
    re.IGNORECASE,
)
JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"(?:\.[A-Za-z0-9_-]{8,})?\b"
)
AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
BASE64_RE = re.compile(r"[A-Za-z0-9+/=_-]{48,4096}")
HEX_RE = re.compile(r"[0-9A-Fa-f]{64,4096}")


def _sha256(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def _entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def _extract_strings(data: bytes) -> tuple[list[tuple[int, str]], bool]:
    strings: list[tuple[int, str]] = []
    start = None
    truncated = False
    for index, byte in enumerate(data):
        printable = 0x20 <= byte <= 0x7E
        if printable:
            if start is None:
                start = index
            if index - start >= MAX_STRING_LENGTH:
                strings.append(
                    (start, data[start:index + 1].decode("ascii"))
                )
                start = None
        elif start is not None:
            if index - start >= 4:
                strings.append(
                    (start, data[start:index].decode("ascii"))
                )
            start = None
        if len(strings) >= MAX_STRINGS:
            truncated = True
            break
    if start is not None and len(data) - start >= 4:
        end = min(len(data), start + MAX_STRING_LENGTH)
        strings.append((start, data[start:end].decode("ascii")))
    return strings, truncated


def _sanitized_urls(
    strings: list[tuple[int, str]],
) -> tuple[list[dict], bool]:
    records: list[dict] = []
    seen: set[str] = set()
    truncated = False
    for string_offset, text in strings:
        for match in URL_RE.finditer(text):
            raw = match.group(0).rstrip(".,);]")
            parsed = urlsplit(raw)
            try:
                hostname = parsed.hostname
                port = parsed.port
            except ValueError:
                authority = parsed.netloc.rsplit("@", 1)[-1]
                if authority.startswith("[") and "]" in authority:
                    hostname = authority[1:authority.index("]")]
                else:
                    hostname = authority.rsplit(":", 1)[0]
                port = None
            if not hostname or "%" in hostname:
                continue
            digest = _sha256(raw)
            if digest in seen:
                continue
            seen.add(digest)
            record = {
                "scheme": parsed.scheme.lower(),
                "host": hostname.lower(),
                "url_sha256": digest,
                "path_sha256": _sha256(parsed.path or "/"),
                "offset": string_offset + match.start(),
                "length": len(raw),
            }
            if port is not None:
                record["port"] = port
            records.append(record)
            if len(records) >= MAX_URLS:
                truncated = True
                return records, truncated
    return records, truncated


def _credential_findings(
    strings: list[tuple[int, str]],
) -> tuple[list[dict], bool]:
    patterns = (
        ("private-key", "critical", PRIVATE_KEY_RE),
        ("bearer-token", "warning", BEARER_RE),
        ("credential-assignment", "warning", CREDENTIAL_RE),
        ("jwt", "warning", JWT_RE),
        ("aws-access-key", "critical", AWS_ACCESS_KEY_RE),
    )
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    truncated = False
    for string_offset, text in strings:
        for kind, severity, pattern in patterns:
            for match in pattern.finditer(text):
                evidence_hash = _sha256(match.group(0))
                key = (kind, evidence_hash)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "code": "credential_like_material",
                        "category": kind,
                        "severity": severity,
                        "message": (
                            "credential-like material detected; value is "
                            "redacted"
                        ),
                        "offset": string_offset + match.start(),
                        "evidence_sha256": evidence_hash,
                    }
                )
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    return findings, truncated
    return findings, truncated


def _encoded_blobs(
    strings: list[tuple[int, str]],
) -> tuple[list[dict], bool]:
    records: list[dict] = []
    seen: set[tuple[int, int]] = set()
    truncated = False
    for string_offset, text in strings:
        for match in BASE64_RE.finditer(text):
            token = match.group(0)
            if len(token) < 48 or "://" in text:
                continue
            if HEX_RE.fullmatch(token) and len(token) >= 64:
                encoding = "hex"
                threshold = 3.2
            elif any(char.isupper() for char in token) and any(
                char.islower() for char in token
            ) and any(char.isdigit() for char in token):
                encoding = "base64-like"
                threshold = 4.5
            else:
                continue
            entropy = _entropy(token)
            if entropy < threshold:
                continue
            key = (string_offset + match.start(), len(token))
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "encoding": encoding,
                    "entropy": round(entropy, 3),
                    "length": len(token),
                    "offset": key[0],
                    "sha256": _sha256(token),
                }
            )
            if len(records) >= MAX_ENCODED_BLOBS:
                truncated = True
                return records, truncated
    return records, truncated


def review_sbom(path: Path | None) -> dict:
    if path is None:
        return {
            "status": "NOT_PROVIDED",
            "format": None,
            "spec_version": None,
            "component_count": 0,
            "licenses": [],
        }
    if not path.is_file():
        return {
            "status": "INVALID",
            "format": None,
            "spec_version": None,
            "component_count": 0,
            "licenses": [],
            "errors": ["SBOM file does not exist"],
        }
    data = path.read_bytes()
    if len(data) > MAX_SBOM_BYTES:
        return {
            "status": "INVALID",
            "format": None,
            "spec_version": None,
            "component_count": 0,
            "licenses": [],
            "sha256": _sha256(data),
            "errors": [f"SBOM exceeds {MAX_SBOM_BYTES} bytes"],
        }
    try:
        document = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {
            "status": "INVALID",
            "format": None,
            "spec_version": None,
            "component_count": 0,
            "licenses": [],
            "sha256": _sha256(data),
            "errors": [f"invalid SBOM JSON: {error}"],
        }
    if not isinstance(document, dict):
        return {
            "status": "INVALID",
            "format": None,
            "spec_version": None,
            "component_count": 0,
            "licenses": [],
            "sha256": _sha256(data),
            "errors": ["SBOM root must be an object"],
        }
    licenses: set[str] = set()
    if "spdxVersion" in document:
        file_format = "spdx-json"
        spec_version = document.get("spdxVersion")
        packages = document.get("packages")
        components = packages if isinstance(packages, list) else []
        for package in components:
            if not isinstance(package, dict):
                continue
            for key in ("licenseDeclared", "licenseConcluded"):
                value = package.get(key)
                if isinstance(value, str) and value not in {"", "NOASSERTION"}:
                    licenses.add(value)
    elif document.get("bomFormat") == "CycloneDX":
        file_format = "cyclonedx-json"
        spec_version = document.get("specVersion")
        values = document.get("components")
        components = values if isinstance(values, list) else []
        for component in components:
            if not isinstance(component, dict):
                continue
            entries = component.get("licenses")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                license_value = entry.get("license") if isinstance(entry, dict) else None
                if isinstance(license_value, dict):
                    value = license_value.get("id") or license_value.get("name")
                    if isinstance(value, str) and value:
                        licenses.add(value)
    else:
        file_format = "generic-json"
        spec_version = None
        values = document.get("components") or document.get("packages")
        components = values if isinstance(values, list) else []
    return {
        "status": "PASS",
        "format": file_format,
        "spec_version": spec_version,
        "component_count": len(components),
        "licenses": sorted(licenses)[:128],
        "sha256": _sha256(data),
    }


def review_firmware(
    path: Path,
    *,
    sbom_path: Path | None = None,
) -> dict:
    data = path.read_bytes()
    strings, strings_truncated = _extract_strings(data)
    urls, urls_truncated = _sanitized_urls(strings)
    credentials, credentials_truncated = _credential_findings(strings)
    blobs, blobs_truncated = _encoded_blobs(strings)
    findings = list(credentials)
    for blob in blobs[:16]:
        findings.append(
            {
                "code": "high_entropy_encoded_blob",
                "category": blob["encoding"],
                "severity": "info",
                "message": (
                    "high-entropy encoded literal detected; value is redacted"
                ),
                "offset": blob["offset"],
                "evidence_sha256": blob["sha256"],
            }
        )
    review_required = bool(findings)
    return {
        "schema_version": 1,
        "status": "REVIEW_REQUIRED" if review_required else "CLEAN",
        "coverage": {
            "bytes_scanned": len(data),
            "strings_scanned": len(strings),
            "url_count": len(urls),
            "credential_finding_count": len(credentials),
            "encoded_blob_count": len(blobs),
        },
        "urls": urls,
        "encoded_blobs": blobs,
        "findings": findings[:MAX_FINDINGS],
        "sbom": review_sbom(sbom_path),
        "limits": {
            "strings_truncated": strings_truncated,
            "urls_truncated": urls_truncated,
            "credentials_truncated": credentials_truncated,
            "encoded_blobs_truncated": blobs_truncated,
            "findings_truncated": len(findings) > MAX_FINDINGS,
        },
    }

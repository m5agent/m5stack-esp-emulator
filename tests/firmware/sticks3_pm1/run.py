#!/usr/bin/env python3
"""Exercise the original StickS3 updater and the PM1-controlled ROM strap."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile


FIRMWARE_SHA = "35e5acdb0f6e503e0ddb65fc81b91d44ef0e10550aca87a945e9d3f0300582a4"
PM1_APP_SHA = "e3c8e94171384af2b8f946e430617b71848efc385d63041206b1a5f3f9024ec7"
PM1_APP_OFFSET = 0x107F8
PM1_APP_SIZE = 0x5000
FLASH_BOOT = "boot:0x4 (SPI_FLASH_BOOT)"
DOWNLOAD_BOOT = "boot:0x0 (DOWNLOAD(USB/UART0))"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def wait_for(check, description, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.25)
    raise TimeoutError(description)


def corrupt_pm1_crc(source):
    image = bytearray(source)
    # Change the inner image CRC. Preserve the outer ESP32-S3 checksum
    # and digest so the original guest continues to execute.
    image[PM1_APP_OFFSET + PM1_APP_SIZE - 1] ^= 1
    base = 0x10000
    pos = base + 24
    checksum = 0xef
    for _ in range(image[base + 1]):
        _, size = struct.unpack_from("<II", image, pos)
        pos += 8
        for byte in image[pos:pos + size]:
            checksum ^= byte
        pos += size
    end = (pos | 15) + 1
    image[end - 1] = checksum
    image[end:end + 32] = hashlib.sha256(image[base:end]).digest()
    return bytes(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, help="agent-owned loopback /api/v1 URL")
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--runtime-binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("iap", "bad-crc", "strap"), required=True)
    args = parser.parse_args()
    endpoint = urlsplit(args.service)
    require(endpoint.scheme == "http" and endpoint.hostname == "127.0.0.1"
            and endpoint.port not in {None, 8787, 8830} and endpoint.path == "/api/v1",
            "use an isolated loopback Device Service")
    token = os.environ["M5_SERVICE_API_TOKEN"]
    firmware = args.firmware.read_bytes()
    require(hashlib.sha256(firmware).hexdigest() == FIRMWARE_SHA, "unexpected stock firmware")
    payload = firmware[PM1_APP_OFFSET:PM1_APP_OFFSET + PM1_APP_SIZE]
    require(hashlib.sha256(payload).hexdigest() == PM1_APP_SHA, "unexpected inner PM1 app")
    if args.mode == "bad-crc":
        firmware = corrupt_pm1_crc(firmware)
    args.output_dir.mkdir(parents=True, exist_ok=False)

    def request(path, *, payload=None, binary=False, method=None):
        headers = {"Authorization": f"Bearer {token}"}
        if isinstance(payload, bytes):
            headers.update({"Content-Type": "application/octet-stream", "X-Artifact-Name": "sticks3-pm1.bin"})
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(payload).encode()
        req = Request(args.service + path, data=payload, headers=headers, method=method)
        with urlopen(req, timeout=60) as response:
            return response.read() if binary else json.load(response)

    artifact = request("/artifacts", payload=firmware)
    firmware_sha = hashlib.sha256(firmware).hexdigest()
    require(artifact["sha256"] == firmware_sha, "uploaded firmware digest mismatch")
    composed = request("/firmware", payload={
        "device_id": "sticks3", "kind": "merged", "artifact_id": artifact["artifact_id"],
    })
    session = request("/sessions", payload={
        "device_id": "sticks3", "firmware_id": composed["firmware_id"], "runtime": "qemu",
        "ttl_seconds": 600, "ready_timeout_seconds": 40,
        "runtime_env": {} if args.mode == "strap" else {"M5SW_USB_SERIAL_JTAG_CAPTURE": "1"},
    })
    route = "/sessions/" + session["session_id"]
    with args.runtime_binary.open("rb") as runtime:
        runtime_sha = hashlib.file_digest(runtime, "sha256").hexdigest()
    report = {"mode": args.mode, "source_firmware_sha256": firmware_sha, "runtime_sha256": runtime_sha}

    def serial():
        return request(route + "/serial?limit=262144")["data"]

    def prop(name):
        return request(route + f"/qom?path=/machine/m5pm1&property={name}")["value"]

    def key(name, action):
        result = request(route + "/input", payload={"kind": "key", "key": name, "action": action})
        require(result["accepted"], f"{name} {action} input rejected")

    def frame(name):
        data = request(route + "/frame.png", binary=True)
        (args.output_dir / f"{name}.png").write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    try:
        def ready():
            state = request(route)["state"]
            require(state not in {"failed", "stopped"}, f"guest {state}")
            return state == "running" and serial().count("Initialising I2C Master") >= 2

        wait_for(ready, "stock app I2C startup")
        time.sleep(1)
        report["before_frame"] = frame("before")
        require(prop("iap-upgrades") == 0 and prop("address") == 0x6e, "PM1 must start in application mode")
        if args.mode == "strap":
            key("p", "down")
            wait_for(lambda: prop("download-requested"), "PM1 long-press request", timeout=5)
            require(DOWNLOAD_BOOT not in serial(), "ROM started before button release")
            key("p", "up")
            wait_for(lambda: DOWNLOAD_BOOT in serial() and "waiting for download" in serial(),
                     "ESP32-S3 ROM downloader")
            report["download_frame"] = frame("download")
            time.sleep(1)
            key("p", "down")
            time.sleep(0.08)
            key("p", "up")
            wait_for(lambda: serial().count(FLASH_BOOT) >= 2
                     and serial().count("Initialising I2C Master") >= 4, "boot from Flash after short PWR press")
        else:
            key("a", "tap")
            wait_for(lambda: "Button A" in serial(), "original firmware A input")
            if args.mode == "bad-crc":
                wait_for(lambda: prop("iap-run-rejections") > 0, "bad inner CRC must reject RUN")
                require(prop("iap-active") and prop("address") == 0x54, "invalid image left bootloader")
                require(prop("iap-upgrades") == 0, "invalid image committed")
            else:
                wait_for(lambda: prop("iap-upgrades") == 1, "original firmware IAP completion")
                require(not prop("iap-active") and prop("address") == 0x6e, "bootloader did not return to PM1")
                require(prop("iap-app-sha256") == PM1_APP_SHA, "programmed PM1 app differs from stock payload")
            require(prop("iap-bytes-written") == PM1_APP_SIZE, "PM1 data transfer incomplete")
            time.sleep(1)
        report["after_frame"] = frame("after")
        report["qom"] = request(route + "/qom-snapshot", payload={"path": "/machine/m5pm1", "depth": 0})
        if args.mode != "strap":
            def read_completion():
                evidence = request(route + "/evidence?include=serial,manifest", binary=True)
                with ZipFile(io.BytesIO(evidence)) as archive:
                    cdc = archive.read("usb-serial-jtag.log")
                report["hwcdc_sha256"] = hashlib.sha256(cdc).hexdigest()
                report["hwcdc_bytes"] = len(cdc)
                return b"=== Firmware upgrade completed ===" in cdc

            if args.mode == "bad-crc":
                require(not read_completion(), "stock guest reported success on the bad PM1 CRC")
            else:
                wait_for(read_completion, "stock USB Serial/JTAG completion marker", timeout=10)
        report["status"] = "PASS"
    finally:
        try:
            report["session"] = request(route)
            report["serial"] = serial()
            evidence = request(route + "/evidence", binary=True)
            (args.output_dir / "evidence.zip").write_bytes(evidence)
        finally:
            report["stop"] = request(route + "?purge=0", method="DELETE")
            (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS {args.mode}")


if __name__ == "__main__":
    main()

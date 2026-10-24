#!/usr/bin/env python3
"""Exercise an ESP32-C6 Zigbee pair through esp-emu's 802.15.4 UDP bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import selectors
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class RadioRelay:
    def __init__(
        self,
        switch_bind: int,
        light_bind: int,
        switch_relay: int,
        light_relay: int,
    ) -> None:
        self.switch_bind = switch_bind
        self.light_bind = light_bind
        self.switch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.light = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.switch.bind(("127.0.0.1", switch_relay))
        self.light.bind(("127.0.0.1", light_relay))
        self.switch.setblocking(False)
        self.light.setblocking(False)
        self.stop_event = threading.Event()
        self.frames = {"switch": [], "light": []}
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)
        self.switch.close()
        self.light.close()

    def _run(self) -> None:
        selector = selectors.DefaultSelector()
        selector.register(self.switch, selectors.EVENT_READ, "switch")
        selector.register(self.light, selectors.EVENT_READ, "light")
        try:
            while not self.stop_event.is_set():
                for key, _ in selector.select(timeout=0.2):
                    data, _ = key.fileobj.recvfrom(8192)
                    side = str(key.data)
                    self.frames[side].append(data)
                    destination = (
                        self.light_bind
                        if side == "switch"
                        else self.switch_bind
                    )
                    target = (
                        self.light if side == "switch" else self.switch
                    )
                    target.sendto(data, ("127.0.0.1", destination))
        finally:
            selector.close()

    def summary(self) -> dict:
        return {
            side: {
                "frames": len(frames),
                "bytes": sum(len(frame) for frame in frames),
                "payload_sha256": hashlib.sha256(
                    b"".join(frames)
                ).hexdigest(),
            }
            for side, frames in self.frames.items()
        }


def emulator_command(
    emulator: Path,
    firmware: Path,
    elf: Path,
    bind_port: int,
    peer_port: int,
    timeout: float,
) -> list[str]:
    return [
        str(emulator),
        "--chip",
        "esp32c6",
        "--firmware",
        str(firmware),
        "--elf",
        str(elf),
        "--thread-sim",
        f"bind:{bind_port},peer:127.0.0.1:{peer_port}",
        "--net",
        "user",
        "--timeout",
        f"{timeout:g}s",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument("--switch-image", type=Path, required=True)
    parser.add_argument("--switch-elf", type=Path, required=True)
    parser.add_argument("--light-image", type=Path, required=True)
    parser.add_argument("--light-elf", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    for label, path in (
        ("emulator", args.emulator),
        ("switch image", args.switch_image),
        ("switch ELF", args.switch_elf),
        ("light image", args.light_image),
        ("light ELF", args.light_elf),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    switch_bind = free_udp_port()
    light_bind = free_udp_port()
    switch_relay = free_udp_port()
    light_relay = free_udp_port()
    relay = RadioRelay(
        switch_bind,
        light_bind,
        switch_relay,
        light_relay,
    )
    relay.start()
    switch_log = args.out_dir / "switch.log"
    light_log = args.out_dir / "light.log"
    processes: list[subprocess.Popen] = []
    try:
        with switch_log.open("wb") as switch_output:
            processes.append(
                subprocess.Popen(
                    emulator_command(
                        args.emulator,
                        args.switch_image,
                        args.switch_elf,
                        switch_bind,
                        switch_relay,
                        args.timeout,
                    ),
                    stdout=switch_output,
                    stderr=subprocess.STDOUT,
                )
            )
            time.sleep(1)
            with light_log.open("wb") as light_output:
                processes.append(
                    subprocess.Popen(
                        emulator_command(
                            args.emulator,
                            args.light_image,
                            args.light_elf,
                            light_bind,
                            light_relay,
                            args.timeout - 1,
                        ),
                        stdout=light_output,
                        stderr=subprocess.STDOUT,
                    )
                )
        for process in processes:
            try:
                process.wait(timeout=args.timeout + 10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        relay.stop()

    switch_text = switch_log.read_text(errors="replace")
    light_text = light_log.read_text(errors="replace")
    switch_formed = "Formed network successfully" in switch_text
    steering_started = "Start network steering" in light_text
    joined = "Joined network successfully" in light_text
    command_received = (
        "Received message: endpoint(10)" in light_text
        and "Light sets to" in light_text
    )
    frames = relay.summary()
    bidirectional = (
        frames["switch"]["frames"] > 0 and frames["light"]["frames"] > 0
    )
    if switch_formed and steering_started and joined and command_received:
        status = "PASS"
        classification = "zigbee_commissioning_and_on_off_observed"
    elif bidirectional and switch_formed and steering_started:
        status = "PARTIAL"
        classification = "zigbee_commissioning_or_mac_ack_not_completed"
    else:
        status = "FAIL"
        classification = "zigbee_radio_or_boot_path_not_observed"
    evidence = {
        "schema_version": 1,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "kind": "c6-zigbee-thread-sim-feasibility",
        "validation": "virtual-device validation",
        "status": status,
        "classification": classification,
        "emulator": {
            "sha256": sha256(args.emulator),
            "version": "esp-emu 0.50.0",
        },
        "artifacts": {
            "switch_image_sha256": sha256(args.switch_image),
            "switch_elf_sha256": sha256(args.switch_elf),
            "light_image_sha256": sha256(args.light_image),
            "light_elf_sha256": sha256(args.light_elf),
        },
        "radio": {
            "transport": "esp-emu --thread-sim local UDP relay",
            "frames": frames,
            "bidirectional": bidirectional,
        },
        "markers": {
            "switch_formed_network": switch_formed,
            "light_started_steering": steering_started,
            "light_joined_network": joined,
            "light_received_on_off": command_received,
        },
        "logs": {
            "switch": switch_log.name,
            "light": light_log.name,
        },
        "boundary": {
            "source_built_examples": [
                "ESP-IDF HA_on_off_switch",
                "ESP-IDF HA_on_off_light",
            ],
            "not_claimed": [
                "public M5Burner Zigbee binary compatibility without a matching ELF",
                "QEMU C6 Zigbee controller support",
                "physical RF or hardware validation",
            ],
        },
    }
    (args.out_dir / "evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Collect exact-time Core2 handoff state through isolated Device Service leases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVE = ROOT / "platform/tools/serve.py"
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
EXPECTED_IMAGE_SHA256 = (
    "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc"
)
TRACE_PATTERN = re.compile(
    r"^\[esp32-handoff\] now=(?P<now>\d+) "
    r"cpu=(?P<cpu>-?\d+) pc=(?P<pc>[0-9a-fA-F]+) "
    r"component=(?P<component>\S+) event=(?P<event>\S+) "
    r"a=(?P<a>[0-9a-fA-F]+) b=(?P<b>[0-9a-fA-F]+) "
    r"c=(?P<c>[0-9a-fA-F]+) d=(?P<d>[0-9a-fA-F]+)$"
)
UART_TRACE_PATTERN = re.compile(
    r"^\[uart-tx\] now=(?P<now>\d+) (?P<byte>[0-9a-fA-F]{2})$"
)
SSI_READ_COMMANDS = frozenset({0x03, 0x0B, 0xBB})
SSI_RX_LENGTH_OVERFLOW_BUCKET = 256
SSI_GAP_BUCKET_LABELS = (
    "0ns",
    "1..1000ns",
    "1001..10000ns",
    "10001..100000ns",
    "100001..1000000ns",
    "1000001..10000000ns",
    "10000001..100000000ns",
    "100000001..1000000000ns",
    ">1000000000ns",
)


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: float = 60,
    ) -> tuple[int, bytes, str]:
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:2000]
            raise RuntimeError(
                f"{path} returned HTTP {error.code}: {detail}"
            ) from error

    def json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        data = None
        content_type = None
        if payload is not None:
            data = json.dumps(payload).encode()
            content_type = "application/json"
        status, body, _ = self.request(
            path,
            method=method,
            data=data,
            content_type=content_type,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise RuntimeError(f"{path} returned HTTP {status}")
        return json.loads(body)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_metrics(data: bytes) -> dict[str, int]:
    tools_dir = str(ROOT / "platform/tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from user_firmware_matrix import png_metrics as metrics

    return metrics(data)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(api: Api, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Device Service exited during startup with {process.returncode}"
            )
        try:
            status, _, _ = api.request("/api/health", timeout=2)
            if status == 200:
                return
        except (OSError, RuntimeError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Device Service did not become healthy")


def parse_trace(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        match = TRACE_PATTERN.match(line)
        if not match:
            continue
        fields = match.groupdict()
        events.append(
            {
                "now_ns": int(fields["now"]),
                "cpu": int(fields["cpu"]),
                "pc": int(fields["pc"], 16),
                "component": fields["component"],
                "event": fields["event"],
                "a": fields["a"],
                "b": fields["b"],
                "c": fields["c"],
                "d": fields["d"],
            }
        )
    return events


def parse_uart_tx_lines(
    text: str,
    limit: int = 512,
) -> list[dict[str, Any]]:
    """Reconstruct guest UART lines on the same virtual-time axis as traces."""
    rows: list[dict[str, Any]] = []
    current = bytearray()
    start_ns: int | None = None
    for raw_line in text.splitlines():
        match = UART_TRACE_PATTERN.match(raw_line)
        if not match:
            continue
        now_ns = int(match.group("now"))
        byte = int(match.group("byte"), 16)
        if start_ns is None:
            start_ns = now_ns
        if byte == 0x0A:
            rows.append(
                {
                    "start_ns": start_ns,
                    "end_ns": now_ns,
                    "text": current.rstrip(b"\r").decode(
                        errors="replace"
                    ),
                }
            )
            current = bytearray()
            start_ns = None
            if len(rows) >= limit:
                break
        elif len(current) < 4096:
            current.append(byte)
    return rows


def summarize_phase_profile(
    text: str,
    *,
    top_limit: int = 8,
) -> dict[str, Any]:
    """Summarize opt-in PC sampling and sampled SSI command phases."""
    events = parse_trace(text)
    samples = [
        event
        for event in events
        if event["component"] == "cpu" and event["event"] == "sample"
    ]
    ssi_commands = [
        event
        for event in events
        if event["component"] == "ssi"
        and event["event"] == "transaction-begin"
    ]
    cpu0 = Counter(int(event["a"], 16) for event in samples)
    cpu1 = Counter(int(event["b"], 16) for event in samples)
    histograms = summarize_ssi_histograms(events)

    def top(counter: Counter[int]) -> list[dict[str, Any]]:
        return [
            {"pc": f"0x{pc:08x}", "samples": count}
            for pc, count in counter.most_common(top_limit)
        ]

    profile = {
        "pc_samples": len(samples),
        "sample_window_ns": (
            {
                "first": samples[0]["now_ns"],
                "last": samples[-1]["now_ns"],
            }
            if samples
            else None
        ),
        "cpu0_top_pcs": top(cpu0),
        "cpu1_top_pcs": top(cpu1),
        "ssi_transaction_events": len(ssi_commands),
        "ssi_read_events": sum(
            int(event["a"], 10) in SSI_READ_COMMANDS
            for event in ssi_commands
        ),
        "ssi_read64_events": sum(
            int(event["a"], 10) in SSI_READ_COMMANDS
            and int(event["d"], 10) == 64
            for event in ssi_commands
        ),
        "ssi_command_histogram": histograms["commands"],
        "ssi_rx_length_histogram": histograms["rx_lengths"],
        "ssi_gap_histogram": histograms["gaps"],
        "ssi_command_length_histogram": histograms["command_lengths"],
        "ssi_command_gap_profile": histograms["command_gaps"],
        "ssi_command_transitions": histograms["transitions"],
        "ssi_command_pcs": histograms["command_pcs"],
    }
    rdsr_profile = summarize_rdsr_profile(events)
    if rdsr_profile["count"]:
        profile["ssi_rdsr_profile"] = rdsr_profile
    s32c1i_profile = summarize_s32c1i_profile(events)
    if s32c1i_profile["total"]:
        profile["s32c1i_profile"] = s32c1i_profile
    return profile


def summarize_ssi_histograms(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Return exact controller-side command and RX-length bucket totals."""
    commands: Counter[int] = Counter()
    rx_lengths: Counter[int] = Counter()
    gaps: Counter[int] = Counter()
    command_lengths: Counter[tuple[int, int]] = Counter()
    command_gaps: dict[int, dict[str, int]] = {}
    command_length_overflow = 0
    command_gap_overflow = 0
    transitions: Counter[tuple[int, int]] = Counter()
    transition_overflow = 0
    command_pcs: dict[int, Counter[tuple[int, int]]] = {}
    command_pc_overflow = 0
    for event in events:
        if event["component"] != "ssi":
            continue
        if event["event"] == "freeze-command":
            commands[int(event["a"], 10)] += int(event["b"], 10)
        elif event["event"] == "freeze-rx-length":
            rx_lengths[int(event["a"], 10)] += int(event["b"], 10)
        elif event["event"] == "freeze-gap":
            gaps[int(event["a"], 10)] += int(event["b"], 10)
        elif event["event"] == "freeze-command-length":
            command_lengths[(int(event["a"], 10), int(event["b"], 10))] += (
                int(event["c"], 10)
            )
        elif event["event"] == "freeze-command-length-overflow":
            command_length_overflow += int(event["a"], 10)
        elif event["event"] == "freeze-command-gap":
            command_gaps[int(event["a"], 10)] = {
                "count": int(event["b"], 10),
                "total_gap_ns": int(event["c"], 10),
                "max_gap_ns": int(event["d"], 10),
            }
        elif event["event"] == "freeze-command-gap-overflow":
            command_gap_overflow += int(event["a"], 10)
        elif event["event"] == "freeze-command-transition":
            transitions[(int(event["a"], 10), int(event["b"], 10))] += (
                int(event["c"], 10)
            )
        elif event["event"] == "freeze-command-transition-overflow":
            transition_overflow += int(event["a"], 10)
        elif event["event"] == "freeze-command-pc":
            command = int(event["a"], 10)
            cpu = int(event["b"], 10)
            pc = int(event["c"], 16)
            command_pcs.setdefault(command, Counter())[(cpu, pc)] += int(
                event["d"], 10
            )
        elif event["event"] == "freeze-command-pc-overflow":
            command_pc_overflow += int(event["a"], 10)
    return {
        "commands": {
            f"0x{command:02x}": count
            for command, count in sorted(commands.items())
        },
        "rx_lengths": {
            (
                f"{bucket}+"
                if bucket == SSI_RX_LENGTH_OVERFLOW_BUCKET
                else str(bucket)
            ): count
            for bucket, count in sorted(rx_lengths.items())
        },
        "gaps": {
            SSI_GAP_BUCKET_LABELS[bucket]: count
            for bucket, count in sorted(gaps.items())
        },
        "command_lengths": {
            (
                f"0x{command:02x}/"
                + (
                    f"{length}+"
                    if length == SSI_RX_LENGTH_OVERFLOW_BUCKET
                    else str(length)
                )
            ): count
            for (command, length), count in sorted(command_lengths.items())
        },
        "command_gaps": {
            f"0x{command:02x}": values
            for command, values in sorted(command_gaps.items())
        },
        "transitions": {
            f"0x{previous:02x}->0x{command:02x}": count
            for (previous, command), count in sorted(transitions.items())
        },
        "command_pcs": {
            f"0x{command:02x}": {
                f"cpu{cpu}:0x{pc:08x}": count
                for (cpu, pc), count in sorted(pcs.items())
            }
            for command, pcs in sorted(command_pcs.items())
        },
        "command_total": sum(commands.values()),
        "rx_length_total": sum(rx_lengths.values()),
        "gap_total": sum(gaps.values()),
        "command_length_total": sum(command_lengths.values()),
        "command_length_overflow": command_length_overflow,
        "command_gap_total": sum(
            values["count"] for values in command_gaps.values()
        ),
        "command_gap_overflow": command_gap_overflow,
        "transition_total": sum(transitions.values()),
        "transition_overflow": transition_overflow,
        "command_pc_total": sum(
            sum(pcs.values()) for pcs in command_pcs.values()
        ),
        "command_pc_overflow": command_pc_overflow,
    }


def summarize_rdsr_profile(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize the bounded RDSR status/cache correlation table."""
    statuses: Counter[int] = Counter()
    previous_commands: Counter[int] = Counter()
    previous_lengths: Counter[int] = Counter()
    byte0: Counter[int] = Counter()
    byte1: Counter[int] = Counter()
    intlevels: Counter[int] = Counter()
    irq_requests: Counter[int] = Counter()
    contexts: dict[int, Counter[tuple[int, int]]] = {}
    cache_delta: dict[int, dict[str, int]] = {}
    fast_read = {
        "count": 0,
        "address_min": None,
        "address_max": None,
    }
    last: dict[str, Any] = {}
    last_context: dict[str, Any] = {}
    last_cache: dict[str, Any] = {}
    count = 0
    previous_command_hi = 0
    context_overflow = 0
    gap_total = 0
    gap_max = 0

    for event in events:
        if event["component"] != "ssi":
            continue
        name = event["event"]
        if name == "freeze-rdsr-count":
            count += int(event["a"], 10)
        elif name == "freeze-rdsr-status":
            statuses[int(event["a"], 10)] += int(event["b"], 10)
        elif name == "freeze-rdsr-previous-command":
            previous_commands[int(event["a"], 10)] += int(event["b"], 10)
        elif name == "freeze-rdsr-previous-command-hi":
            previous_command_hi += int(event["a"], 10)
        elif name == "freeze-rdsr-previous-length":
            previous_lengths[int(event["a"], 10)] += int(event["b"], 10)
        elif name == "freeze-rdsr-gap":
            gap_total = int(event["a"], 10)
            gap_max = int(event["b"], 10)
        elif name == "freeze-rdsr-fast-read":
            fast_read = {
                "count": int(event["a"], 10),
                "address_min": int(event["b"], 10),
                "address_max": int(event["c"], 10),
            }
        elif name == "freeze-rdsr-fast-read-byte":
            value = int(event["a"], 10)
            byte0[value] += int(event["b"], 10)
            byte1[value] += int(event["c"], 10)
        elif name == "freeze-rdsr-interrupt":
            level = int(event["a"], 10)
            intlevels[level] += int(event["b"], 10)
            irq_requests[level] += int(event["c"], 10)
        elif name == "freeze-rdsr-context":
            status = int(event["a"], 10)
            contexts.setdefault(status, Counter())[
                (int(event["b"], 10), int(event["c"], 16))
            ] += int(event["d"], 10)
        elif name == "freeze-rdsr-context-overflow":
            context_overflow += int(event["a"], 10)
        elif name == "freeze-rdsr-cache-delta":
            cache_delta[int(event["a"], 10)] = {
                "nonzero": int(event["b"], 10),
                "total": int(event["c"], 10),
                "max": int(event["d"], 10),
            }
        elif name == "freeze-rdsr-last":
            last = {
                "status": int(event["a"], 10),
                "previous_command": int(event["b"], 10),
                "previous_address": int(event["c"], 10),
                "previous_prefix": int(event["d"], 10),
            }
        elif name == "freeze-rdsr-last-context":
            last_context = {
                "cpu": int(event["a"], 10),
                "ps": int(event["b"], 10),
                "irq_request": int(event["c"], 10),
                "pc": int(event["d"], 16),
            }
        elif name == "freeze-rdsr-last-cache":
            last_cache = {
                "gap_ns": int(event["a"], 10),
                "sync_calls": int(event["b"], 10),
                "sync_pages": int(event["c"], 10),
                "last_sync_ns": int(event["d"], 10),
            }
        elif name == "freeze-rdsr-last-cache1":
            last_cache.update(
                {
                    "state_updates": int(event["a"], 10),
                    "invalidate_calls": int(event["b"], 10),
                    "illegal_reads": int(event["c"], 10),
                }
            )

    return {
        "count": count,
        "statuses": {
            f"0x{status:02x}": status_count
            for status, status_count in sorted(statuses.items())
        },
        "previous_commands": {
            f"0x{command:02x}": command_count
            for command, command_count in sorted(previous_commands.items())
        },
        "previous_command_hi": previous_command_hi,
        "previous_lengths": {
            (
                f"{length}+"
                if length == SSI_RX_LENGTH_OVERFLOW_BUCKET
                else str(length)
            ): length_count
            for length, length_count in sorted(previous_lengths.items())
        },
        "gap": {"count": max(count - 1, 0), "total_ns": gap_total,
                "max_ns": gap_max},
        "fast_read": {
            "count": fast_read["count"],
            "address_min": (
                f"0x{fast_read['address_min']:08x}"
                if fast_read["address_min"] is not None
                else None
            ),
            "address_max": (
                f"0x{fast_read['address_max']:08x}"
                if fast_read["address_max"] is not None
                else None
            ),
            "byte0": {str(value): byte0[value] for value in sorted(byte0)},
            "byte1": {str(value): byte1[value] for value in sorted(byte1)},
        },
        "interrupt": {
            "intlevel": {
                str(level): intlevels[level] for level in sorted(intlevels)
            },
            "irq_request": {
                str(level): irq_requests[level]
                for level in sorted(irq_requests)
            },
        },
        "contexts": {
            f"0x{status:02x}": {
                f"cpu{cpu}:0x{pc:08x}": context_count
                for (cpu, pc), context_count in sorted(context_counts.items())
            }
            for status, context_counts in sorted(contexts.items())
        },
        "context_total": sum(
            sum(context_counts.values()) for context_counts in contexts.values()
        ),
        "context_overflow": context_overflow,
        "cache_delta": {
            str(index): values for index, values in sorted(cache_delta.items())
        },
        "last": last,
        "last_context": {
            **last_context,
            "pc": (
                f"0x{last_context['pc']:08x}"
                if "pc" in last_context
                else None
            ),
        },
        "last_cache": last_cache,
    }


def summarize_s32c1i_profile(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize bounded conditional-store sites, lock owners and outcomes."""
    total = 0
    success = 0
    contended = 0
    pcs: Counter[tuple[int, int, int]] = Counter()
    pc_successes: Counter[tuple[int, int, int]] = Counter()
    locks: dict[int, dict[str, int]] = {}
    old_values: Counter[int] = Counter()
    callers: Counter[tuple[int, int, int, int, int]] = Counter()
    holders: Counter[tuple[int, int, int, int]] = Counter()
    episode_buckets: Counter[int] = Counter()
    episode_locks: dict[int, dict[str, int]] = {}
    episode_lock_attempts: dict[int, dict[str, int]] = {}
    episode_summary: dict[str, Any] = {}
    episode_last: dict[str, Any] = {}
    pc_overflow = 0
    lock_overflow = 0
    old_overflow = 0
    caller_overflow = 0
    holder_overflow = 0
    episode_lock_overflow = 0
    last: dict[str, Any] = {}
    last_context: dict[str, Any] = {}

    for event in events:
        if event["component"] != "s32c1i":
            continue
        name = event["event"]
        if name == "freeze-total":
            total += int(event["a"], 10)
            success += int(event["b"], 10)
            contended += int(event["c"], 10)
        elif name == "freeze-pc":
            key = (
                int(event["a"], 10),
                int(event["b"], 10),
                int(event["c"], 16),
            )
            pcs[key] += int(event["d"], 10)
            if key[1]:
                pc_successes[key] += int(event["d"], 10)
        elif name == "freeze-pc-overflow":
            pc_overflow += int(event["a"], 10)
        elif name == "freeze-lock":
            locks[int(event["a"], 16)] = {
                "count": int(event["b"], 10),
                "success": int(event["c"], 10),
                "last_old": int(event["d"], 16),
            }
        elif name == "freeze-lock-overflow":
            lock_overflow += int(event["a"], 10)
        elif name == "freeze-old":
            old_values[int(event["a"], 16)] += int(event["b"], 10)
        elif name == "freeze-old-overflow":
            old_overflow += int(event["a"], 10)
        elif name == "freeze-caller":
            callers[
                (
                    event["cpu"],
                    int(event["pc"]),
                    int(event["a"], 16),
                    int(event["c"], 16),
                    int(event["b"], 10),
                )
            ] += int(event["d"], 10)
        elif name == "freeze-caller-overflow":
            caller_overflow += int(event["a"], 10)
        elif name == "freeze-holder":
            holders[
                (
                    int(event["a"], 16),
                    int(event["b"], 10),
                    int(event["c"], 16),
                    int(event["pc"]),
                )
            ] += int(event["d"], 10)
        elif name == "freeze-holder-overflow":
            holder_overflow += int(event["a"], 10)
        elif name == "freeze-episodes":
            episode_summary = {
                "count": int(event["a"], 10),
                "duration_ns_total": int(event["b"], 10),
                "duration_ns_max": int(event["c"], 10),
                "incomplete": int(event["d"], 10),
            }
        elif name == "freeze-episode-bucket":
            episode_buckets[int(event["a"], 10)] += int(event["b"], 10)
        elif name == "freeze-episode-lock":
            episode_locks[int(event["a"], 16)] = {
                "count": int(event["b"], 10),
                "duration_ns_total": int(event["c"], 10),
                "duration_ns_max": int(event["d"], 10),
            }
        elif name == "freeze-episode-lock-attempts":
            episode_lock_attempts[int(event["a"], 16)] = {
                "attempts_total": int(event["b"], 10),
                "attempts_max": int(event["c"], 10),
                "attempt_gap_ns_max": int(event["d"], 10),
            }
        elif name == "freeze-episode-lock-overflow":
            episode_lock_overflow += int(event["a"], 10)
        elif name == "freeze-episode-last":
            episode_last = {
                "lock": int(event["a"], 16),
                "duration_ns": int(event["b"], 10),
                "attempts": int(event["c"], 10),
                "holder_cpu": int(event["d"], 10),
            }
        elif name == "freeze-last":
            last = {
                "pc": int(event["a"], 16),
                "address": int(event["b"], 16),
                "old": int(event["c"], 16),
                "desired": int(event["d"], 16),
            }
        elif name == "freeze-last-context":
            last_context = {
                "cpu": int(event["a"], 10),
                "success": int(event["b"], 10),
                "caller": int(event["c"], 16),
            }

    return {
        "total": total,
        "success": success,
        "failure": total - success,
        "contended": contended,
        "pc": {
            f"cpu{cpu}:success={pc_success}:0x{pc:08x}": count
            for (cpu, pc_success, pc), count in sorted(pcs.items())
        },
        "pc_success": {
            f"cpu{cpu}:success={pc_success}:0x{pc:08x}": count
            for (cpu, pc_success, pc), count in sorted(pc_successes.items())
        },
        "pc_overflow": pc_overflow,
        "locks": {
            f"0x{address:08x}": values
            for address, values in sorted(locks.items())
        },
        "lock_overflow": lock_overflow,
        "old_values": {
            f"0x{value:08x}": count
            for value, count in sorted(old_values.items())
        },
        "old_overflow": old_overflow,
        "callers": {
            (
                f"cpu{cpu}:success={success}:site=0x{site:08x}:"
                f"caller=0x{caller:08x}:lock=0x{address:08x}"
            ): count
            for (
                cpu,
                caller,
                site,
                address,
                success,
            ), count in sorted(callers.items())
        },
        "caller_overflow": caller_overflow,
        "holders": {
            (
                f"holder_cpu{cpu}:holder=0x{holder_pc:08x}:"
                f"site=0x{site:08x}:lock=0x{address:08x}"
            ): count
            for (
                site,
                cpu,
                address,
                holder_pc,
            ), count in sorted(holders.items())
        },
        "holder_overflow": holder_overflow,
        "episode_buckets": {
            str(bucket): count
            for bucket, count in sorted(episode_buckets.items())
        },
        "episode_locks": {
            f"0x{address:08x}": {
                **values,
                **episode_lock_attempts.get(address, {}),
            }
            for address, values in sorted(episode_locks.items())
        },
        "episode_lock_overflow": episode_lock_overflow,
        "episodes": episode_summary,
        "episode_last": {
            **episode_last,
            **(
                {"lock": f"0x{episode_last['lock']:08x}"}
                if "lock" in episode_last
                else {}
            ),
        },
        "last": {
            **last,
            **{
                key: f"0x{value:08x}"
                for key, value in last.items()
            },
        },
        "last_context": last_context,
    }


def snapshot_at_pause(
    stderr: str,
    target_ns: int,
    tolerance_ns: int,
) -> dict[str, Any]:
    events = parse_trace(stderr)
    pauses = [
        event
        for event in events
        if event["component"] == "cpu" and event["event"] == "pause"
    ]
    if not pauses:
        raise RuntimeError("QEMU did not emit an exact-time pause marker")
    pause = pauses[-1]
    if abs(pause["now_ns"] - target_ns) > tolerance_ns:
        raise RuntimeError(
            f"pause marker missed target by "
            f"{abs(pause['now_ns'] - target_ns)} ns"
        )
    same_time = [
        event for event in events if event["now_ns"] == pause["now_ns"]
    ]
    cpu = {}
    memory = {}
    dport = {}
    io = {}
    registers: dict[str, dict[str, str]] = {}
    points: dict[str, dict[str, str]] = {}
    stack_words: list[dict[str, Any]] = []
    for event in same_time:
        if event["component"] == "cpu" and event["event"] == "freeze":
            cpu[str(event["cpu"])] = {
                "pc": f"0x{event['pc']:08x}",
                "interrupt_request": f"0x{int(event['a'], 16):08x}",
                "state_flags": int(event["b"], 10),
            }
        elif event["component"] == "cpu" and event["event"] == "freeze-reg":
            registers[str(event["cpu"])] = {
                "a0": f"0x{int(event['a'], 16):08x}",
                "a1": f"0x{int(event['b'], 16):08x}",
                "ps": f"0x{int(event['c'], 16):08x}",
            }
        elif event["component"] == "cpu" and event["event"].startswith(
            "freeze-reg"
        ):
            key = str(event["cpu"])
            base = int(event["event"].removeprefix("freeze-reg"))
            values = registers.setdefault(key, {})
            fields = ("a", "b") if base == 14 else ("a", "b", "c", "d")
            for offset, field in enumerate(fields):
                values[f"a{base + offset}"] = (
                    f"0x{int(event[field], 16):08x}"
                )
        elif event["component"] == "mem" and event["event"] == "freeze-point":
            points[f"0x{int(event['a'], 16):08x}"] = {
                "value": f"0x{int(event['b'], 16):08x}",
                "offset24": f"0x{int(event['c'], 16):08x}",
                "offset28": f"0x{int(event['d'], 16):08x}",
            }
        elif event["component"] == "mem" and event["event"] == "stack-word":
            stack_words.append(
                {
                    "cpu": int(event["c"], 10),
                    "index": int(event["d"], 10),
                    "address": f"0x{int(event['a'], 16):08x}",
                    "value": f"0x{int(event['b'], 16):08x}",
                }
            )
        elif event["component"] == "mem" and event["event"] in {
            "freeze-byte",
            "freeze-word",
        }:
            memory[f"0x{int(event['a'], 16):08x}"] = (
                f"0x{int(event['b'], 16):02x}"
                if event["event"] == "freeze-byte"
                else f"0x{int(event['b'], 16):08x}"
            )
        elif event["component"] == "dport" and event["event"].startswith(
            "freeze-"
        ):
            if event["event"].startswith("freeze-state"):
                dport[event["event"]] = {
                    "a": int(event["a"], 10),
                    "b": int(event["b"], 10),
                    "c": f"0x{int(event['c'], 16):08x}",
                    "d": f"0x{int(event['d'], 16):08x}",
                }
            else:
                dport[event["event"]] = {
                    "a": int(event["a"], 10),
                    "b": int(event["b"], 10),
                    "c": int(event["c"], 10),
                    "d": int(event["d"], 10),
                }
        elif (
            event["component"] in {"ssi", "crosscore"}
            and event["event"].startswith("freeze-")
            and event["event"]
            not in {
                "freeze-command",
                "freeze-rx-length",
                "freeze-gap",
                "freeze-command-length",
                "freeze-command-length-overflow",
                "freeze-command-gap",
                "freeze-command-gap-overflow",
                "freeze-command-transition",
                "freeze-command-transition-overflow",
                "freeze-command-pc",
                "freeze-command-pc-overflow",
                "freeze-rdsr-count",
                "freeze-rdsr-status",
                "freeze-rdsr-previous-command",
                "freeze-rdsr-previous-command-hi",
                "freeze-rdsr-previous-length",
                "freeze-rdsr-gap",
                "freeze-rdsr-fast-read",
                "freeze-rdsr-fast-read-byte",
                "freeze-rdsr-interrupt",
                "freeze-rdsr-context",
                "freeze-rdsr-context-overflow",
                "freeze-rdsr-cache-delta",
                "freeze-rdsr-last",
                "freeze-rdsr-last-context",
                "freeze-rdsr-last-cache",
                "freeze-rdsr-last-cache1",
            }
        ):
            io[f"{event['component']}:{event['event']}"] = {
                "a": int(event["a"], 10),
                "b": int(event["b"], 10),
                "c": int(event["c"], 10),
                "d": int(event["d"], 10),
            }
    required_memory = {
        "0x3ffc7ec8",
        "0x3ffc7ec9",
        "0x3ffc7750",
        "0x3ffc7754",
    }
    if set(cpu) != {"0", "1"}:
        raise RuntimeError(f"incomplete CPU state: {sorted(cpu)}")
    if not required_memory.issubset(memory):
        raise RuntimeError(
            "incomplete memory state: "
            f"missing {sorted(required_memory - set(memory))}"
        )
    if "freeze-state" not in dport:
        raise RuntimeError("missing DPORT freeze state")
    if "ssi:freeze-counters" not in io:
        raise RuntimeError("missing SSI freeze counters")
    histograms = summarize_ssi_histograms(same_time)
    rdsr_profile = summarize_rdsr_profile(same_time)
    s32c1i_profile = summarize_s32c1i_profile(same_time)
    transactions = io["ssi:freeze-counters"]["a"]
    if histograms["command_total"]:
        if histograms["command_total"] != transactions:
            raise RuntimeError(
                "SSI command histogram total does not match transactions"
            )
        if histograms["rx_length_total"] != transactions:
            raise RuntimeError(
                "SSI RX-length histogram total does not match transactions"
            )
        if histograms["gap_total"] != transactions - 1:
            raise RuntimeError(
                "SSI gap histogram total does not match transaction gaps"
            )
        if (
            histograms["command_length_total"]
            + histograms["command_length_overflow"]
            != transactions
        ):
            raise RuntimeError(
                "SSI command-length histogram total does not match transactions"
            )
        if (
            histograms["command_gap_total"]
            + histograms["command_gap_overflow"]
            != transactions - 1
        ):
            raise RuntimeError(
                "SSI per-command gap total does not match transaction gaps"
            )
        if (
            histograms["transition_total"]
            + histograms["transition_overflow"]
            != transactions - 1
        ):
            raise RuntimeError(
                "SSI transition histogram total does not match transaction gaps"
            )
        if (
            histograms["command_pc_total"]
            + histograms["command_pc_overflow"]
            != transactions
        ):
            raise RuntimeError(
                "SSI command PC histogram total does not match transactions"
            )
        if rdsr_profile["count"]:
            if histograms["commands"].get("0x05", 0) != rdsr_profile["count"]:
                raise RuntimeError(
                    "SSI RDSR status total does not match command histogram"
                )
            if (
                rdsr_profile["context_total"]
                + rdsr_profile["context_overflow"]
                != rdsr_profile["count"]
            ):
                raise RuntimeError(
                    "SSI RDSR context total does not match status reads"
                )
    if s32c1i_profile["total"]:
        if (
            sum(s32c1i_profile["pc"].values())
            + s32c1i_profile["pc_overflow"]
            != s32c1i_profile["total"]
        ):
            raise RuntimeError(
                "S32C1I PC total does not match conditional stores"
            )
        if (
            sum(s32c1i_profile["callers"].values())
            + s32c1i_profile["caller_overflow"]
            != s32c1i_profile["total"]
        ):
            raise RuntimeError(
                "S32C1I caller total does not match conditional stores"
            )
        if (
            sum(s32c1i_profile["holders"].values())
            + s32c1i_profile["holder_overflow"]
            != s32c1i_profile["contended"]
        ):
            raise RuntimeError(
                "S32C1I holder total does not match cross-core contention"
            )
    snapshot = {
        "pause_target_ns": target_ns,
        "pause_event_ns": pause["now_ns"],
        "pause_delta_ns": pause["now_ns"] - target_ns,
        "cpu": cpu,
        "memory": memory,
        "dport": dport,
        "io": io,
        "ssi_command_histogram": histograms["commands"],
        "ssi_rx_length_histogram": histograms["rx_lengths"],
        "ssi_gap_histogram": histograms["gaps"],
        "ssi_command_length_histogram": histograms["command_lengths"],
        "ssi_command_gap_profile": histograms["command_gaps"],
        "ssi_command_transitions": histograms["transitions"],
        "ssi_command_pcs": histograms["command_pcs"],
        "ssi_rdsr_profile": rdsr_profile,
        "s32c1i_profile": s32c1i_profile,
    }
    if registers:
        snapshot["registers"] = registers
    if points:
        snapshot["points"] = points
    if stack_words:
        snapshot["stack_words"] = sorted(
            stack_words,
            key=lambda item: (item["cpu"], item["index"]),
        )
    return snapshot


def stop_service(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_target(
    image: Path,
    qemu: Path,
    out_dir: Path,
    target_ns: int,
    attempt: int,
    runtime: str,
    icount_shift: str,
    timeout: float,
    tolerance_ns: int,
    disable_wdt: bool,
    capture_frame: bool,
    pc_sample_ns: int | None,
    uart_trace: bool,
    trace_sample: int,
    service_port: int | None = None,
) -> dict[str, Any]:
    run_dir = out_dir / f"pause-{target_ns}-attempt-{attempt}"
    run_dir.mkdir(parents=True, exist_ok=True)
    port = service_port or free_port()
    base_url = f"http://127.0.0.1:{port}"
    api = Api(base_url)
    env = os.environ.copy()
    env.update(
        {
            "M5_QEMU_XTENSA": str(qemu),
            "M5_CORE2_RADIO_QEMU": str(qemu),
            "M5_CORE2_ICOUNT_SHIFT": icount_shift,
            "M5SW_ESP32_HANDOFF_TRACE": "1",
            "M5SW_ESP32_HANDOFF_TRACE_SAMPLE": str(trace_sample),
            "M5SW_ESP32_HANDOFF_PAUSE_NS": str(target_ns),
            "M5SW_ESP32_HANDOFF_DUMP_STATE": "1",
        }
    )
    if capture_frame:
        # Preserve the stopped process so it can be resumed briefly for a QMP
        # screendump after the exact-time state has been collected.
        env.pop("M5SW_ESP32_HANDOFF_PAUSE_ACTION", None)
    else:
        env["M5SW_ESP32_HANDOFF_PAUSE_ACTION"] = "exit"
    if disable_wdt:
        env["M5SW_DISABLE_WDT"] = "1"
    else:
        env.pop("M5SW_DISABLE_WDT", None)
    if pc_sample_ns is not None:
        env["M5SW_ESP32_HANDOFF_PC_SAMPLE_NS"] = str(pc_sample_ns)
    else:
        env.pop("M5SW_ESP32_HANDOFF_PC_SAMPLE_NS", None)
    if uart_trace:
        env["M5SW_UART_TRACE"] = "1"
    else:
        env.pop("M5SW_UART_TRACE", None)
    service_log = (run_dir / "device-service.log").open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVE),
            str(port),
            "--bind",
            "127.0.0.1",
            "--state-dir",
            str(run_dir / "service-state"),
            "--max-sessions",
            "1",
            "--max-per-device",
            "1",
            "--session-ttl",
            "3600",
        ],
        cwd=ROOT,
        env=env,
        stdout=service_log,
        stderr=subprocess.STDOUT,
    )
    session_id = ""
    try:
        wait_for_health(api, process, timeout=10)
        status, body, _ = api.request(
            "/api/v1/artifacts",
            method="POST",
            data=image.read_bytes(),
            content_type="application/octet-stream",
            timeout=120,
        )
        artifact = json.loads(body)
        if status != 201:
            raise RuntimeError(f"artifact upload returned HTTP {status}")
        firmware = api.json(
            "/api/v1/firmware",
            method="POST",
            payload={
                "device_id": "core2",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            },
        )
        session_payload: dict[str, Any] = {
            "device_id": "core2",
            "firmware_id": firmware["firmware_id"],
            "runtime": runtime,
            "ttl_seconds": 3600,
        }
        if runtime == "qemu-wifi":
            session_payload["network"] = {
                "profile": "core2-openmac",
                "net_mode": "user",
                "expected_markers": [],
            }
        created = api.json(
            "/api/v1/sessions",
            method="POST",
            payload=session_payload,
        )
        session_id = str(created["session_id"])

        deadline = time.monotonic() + timeout
        logs: dict[str, Any] = {}
        stderr = ""
        while time.monotonic() < deadline:
            logs = api.json(
                f"/api/v1/sessions/{session_id}/logs"
                "?offset=0&limit=1048576"
            )
            stderr = str(logs.get("qemu_stderr") or "")
            if "component=mem event=freeze-byte" in stderr:
                break
            state = str(
                api.json(f"/api/v1/sessions/{session_id}").get("state")
            )
            if state in {"failed", "stopped"} and stderr:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("timed out waiting for exact-time state dump")

        (run_dir / "qemu.stderr").write_text(stderr)
        serial = str(logs.get("data") or "")
        (run_dir / "serial.log").write_text(serial)
        events = api.json(f"/api/v1/sessions/{session_id}/events")
        (run_dir / "events.json").write_text(
            json.dumps(events, indent=2) + "\n"
        )
        snapshot = snapshot_at_pause(stderr, target_ns, tolerance_ns)
        if capture_frame:
            # The exact-time marker stops the whole QEMU process with SIGSTOP.
            # Resume it after collecting register/state evidence so QMP can
            # service screendump, then stop the lease immediately afterwards.
            session = api.json(f"/api/v1/sessions/{session_id}")
            os.kill(int(session["pid"]), signal.SIGCONT)
            deadline = time.monotonic() + 5
            while True:
                state = str(
                    api.json(f"/api/v1/sessions/{session_id}").get("state")
                )
                if state == "running":
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"QEMU did not resume for frame capture: state={state}"
                    )
                time.sleep(0.1)
            frame_status, frame, _ = api.request(
                f"/api/v1/sessions/{session_id}/frame.png",
                timeout=30,
            )
            if frame_status != 200:
                raise RuntimeError(
                    f"frame capture returned HTTP {frame_status}"
                )
            (run_dir / "frame.png").write_bytes(frame)
            snapshot["frame"] = {
                "bytes": len(frame),
                "sha256": sha256_bytes(frame),
                "capture_phase": "immediately-after-pause-resume",
                **png_metrics(frame),
            }
        snapshot.update(
            {
                "attempt": attempt,
                "runtime": runtime,
                "icount_shift": icount_shift,
                "wdt_disabled": disable_wdt,
                "session_id_sha256": sha256_bytes(session_id.encode()),
                "qemu_stderr_sha256": sha256_bytes(stderr.encode()),
                "serial_bytes": len(serial.encode()),
                "serial_sha256": sha256_bytes(serial.encode()),
                "uart_tx_lines": parse_uart_tx_lines(stderr),
                "phase_profile": summarize_phase_profile(stderr),
                "trace_sample": trace_sample,
            }
        )
        return snapshot
    finally:
        if session_id:
            session_dir = run_dir / "service-state" / "sessions" / session_id
            for name in ("qemu.stderr", "serial.log", "session.json"):
                source = session_dir / name
                destination = run_dir / name
                if source.is_file() and not destination.exists():
                    shutil.copy2(source, destination)
            try:
                api.json(
                    f"/api/v1/sessions/{session_id}?purge=0",
                    method="DELETE",
                    payload={},
                )
            except Exception:
                pass
        stop_service(process)
        service_log.close()
        shutil.rmtree(run_dir / "service-state", ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument(
        "--pause-seconds",
        type=float,
        action="append",
        required=True,
        help="repeat for each exact virtual-time freeze",
    )
    parser.add_argument(
        "--expected-image-sha256",
        default=EXPECTED_IMAGE_SHA256,
    )
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument("--pause-tolerance-ms", type=float, default=5)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--disable-wdt", action="store_true")
    parser.add_argument(
        "--service-port",
        type=int,
        help="explicit local Device Service port for concurrent diagnostics",
    )
    parser.add_argument(
        "--pc-sample-ns",
        type=int,
        help="sample both guest PCs at this virtual-time interval",
    )
    parser.add_argument(
        "--uart-trace",
        action="store_true",
        help="record UART TX bytes with virtual timestamps",
    )
    parser.add_argument(
        "--trace-sample",
        type=int,
        default=1024,
        help="record every Nth routine handoff event (default: 1024)",
    )
    parser.add_argument(
        "--capture-frame",
        action="store_true",
        help="capture the current PNG before stopping the lease",
    )
    parser.add_argument(
        "--runtime",
        choices=("qemu", "qemu-wifi"),
        default="qemu",
    )
    parser.add_argument(
        "--icount-shift",
        choices=("auto", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"),
        default="5",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"image does not exist: {args.image}")
    if not args.qemu.is_file():
        parser.error(f"QEMU does not exist: {args.qemu}")
    if args.attempts < 1 or args.attempts > 10:
        parser.error("--attempts must be from 1 to 10")
    if args.service_port is not None and not 1024 <= args.service_port <= 65535:
        parser.error("--service-port must be from 1024 to 65535")
    if args.pc_sample_ns is not None and not (
        1_000_000 <= args.pc_sample_ns <= 1_000_000_000
    ):
        parser.error("--pc-sample-ns must be from 1000000 to 1000000000")
    if not 1 <= args.trace_sample <= 1_000_000:
        parser.error("--trace-sample must be from 1 to 1000000")
    image_sha256 = sha256_file(args.image)
    if image_sha256 != args.expected_image_sha256.lower():
        parser.error(
            f"image SHA256 mismatch: expected "
            f"{args.expected_image_sha256}, got {image_sha256}"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    targets = sorted({round(value, 9) for value in args.pause_seconds})
    snapshots = []
    failures = []
    for seconds in targets:
        target_ns = int(round(seconds * 1_000_000_000))
        for attempt in range(1, args.attempts + 1):
            try:
                snapshot = run_target(
                    args.image,
                    args.qemu,
                    args.out_dir,
                    target_ns,
                    attempt,
                    args.runtime,
                    args.icount_shift,
                    args.timeout_seconds,
                    int(args.pause_tolerance_ms * 1_000_000),
                    args.disable_wdt,
                    args.capture_frame,
                    args.pc_sample_ns,
                    args.uart_trace,
                    args.trace_sample,
                    args.service_port,
                )
                snapshots.append(snapshot)
                print(
                    f"PAUSE {seconds:.6f}s attempt={attempt} "
                    f"cpu0={snapshot['cpu']['0']['pc']} "
                    f"cpu1={snapshot['cpu']['1']['pc']}"
                )
            except Exception as error:
                failures.append(
                    {
                        "pause_target_ns": target_ns,
                        "attempt": attempt,
                        "error": str(error),
                    }
                )
                print(
                    f"PAUSE {seconds:.6f}s attempt={attempt} FAILED: {error}",
                    file=sys.stderr,
                )

    captured_frames = [
        snapshot["frame"]
        for snapshot in snapshots
        if "frame" in snapshot
    ]
    frame_classification = "NOT RUN"
    if captured_frames:
        frame_classification = (
            "CAPTURED_BLACK"
            if all(row["nonblack_pixels"] == 0 for row in captured_frames)
            else "CAPTURED_NONBLANK"
        )

    evidence = {
        "schema_version": 1,
        "kind": "core2-handoff-pause-sweep",
        "validation": "virtual-device validation",
        "status": "PASS" if snapshots and not failures else (
            "PARTIAL" if snapshots else "FAIL"
        ),
        "firmware": {
            "name": "UIFlow_Core2 v1.15.4",
            "normalized_flash_sha256": image_sha256,
            "bytes": args.image.stat().st_size,
        },
        "runtime": {
            "machine": "m5core2",
            "qemu_binary_sha256": sha256_file(args.qemu),
            "trace_sample": args.trace_sample,
            "pc_sampling_ns": args.pc_sample_ns,
            "uart_trace": args.uart_trace,
            "runtime": args.runtime,
            "icount_shift": args.icount_shift,
            "pause_action": (
                "sigstop-resume-for-frame" if args.capture_frame else "exit"
            ),
            "frame_capture": args.capture_frame,
            "wdt_disabled": args.disable_wdt,
            "attempts_per_target": args.attempts,
            "pause_tolerance_ns": int(
                args.pause_tolerance_ms * 1_000_000
            ),
        },
        "snapshots": snapshots,
        "failures": failures,
        "classification": {
            "uart_storm": "REJECTED",
            "guest_deadlock": "NOT PROVEN",
            "application_frame": frame_classification,
        },
        "boundaries": [
            "Only virtual-device validation.",
            "The state dump reads SRAM and DPORT model state at the pause boundary.",
            "Exact-time CPU register snapshots do not prove a permanent deadlock.",
            "No physical cache, PSRAM, Flash, RF, electrical or hardware validation is claimed.",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"evidence={evidence_path}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

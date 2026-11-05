#!/usr/bin/env python3
"""Run the registered M5Stack UIFlow2 virtual-host matrix."""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from esp_flash import flash_with_esp_emu, flash_with_qemu

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"
RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
TAB5_RUNNER = ROOT / "tests/uiflow2/run_tab5_ui_test.py"


def run_logged(label: str, command: list[str], out_dir: Path, timeout: float,
               env: dict[str, str]) -> tuple[int, str]:
    stdout_path = out_dir / f"{label}.stdout"
    stderr_path = out_dir / f"{label}.stderr"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout,
                check=False,
            )
            return result.returncode, stdout_path.read_text(errors="replace")
        except subprocess.TimeoutExpired:
            return 124, stdout_path.read_text(errors="replace")


def ui_command(
    device: dict,
    backend: dict,
    device_out: Path,
    *,
    prebuilt_image: Path | None = None,
    build_only: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--base", str(ROOT / device["base"]),
        "--machine", device["machine"],
        "--files-dir", str(ROOT / device["files_dir"]),
        "--vfs-offset", device["vfs_offset"],
        "--vfs-size", device["vfs_size"],
        "--flash-size", device["flash_size"],
        "--expected-size", device["expected_size"],
        "--input", device["input"],
        "--wait", str(device.get("wait", 6)),
        "--post-input-wait", str(device.get("post_input_wait", 0.6)),
        "--efuse-driver", device.get("efuse_driver", backend["efuse_driver"]),
        "--qemu", str(ROOT / backend["qemu"]),
        "--rom-dir", str(ROOT / backend["rom_dir"]),
        "--out-dir", str(device_out),
    ]
    if prebuilt_image:
        command.extend(["--prebuilt-image", str(prebuilt_image)])
    if build_only:
        command.append("--build-only")
    if "efuse_pkg_version" in device:
        command.extend(["--efuse-pkg-version", str(device["efuse_pkg_version"])])
    if "memory" in device:
        command.extend(["--memory", device["memory"]])
    if device.get("deterministic"):
        command.append("--deterministic")
    if "post_frame_color" in device:
        command.extend(["--post-frame-color", device["post_frame_color"]])
    for name in ("pre_input_marker", "post_input_marker"):
        if device.get(name):
            command.extend(["--" + name.replace("_", "-"), device[name]])
    serial_expect = device.get("serial_expect", [])
    if isinstance(serial_expect, str):
        serial_expect = [serial_expect]
    for marker in serial_expect:
        command.extend(["--serial-expect", marker])
    return command


def run_ui(
    device: dict,
    backend: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    flash_info = {"transport": "host-image", "verified": True}
    prebuilt_image = None
    build_out = device_out / "build"
    build_out.mkdir(parents=True, exist_ok=True)
    esp_emu_chip = backend.get("esp_emu_chip")
    qemu_esptool_chip = backend.get("qemu_esptool_chip")
    esptool_transport = (
        "esp-emu-esptool" if esp_emu_chip else "qemu-esptool"
    )
    if flash_transport == "esp-emu" and (esp_emu_chip or qemu_esptool_chip):
        build_command = ui_command(
            device, backend, build_out, build_only=True
        )
        build_code, build_stdout = run_logged(
            f"{device['id']}-build",
            build_command,
            out_dir,
            device.get("timeout", 60),
            env,
        )
        built_image = build_out / "uiflow2-ui-test.bin"
        if build_code or not built_image.is_file():
            return {
                "status": "FAIL",
                "exit_code": build_code or 1,
                "command": build_command,
                "output": str(build_out),
                "flash": {"transport": esptool_transport, "verified": False},
                "reason": build_stdout[-1200:] or "test image build failed",
            }
        try:
            flash_args = {
                "chip": esp_emu_chip or qemu_esptool_chip,
                "image": built_image,
                "flash_size": int(device["flash_size"], 0),
                "out_dir": device_out / "flash",
                "env": env,
                "timeout": max(
                    device.get("timeout", 60),
                    600 if qemu_esptool_chip else 240,
                ),
            }
            if esp_emu_chip:
                flash_info = flash_with_esp_emu(**flash_args)
            else:
                flash_info = flash_with_qemu(
                    **flash_args,
                    machine=device["machine"],
                    qemu=ROOT / backend["qemu"],
                    rom_dir=ROOT / backend["rom_dir"],
                    memory=device.get("memory"),
                )
            prebuilt_image = Path(flash_info["virtual_flash"])
        except Exception as error:
            return {
                "status": "FAIL",
                "exit_code": 1,
                "command": build_command,
                "output": str(build_out),
                "flash": {
                    "transport": esptool_transport,
                    "verified": False,
                    "error": str(error),
                },
                "reason": str(error),
            }

    run_out = device_out / "run" if prebuilt_image else device_out
    run_out.mkdir(parents=True, exist_ok=True)
    command = ui_command(device, backend, run_out, prebuilt_image=prebuilt_image)
    code, stdout = run_logged(
        f"{device['id']}-run" if prebuilt_image else device["id"],
        command,
        out_dir,
        device.get("timeout", 60),
        env,
    )
    passed = code == 0 and "PASS " in stdout
    return {
        "status": "PASS" if passed else "FAIL",
        "exit_code": code,
        "command": command,
        "output": str(run_out),
        "flash": flash_info,
    }


def build_console_image(device: dict, device_out: Path,
                        env: dict[str, str]) -> Path:
    # Console and display probes have the same VFS contract. A per-fixture
    # make_image.py used to duplicate pinned offsets (or be missing entirely).
    for path in reversed(env.get("PYTHONPATH", "").split(os.pathsep)):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    from run_profile_ui_test import build_image

    built = build_image(SimpleNamespace(
        base=ROOT / device["base"], files_dir=ROOT / device["files_dir"],
        flash_size=int(device["flash_size"], 0),
        vfs_offset=int(device["vfs_offset"], 0),
        vfs_size=int(device["vfs_size"], 0),
        preserve_vfs=True, mklittlefs=None, prog_size=32, out_dir=device_out,
    ))
    return built.rename(device_out / "uiflow2-console-test.bin")


def _apply_console_qom_sets(qmp, sets: list) -> dict[str, object]:
    """Apply QOM writes through the console QMP channel.

    Console cases can request a runtime controller transition once a guest
    serial marker proves the pre-transition phase finished (for example the
    LCD_CAM frame-counter animation only starts after the static frame
    digest was captured).  The guest observes the change through the modelled
    controller state, never through injected frame data.
    """
    applied: dict[str, object] = {}
    for spec in sets:
        path, prop, value = spec
        qmp.cmd("qom-set", path=path, property=prop, value=value)
        reply = qmp.cmd("qom-get", path=path, property=prop)
        applied[f"{path}.{prop}"] = reply.get("return")
    return applied


def _check_console_qom(device: dict, qmp, deadline: float
                       ) -> tuple[bool, dict, str]:
    """Read QOM values from a live console QEMU after the serial markers.

    Console cases have no display-frame contract, so a controller-level value
    (for example the decoded RMT RGB chain) is read through QMP with the same
    guest session that produced the serial markers.  ``min`` is used for
    monotonic counters, ``expect`` for exact integers.
    """
    expectations = device.get("qom_expect") or []
    if not expectations:
        return True, {}, ""
    if qmp is None:
        return False, {}, "QOM expectations require an injected-input QMP console"
    remaining = [dict(spec) for spec in expectations]
    observed: dict[str, object] = {}
    while True:
        for spec in list(remaining):
            reply = qmp.cmd("qom-get", path=spec["path"],
                            property=spec["property"])
            value = reply.get("return")
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                numeric = None
            if "min" in spec:
                matched = numeric is not None and numeric >= int(spec["min"])
            else:
                matched = numeric is not None and numeric == int(spec["expect"])
            if matched:
                observed[f"{spec['path']}.{spec['property']}"] = value
                remaining.remove(spec)
        if not remaining:
            return True, observed, ""
        if time.time() >= deadline:
            pending = json.dumps(remaining, ensure_ascii=False)
            return False, observed, pending
        time.sleep(0.1)


def send_console_inputs(qmp, inputs, frame, settle, serial, deadline,
                        after_markers=()):
    """Keep each input pulse unchanged, then fence on guest draw completion."""
    from run_profile_ui_test import send_input

    if after_markers and (not isinstance(after_markers, (list, tuple))
        or len(after_markers) != len(inputs) or any(
        not isinstance(marker, str) or not marker for marker in after_markers
    )):
        raise ValueError("input_after_markers must name one marker per input")
    observations = []

    class Recorder:
        def cmd(self, name, **arguments):
            sent = time.monotonic()
            result = qmp.cmd(name, **arguments)
            if name == "input-send-event":
                observations[-1]["events"].append({
                    "sent_monotonic": sent,
                    "acked_monotonic": time.monotonic(),
                    "events": arguments["events"],
                })
            return result

    for index, spec in enumerate(inputs):
        offset = serial.stat().st_size if serial.exists() else 0
        row = {"spec": spec, "events": [], "serial_offset": offset}
        observations.append(row)
        send_input(Recorder(), spec, frame, settle)
        if after_markers:
            marker = after_markers[index]
            row["after_marker"] = marker
            while time.time() < deadline:
                text = serial.read_bytes()[offset:].decode(errors="replace") if serial.exists() else ""
                if marker in text:
                    row["after_marker_observed"] = True
                    break
                time.sleep(0.05)
            else:
                row["after_marker_observed"] = False
                return observations, f"guest input completion marker missing: {marker}"
    return observations, None


def run_console(
    device: dict,
    backend: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    image = build_console_image(device, device_out, env)
    case_env = env.copy()
    case_env.update(device.get("env", {}))
    # Deterministic host-side PCM fixture for a board-local PDM/I2S capture
    # path.  The guest must consume it through the real DMA descriptors; the
    # host never writes guest buffers or values.
    microphone_fixture = None
    fixture = device.get("microphone_fixture")
    if fixture:
        microphone_fixture = device_out / str(
            fixture.get("file", "microphone-source.pcm")
        )
        sample_count = int(fixture.get("samples", 16000))
        signed = b"".join(
            struct.pack("<h", ((index * 137) % 20000) - 10000)
            for index in range(sample_count)
        )
        microphone_fixture.write_bytes(signed)
        case_env["M5SW_I2S_RX_PCM_FILE"] = str(microphone_fixture)
    rmt_nec = device.get("rmt_nec")
    rmt_capture = None
    if rmt_nec:
        rmt_capture = Path(rmt_nec["capture"]).with_name(
            f"{device['id']}-{Path(rmt_nec['capture']).name}"
        )
        rmt_capture = device_out / rmt_capture.name
        case_env["M5SW_RMT_TX_FILE"] = str(rmt_capture)
    pcm = device.get("pcm")
    pcm_capture = None
    if pcm:
        pcm_capture = device_out / pcm.get("file", "audio.pcm")
        case_env["M5SW_I2S_PCM_FILE"] = str(pcm_capture)
    flash_info = {"transport": "host-image", "verified": True}
    esp_emu_chip = backend.get("esp_emu_chip")
    qemu_esptool_chip = backend.get("qemu_esptool_chip")
    if flash_transport == "esp-emu" and (esp_emu_chip or qemu_esptool_chip):
        try:
            flash_args = dict(
                chip=esp_emu_chip or qemu_esptool_chip,
                image=image,
                flash_size=int(device["flash_size"], 0),
                out_dir=device_out / "flash",
                env=case_env,
                timeout=max(device.get("timeout", 20), 120),
            )
            if esp_emu_chip:
                flash_info = flash_with_esp_emu(**flash_args)
            else:
                flash_info = flash_with_qemu(
                    **flash_args, machine=device["machine"],
                    qemu=ROOT / backend["qemu"],
                    rom_dir=ROOT / backend["rom_dir"],
                    memory=device.get("memory"),
                )
            image = Path(flash_info["virtual_flash"])
        except Exception as error:
            return {
                "status": "FAIL",
                "exit_code": 1,
                "output": str(device_out),
                "flash": {
                    "transport": "esp-emu-esptool" if esp_emu_chip else "qemu-esptool",
                    "verified": False,
                    "error": str(error),
                },
                "reason": str(error),
            }
    serial = device_out / "serial.log"
    command = [
        str(ROOT / backend["qemu"]),
        "-M", device["machine"],
        "-drive", f"file={image},if=mtd,format=raw",
        "-L", str(ROOT / backend["rom_dir"]),
        "-display", "none",
    ]
    if "memory" in device:
        command.extend(["-m", str(device["memory"])])
    from run_profile_ui_test import efuse_image

    efuse_driver = device.get("efuse_driver", backend["efuse_driver"])
    efuse = device_out / "efuse.bin"
    efuse.write_bytes(efuse_image(device.get("efuse_pkg_version", 0), efuse_driver))
    if efuse_driver != "none":
        command.extend([
            "-drive", f"if=none,id=efuse,file={efuse},format=raw",
            "-global", f"driver={efuse_driver},property=drive,value=efuse",
        ])
    # The console probe channel depends on the board's physical UART
    # assignment.  NanoC6 observes UART2 in the third slot; ESP32-S3 boards
    # without a USB model keep the console on UART0 in the first slot.
    console_serial = int(device.get("serial_index", 2))
    for index in range(3):
        command.extend([
            "-serial",
            f"file:{serial}" if index == console_serial else "null",
        ])
    # Console cases may inject host key events through QMP after a guest
    # readiness marker (for example a device-local button case).  The panel
    # input handler then drives the real GPIO/controller path, so the guest
    # observes the press through the same registers as physical input.
    inputs = device.get("input") or []
    if isinstance(inputs, str):
        inputs = [inputs]
    qom_markers = device.get("qom_set_on_marker") or []
    qmp_path = None
    if inputs or qom_markers:
        qmp_path = Path("/tmp") / f"m5-console-{os.getpid()}-{device['id']}.sock"
        try:
            qmp_path.unlink()
        except FileNotFoundError:
            pass
        command.extend([
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
        ])
    deadline = time.time() + device.get("timeout", 20)
    proc = subprocess.Popen(
        command, cwd=ROOT, env=case_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    expected = device["serial_expect"]
    matched = False
    qmp = None
    qom_detail = None
    qom_error = None
    input_observations = []
    input_error = None
    qom_transitions: dict[str, object] = {}
    qom_markers_pending = [
        (spec["marker"], list(spec.get("set") or [])) for spec in qom_markers
    ]
    injected = not inputs
    try:
        while time.time() < deadline:
            text = serial.read_text(errors="replace") if serial.exists() else ""
            for entry in list(qom_markers_pending):
                marker, sets = entry
                if marker not in text:
                    continue
                from run_profile_ui_test import wait_qmp

                if qmp is None:
                    qmp = wait_qmp(
                        qmp_path, timeout=max(1.0, deadline - time.time())
                    )
                qom_transitions.update(_apply_console_qom_sets(qmp, sets))
                qom_markers_pending.remove(entry)
            if not injected:
                pre_marker = device.get("pre_input_marker")
                if pre_marker is None or pre_marker in text:
                    from run_profile_ui_test import wait_qmp

                    if qmp is None:
                        qmp = wait_qmp(
                            qmp_path, timeout=max(1.0, deadline - time.time())
                        )
                    # Let the guest enter its event loop before the first
                    # injected key event; the readiness marker is printed
                    # immediately before the loop starts.
                    time.sleep(0.3)
                    frame = tuple(
                        int(value)
                        for value in device.get(
                            "input_frame", (320, 240)
                        )
                    )
                    input_observations, input_error = send_console_inputs(
                        qmp, inputs, frame,
                        device.get("post_input_wait", 0.3), serial, deadline,
                        device.get("input_after_markers", ()),
                    )
                    injected = True
                    if input_error:
                        break
                    continue
            if all(marker in text for marker in expected):
                matched = True
                if device.get("qom_expect"):
                    qom_ok, qom_observed, pending = _check_console_qom(
                        device, qmp, deadline
                    )
                    qom_detail = qom_observed
                    if not qom_ok:
                        qom_error = pending
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        if qmp is not None:
            qmp.close()
        if qmp_path is not None:
            try:
                qmp_path.unlink()
            except FileNotFoundError:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    text = serial.read_text(errors="replace") if serial.exists() else ""
    missing = [marker for marker in expected if marker not in text]
    if input_error:
        missing.append(input_error)
    if matched and qom_error is not None:
        missing.append("QOM validation: " + qom_error)
    if matched and qom_markers_pending:
        missing.append(
            "QOM transition markers not reached: "
            + json.dumps([marker for marker, _ in qom_markers_pending])
        )
    if matched and qom_transitions:
        qom_detail = dict(qom_detail or {})
        qom_detail.update(qom_transitions)
    pcm_detail = None
    if matched and pcm and pcm_capture:
        pcm_command = [
            sys.executable,
            str(ROOT / "tests/uiflow2/check_pcm.py"),
            str(pcm_capture),
        ]
        if "min_nonzero" in pcm:
            pcm_command.extend(["--min-nonzero", str(pcm["min_nonzero"])])
        if "min_peak_to_peak" in pcm:
            pcm_command.extend(
                ["--min-peak-to-peak", str(pcm["min_peak_to_peak"])]
            )
        validation = subprocess.run(
            pcm_command,
            cwd=ROOT,
            env=case_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        pcm_detail = validation.stdout.strip()
        if validation.returncode:
            missing.append("PCM validation: " + pcm_detail)
    if matched and not missing and rmt_nec and rmt_capture:
        validation = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/uiflow2/check_rmt_nec.py"),
                str(rmt_capture),
                "--address", hex(int(rmt_nec["address"])),
                "--command", hex(int(rmt_nec["command"])),
            ],
            cwd=ROOT,
            env=case_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if validation.returncode == 0:
            return {
                "status": "PASS",
                "exit_code": 0,
                "command": command,
                "output": str(device_out),
                "flash": flash_info,
                "rmt_nec": validation.stdout.strip(),
                **({"input_observations": input_observations} if input_observations else {}),
                **({"pcm": pcm_detail} if pcm_detail else {}),
                **({"qom": qom_detail} if qom_detail else {}),
                **({"microphone_fixture": str(microphone_fixture)}
                   if microphone_fixture else {}),
            }
        missing.append("RMT validation: " + validation.stdout.strip())
    elif matched and not missing:
        return {
            "status": "PASS",
            "exit_code": 0,
            "command": command,
            "output": str(device_out),
            "flash": flash_info,
            **({"input_observations": input_observations} if input_observations else {}),
            **({"pcm": pcm_detail} if pcm_detail else {}),
            **({"qom": qom_detail} if qom_detail else {}),
            **({"microphone_fixture": str(microphone_fixture)}
               if microphone_fixture else {}),
        }
    return {
        "status": "FAIL",
        "exit_code": 1,
        "command": command,
        "output": str(device_out),
        "flash": flash_info,
        "reason": f"missing serial markers: {', '.join(missing)}",
        **({"input_observations": input_observations} if input_observations else {}),
    }


def run_firmware(
    device: dict,
    backend: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    """Run a prebuilt external firmware image and collect serial evidence.

    This lane is for factory/vendor images that have no injectable MicroPython
    filesystem.  The case PASSes only when the declared serial markers appear;
    it does not claim more than the markers say.  Deterministic icount mode is
    used when the case sets "deterministic", because some legacy Arduino-era
    images depend on interrupt/timer timing that is otherwise host-speed
    dependent.
    """
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    image = ROOT / device["base"]
    if not image.is_file():
        return {
            "status": "FAIL",
            "exit_code": 1,
            "output": str(device_out),
            "flash": {"transport": "host-image", "verified": False},
            "reason": (
                f"missing firmware image {image}; run the pinned extraction "
                "tool documented in the device evidence README"
            ),
        }
    case_env = env.copy()
    case_env.update(device.get("env", {}))
    serial = device_out / "serial.log"
    command = [
        str(ROOT / backend["qemu"]),
        "-M", device["machine"],
        "-drive", f"file={image},if=mtd,format=raw",
        "-L", str(ROOT / backend["rom_dir"]),
        "-display", "none",
    ]
    if device.get("deterministic"):
        command[1:1] = [
            "-accel", "tcg,thread=single",
            "-icount", device.get("icount", "shift=2,align=off,sleep=off"),
        ]
    console_serial = int(device.get("serial_index", 0))
    for index in range(3):
        command.extend([
            "-serial",
            f"file:{serial}" if index == console_serial else "null",
        ])
    deadline = time.time() + device.get("timeout", 120)
    proc = subprocess.Popen(
        command, cwd=ROOT, env=case_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    expected = device.get("serial_expect", [])
    if isinstance(expected, str):
        expected = [expected]
    matched = False
    try:
        while time.time() < deadline:
            text = serial.read_text(errors="replace") if serial.exists() else ""
            if expected and all(marker in text for marker in expected):
                matched = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    text = serial.read_text(errors="replace") if serial.exists() else ""
    missing = [marker for marker in expected if marker not in text]
    if matched and not missing:
        return {
            "status": "PASS",
            "exit_code": 0,
            "command": command,
            "output": str(device_out),
            "flash": {"transport": "host-image", "verified": True},
            "serial_markers": expected,
            "note": device.get("expected_blocked", ""),
        }
    return {
        "status": "FAIL",
        "exit_code": 1,
        "command": command,
        "output": str(device_out),
        "flash": {"transport": "host-image", "verified": True},
        "reason": f"missing serial markers: {', '.join(missing)}",
    }


def run_kernel(
    device: dict,
    backend: dict,
    out_dir: Path,
    env: dict[str, str],
) -> dict:
    """Boot a directly loadable probe ELF with -kernel and check markers.

    This lane covers committed bare-metal probe images (for example the
    M5StickT2 thermal probe) that have no flash partition layout and are
    loaded into RAM by the machine's ELF loader.
    """
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    image = ROOT / device["kernel"]
    if not image.is_file():
        return {
            "status": "FAIL",
            "exit_code": 1,
            "output": str(device_out),
            "reason": (
                f"missing probe ELF {image}; build it with "
                f"{device.get('build', 'tests/uiflow2/stickt2_probe/build.sh')}"
            ),
        }
    case_env = env.copy()
    case_env.update(device.get("env", {}))
    serial = device_out / "serial.log"
    command = [
        str(ROOT / backend["qemu"]),
        "-M", device["machine"],
        "-accel", "tcg,thread=single",
        "-kernel", str(image),
        "-L", str(ROOT / backend["rom_dir"]),
        "-display", "none",
    ]
    for index in range(3):
        command.extend([
            "-serial",
            f"file:{serial}" if index == device.get("serial_index", 0)
            else "null",
        ])
    deadline = time.time() + device.get("timeout", 60)
    proc = subprocess.Popen(
        command, cwd=ROOT, env=case_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    expected = device.get("serial_expect", [])
    if isinstance(expected, str):
        expected = [expected]
    matched = False
    try:
        while time.time() < deadline:
            text = serial.read_text(errors="replace") if serial.exists() else ""
            if expected and all(marker in text for marker in expected):
                matched = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    text = serial.read_text(errors="replace") if serial.exists() else ""
    missing = [marker for marker in expected if marker not in text]
    if matched and not missing:
        return {
            "status": "PASS",
            "exit_code": 0,
            "command": command,
            "output": str(device_out),
            "flash": {"transport": "kernel-elf", "verified": True},
            "serial_markers": expected,
            "note": device.get("expected_blocked", ""),
        }
    return {
        "status": "FAIL",
        "exit_code": 1,
        "command": command,
        "output": str(device_out),
        "flash": {"transport": "kernel-elf", "verified": True},
        "reason": f"missing serial markers: {', '.join(missing)}",
    }


def run_blocked_smoke(device: dict, out_dir: Path,
                      env: dict[str, str]) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    command = [
        str(ROOT / device["emulator"]),
        "--chip", "esp32p4",
        "--firmware", str(ROOT / device["base"]),
        "--timeout", f"{device.get('timeout', 12)}s",
        "--console", "uart0",
    ]
    code, stdout = run_logged(
        device["id"], command, out_dir, device.get("timeout", 12) + 10, env
    )
    stderr = (out_dir / f"{device['id']}.stderr").read_text(errors="replace")
    text = stdout + stderr
    if device["expected_error"] in text:
        return {
            "status": "BLOCKED",
            "exit_code": code,
            "command": command,
            "output": str(device_out),
            "reason": device["reason"],
        }
    return {
        "status": "FAIL",
        "exit_code": code,
        "command": command,
        "output": str(device_out),
        "reason": f"expected failure marker not observed: {device['expected_error']}",
    }


def run_tab5(
    device: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(TAB5_RUNNER),
        "--base", str(ROOT / device["base"]),
        "--elf", str(ROOT / device["elf"]),
        "--files-dir", str(ROOT / device["files_dir"]),
        "--out-dir", str(device_out),
        "--emulator", str(ROOT / device["emulator"]),
        "--rom", str(ROOT / device["rom"]),
        "--efuse", str(ROOT / device["efuse"]),
        "--c6-firmware", str(ROOT / device["c6_firmware"]),
        "--expected-size", device["expected_size"],
        "--touch", device["touch"],
        "--timeout", str(device.get("timeout", 120)),
        "--flash-transport",
        "esptool" if flash_transport == "esp-emu" else "host-image",
    ]
    code, stdout = run_logged(
        device["id"],
        command,
        out_dir,
        device.get("matrix_timeout", 420),
        env,
    )
    result_path = device_out / "result.json"
    detail = (
        json.loads(result_path.read_text())
        if result_path.is_file()
        else {}
    )
    passed = code == 0 and "PASS " in stdout
    return {
        "status": "PASS" if passed else "FAIL",
        "exit_code": code,
        "command": command,
        "output": str(device_out),
        "flash": detail.get("flash", {
            "transport": "esp-emu-esptool" if flash_transport == "esp-emu"
            else "host-image",
            "verified": False,
        }),
        "detail": detail,
        **({} if passed else {"reason": stdout[-1200:]}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append", default=[],
                        help="device id; repeat to select multiple")
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/tmp/m5-uiflow2-device-matrix"))
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--matrix", type=Path, default=MATRIX,
                        help="explicit matrix source; defaults to the tracked registry")
    parser.add_argument("--write-resolved-matrix", type=Path,
                        help="write actual base VFS layouts and exit without launching guests")
    parser.add_argument(
        "--flash-transport",
        choices=("direct", "esp-emu"),
        default="esp-emu",
        help="flash the test image through esptool where supported",
    )
    parser.add_argument(
        "--allow-retries",
        action="store_true",
        help=(
            "allow devices that explicitly configure retries; disabled by "
            "default so a retry success cannot be reported as a clean PASS"
        ),
    )
    args = parser.parse_args()

    matrix = json.loads(args.matrix.read_text())
    backends = matrix["backends"]
    selected = set(args.device)
    devices = [
        device for device in matrix["devices"]
        if not selected or device["id"] in selected
    ]
    unknown = selected - {device["id"] for device in matrix["devices"]}
    if unknown:
        raise SystemExit(f"unknown device ids: {', '.join(sorted(unknown))}")

    if args.write_resolved_matrix:
        sys.path.insert(0, str(ROOT / "platform/tools"))
        from uiflow_source import uiflow_vfs_layout

        for device in devices:
            if device["mode"] not in {"ui", "console"}:
                continue
            layout = uiflow_vfs_layout((ROOT / device["base"]).read_bytes(),
                                      int(device["flash_size"], 0))
            device["vfs_offset"], device["vfs_size"] = (
                hex(layout["offset"]), hex(layout["size"]))
        args.write_resolved_matrix.parent.mkdir(parents=True, exist_ok=True)
        args.write_resolved_matrix.write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2) + "\n")
        print(f"resolved matrix: {args.write_resolved_matrix}")
        return

    for name, backend in backends.items():
        variable = {"qemu-esp32s3": "M5_QEMU_XTENSA", "qemu-esp32lx6": "M5_QEMU_XTENSA",
                    "qemu-esp32c6": "M5_QEMU_RISCV32"}.get(name)
        if variable and os.environ.get(variable):
            backend["qemu"] = os.environ[variable]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )

    results = {}
    for device in devices:
        print(f"[{device['id']}] {device['mode']}", flush=True)
        if device["mode"] == "ui":
            if int(device.get("retries", 0)) and not args.allow_retries:
                raise SystemExit(
                    f"{device['id']}: retries are configured; remove them "
                    "for clean regression evidence or pass --allow-retries "
                    "for diagnostic-only runs"
                )
            attempts = int(device.get("retries", 0)) + 1
            for attempt in range(attempts):
                attempt_root = (
                    args.out_dir
                    if attempt == 0
                    else args.out_dir / f"retry-{attempt}"
                )
                result = run_ui(
                    device,
                    backends[device["backend"]],
                    attempt_root,
                    env,
                    args.flash_transport,
                )
                result["attempts"] = attempt + 1
                result["retry_used"] = attempt > 0
                if result["status"] == "PASS":
                    break
        elif device["mode"] == "console":
            result = run_console(
                device,
                backends[device["backend"]],
                args.out_dir,
                env,
                args.flash_transport,
            )
        elif device["mode"] == "firmware":
            result = run_firmware(
                device,
                backends[device["backend"]],
                args.out_dir,
                env,
                args.flash_transport,
            )
        elif device["mode"] == "kernel":
            result = run_kernel(
                device,
                backends[device["backend"]],
                args.out_dir,
                env,
            )
        elif device["mode"] == "blocked-smoke":
            result = run_blocked_smoke(device, args.out_dir, env)
        elif device["mode"] == "tab5-gdb-ui":
            result = run_tab5(
                device, args.out_dir, env, args.flash_transport
            )
        elif device["mode"] == "backend-required":
            result = {
                "status": "BLOCKED",
                "exit_code": 0,
                "reason": device["reason"],
            }
        elif device["mode"] == "excluded":
            result = {
                "status": "EXCLUDED",
                "exit_code": 0,
                "reason": device["reason"],
            }
        else:
            result = {
                "status": "FAIL",
                "exit_code": 2,
                "reason": f"unsupported mode: {device['mode']}",
            }
        results[device["id"]] = result
        print(f"[{device['id']}] {result['status']}", flush=True)

    summary = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "out_dir": str(args.out_dir),
        "results": results,
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    counts = {
        status: sum(result["status"] == status for result in results.values())
        for status in ("PASS", "FAIL", "BLOCKED", "EXCLUDED")
    }
    print(json.dumps(counts, sort_keys=True))
    if counts["FAIL"] or (counts["BLOCKED"] and not args.allow_blocked):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

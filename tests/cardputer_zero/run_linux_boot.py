#!/usr/bin/env python3
"""Boot the official CardputerZero ARM64 image on the QEMU BCM2837 machine."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build-aarch64/qemu-system-aarch64"
)
DEFAULT_IMAGE = (
    ROOT
    / ".work/cardputerzero/cardputerzero-trixie-arm64-stable.img"
)
ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)


def normalize_console(text: str) -> str:
    return ANSI_OSC_RE.sub("", ANSI_CSI_RE.sub("", text)).replace("\x00", "")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(16 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qmp_execute(path: Path, execute: str, arguments: dict | None = None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        sock.connect(str(path))
        reader = sock.makefile("rwb")
        greeting = json.loads(reader.readline())
        if "QMP" not in greeting:
            raise RuntimeError(f"unexpected QMP greeting: {greeting}")

        def command(name: str, args: dict | None = None):
            request = {"execute": name}
            if args is not None:
                request["arguments"] = args
            sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
            while True:
                line = reader.readline()
                if not line:
                    raise RuntimeError("QMP connection closed")
                message = json.loads(line)
                if "error" in message:
                    raise RuntimeError(f"QMP {name} failed: {message['error']}")
                if "return" in message:
                    return message["return"]

        command("qmp_capabilities")
        return command(execute, arguments)


def marker_value(text: str, marker: str) -> str | None:
    prefix = marker + "="
    for line in reversed(text.splitlines()):
        if line.startswith(prefix):
            values = line[len(prefix):].split()
            return values[0] if values else ""
    return None


def ethernet_peer(port: int, result: dict) -> None:
    deadline = time.time() + 150
    sock = None
    seen = []
    try:
        while time.time() < deadline:
            if sock is None:
                try:
                    sock = socket.create_connection(
                        ("127.0.0.1", port), timeout=1
                    )
                    sock.settimeout(1)
                except OSError:
                    time.sleep(0.1)
                    continue
            try:
                header = sock.recv(4)
            except socket.timeout:
                continue
            if len(header) != 4:
                sock.close()
                sock = None
                continue
            length = int.from_bytes(header, "big")
            candidate = b""
            while len(candidate) < length:
                try:
                    chunk = sock.recv(length - len(candidate))
                except socket.timeout:
                    continue
                if not chunk:
                    break
                candidate += chunk
            if len(candidate) != length:
                sock.close()
                sock = None
                continue
            seen.append(
                {
                    "length": len(candidate),
                    "ethertype": candidate[12:14].hex(),
                    "prefix": candidate[:32].hex(),
                }
            )
            if (candidate[12:14] == b"\x88\xb5"
                    and b"M5-SR9900A-TX" in candidate):
                guest_mac = bytes.fromhex("020000009900")
                host_mac = bytes.fromhex("020000009901")
                response = (
                    guest_mac + host_mac + b"\x88\xb5" + b"M5-SR9900A-RX"
                )
                if len(response) < 60:
                    response += bytes(60 - len(response))
                sock.sendall(len(response).to_bytes(4, "big") + response)
                result.update(
                    {
                        "status": "PASS",
                        "guest_tx": candidate.hex(),
                        "host_rx": response.hex(),
                    }
                )
                return
        raise RuntimeError(
            f"did not receive SR9900A probe frame; seen={seen}"
        )
    except Exception as error:
        result.update({"status": "FAIL", "error": str(error)})
    finally:
        if sock:
            sock.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/tmp/m5-cardputer-zero-boot"))
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--machine", default="raspi3b")
    parser.add_argument("--memory", default="512M")
    parser.add_argument("--complete-marker")
    parser.add_argument("--post-marker-delay", type=float, default=0)
    parser.add_argument("--qmp-key-event", type=int)
    parser.add_argument("--qmp-key-marker", default="M5_KEY_FRAME_READY")
    parser.add_argument(
        "--qmp-key-path", default="/machine/peripheral/m5-tca8418"
    )
    parser.add_argument("--qmp-ir-inject", action="store_true")
    parser.add_argument("--qmp-ir-marker", default="M5_IR_RX_READY")
    parser.add_argument(
        "--expect-cardputerzero-peripherals", action="store_true"
    )
    parser.add_argument("--expect-audio-gpio24", action="store_true")
    parser.add_argument("--expect-audio-capture", action="store_true")
    parser.add_argument("--expected-audio-capture-sha256")
    parser.add_argument("--qmp-charging-marker")
    parser.add_argument(
        "--qmp-charging-path", default="/machine/peripheral/m5-ip2315"
    )
    parser.add_argument("--expect-charging-control", action="store_true")
    parser.add_argument("--usb-ethernet", action="store_true")
    parser.add_argument("--usb-ethernet-direct", action="store_true")
    parser.add_argument("--hub-high-speed", action="store_true")
    parser.add_argument("--hub-tt-compat", action="store_true")
    parser.add_argument("--usb-ethernet-full-speed", action="store_true")
    parser.add_argument("--expect-hub-tt", action="store_true")
    parser.add_argument("--expected-tt-mask", type=lambda x: int(x, 0), default=1)
    parser.add_argument("--hub-low-speed-hid", action="store_true")
    parser.add_argument("--expect-low-speed-hid", action="store_true")
    parser.add_argument(
        "--expected-usb-speed", choices=("low", "full", "high")
    )
    parser.add_argument(
        "--imx219",
        action="store_true",
        help="attach the Sony IMX219 CCI sensor model to the CSI I2C bus",
    )
    parser.add_argument("--camera-probe", action="store_true")
    parser.add_argument("--expect-camera-capture", action="store_true")
    parser.add_argument("--expect-imx219-controls", action="store_true")
    parser.add_argument("--expected-camera-bytes", type=int)
    parser.add_argument("--expected-camera-sha256")
    parser.add_argument("--net-socket-port", type=int, default=0)
    parser.add_argument("--expect-sr9900a-roundtrip", action="store_true")
    parser.add_argument("--transient", action="store_true")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-size", type=int)
    parser.add_argument("--base-image", type=Path)
    parser.add_argument("--base-sha256")
    parser.add_argument("--base-size", type=int)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--dtb", type=Path)
    parser.add_argument("--initrd", type=Path)
    parser.add_argument(
        "--append",
        default=(
            "console=ttyAMA0,115200 root=PARTUUID=f6c408b0-02 "
            "rootfstype=ext4 rootwait rw earlycon=pl011,0x3f201000"
        ),
    )
    args = parser.parse_args()
    if args.append and args.qmp_key_event is not None:
        if "m5.key_probe=1" not in args.append:
            args.append += " m5.key_probe=1"
    if args.append and args.qmp_charging_marker:
        if "m5.charge_probe=1" not in args.append:
            args.append += " m5.charge_probe=1"
    if args.append and args.usb_ethernet:
        if "m5.usb_eth_probe=1" not in args.append:
            args.append += " m5.usb_eth_probe=1"
    if args.append and args.camera_probe:
        if "m5.camera_probe=1" not in args.append:
            args.append += " m5.camera_probe=1"

    optional_paths = [
        path for path in (args.base_image, args.kernel, args.dtb, args.initrd)
        if path
    ]
    for path in (args.qemu, args.image, *optional_paths):
        if not path.is_file():
            raise SystemExit(f"missing required file: {path}")
    size = args.image.stat().st_size
    if args.expected_size and size != args.expected_size:
        raise SystemExit(
            f"image size {size} does not match expected {args.expected_size}"
        )
    image_hash = sha256(args.image)
    if args.expected_sha256 and image_hash != args.expected_sha256:
        raise SystemExit(
            f"image sha256 {image_hash} does not match "
            f"expected {args.expected_sha256}"
        )
    base_result = None
    if args.base_image:
        if not args.base_image.is_file():
            raise SystemExit(f"missing base image: {args.base_image}")
        base_size = args.base_image.stat().st_size
        base_hash = sha256(args.base_image)
        if args.base_size and base_size != args.base_size:
            raise SystemExit(
                f"base image size {base_size} does not match {args.base_size}"
            )
        if args.base_sha256 and base_hash != args.base_sha256:
            raise SystemExit(
                f"base image sha256 {base_hash} does not match "
                f"{args.base_sha256}"
            )
        base_result = {
            "path": str(args.base_image),
            "size": base_size,
            "sha256": base_hash,
        }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / "console.log"
    qmp_path = args.out_dir / "qmp.sock"
    try:
        qmp_path.unlink()
    except FileNotFoundError:
        pass
    i2c_devices = [
        ("m5-tca8418", "i2c-bus.1", "0x34", "tca8418"),
        ("m5-m5ioe1", "i2c-bus.1", "0x4f", "m5ioe1"),
        ("m5-bmi270", "i2c-bus.1", "0x68", "bmi270"),
        # BMM150 is reached through the BMI270 auxiliary master.  Keep its
        # model on the otherwise-unused SoC bus so the sensor-hub bridge can
        # reference it without colliding with ES8389 at I2C-1 0x10.
        ("m5-bmm150", "i2c-bus.2", "0x10", "bmm150"),
        ("m5-rx8130", "i2c-bus.1", "0x32", "rx8130"),
        ("m5-bq27220", "i2c-bus.1", "0x55", "bq27220"),
        ("m5-es8389", "i2c-bus.1", "0x10", "es8389"),
    ]
    if args.imx219:
        i2c_devices.append(("m5-imx219", "i2c-bus.0", "0x10", "imx219"))
    image_format = (
        "qcow2" if args.image.suffix.lower() in {".qcow2", ".qcow"} else "raw"
    )
    command = [
        str(args.qemu),
        "-M", args.machine,
        "-cpu", "cortex-a53",
        "-smp", "4",
        "-m", args.memory,
        "-drive",
        (
            f"file={args.image},if=sd,format={image_format}"
            + (",snapshot=on" if args.transient else "")
        ),
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
    ]
    if args.transient:
        command.append("-no-reboot")
    if args.kernel:
        command.extend(["-kernel", str(args.kernel)])
        if args.dtb:
            command.extend(["-dtb", str(args.dtb)])
        if args.initrd:
            command.extend(["-initrd", str(args.initrd)])
        command.extend(["-append", args.append])
    for device_id, bus, address, model in i2c_devices:
        command.extend(
            [
                "-device",
                (
                    f"m5sw-i2c-dev,id={device_id},bus={bus},"
                    f"address={address},model={model}"
                ),
            ]
        )
    if not args.usb_ethernet_direct:
        command.extend(
            [
                "-device",
                (
                    "m5sw-gl852g,id=m5-gl852g,bus=usb-bus.0,port=1,"
                    "ports=4"
                    + (",high-speed=on" if args.hub_high_speed else "")
                    + (",tt-compat=on" if args.hub_tt_compat else "")
                ),
            ]
        )
    command.extend(
        [
            "-device",
            (
                "m5sw-ip2315,id=m5-ip2315,charging=on,"
                "vbus-mv=5000,ntc-ohms=100000"
            ),
        ]
    )
    if args.usb_ethernet:
        if not args.net_socket_port:
            raise SystemExit("--usb-ethernet requires --net-socket-port")
        command.extend(
            [
                "-netdev",
                (
                    "socket,id=net0,"
                    f"listen=127.0.0.1:{args.net_socket_port}"
                ),
                "-device",
                (
                    "m5sw-sr9900a,id=m5-sr9900a,bus=usb-bus.0,port="
                    f"{'1' if args.usb_ethernet_direct else '1.1'},"
                    "netdev=net0,mac=02:00:00:00:99:00"
                    + (
                        ",full-speed-only=on"
                        if args.usb_ethernet_full_speed else ""
                    )
                ),
            ]
        )
    if args.hub_low_speed_hid:
        command.extend(
            [
                "-device",
                (
                    "usb-mouse,id=m5-low-speed-hid,bus=usb-bus.0,"
                    "port=1.2,usb_version=1,low-speed-only=on"
                ),
            ]
        )
    started = time.time()
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = started + args.timeout
        linux_seen = False
        userspace_seen = False
        boot_complete_seen = False
        qmp_injection = None
        qmp_ir_injection = None
        qmp_charging_injection = None
        ethernet_result = {}
        qom_values = {}
        ethernet_thread = None
        fatal_error = None
        if args.usb_ethernet:
            ethernet_thread = threading.Thread(
                target=ethernet_peer,
                args=(args.net_socket_port, ethernet_result),
                daemon=True,
            )
            ethernet_thread.start()
        while time.time() < deadline and process.poll() is None:
            text = log_path.read_text(errors="replace") if log_path.exists() else ""
            text = normalize_console(text)
            linux_seen = linux_seen or "Linux version" in text
            userspace_seen = userspace_seen or any(
                marker in text
                for marker in (
                    "systemd-udevd",
                    "systemd[1]:",
                    "Starting kernel",
                )
            )
            if args.complete_marker:
                boot_complete_seen = boot_complete_seen or (
                    args.complete_marker in text
                )
            else:
                boot_complete_seen = boot_complete_seen or any(
                    marker in text
                    for marker in (
                        "Reached target multi-user.target",
                        "Reached target graphical.target",
                        "Startup finished in",
                        "cardputerzero login:",
                        "login:",
                    )
                )
            if (
                args.qmp_key_event is not None
                and qmp_injection is None
                and args.qmp_key_marker in text
            ):
                try:
                    qmp_execute(
                        qmp_path,
                        "qom-set",
                        {
                            "path": args.qmp_key_path,
                            "property": "key-event",
                            "value": args.qmp_key_event,
                        },
                    )
                    qmp_injection = {
                        "status": "PASS",
                        "path": args.qmp_key_path,
                        "property": "key-event",
                        "value": args.qmp_key_event,
                    }
                except Exception as error:
                    qmp_injection = {
                        "status": "FAIL",
                        "error": str(error),
                    }
                    fatal_error = str(error)
                    break
            if (
                args.qmp_charging_marker
                and qmp_charging_injection is None
                and args.qmp_charging_marker in text
            ):
                try:
                    qmp_execute(
                        qmp_path,
                        "qom-set",
                        {
                            "path": args.qmp_charging_path,
                            "property": "charging",
                            "value": False,
                        },
                    )
                    qmp_charging_injection = {
                        "status": "PASS",
                        "path": args.qmp_charging_path,
                        "property": "charging",
                        "value": False,
                    }
                except Exception as error:
                    qmp_charging_injection = {
                        "status": "FAIL",
                        "error": str(error),
                    }
                    fatal_error = str(error)
                    break
            if (
                args.qmp_ir_inject
                and qmp_ir_injection is None
                and args.qmp_ir_marker in text
            ):
                try:
                    qmp_execute(
                        qmp_path,
                        "qom-set",
                        {
                            "path": "/machine/peripheral/m5-tca8418",
                            "property": "ir-rx-start",
                            "value": 1,
                        },
                    )
                    qmp_ir_injection = {"status": "PASS"}
                except Exception as error:
                    qmp_ir_injection = {
                        "status": "FAIL",
                        "error": str(error),
                    }
                    fatal_error = str(error)
                    break
            if boot_complete_seen:
                if args.post_marker_delay > 0:
                    time.sleep(args.post_marker_delay)
                break
            time.sleep(0.5)
        if process.poll() is None:
            qom_requests = []
            if args.expect_hub_tt:
                qom_requests.append(
                    (
                        "/machine/peripheral/m5-gl852g",
                        ("tt-active-port-mask",),
                    )
                )
            if args.expect_imx219_controls:
                qom_requests.append(
                    (
                        "/machine/peripheral/m5-imx219",
                        (
                            "configured",
                            "streaming",
                            "sensor-width",
                            "sensor-height",
                            "lanes",
                            "exposure",
                            "analog-gain",
                            "digital-gain",
                            "test-pattern",
                            "frame-length",
                            "line-length",
                            "frame-interval-ms",
                            "frame-count",
                        ),
                    )
                )
            for path, properties in qom_requests:
                qom_values[path] = {}
                for prop in properties:
                    try:
                        qom_values[path][prop] = qmp_execute(
                            qmp_path,
                            "qom-get",
                            {"path": path, "property": prop},
                        )
                    except Exception as error:
                        qom_values[path][prop] = {"error": str(error)}
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    text = log_path.read_text(errors="replace")
    key_event_hex = marker_value(text, "M5_KEY_EVENT_HEX")
    key_event_ok = (
        args.qmp_key_event is None
        or bool(key_event_hex)
    )
    ir_rx_bytes_text = marker_value(text, "IR_RX_BYTES")
    ir_rx_bytes = (
        int(ir_rx_bytes_text)
        if ir_rx_bytes_text and ir_rx_bytes_text.isdigit()
        else 0
    )
    ir_tx_rc = marker_value(text, "IR_TX_RC")
    ir_ok = (
        not args.qmp_ir_inject
        or (ir_rx_bytes > 0 and ir_tx_rc == "0")
    )
    audio_gpio24_ok = (
        not args.expect_audio_gpio24
        or (
            "[bcm2835-gpio] output pin=24 level=1" in text
            and "gpio-24" in text
            and "out hi" in text
        )
    )
    audio_capture_rc = marker_value(text, "AUDIO_CAPTURE_RC")
    audio_capture_bytes_text = marker_value(text, "AUDIO_CAPTURE_BYTES")
    audio_capture_bytes = (
        int(audio_capture_bytes_text)
        if audio_capture_bytes_text and audio_capture_bytes_text.isdigit()
        else 0
    )
    audio_capture_sha256 = marker_value(text, "AUDIO_CAPTURE_SHA256")
    audio_capture_ok = (
        not args.expect_audio_capture
        or (
            audio_capture_rc == "0"
            and audio_capture_bytes > 44
            and (
                not args.expected_audio_capture_sha256
                or audio_capture_sha256
                == args.expected_audio_capture_sha256
            )
        )
    )
    charge_status_before = marker_value(text, "CHARGE_STATUS_BEFORE")
    charge_status_after = marker_value(text, "CHARGE_STATUS_AFTER")
    charge_current_before = marker_value(text, "CHARGE_CURRENT_BEFORE")
    charge_current_after = marker_value(text, "CHARGE_CURRENT_AFTER")
    charging_control_ok = (
        not args.expect_charging_control
        or (
            qmp_charging_injection is not None
            and qmp_charging_injection["status"] == "PASS"
            and charge_status_before == "Charging,"
            and charge_status_after == "Discharging,"
            and charge_current_before
            and charge_current_after
            and int(charge_current_before.rstrip(","))
            > int(charge_current_after.rstrip(","))
        )
    )
    if ethernet_thread:
        ethernet_thread.join(timeout=20)
    ethernet_roundtrip_ok = (
        not args.expect_sr9900a_roundtrip
        or (
            ethernet_result.get("status") == "PASS"
            and "USB_ETH_ROUNDTRIP=PASS" in text
        )
    )
    usb_speeds = re.findall(
        r"usb 1-1(?:\.\d+)?: new (low|full|high)-speed USB device",
        text,
    )
    usb_device_speed = usb_speeds[-1] if usb_speeds else None
    usb_speed_ok = (
        not args.expected_usb_speed
        or usb_device_speed == args.expected_usb_speed
    )
    camera_stream_rc = marker_value(text, "CAMERA_STREAM_RC")
    camera_frame_bytes_text = marker_value(text, "CAMERA_FRAME_BYTES")
    camera_frame_bytes = (
        int(camera_frame_bytes_text)
        if camera_frame_bytes_text and camera_frame_bytes_text.isdigit()
        else 0
    )
    camera_frame_sha256 = marker_value(text, "CAMERA_FRAME_SHA256")
    camera_capture_ok = (
        not args.expect_camera_capture
        or (
            "UNICAM_DRIVER=unicam" in text
            and "/dev/video0" in text
            and camera_stream_rc == "0"
            and camera_frame_bytes > 0
            and (
                not args.expected_camera_bytes
                or camera_frame_bytes == args.expected_camera_bytes
            )
            and (
                not args.expected_camera_sha256
                or camera_frame_sha256 == args.expected_camera_sha256
            )
        )
    )
    imx219_qom = qom_values.get("/machine/peripheral/m5-imx219", {})
    imx219_controls_ok = (
        not args.expect_imx219_controls
        or (
            imx219_qom.get("configured") is True
            and imx219_qom.get("sensor-width") == 640
            and imx219_qom.get("sensor-height") == 480
            and imx219_qom.get("lanes") == 1
            and imx219_qom.get("test-pattern") == 1
            and imx219_qom.get("exposure") == 500
            and imx219_qom.get("analog-gain") == 64
            and imx219_qom.get("digital-gain") == 0x140
            and isinstance(imx219_qom.get("frame-interval-ms"), int)
            and 15 <= imx219_qom.get("frame-interval-ms") <= 18
            and isinstance(imx219_qom.get("frame-count"), int)
            and imx219_qom.get("frame-count") > 0
        )
    )
    hub_qom = qom_values.get("/machine/peripheral/m5-gl852g", {})
    hub_tt_ok = (
        not args.expect_hub_tt
        or (
            isinstance(hub_qom.get("tt-active-port-mask"), int)
            and hub_qom.get("tt-active-port-mask") == args.expected_tt_mask
        )
    )
    low_speed_hid_ok = (
        not args.expect_low_speed_hid
        or (
            "USB_ID=0627:0001" in text
            and "USB_PRODUCT=QEMU USB Mouse" in text
            and "INPUT_NAME=QEMU QEMU USB Mouse" in text
        )
    )
    peripheral_checks = {}
    if args.expect_cardputerzero_peripherals:
        peripheral_checks = {
            "linux_boot": "Linux version" in text,
            "tca8418_driver": "DRIVER=tca8418_keypad" in text,
            "m5ioe1_driver": "DRIVER=m5ioe1-gpio" in text,
            "bmi270_driver": "DRIVER=bmi270_i2c" in text,
            "bmm150_driver": "IIO_NAME=bmm150" in text,
            "rx8130_driver": "DRIVER=rtc-ds1307" in text,
            "bq27220_driver": "DRIVER=bq27xxx-battery" in text,
            "es8389_driver": "DRIVER=es8389" in text,
            "es8389_chip_id": "ES8389_CHIP_ID=0x83:0x89" in text,
            "es8389_state": "ES8389_STATE=0x0" in text,
            "gl852g_hub": "USB_ID=05e3:0610" in text,
            "sr9900a_ethernet": (
                not args.usb_ethernet
                or "USB_ID=0fe6:9900" in text
            ),
            "r8152_driver": (
                not args.usb_ethernet
                or "USB_ETH_DRIVER=r8152" in text
            ),
            "input_device": "INPUT_NAME=tca8418c" in text,
            "battery_voltage": "POWER_VOLTAGE_NOW=4000000" in text,
            "battery_current": "POWER_CURRENT_NOW=250000" in text,
            "battery_capacity": "POWER_CAPACITY=87" in text,
            "battery_design_capacity": (
                "POWER_CHARGE_FULL_DESIGN=1750000" in text
            ),
            "panel_drm": "DRM_NAME=card0-SPI-1" in text,
            "audio_card": "0 [ES8388Audio" in text,
            "lirc_receiver": "RC_DEVICE=rc1" in text,
            "framebuffer_320x170": (
                "M5_KEY_FRAME_READY" in text
                and "WIDTH=320 HEIGHT=170" in text
                and "BPP=16" in text
            ),
            "no_bcm_external_abort": "synchronous external abort" not in text,
        }
    peripheral_checks_ok = all(peripheral_checks.values())
    result = {
        "schema_version": 1,
        "status": (
            "PASS"
            if (
                boot_complete_seen
                and fatal_error is None
                and key_event_ok
                and ir_ok
                and audio_gpio24_ok
                and audio_capture_ok
                and charging_control_ok
                and ethernet_roundtrip_ok
                and usb_speed_ok
                and hub_tt_ok
                and low_speed_hid_ok
                and camera_capture_ok
                and imx219_controls_ok
                and peripheral_checks_ok
            )
            else "FAIL"
        ),
        "machine": args.machine,
        "memory": args.memory,
        "image": str(args.image),
        "image_size": size,
        "image_sha256": image_hash,
        "image_format": image_format,
        "base_image": base_result,
        "elapsed_seconds": round(time.time() - started, 3),
        "qemu_exit_code": process.returncode,
        "linux_seen": linux_seen,
        "userspace_seen": userspace_seen,
        "boot_complete_seen": boot_complete_seen,
        "console_log": str(log_path),
        "qmp_socket": str(qmp_path),
        "i2c_devices": [
            {"id": device_id, "bus": bus, "address": address, "model": model}
            for device_id, bus, address, model in i2c_devices
        ],
        "qmp_injection": qmp_injection,
        "qmp_ir_injection": qmp_ir_injection,
        "qmp_charging_injection": qmp_charging_injection,
        "ethernet_peer": ethernet_result,
        "ir_rx_bytes": ir_rx_bytes,
        "ir_tx_rc": ir_tx_rc,
        "ir_ok": ir_ok,
        "audio_gpio24_ok": audio_gpio24_ok,
        "audio_capture_rc": audio_capture_rc,
        "audio_capture_bytes": audio_capture_bytes,
        "audio_capture_sha256": audio_capture_sha256,
        "audio_capture_ok": audio_capture_ok,
        "charge_status_before": charge_status_before,
        "charge_status_after": charge_status_after,
        "charge_current_before": charge_current_before,
        "charge_current_after": charge_current_after,
        "charging_control_ok": charging_control_ok,
        "ethernet_roundtrip_ok": ethernet_roundtrip_ok,
        "usb_device_speed": usb_device_speed,
        "usb_speed_ok": usb_speed_ok,
        "hub_qom": hub_qom,
        "hub_tt_ok": hub_tt_ok,
        "low_speed_hid_ok": low_speed_hid_ok,
        "camera_stream_rc": camera_stream_rc,
        "camera_frame_bytes": camera_frame_bytes,
        "camera_frame_sha256": camera_frame_sha256,
        "camera_capture_ok": camera_capture_ok,
        "camera_qom": imx219_qom,
        "camera_controls_ok": imx219_controls_ok,
        "key_event_hex": key_event_hex,
        "key_event_ok": key_event_ok,
        "peripheral_checks": peripheral_checks,
        "peripheral_checks_ok": peripheral_checks_ok,
        "frame_before_sha256": marker_value(text, "M5_FRAME_BEFORE_SHA256"),
        "frame_after_sha256": marker_value(text, "M5_FRAME_AFTER_SHA256"),
        "error": fatal_error,
        "command": command,
    }
    (args.out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    if (
        not boot_complete_seen
        or fatal_error is not None
        or not key_event_ok
        or not ir_ok
        or not audio_gpio24_ok
        or not audio_capture_ok
        or not charging_control_ok
        or not ethernet_roundtrip_ok
        or not usb_speed_ok
        or not hub_tt_ok
        or not low_speed_hid_ok
        or not camera_capture_ok
        or not imx219_controls_ok
        or not peripheral_checks_ok
        or (
            args.qmp_ir_inject
            and (
                qmp_ir_injection is None
                or qmp_ir_injection["status"] != "PASS"
            )
        )
        or (
            qmp_injection is not None
            and qmp_injection["status"] != "PASS"
        )
    ):
        tail = "\n".join(text.splitlines()[-40:])
        raise SystemExit(f"Linux key/frame probe failed\n{tail}")
    print(
        f"PASS machine={args.machine} memory={args.memory} "
        f"image={args.image.name} "
        f"userspace={int(userspace_seen)} "
        f"complete={int(boot_complete_seen)} "
        f"elapsed={result['elapsed_seconds']}s"
    )


if __name__ == "__main__":
    main()

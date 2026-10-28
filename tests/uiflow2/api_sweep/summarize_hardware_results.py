#!/usr/bin/env python3
"""Join hardware inventory to retained real-session observations conservatively.

Presence, configuration assertions and controller data-plane assertions remain
distinct result categories. Every inventory API receives a per-device row;
unexecuted methods retain a concrete recipe blocker instead of becoming PASS.
"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile


def canonical(api):
    api = api.replace("M5.ALS.", "M5.Als.").replace(".config().", ".config.")
    return re.sub(r"^M5\.Btn(?:A|B|C|PWR|EXT)\.", "M5.Button.", api)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, default=Path(__file__).with_name("inventory_hardware.source.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    observations = {}
    reports = {}
    power_attempts = {}
    pcm_oracles = {}
    wav_oracles = {}
    camera_oracles = {}
    storage_oracles = {}
    touch_oracles = {}

    def recorded_at(report_path):
        created = report_path.with_name("created.json")
        if created.is_file():
            return json.loads(created.read_text()).get("created_at", "")
        return ""

    for report_path in sorted(args.raw_root.glob("*/report.json"), key=recorded_at):
        report = json.loads(report_path.read_text())
        device = report.get("device_id")
        if device not in inventory["devices"]:
            continue
        folder = report_path.parent
        serial_path = folder / "serial.txt"
        if not serial_path.is_file():
            continue
        reference = str(folder)
        reports[reference] = {key: report.get(key) for key in ("session_id", "firmware_sha256", "base_sha256", "runtime_binary_sha256", "source_sha256", "evidence_sha256", "status", "cleanup", "error")}
        serial_text = serial_path.read_text(errors="replace")
        oracle_path = folder / "pcm-oracle.json"
        if oracle_path.is_file():
            pcm_oracles.setdefault(device, []).append((oracle_path, json.loads(oracle_path.read_text())))
        wav_path = folder / "wav-oracle.json"
        if wav_path.is_file():
            wav_oracles.setdefault(device, []).append((wav_path, json.loads(wav_path.read_text())))
        camera_path = folder / "camera-oracle.json"
        if camera_path.is_file():
            camera_oracles.setdefault(device, []).append((camera_path, json.loads(camera_path.read_text())))
        storage_path = folder / "storage-oracle.json"
        if storage_path.is_file():
            storage_oracles.setdefault(device, []).append((storage_path, json.loads(storage_path.read_text())))
        touch_path = folder / "touch-oracle.json"
        if touch_path.is_file():
            touch_oracles.setdefault(device, []).append((touch_path, json.loads(touch_path.read_text())))
        for kind in ("lightSleep", "deepSleep", "timerSleep", "powerOff"):
            if "HARDWARE_POWER_CALL_START " + kind not in serial_text:
                continue
            attempt = {"report": str(report_path), "serial": str(serial_path), "session_id": report.get("session_id"), "firmware_sha256": report.get("firmware_sha256"), "evidence_sha256": report.get("evidence_sha256"), "source_entered": True, "completed": report.get("status") == "EXECUTED"}
            try:
                with zipfile.ZipFile(folder / "evidence.zip") as archive:
                    manifest = json.loads(archive.read("manifest.json"))
                started = next(row["at"] for row in manifest["timeline"] if row.get("event") == "state" and row.get("to") == "running")
                attempt["running_observation_seconds"] = (datetime.fromisoformat(manifest["generated_at"]) - datetime.fromisoformat(started)).total_seconds()
            except (OSError, ValueError, KeyError, StopIteration):
                pass
            power_attempts.setdefault((device, "M5.Power." + kind), []).append(attempt)
        for line_number, text in enumerate(serial_text.splitlines(), 1):
            for prefix in ("HARDWARE_API ", "HARDWARE_LIFECYCLE "):
                if prefix not in text:
                    continue
                try:
                    row = json.loads(text.split(prefix, 1)[1])
                except ValueError:
                    continue
                row["evidence"] = {"report": reference + "/report.json", "serial": reference + "/serial.txt", "line": line_number, "session_id": report.get("session_id"), "firmware_sha256": report.get("firmware_sha256"), "base_sha256": report.get("base_sha256"), "runtime_binary_sha256": report.get("runtime_binary_sha256"), "evidence_sha256": report.get("evidence_sha256")}
                observations.setdefault((device, canonical(row["api"])), []).append(row)

    result = []
    for device in inventory["devices"]:
        for item in inventory["entries"]:
            api = item["api"]
            seen = observations.get((device, api), [])
            present = [row for row in seen if row["status"] == "PRESENT"]
            absent = [row for row in seen if row["status"] == "ABSENT"]
            asserted = [row for row in seen if row["status"] == "API_ASSERTION_PASS"]
            successful = [row for row in seen if row["status"] == "CALL_OK"]
            row = {"api": api, "device": device, "status": "BLOCKED", "oracle": item["test_strategy"], "required_evidence": item["required_evidence"], "required_evidence_met": False, "recipe_id": item["recipe_id"], "evidence": [], "blocker": api + ": " + item["test_strategy"] + " The retained sessions do not yet establish every required assertion for this method."}
            board_missing = (
                device == "cardputer-adv" and (api.startswith(("M5.Touch", "M5.Als", "camera.")) or api == "M5.Imu.getMag")
                or device == "cores3" and api.startswith(("hardware.Keyboard", "hardware.RGB", "hardware.IR"))
                or item["recipe_id"] == "other-board-hardware"
            )
            if board_missing:
                row.update(status="UNAVAILABLE", blocker=None, oracle="Selected-board capability boundary: this public API targets hardware absent from " + device + "; imports/default zero values are not functional evidence.")
            elif item["kind"] == "constant" and present:
                latest = present[-1]
                value = latest.get("value")
                if isinstance(value, dict) and "value" in value:
                    row.update(status="VALUE_OBSERVED", required_evidence_met=True, blocker=None, oracle="Public constant value/type recorded on exact firmware; this is constant availability only.", observed=value)
                    row["evidence"] = [latest["evidence"]]
                else:
                    row.update(status="PRESENT", oracle="Public constant export found; its numeric value was not captured by this older reflection probe.")
                    row["evidence"] = [latest["evidence"]]
            elif item["recipe_id"] == "config-roundtrip" and asserted:
                latest = asserted[-1]
                row.update(status="CONFIG_ASSERTION_PASS", required_evidence_met=True, blocker=None, oracle="Stopped-subsystem configuration object/getter/setter roundtrip matched and original settings restored; no peripheral data-plane claim.", observed=latest.get("value"))
                row["evidence"] = [latest["evidence"]]
            elif api in ("M5.Imu.getAccel", "M5.Imu.getGyro"):
                dynamic = [value for value in asserted if "imu-dynamic" in value["evidence"]["report"] or "sensors-dynamic" in value["evidence"]["report"]]
                actions_path = args.raw_root / ("cardputer-imu-dynamic-fixed/host-actions.json" if device == "cardputer-adv" else "cores3-sensors-dynamic-r1/host-actions.json")
                actions_ok = actions_path.is_file() and all(value.get("status") == "OBSERVED" for value in json.loads(actions_path.read_text()))
                if len(dynamic) >= 2 and actions_ok:
                    row.update(status="DATA_PLANE_PASS", required_evidence_met=True, blocker=None, oracle="Two distinct same-session QOM physical vectors crossed BMI270 I2C registers and M5.Imu API; accel error <0.05 g, gyro error <1 dps.", observed=[value.get("value") for value in dynamic[-2:]])
                    row["evidence"] = [value["evidence"] for value in dynamic[-2:]] + [{"host_actions": str(actions_path)}]
            elif device == "cores3" and (api.startswith("M5.Als.") or api in ("M5.Power.getBatteryLevel", "M5.Power.getBatteryVoltage", "M5.Power.getVBUSVoltage", "M5.Power.isCharging")):
                dynamic = [value for value in asserted if "sensors-dynamic" in value["evidence"]["report"]]
                actions_path = args.raw_root / "cores3-sensors-dynamic-r1/host-actions.json"
                actions_ok = actions_path.is_file() and all(value.get("status") == "OBSERVED" for value in json.loads(actions_path.read_text()))
                if len(dynamic) >= 2 and actions_ok:
                    row.update(status="DATA_PLANE_PASS", required_evidence_met=True, blocker=None, oracle="Two same-session QOM inputs crossed the LTR553 or AXP2101 I2C register model and matched this getter on the exact firmware.", observed=[value.get("value") for value in dynamic[-2:]])
                    row["evidence"] = [value["evidence"] for value in dynamic[-2:]] + [{"host_actions": str(actions_path)}]
            elif api.startswith("machine.RTC.") or api in ("machine.Timer.init", "machine.Timer.deinit", "machine.Timer.value"):
                if asserted:
                    latest = asserted[-1]
                    row.update(status="API_ASSERTION_PASS", required_evidence_met=True, blocker=None, observed=latest.get("actual", latest.get("value")))
                    row["evidence"] = [latest["evidence"]]
            elif api.startswith("machine.WDT"):
                reset_asserted = [value for value in observations.get((device, "machine.WDT"), []) if value["status"] == "API_ASSERTION_PASS"]
                blocked = [value for value in observations.get((device, "machine.WDT"), []) if value["status"] == "BLOCKED"]
                if reset_asserted:
                    row.update(status="API_ASSERTION_PASS", required_evidence_met=True, blocker=None, oracle="Disposable guest feed-survival and actual WDT reset-reason assertion on the selected firmware.")
                    row["evidence"] = [reset_asserted[-1]["evidence"]]
                elif blocked:
                    row.update(blocker="TIMG/IDF task-watchdog expiry/reset path remains unproven: guest survived 6 s feeding then 9 s without feed with a 2 s configured timeout; reset_cause remained POWERON. Feed return alone cannot prove watchdog operation.")
                    row["evidence"] = [blocked[-1]["evidence"]]
            elif api == "M5.Mic.record" and pcm_oracles.get(device):
                path, oracle = pcm_oracles[device][-1]
                row.update(status=oracle["status"], required_evidence_met=oracle["status"] == "DATA_PLANE_PASS", oracle=oracle["oracle"], observed=oracle["output"], blocker=None if oracle["status"] == "DATA_PLANE_PASS" else "Independent PCM signal oracle failed: " + ", ".join(key for key, value in oracle["checks"].items() if not value))
                row["evidence"] = [oracle["evidence"], {"pcm_oracle": str(path)}]
            elif api == "M5.Mic.recordWavFile" and wav_oracles.get(device):
                path, oracle = wav_oracles[device][-1]
                row.update(status=oracle["status"], required_evidence_met=oracle["status"] == "DATA_PLANE_PASS", oracle=oracle["oracle"], observed={"format": oracle["format"], "signal": oracle["output"]}, blocker=None if oracle["status"] == "DATA_PLANE_PASS" else "Independent WAV parse/sample/signal oracle failed.")
                row["evidence"] = [oracle["evidence"], {"wav_oracle": str(path)}]
            elif api in ("camera.init", "camera.snapshot") and camera_oracles.get(device):
                path, oracle = camera_oracles[device][-1]
                row.update(status=oracle["status"], required_evidence_met=oracle["status"] == "DATA_PLANE_PASS", oracle=oracle["oracle"], observed={"captures": len(oracle["frames"]), "expected_sha256": oracle["expected_sha256"]}, blocker=None if oracle["status"] == "DATA_PLANE_PASS" else "Independent same-session camera pixel oracle failed.")
                row["evidence"] = [oracle["evidence"], {"camera_oracle": str(path)}]
            elif api == "hardware.SDCard" and storage_oracles.get(device):
                path, oracle = storage_oracles[device][-1]
                row.update(status=oracle["status"], required_evidence_met=oracle["status"] == "DATA_PLANE_PASS", oracle=oracle["oracle"], observed={"payload_bytes": oracle["payload_bytes"], "owned_disk_sha256": oracle["owned_disk_sha256"], "source_artifact_sha256": oracle["source_artifact_sha256"]}, blocker=None if oracle["status"] == "DATA_PLANE_PASS" else "Independent owned disk/source-artifact oracle failed.")
                row["evidence"] = [oracle["evidence"], {"storage_oracle": str(path)}]
            elif api == "hardware.SDCard" and asserted:
                latest = asserted[-1]
                row.update(status="API_ASSERTION_PASS", required_evidence_met=False, blocker="Native SPI block and remounted FAT file assertions passed; independent backing-image/source-artifact checks remain required before DATA_PLANE_PASS.", observed=latest.get("value"))
                row["evidence"] = [latest["evidence"]]
            elif item["recipe_id"] == "power-lifecycle" and power_attempts.get((device, api)):
                attempt = power_attempts[(device, api)][-1]
                row.update(attempted=True, blocker="Guest entered the documented power call but no matching return/reset/wake or stopped-device observation completed before the bounded session deadline. This is a runtime-model gap, not a successful sleep/power-off.")
                row["evidence"] = [attempt]
            elif device == "cores3" and touch_oracles.get(device) and api in touch_oracles[device][-1][1]["touch_observations"]:
                path, oracle = touch_oracles[device][-1]
                assertion = oracle["touch_observations"][api]
                if oracle["status"] == "DATA_PLANE_PASS":
                    complete = api == "M5.Touch.getCount"
                    row.update(status="API_ASSERTION_PASS", required_evidence_met=complete,
                        blocker=None if complete else "The exact one-point coordinate regression passed; movement and multiple-coordinate method recipes remain separate requirements.",
                        oracle=oracle["oracle"], observed=assertion.get("value"),
                        narrow_data_plane_status=oracle["status"], validation_scope=oracle["scope"])
                    row["evidence"] = [oracle["fixed"], {"touch_oracle": str(path)}]
            elif device == "cores3" and api.startswith(("M5.Touch.", "M5.Button.")):
                dynamic = [value for value in asserted if "input-dataplane" in value["evidence"]["report"]]
                actions_path = Path(dynamic[-1]["evidence"]["report"]).with_name("host-actions.json") if dynamic else args.raw_root / "cores3-input-dataplane-r1/host-actions.json"
                actions_ok = actions_path.is_file() and all(value.get("status") == "OBSERVED" for value in json.loads(actions_path.read_text()))
                if dynamic and actions_ok:
                    row.update(status="API_ASSERTION_PASS", required_evidence_met=api == "M5.Touch.getCount", blocker=None if api == "M5.Touch.getCount" else "The retained input subcase establishes this assertion, but the complete per-method move/multiple-coordinate or PMIC-button recipe is not yet satisfied.", observed=dynamic[-1].get("value"))
                    row["evidence"] = [dynamic[-1]["evidence"], {"host_actions": str(actions_path)}]
            elif item["recipe_id"] == "speaker-pcm":
                folder = args.raw_root / ("cores3-audio-default-fixed" if device == "cores3" else "cardputer-audio-default-fixed")
                if folder.joinpath("report.json").is_file():
                    record = json.loads(folder.joinpath("report.json").read_text())
                    text = folder.joinpath("serial.txt").read_text()
                    method = api.rsplit(".", 1)[-1]
                    playback = {"tone": "tone", "playRaw": "raw", "playWav": "wav", "playWavFile": "file"}
                    if method in playback and record.get("status") == "EXECUTED" and "AUDIO_QUEUE_CALL_RETURN " + playback[method] in text and "AUDIO_QUEUE_PROBE_DONE" in text:
                        row.update(status="DATA_PLANE_OBSERVED", blocker="The session completed this playback and archived nonempty I2S PCM, but the concatenated capture has not yet been segmented and compared with this individual method's expected samples/rate/channel.")
                        row["evidence"] = [{"report": str(folder / "report.json"), "serial": str(folder / "serial.txt"), "evidence_sha256": record.get("evidence_sha256")}]

            if not row["evidence"] and seen:
                chosen = asserted[-1:] or successful[-1:] or present[-1:] or seen[-1:]
                row["evidence"] = [value["evidence"] for value in chosen]
            if row["status"] == "BLOCKED" and successful:
                row["observed_call"] = successful[-1].get("value")
                row["call_status"] = "CALL_OK"
            failures = [value for value in seen if value["status"] in ("FAIL", "ERROR")]
            if row["status"] == "BLOCKED" and failures:
                latest = failures[-1]
                row.update(status="FAIL", blocker=latest.get("detail", latest.get("error", "Guest API assertion failed; see retained exact-firmware transcript.")), observed=latest.get("value"))
                row["evidence"] = [latest["evidence"]]
            if device == "cores3" and api in ("M5.Button.setCallback", "M5.Button.removeCallback", "M5.Button.wasClicked") and row["status"] == "FAIL":
                row.update(status="BLOCKED", blocker="The first probe incorrectly required a short click from key:p. The published key API does not promise short-click semantics; the current AXP2101 mapping emits a hold event. This is an inapplicable probe oracle, not evidence that the firmware callback API is broken. An explicit short-event injection and callback-removal subcase remain required.")
            if row["status"] == "BLOCKED" and absent and not present and not successful and not asserted:
                row.update(status="UNAVAILABLE", blocker="The public official-source API is absent from this exact selected firmware export; no functional claim can be made.", availability="FIRMWARE_EXPORT_ABSENT")
                row["evidence"] = [absent[-1]["evidence"]]
            if row["status"] == "BLOCKED" and not seen:
                row["blocker"] = api + ": no applicable executable method observation is retained yet. Required recipe: " + item["recipe_id"] + "; " + item["test_strategy"]
            result.append(row)

    output = {"schema_version": 1, "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(), "api_count": len(inventory["entries"]), "result_count": len(result), "status_counts": {device: dict(Counter(row["status"] for row in result if row["device"] == device)) for device in inventory["devices"]}, "reports": reports, "results": result}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"api_count": output["api_count"], "result_count": output["result_count"], "status_counts": output["status_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

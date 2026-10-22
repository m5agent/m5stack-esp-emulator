#!/usr/bin/env python3
"""Derive machine-readable peripheral controls from runtime evidence cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from runtime_coverage import load_matrix_cases

ROOT = Path(__file__).resolve().parents[2]
PERIPHERALS = ROOT / "platform/peripherals/catalog.json"
COVERAGE = ROOT / "platform/peripherals/runtime-coverage.json"
PROFILES = ROOT / "platform/qemu/profiles.json"

ENV_INTERFACES = {
    "M5SW_I2S_PCM_FILE": {
        "adapter": "host-file",
        "direction": "output",
        "format": "pcm-s16le",
        "capability": "speaker PCM capture",
    },
    "M5SW_I2S_RX_PCM_FILE": {
        "adapter": "host-file",
        "direction": "input",
        "format": "pcm-s16le",
        "capability": "microphone PCM injection",
    },
    "M5SW_RMT_TX_FILE": {
        "adapter": "host-file",
        "direction": "output",
        "format": "rmt-symbols",
        "capability": "RMT TX symbol capture",
    },
    "M5SW_RMT_RX_FILE": {
        "adapter": "host-file",
        "direction": "input",
        "format": "rmt-symbols",
        "capability": "RMT RX symbol injection",
    },
    "M5SW_CAMERA_FRAME": {
        "adapter": "host-file",
        "direction": "input",
        "format": "rgb565",
        "capability": "camera frame injection",
    },
}


def _qom(interface: dict, path: str, prop: str, phase: str) -> dict:
    return {
        **interface,
        "adapter": "qmp-qom",
        "path": path,
        "property": prop,
        "phase": phase,
    }


def case_interfaces(case: dict) -> list[dict]:
    interfaces: list[dict] = []
    for path, prop, value in case.get("qom_set_boot", []):
        interfaces.append(
            _qom(
                {
                    "direction": "input",
                    "value": value,
                    "value_type": "qom",
                    "capability": "boot-time physical state",
                },
                path,
                prop,
                "boot",
            )
        )
    for path, prop, value in case.get("qom", []):
        interfaces.append(
            _qom(
                {
                    "direction": "input",
                    "value": value,
                    "value_type": "qom",
                    "capability": "runtime physical state",
                },
                path,
                prop,
                "runtime",
            )
        )
    for delay, path, prop, value in case.get("qom_steps", []):
        interface = _qom(
            {
                "direction": "input",
                "value": value,
                "value_type": "qom-sequence",
                "capability": "runtime physical state transition",
                "delay_seconds": delay,
            },
            path,
            prop,
            "runtime",
        )
        interfaces.append(interface)
    for path, prop, expected in case.get("qom_expect", []):
        interfaces.append(
            _qom(
                {
                    "direction": "output",
                    "expected": expected,
                    "value_type": "qom",
                    "capability": "device state readback",
                },
                path,
                prop,
                "runtime",
            )
        )

    for spec in case.get("inputs", []):
        interfaces.append(
            {
                "adapter": "qmp-input",
                "direction": "input",
                "control": spec,
                "capability": "touch keyboard button pointer",
            }
        )
    for marker in case.get("serial_expect", []):
        interfaces.append(
            {
                "adapter": "serial",
                "direction": "output",
                "channel": "uart0",
                "expect": marker,
            }
        )
    for marker in case.get("serial1_expect", []):
        interfaces.append(
            {
                "adapter": "serial",
                "direction": "output",
                "channel": "uart1",
                "expect": marker,
            }
        )

    for env_name, env_value in case.get("env", {}).items():
        interface = ENV_INTERFACES.get(env_name)
        if interface:
            interfaces.append(
                {
                    **interface,
                    "env": env_name,
                    "path": env_value,
                }
            )
    if case.get("pcm"):
        interfaces.append(
            {
                "adapter": "host-file",
                "direction": "output",
                "format": "pcm-s16le",
                "path": case["pcm"]["capture"],
                "capability": "speaker PCM verification",
            }
        )
    if case.get("pcm_tone_source"):
        interfaces.append(
            {
                "adapter": "host-file",
                "direction": "input",
                "format": "pcm-s16le",
                "path": case["pcm_tone_source"]["output"],
                "capability": "microphone PCM source",
            }
        )
    if case.get("rmt_nec"):
        interfaces.append(
            {
                "adapter": "host-file",
                "direction": "output",
                "format": "rmt-symbols",
                "path": case["rmt_nec"]["capture"],
                "capability": "NEC IR capture",
            }
        )
    if case.get("rmt_nec_source"):
        interfaces.append(
            {
                "adapter": "host-file",
                "direction": "input",
                "format": "rmt-symbols",
                "path": case["rmt_nec_source"]["output"],
                "capability": "NEC IR injection",
            }
        )
    if case.get("rmt_ws2812"):
        interfaces.append(
            {
                "adapter": "host-file",
                "direction": "output",
                "format": "rmt-symbols",
                "path": case["rmt_ws2812"]["capture"],
                "capability": "WS2812 waveform capture",
            }
        )
    if case.get("disk"):
        interfaces.append(
            {
                "adapter": "block-device",
                "direction": "input-output",
                "format": "raw",
                "path": case["disk"]["image"],
                "sector": case["disk"]["sector"],
                "capability": "SD block read/write",
            }
        )
    if case.get("frame_color"):
        interfaces.append(
            {
                "adapter": "framebuffer",
                "direction": "output",
                "capability": "rendered display capture",
            }
        )
    return interfaces


def build_interfaces() -> dict:
    catalog = json.loads(PERIPHERALS.read_text())
    coverage = json.loads(COVERAGE.read_text())
    profiles = json.loads(PROFILES.read_text())["devices"]
    cases = load_matrix_cases()
    external = coverage.get("external_cases", {})
    case_models = coverage.get("case_models", {})
    machine_devices = {
        profile.get("board_model"): profile["id"]
        for profile in profiles
        if profile.get("board_model")
    }
    machine_devices.update(coverage.get("machine_devices", {}))

    models = {}
    for model_id, model in catalog["models"].items():
        model_interfaces = []
        evidence_cases = []
        model_case_ids = [
            case_id
            for case_id, covered_models in case_models.items()
            if model_id in covered_models
        ]
        for case_id in model_case_ids:
            if case_id in cases:
                case = cases[case_id]
                device_id = machine_devices.get(case.get("machine"))
                for interface in case_interfaces(case):
                    model_interfaces.append(
                        {
                            **interface,
                            "case": case_id,
                            "device": device_id,
                            "backend": "qemu-runtime",
                        }
                    )
            else:
                case = external[case_id]
                model_interfaces.append(
                    {
                        "adapter": "external-probe",
                        "direction": "input-output",
                        "case": case_id,
                        "device": case["device"],
                        "backend": "external",
                        "test": case["test"],
                        "evidence": case["evidence"],
                    }
                )
            evidence_cases.append(case_id)

        unique = []
        seen = set()
        for interface in model_interfaces:
            key = json.dumps(interface, sort_keys=True)
            if key not in seen:
                seen.add(key)
                unique.append(interface)
        models[model_id] = {
            "status": model["status"],
            "kind": model.get("kind"),
            "interface": model.get("interface"),
            "capabilities": model.get("capabilities", []),
            "evidence_cases": evidence_cases,
            "interfaces": unique,
        }

    devices = {}
    for device_id, group in coverage.get("device_case_groups", {}).items():
        devices[device_id] = {
            "models": group.get("models", []),
            "matrix": [
                {
                    "id": case_id,
                    "machine": cases[case_id].get("machine"),
                }
                for case_id in group.get("matrix", [])
            ],
            "external": [
                {
                    "id": case_id,
                    **external[case_id],
                }
                for case_id in group.get("external", [])
            ],
            "case_models": {
                case_id: case_models.get(case_id, [])
                for case_id in group.get("matrix", [])
                + group.get("external", [])
            },
        }

    return {
        "schema_version": 2,
        "model_count": len(models),
        "models_with_interfaces": sum(
            bool(model["interfaces"]) for model in models.values()
        ),
        "device_count": len(devices),
        "devices": devices,
        "models": models,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_interfaces()
    if args.model:
        model = payload["models"].get(args.model)
        if model is None:
            raise SystemExit(f"unknown model: {args.model}")
        print(json.dumps(model, ensure_ascii=False, indent=2))
        return
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for model_id, model in payload["models"].items():
        print(
            f"{model_id:28} {model['status']:11} "
            f"interfaces={len(model['interfaces']):2} "
            f"cases={','.join(model['evidence_cases']) or 'none'}"
        )


if __name__ == "__main__":
    main()

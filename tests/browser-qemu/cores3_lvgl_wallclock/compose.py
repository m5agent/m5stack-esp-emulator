"""Compose the pinned candidate into a local base; never execute or flash it."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
from uiflow_source import build_uiflow_source_image


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compose(base_path, output):
    directory = Path(__file__).resolve().parent
    contract = json.loads((directory / "contract.json").read_text())
    identity = contract["identity"]
    sources = {}
    for name, expected in identity["files"].items():
        payload = (directory / name).read_bytes()
        if digest(payload) != expected:
            raise ValueError("fixture source hash mismatch: " + name)
        sources[name] = payload.decode("utf-8")
    source_hash = digest(json.dumps(sources, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8"))
    if source_hash != identity["source_sha256"]:
        raise ValueError("fixture source bundle hash mismatch")
    base = Path(base_path).read_bytes()
    supplied_hash = digest(base)
    raw, normalized = identity["raw_base"], identity["normalized_base"]
    if len(base) == raw["size"] and supplied_hash == raw["sha256"]:
        base += b"\xff" * (normalized["size"] - len(base))
    if len(base) != normalized["size"] or digest(base) != normalized["sha256"]:
        raise ValueError("input is neither the pinned raw nor normalized UIFlow2 base")
    firmware, receipt = build_uiflow_source_image(
        base, normalized["size"], sources, expected_base_sha256=normalized["sha256"])
    if receipt["source_sha256"] != source_hash:
        raise ValueError("composed source identity changed")
    if (len(firmware) != identity["composed_firmware"]["size"]
            or receipt["firmware_sha256"] != identity["composed_firmware"]["sha256"]):
        raise ValueError("composed firmware differs from the pinned candidate")
    receipt["fixture"] = contract["fixture"]
    receipt["scheduler_candidate"] = contract["execution"]["scheduler_candidate"]["identity"]
    receipt["supplied_base_sha256"] = supplied_hash
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "candidate.bin").write_bytes(firmware)
    (output / "composition.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "fixture": receipt["fixture"],
                      "firmware_sha256": receipt["firmware_sha256"],
                      "source_sha256": source_hash}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="ignored local storage; never publish the firmware/ROM")
    args = parser.parse_args()
    compose(args.base, args.output_dir)

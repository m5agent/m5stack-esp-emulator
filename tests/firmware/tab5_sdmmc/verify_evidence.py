#!/usr/bin/env python3
"""Check the Tab5 slot 0 guest ZIP and the separately exported SD artifact."""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json

from firmware_filesystems import inventory_sd_filesystems


EXPECTED_READBACKS = {
    "/FOO.TXT": b"Hello EMUSD!\n",
    "/NIHAO.TXT": b"Nihao EMUSD!\n",
}
WIRING = "slot=0 width=4 max_freq_khz=40000 clk=43 cmd=44 d0=39 d1=40 d2=41 d3=42 ldo=4"


def verify(evidence: Path, exported: Path, source_sha256: str) -> dict:
    with ZipFile(evidence) as bundle:
        broken_member = bundle.testzip()
        if broken_member is not None:
            raise ValueError(f"Corrupt ZIP member {broken_member}")
        serial = bundle.read("serial.log").decode("utf-8", errors="replace")
        manifest = json.loads(bundle.read("manifest.json"))
        storage = json.loads(bundle.read("storage/summary.json"))
    if manifest.get("storage") != storage or storage.get("interface") != "sdmmc":
        raise ValueError("The ZIP has inconsistent SDMMC metadata")
    if storage.get("artifact_id") != source_sha256 or not storage.get("session_isolated_copy"):
        raise ValueError("The ZIP is bound to a different SD source")
    markers = [WIRING, "Filesystem mounted", "Card unmounted"]
    markers.extend(f"Read from file: '{data.decode().strip()}'" for data in EXPECTED_READBACKS.values())
    if any(marker not in serial for marker in markers) or serial.count("File written") != 2:
        raise ValueError("The guest did not mount, write, read, and unmount both files")

    data = exported.read_bytes()
    if len(data) != storage.get("bytes"):
        raise ValueError("The exported card has a different capacity")
    inventory = inventory_sd_filesystems(data)
    files = {
        entry["path"]: entry["sha256"]
        for volume in inventory["filesystems"]
        for entry in volume.get("files", [])
        if "sha256" in entry
    }
    checksums = {path: sha256(data).hexdigest() for path, data in EXPECTED_READBACKS.items()}
    if inventory["errors"] or files != checksums:
        raise ValueError("The stopped export does not contain the expected files")
    return {"status": "PASS", "export_sha256": sha256(data).hexdigest(), "files": files}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("exported", type=Path)
    parser.add_argument("source_sha256")
    args = parser.parse_args()
    try:
        receipt = verify(args.evidence, args.exported, args.source_sha256)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(receipt, indent=2))

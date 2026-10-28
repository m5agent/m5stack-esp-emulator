#!/usr/bin/env python3
"""Generate an explicit QR input for image-processing tests (requires qrcode).

The fixture is drawn through image.Image methods after real camera capture.
It tests image-processing APIs, and is not evidence of optical camera input.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def main():
    import qrcode
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--uiflow-source", type=Path, help="optional official esp_dl example images; requires Pillow")
    args = parser.parse_args()
    payload = "M5EMU_API_QR_20261027"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    rows = ["".join("1" if bit else "0" for bit in row) for row in qr.get_matrix()]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "qr.json").write_text(json.dumps({"payload": payload, "rows": rows}) + "\n")
    if args.uiflow_source:
        from PIL import Image
        examples = args.uiflow_source / "m5stack/components/esp_dl/examples"
        provenance = {}
        for name, relative in (("face", "human_face_detect/main/human_face.jpg"),
                               ("pedestrian", "pedestrian_detect/main/pedestrian.jpg")):
            source = examples / relative
            image = Image.open(source).convert("RGB").resize((320, 240))
            data = b"".join(struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
                            for r, g, b in image.getdata())
            (args.out_dir / (name + ".rgb565")).write_bytes(data)
            provenance[name] = {"source": "m5stack/components/esp_dl/examples/" + relative,
                                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                "fixture_sha256": hashlib.sha256(data).hexdigest(),
                                "transform": "Pillow RGB resize 320x240, RGB565 little-endian"}
        (args.out_dir / "dl-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()

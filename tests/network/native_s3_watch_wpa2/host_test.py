#!/usr/bin/env python3
"""Opt-in actual QEMU C checks; requires the replayed native source and gcrypt deps."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path


def function(source, name):
    start = source.index("static ", source.rfind("\n", 0, source.index(name + "(")))
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ap = (args.source / "hw/misc/esp32_wifi_ap.c").read_text()
    inc = (args.source / "hw/misc/esp32_wifi_wpa2_peer.inc").read_text()
    header = (args.source / "hw/misc/esp32_wlan.h").read_text()
    parts = [
        header[
            header.index("typedef struct beacon_info_t") : header.index(
                "typedef struct access_point_info"
            )
        ]
    ]
    parts += [
        function(ap, n)
        for n in (
            "aes_block",
            "xor_block",
            "ccmp_header_aad_nonce",
            "aes_ccm_encrypt",
            "aes_ccm_decrypt",
        )
    ]
    begin = ap.index("static const uint8_t wpa_rsn_ie[]")
    parts.append(ap[begin : ap.index(";", begin) + 1])
    parts += [
        function(inc, n)
        for n in (
            "wpa_peer_equal",
            "wpa_peer_key_unwrap",
            "wpa_peer_rsn",
            "wpa_peer_guest_key",
            "wpa_peer_data",
        )
    ]
    template = Path(__file__).with_name("host_crypto.c.in").read_text()
    source = args.out / "actual.c"
    source.write_text(template.replace("@ACTUAL_FUNCTIONS@", "\n".join(parts)))
    flags = shlex.split(
        subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "glib-2.0"], text=True
        )
    )
    subprocess.run(
        [
            "clang",
            "-std=c11",
            "-O1",
            "-g",
            "-fsanitize=address,undefined",
            "-Wno-unused-parameter",
            "-I" + str(args.deps / "include"),
            str(source),
            str(args.deps / "lib/libgcrypt.a"),
            str(args.deps / "lib/libgpg-error.a"),
            *flags,
            "-o",
            str(args.out / "actual"),
        ],
        check=True,
    )
    subprocess.run(
        [str(args.out / "actual")],
        check=True,
        env={
            **os.environ,
            "ASAN_OPTIONS": "detect_leaks=0",
            "UBSAN_OPTIONS": "halt_on_error=1",
        },
    )
    receipt = {
        "inc_sha256": hashlib.sha256(inc.encode()).hexdigest(),
        "ap_sha256": hashlib.sha256(ap.encode()).hexdigest(),
        "extracted_c_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "asan": True,
        "ubsan": True,
        "leak_check": "NOT RUN",
    }
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    run()

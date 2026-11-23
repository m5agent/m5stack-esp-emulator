#!/usr/bin/env python3
"""Outputs raw private evidence; publish only a reviewed aggregate."""

import argparse
import hashlib
import json
import secrets
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import ProxyHandler, Request, build_opener
from zipfile import ZipFile

parser = argparse.ArgumentParser(
    description="Exact original, same-native read-only WPA2/HTTP qualification"
)
parser.add_argument(
    "--url", required=True, help="agent-owned loopback Device Service origin"
)
parser.add_argument("--token-file", type=Path, required=True)
parser.add_argument("--firmware", type=Path, required=True)
parser.add_argument(
    "--network-file",
    type=Path,
    required=True,
    help="private profile/SSID/passphrase JSON",
)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--wrong-password", action="store_true")
args = parser.parse_args()
parsed = urlparse(args.url)
if (
    parsed.scheme != "http"
    or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
    or parsed.username
    or parsed.password
    or parsed.path not in {"", "/"}
):
    parser.error("use an owned HTTP loopback origin without credentials or path")
ROOT = args.out.resolve()
ROOT.mkdir(parents=True, exist_ok=True)
TOKEN = args.token_file.read_text().strip()
OPEN = build_opener(ProxyHandler({}))
BASE = args.url.rstrip("/") + "/api/v1/"
SHA = "eb7f9425c07cffd972d0de479fc6c82d86af2aa51dc807d9829d5ee55add163b"


def api(route, method="GET", value=None, data=None, raw=False):
    h = {"Authorization": "Bearer " + TOKEN}
    if value is not None:
        data = json.dumps(value).encode()
        h["Content-Type"] = "application/json"
    if data is not None and value is None:
        h["Content-Type"] = "application/octet-stream"
        h["X-Artifact-Name"] = "s3-watch-original.bin"
    with OPEN.open(
        Request(BASE + route, data=data, headers=h, method=method), timeout=45
    ) as r:
        b = r.read()
        return b if raw else json.loads(b)


def run(label="positive", wrong_password=False) -> int:
    out = ROOT / label
    out.mkdir(exist_ok=False)

    def save(name, value):
        (out / name).write_text(json.dumps(value, indent=2))
        return value

    summary = {"status": "PARTIAL", "http": "NOT RUN", "errors": []}
    sid = None
    try:
        w = save("worker-before.private.json", api("worker"))
        assert w["active_lease_count"] == 0 and w["accepting_leases"] and not w["stale"]
        b = args.firmware.read_bytes()
        assert len(b) == 8388608 and hashlib.sha256(b).hexdigest() == SHA
        a = save("artifact.private.json", api("artifacts", "POST", data=b))
        assert a["sha256"] == a["artifact_id"] == SHA
        f = save(
            "firmware.private.json",
            api(
                "firmware",
                "POST",
                value={"device_id": "sticks3", "kind": "merged", "artifact_id": SHA},
            ),
        )
        assert f["sha256"] == SHA
        payload = {
            "device_id": "sticks3",
            "firmware_id": f["firmware_id"],
            "runtime": "qemu-wifi",
            "ready_marker": "",
            "ttl_seconds": 180,
            "network": json.loads(args.network_file.read_text()),
        }
        if wrong_password:
            password = payload["network"]["wifi_password"]
            payload["network"]["wifi_password"] = password[:-1] + (
                "X" if password[-1] != "X" else "Y"
            )
        key = "review-v1:%d:%s" % (int(time.time()) + 300, secrets.token_hex(16))
        _, expires, nonce = key.split(":")
        intent = {
            "key_sha256": hashlib.sha256(key.encode()).hexdigest(),
            "expires_at": int(expires),
            "nonce": nonce,
            "request_sha256": hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest(),
        }
        save("intent.private.json", intent)
        try:
            s = api("sessions", "POST", value={**payload, "idempotency_key": key})
        except Exception:
            rec = api("sessions/reconcile-create", "POST", value=intent)
            assert rec["state"] == "bound" and rec["worker_id"] == w["worker_id"]
            s = api("sessions/" + rec["session_id"])
        sid = s["session_id"]
        save("created.private.json", s)
        assert s["firmware_id"] == f["firmware_id"] and s["runtime"] == "qemu-wifi"
        time.sleep(30)
        parents = ["/machine"]
        wifi = None
        for parent in parents:
            q = api("sessions/" + sid + "/qom/list?path=" + quote(parent, safe="/"))
            if parent == "/machine":
                parents.extend(
                    parent + "/" + v["name"]
                    for v in q["properties"]
                    if v.get("name")
                    in {"unattached", "soc", "peripheral", "peripheral-anon"}
                    and str(v.get("type", "")).startswith("child<")
                )
            for v in q["properties"]:
                if v.get("type") == "child<misc.esp32s3.wifi>":
                    wifi = parent + "/" + v["name"]
                    break
            if wifi:
                break
        assert wifi
        for i in range(31):
            if i in {5, 15}:
                save(
                    f"{i:02d}-input.private.json",
                    api(
                        "sessions/" + sid + "/input",
                        "POST",
                        value={
                            "kind": "button",
                            "control": "b",
                            "action": "hold",
                            "seconds": 2.0,
                            "settle_seconds": 1.0,
                        },
                    ),
                )
            save(
                f"{i:02d}-qom.private.json",
                api(
                    "sessions/" + sid + "/qom-snapshot",
                    "POST",
                    value={"path": wifi, "depth": 0, "max_nodes": 128},
                ),
            )
            save(f"{i:02d}-network.private.json", api("sessions/" + sid + "/network"))
            if i in {0, 4, 6, 14, 16, 30}:
                save(
                    f"{i:02d}-serial.private.json",
                    api("sessions/" + sid + "/serial?offset=0&limit=65536"),
                )
                (out / f"{i:02d}.png").write_bytes(
                    api("sessions/" + sid + "/frame.png", raw=True)
                )
            time.sleep(2)
    except Exception as e:
        summary["errors"].append({"phase": "run", "type": type(e).__name__})
    finally:
        if sid:
            try:
                z = api(
                    "sessions/"
                    + sid
                    + "/evidence?include=manifest,serial,frames,logs,network",
                    raw=True,
                )
                (out / "evidence.private.zip").write_bytes(z)
                with ZipFile(BytesIO(z)) as a:
                    assert a.testzip() is None
                    m = json.loads(a.read("manifest.json"))
                    assert (
                        m["session"]["session_id"] == sid
                        and m["session"]["firmware_sha256"] == SHA
                    )
                summary["zip_sha256"] = hashlib.sha256(z).hexdigest()
            except Exception as e:
                summary["errors"].append(
                    {"phase": "evidence", "type": type(e).__name__}
                )
            try:
                stop = save(
                    "stopped.private.json",
                    api("sessions/" + sid + "?purge=0", "DELETE"),
                )
                assert (
                    stop["state"] == "stopped"
                    and not stop["flash_retained"]
                    and not stop["worker"]["lease_active"]
                )
                w2 = save("worker-after.private.json", api("worker"))
                assert (
                    w2["worker_id"] == w["worker_id"] and w2["active_lease_count"] == 0
                )
                summary["cleanup_confirmed"] = True
                final = save(
                    "network-final.private.json", api("sessions/" + sid + "/network")
                )
                closed = api(
                    "sessions/"
                    + sid
                    + "/evidence?include=manifest,serial,frames,logs,network",
                    raw=True,
                )
                (out / "evidence-stopped.private.zip").write_bytes(closed)
                with ZipFile(BytesIO(closed)) as archive:
                    assert archive.testzip() is None
                summary["stopped_zip_sha256"] = hashlib.sha256(closed).hexdigest()
                summary["network_status"] = final["status"]
                summary["checks"] = final["checks"]
                summary["wpa2_controller_state"] = final.get("wpa2_controller", {}).get(
                    "state", {}
                )
                summary["wrong_password"] = wrong_password
                if wrong_password:
                    controller = summary["wpa2_controller_state"]
                    assert final["status"] == "PARTIAL" and final["checks"]
                    assert not any(final["checks"].values())
                    assert controller["m1"] > 0 and controller["m2"] > 0
                    assert all(
                        controller[key] == 0
                        for key in ("m3", "m4", "protected_tx", "protected_rx")
                    )
                    summary["negative_control"] = "PASS"
                    summary["http"] = "REJECTED_AS_EXPECTED"
                else:
                    assert final["status"] == "PASS" and all(final["checks"].values())
                    summary["status"] = "PASS"
                    summary["http"] = "PASS"
            except Exception as e:
                summary["errors"].append({"phase": "stop", "type": type(e).__name__})
        save("summary.json", summary)
    print(json.dumps(summary))
    if summary["errors"] or not summary.get("cleanup_confirmed"):
        return 1
    return 0 if summary.get("negative_control", summary["status"]) == "PASS" else 1


if __name__ == "__main__":
    case = "wrong-password" if args.wrong_password else "positive"
    raise SystemExit(run(case, args.wrong_password))

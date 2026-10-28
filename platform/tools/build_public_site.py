#!/usr/bin/env python3
"""Export the public workbench as a deterministic GitHub Pages artifact.

This does not publish, start a service, fetch firmware, or package native QEMU.
Only reviewed browser assets and public device/Unit metadata enter the export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".js", ".mjs", ".css", ".html", ".json", ".txt", ".md", ".svg"}
ASSET_SUFFIXES = TEXT_SUFFIXES | {".png", ".webp", ".jpg", ".jpeg", ".avif", ".gif", ".woff", ".woff2"}
MANIFEST_NAME = "public-site-manifest.json"
MANIFEST_KIND = "m5stack-public-site"
PREFIX_PATH = re.compile(r"(?<=[\"'`(])/(platform|devices|data)/")


def normalize_base_path(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("base path must start with /")
    value = value.rstrip("/") + "/"
    if not re.fullmatch(r"/(?:[A-Za-z0-9._~-]+/)*", value):
        raise ValueError("base path must be a URL path such as /m5stack-esp-emulator/")
    if any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("base path cannot contain dot segments")
    return value


def normalize_service_url(value: str) -> str:
    if not value:
        return ""
    if any(ord(character) < 32 for character in value) or "\\" in value:
        raise ValueError("service URL contains invalid characters")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("public service URL must use HTTPS without credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("public service URL cannot contain query parameters or a fragment")
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1"):
        path = path[:-7]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def encode_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def rewrite_paths(content: bytes, base_path: str) -> bytes:
    text = content.decode("utf-8")
    return PREFIX_PATH.sub(lambda match: base_path + match.group(1) + "/", text).encode("utf-8")


def export_sources(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    web = root / "platform/web"
    for path in sorted(web.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"browser asset cannot be a symlink: {path.relative_to(root)}")
        if not path.is_file() or any(part.startswith(".") or part == "node_modules" for part in path.relative_to(web).parts):
            continue
        if path.suffix.lower() in ASSET_SUFFIXES or path.name in {"LICENSE", "NOTICE"}:
            files[path.relative_to(root).as_posix()] = path
    for path in sorted((root / "devices").rglob("device.json")):
        if path.is_symlink():
            raise ValueError("device manifest cannot be a symlink")
        files[path.relative_to(root).as_posix()] = path
    for name in ("devices/catalog.json", "platform/units/catalog.json"):
        files[name] = root / name
    # Existing pinned runtime, preserved for diagnostic consumers only. There is
    # deliberately no board-WASM capability assertion or bundled firmware here.
    for name in ("esp_emu.js", "esp_emu_bg.wasm", "LICENSE"):
        path = root / "platform/runtime/wasm" / name
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path
    for name, path in files.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required public asset is missing or a symlink: {name}")
    if "platform/web/index.html" not in files:
        raise ValueError("public workbench entry point is missing")
    return files


def browser_runtime_files(directory: Path, *, allow_diagnostic: bool = False) -> tuple[dict, dict[str, bytes]]:
    from bootstrap_browser_runtime import SOURCE_COMMIT, ROM_SHA256
    directory = directory.resolve()
    manifest = json.loads((directory / "runtime.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("source", {}).get("commit") != SOURCE_COMMIT:
        raise ValueError("browser runtime source does not match the reviewed commit")
    kind = manifest.get("build", {}).get("kind")
    if kind != "source-build" and not (allow_diagnostic and kind == "downloaded-diagnostic"):
        raise ValueError("public export requires a source build; diagnostic export needs explicit opt-in")
    if manifest.get("profiles") != ["papers3", "stopwatch"] or manifest.get("rom", {}).get("sha256") != ROM_SHA256:
        raise ValueError("browser runtime board profiles or S3 ROM do not match")
    files = {"runtime.json": encode_json(manifest)}
    for key in ("wasm", "rom"):
        row = manifest[key]
        name = row.get("path")
        if name not in {"esp32sim.wasm", "esp32s3_rev0_rom.elf"} or (directory / name).is_symlink():
            raise ValueError("browser runtime path is invalid")
        data = (directory / name).read_bytes()
        if len(data) != row.get("bytes") or hashlib.sha256(data).hexdigest() != row.get("sha256"):
            raise ValueError("browser runtime asset SHA-256 or size mismatch")
        files[name] = data
    if not files["esp32sim.wasm"].startswith(b"\0asm\x01\0\0\0"):
        raise ValueError("browser runtime is not a WebAssembly module")
    for name in ("LICENSE", "ROM_LICENSE", "NOTICE"):
        if (directory / name).is_file():
            files[name] = (directory / name).read_bytes()
    return manifest, files


def qemu_runtime_files(directory: Path, *, allow_diagnostic: bool = False) -> tuple[dict, dict[str, bytes]]:
    from bootstrap_qemu_browser_runtime import runtime_files
    return runtime_files(directory, allow_incremental=allow_diagnostic)


def littlefs_runtime_files(directory: Path) -> dict[str, bytes]:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != "m5stack-browser-littlefs"
            or manifest.get("source", {}).get("commit") != "6cb4e86540eca0d9ba62500a298385c9d863c8be"
            or manifest.get("build", {}).get("kind") != "source-build"
            or manifest.get("firmware_bundled") is not False or manifest.get("rom_bundled") is not False):
        raise ValueError("LittleFS runtime manifest mismatch")
    files = {"manifest.json": encode_json(manifest)}
    rows = manifest["assets"]
    if isinstance(rows, dict):
        rows = list(rows.values())
    allowed = {"littlefs.mjs", "littlefs.wasm", "LICENSE.littlefs", "LICENSE.composer", "LICENSE.emscripten", "LICENSE.musl", "fixture/boot.py", "fixture/main.py", "source.zip"}
    for row in rows:
        name = row["path"]
        if name not in allowed or (directory / name).is_symlink():
            raise ValueError("invalid LittleFS asset path")
        data = (directory / name).read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("LittleFS asset hash or size mismatch")
        files[name] = data
    if set(files) != allowed | {"manifest.json"}:
        raise ValueError("LittleFS runtime is incomplete")
    return files


def build_site(root: Path, output: Path, *, base_path: str = "/", service_url: str = "", browser_runtime: Path | None = None, qemu_runtime: Path | None = None, littlefs_runtime: Path | None = None, allow_diagnostic_runtime: bool = False) -> dict:
    root, output = root.resolve(), output.resolve()
    base_path = normalize_base_path(base_path)
    service_url = normalize_service_url(service_url)
    if browser_runtime and qemu_runtime:
        raise ValueError("select one browser engine per exported site")
    # Never overwrite a source tree or an arbitrary existing user directory.
    in_sources = any(path == output or path in output.parents for path in (root / "platform", root / "devices", root / ".git"))
    if output == root or output in root.parents or in_sources or any((output / name).exists() for name in (".git", "platform", "devices")) and not (output / MANIFEST_NAME).is_file():
        raise ValueError("output must be a separate export directory")
    if output.exists() and any(output.iterdir()):
        try:
            previous = json.loads((output / MANIFEST_NAME).read_text())
        except (OSError, ValueError) as error:
            raise ValueError("refusing to overwrite a directory not owned by this exporter") from error
        if previous.get("kind") != MANIFEST_KIND or previous.get("schema_version") != 1:
            raise ValueError("refusing to overwrite a directory not owned by this exporter")
    sources = export_sources(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".public-site-", dir=output.parent))
    try:
        for name, path in sources.items():
            content = path.read_bytes()
            if path.suffix in TEXT_SUFFIXES:
                content = rewrite_paths(content, base_path)
            destination = temporary / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        (temporary / "index.html").write_bytes((temporary / "platform/web/index.html").read_bytes())
        (temporary / ".nojekyll").write_bytes(b"")
        isolation_worker = temporary / "platform/web/public-coi-serviceworker.js"
        if isolation_worker.is_file():
            (temporary / "coi-serviceworker.js").write_bytes(isolation_worker.read_bytes())
        runtime_manifest = None
        if browser_runtime:
            runtime_manifest, runtime_files = browser_runtime_files(browser_runtime, allow_diagnostic=allow_diagnostic_runtime)
            runtime_directory = temporary / "platform/runtime/esp32sim"
            runtime_directory.mkdir(parents=True, exist_ok=True)
            for name, content in runtime_files.items():
                (runtime_directory / name).write_bytes(content)
        if qemu_runtime:
            runtime_manifest, runtime_files = qemu_runtime_files(qemu_runtime, allow_diagnostic=allow_diagnostic_runtime)
            runtime_directory = temporary / "platform/runtime/qemu"
            runtime_directory.mkdir(parents=True, exist_ok=True)
            for name, content in runtime_files.items():
                (runtime_directory / name).write_bytes(content)
            (temporary / "platform/web/browser-profiles.json").write_bytes(encode_json({
                "schema_version": 1, "scope": "C/QEMU offline CoreS3 vm-div8 only; no inherited native coverage",
                "source": runtime_manifest["source"],
                "devices": [{"id": "cores3", "browser": {
                    "board": "m5cores3", "status": "experimental", "description": "C/QEMU · LVGL / 触摸 / PIR · 1/8 虚拟时钟",
                    "limitations": ["仅验证离线 CoreS3 示例；任意固件兼容性未验证。", "虚拟时间与看门狗到期随墙钟慢放 8 倍。", "网络、音频及其它 Unit 未验证；刷新不保留 Flash。"],
                }}],
            }))
        if littlefs_runtime:
            for name, content in littlefs_runtime_files(littlefs_runtime).items():
                destination = temporary / "platform/runtime/littlefs" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        config = {
            "schema_version": 1, "service_url": service_url,
            "max_firmware_bytes": 64 * 1024 * 1024,
            "browser_board_execution": runtime_manifest is not None,
            "browser_runtime_engine": runtime_manifest.get("engine", "esp32sim") if runtime_manifest else None,
            "browser_runtime_build": runtime_manifest["build"]["kind"] if runtime_manifest else None,
        }
        (temporary / "platform/web/site-config.json").write_bytes(encode_json(config))
        (temporary / "site-config.json").write_bytes(encode_json(config))
        # Unit visual availability and emulated protocol coverage remain distinct.
        visual_catalog = json.loads((root / "platform/web/vendor/m5stack-models/catalog/products.json").read_text())
        data = temporary / "data"
        data.mkdir()
        (data / "units.json").write_bytes(encode_json({
            "schema_version": 1, "scope": "visual-only",
            "units": [row for row in visual_catalog["products"] if row.get("category") == "unit"],
        }))
        asset_rows = []
        for path in sorted(temporary.rglob("*")):
            if path.is_file():
                content = path.read_bytes()
                asset_rows.append({"path": path.relative_to(temporary).as_posix(), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        manifest = {
            "schema_version": 1, "kind": MANIFEST_KIND, "base_path": base_path,
            "entry": "index.html", "service_url": service_url,
            "execution": "browser C/QEMU for CoreS3 offline LVGL/touch/PIR (vm-div8); other profiles need Device Service" if qemu_runtime else "browser esp32sim for papers3/stopwatch; other native boards require Device Service" if runtime_manifest else "native board firmware requires a separately configured Device Service",
            "firmware_bundled": False, "assets": asset_rows,
        }
        (temporary / MANIFEST_NAME).write_bytes(encode_json(manifest))
        if output.exists():
            shutil.rmtree(output)
        temporary.rename(output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".work/public-site")
    parser.add_argument("--base-path", default="/", help="/ for user Pages; /repository/ for project Pages")
    parser.add_argument("--service-url", default="", help="optional public HTTPS Device Service, without token")
    parser.add_argument("--browser-runtime", type=Path, help="directory from bootstrap_browser_runtime.py")
    parser.add_argument("--qemu-runtime", type=Path, help="directory from bootstrap_qemu_browser_runtime.py")
    parser.add_argument("--littlefs-runtime", type=Path, help="source-built browser LittleFS composer")
    parser.add_argument("--allow-diagnostic-runtime", action="store_true", help="explicit preview-only opt-in for the pinned downloaded WASM")
    args = parser.parse_args()
    try:
        manifest = build_site(ROOT, args.output, base_path=args.base_path, service_url=args.service_url, browser_runtime=args.browser_runtime, qemu_runtime=args.qemu_runtime, littlefs_runtime=args.littlefs_runtime, allow_diagnostic_runtime=args.allow_diagnostic_runtime)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"public site export failed: {error}\n")
    print(json.dumps({"output": str(args.output), "assets": len(manifest["assets"]), "bytes": sum(row["bytes"] for row in manifest["assets"]), "base_path": manifest["base_path"], "published": False}))


if __name__ == "__main__":
    main()

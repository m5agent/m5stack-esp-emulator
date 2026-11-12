#!/usr/bin/env python3
"""Rebuild the Unit-enabled Xtensa runtime without changing global packages.

This performs source/dependency builds only. Firmware execution belongs to the
visible Device Service API. The recorded source pins and patch hashes make the
historical snapshot merge reproducible; existing unowned trees are never reset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
QEMU_URL = "https://github.com/espressif/qemu.git"
QEMU_TAG = "esp-develop-9.2.2-20260417"
QEMU_COMMIT = "40edccac415693c5130f91c01d84176ae6008566"
SLIRP_URL = "https://gitlab.freedesktop.org/slirp/libslirp.git"
SLIRP_COMMIT = "26be815b86e8d49add8c9a8b320239b9594ff03d"
# Historical 0065/0066/0069/0070 need context-only ports on this reconstructed
# Unit-enabled source. Native 0013 is the 0099 delta after the existing 0066.
# Keep 0071-0084 out of this recipe until individually integrated and validated.
PATCHES = (
    "patches/qemu-unit-runtime/0001-reconstructed-xtensa-source.patch",
    "patches/qemu-unit-runtime/0002-wifi-radio-lifecycle-compat.patch",
    "patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch",
    "patches/qemu-m5stack-peripherals/0033-unit-runtime-core-and-routing.patch",
    "patches/qemu-m5stack-peripherals/0034-unit-i2c-sensors.patch",
    "patches/qemu-m5stack-peripherals/0035-unit-i2c-controls.patch",
    "patches/qemu-m5stack-peripherals/0036-core2-soft-i2c-handoff-compat.patch",
    "patches/qemu-m5stack-peripherals/0037-s3-ledc-duty-readback.patch",
    "patches/qemu-m5stack-peripherals/0038-unit-pwm-route-refresh.patch",
    "patches/qemu-m5stack-peripherals/0043-unit-scroll-controller.patch",
    "patches/qemu-m5stack-peripherals/0044-unit-2relay-gpio.patch",
    "patches/qemu-m5stack-peripherals/0045-unit-flashlight-aw3641.patch",
    "patches/qemu-m5stack-peripherals/0046-unit-flashlight-route-lifecycle.patch",
    "patches/qemu-m5stack-peripherals/0047-unit-flashlight-cold-pad-observation.patch",
    "patches/qemu-m5stack-peripherals/0048-unit-servos8-joystick2-nfc.patch",
    "patches/qemu-m5stack-peripherals/0049-core2-offline-wifi-controller.patch",
    "patches/qemu-m5stack-peripherals/0050-esp32-spi-panel-dma-transaction.patch",
    "patches/qemu-m5stack-peripherals/0051-cardputer-adv-internal-i2c-pullups.patch",
    "patches/qemu-m5stack-peripherals/0052-cores3-panel-spi2-gdma.patch",
    "patches/qemu-m5stack-peripherals/0053-s3-watchdog-immediate-config.patch",
    "patches/qemu-m5stack-peripherals/0054-i2s-rx-consume-transferred-pcm.patch",
    "patches/qemu-m5stack-peripherals/0055-lcd-cam-frame-dma-chunks.patch",
    "patches/qemu-m5stack-peripherals/0056-spi-sd-multiblock-transfers.patch",
    "patches/qemu-m5stack-peripherals/0057-gc0308-sccb-register-pages.patch",
    "patches/qemu-m5stack-peripherals/0058-gpspi-dma-transfer-chunks.patch",
    "patches/qemu-m5stack-peripherals/0059-lcd-cam-dvp-wire-order.patch",
    "patches/qemu-m5stack-peripherals/0060-gdma-link-cursor-lifecycle.patch",
    "patches/qemu-m5stack-peripherals/0061-gpspi-gdma-channel-lifecycle.patch",
    "patches/qemu-m5stack-peripherals/0062-esp32s3-i2s-continuous-dma-completion.patch",
    "patches/qemu-m5stack-peripherals/0063-core2-touch-buttons.patch",
    "patches/qemu-m5stack-peripherals/0064-esp32-intmatrix-pending-irq-remap.patch",
    "patches/qemu-unit-runtime/0009-native-high-priority-irq-context.patch",
    "patches/qemu-unit-runtime/0010-native-classic-rmt-context.patch",
    "patches/qemu-m5stack-peripherals/0067-esp32-espnow-controlled-peer-loopback.patch",
    "patches/qemu-m5stack-peripherals/0068-core2-dual-spi-panel-routing.patch",
    "patches/qemu-unit-runtime/0011-native-wdt-feed-context.patch",
    "patches/qemu-unit-runtime/0012-native-uart-trace-context.patch",
    "patches/qemu-m5stack-peripherals/0087-unit-hard-reset-output-boundary.patch",
    "patches/qemu-m5stack-peripherals/0091-esp32-timg-feed-reschedule.patch",
    "patches/qemu-unit-runtime/0015-native-wifi-cache-gate-context.patch",
    "patches/qemu-unit-runtime/0016-native-wifi-virtual-time-context.patch",
    "patches/qemu-unit-runtime/0017-native-wifi-station-data-context.patch",
    "patches/qemu-unit-runtime/0018-native-wdt-level-context.patch",
    "patches/qemu-m5stack-peripherals/0096-atoms3-and-atoms3-lite-boards.patch",
    "patches/qemu-m5stack-peripherals/0097-stickc-family-boards.patch",
    "patches/qemu-m5stack-peripherals/0098-atoms3-rgb-and-dial-board.patch",
    "patches/qemu-unit-runtime/0013-native-expanded-atom-rmt-delta.patch",
    "patches/qemu-m5stack-peripherals/0100-esp32-qio-flash-model-header.patch",
    "patches/qemu-unit-runtime/0014-native-core2-atecc608-context.patch",
    "patches/qemu-m5stack-peripherals/0101-stackchan-scs-motion-observer.patch",
    "patches/qemu-m5stack-peripherals/0102-board-power-lifecycle.patch",
    "patches/qemu-m5stack-peripherals/0103-classic-touch-measurement.patch",
    "patches/qemu-m5stack-peripherals/0104-classic-gpio-rtc-sleep.patch",
    "patches/qemu-m5stack-peripherals/0105-stackchan-scs-uart-wiring.patch",
    "patches/qemu-m5stack-peripherals/0106-s3-qio-flash-model-header.patch",
    "patches/qemu-m5stack-peripherals/0107-stackchan-scs-command-edges.patch",
    "patches/qemu-m5stack-peripherals/0108-s3-soft-i2c-reset-handoff.patch",
    "patches/qemu-m5stack-peripherals/0109-uart-rxfifo-reset.patch",
    # Canonical native board additions, then the reconciled Unit batch chain.
    "patches/qemu-unit-runtime/0019-native-atoms3u-board.patch",
    "patches/qemu-unit-runtime/0020-native-atom-voices3r-board.patch",
    "patches/qemu-m5stack-peripherals/0112-atoms3r-cam-board.patch",
    "patches/qemu-m5stack-peripherals/0113-basic-v27-board.patch",
    "patches/qemu-m5stack-peripherals/0114-unit-gpio-batch1.patch",
    "patches/qemu-m5stack-peripherals/0115-atoms3r-cam-sccb.patch",
    "patches/qemu-m5stack-peripherals/0116-atomu-board.patch",
    "patches/qemu-m5stack-peripherals/0117-atomecho-board.patch",
    "patches/qemu-m5stack-peripherals/0118-camera-geometry-stream.patch",
    "patches/qemu-m5stack-peripherals/0119-unit-i2c-batch2.patch",
    "patches/qemu-m5stack-peripherals/0120-unit-i2c-dlight-command-mask.patch",
    "patches/qemu-m5stack-peripherals/0121-m5stick-board.patch",
    "patches/qemu-m5stack-peripherals/0122-atoms3r-m12-board.patch",
    "patches/qemu-m5stack-peripherals/0123-unit-i2c-batch3.patch",
    "patches/qemu-m5stack-peripherals/0124-stickt2-board.patch",
    "patches/qemu-m5stack-peripherals/0125-unit-batch2.patch",
    "patches/qemu-m5stack-peripherals/0126-unit-batch2b.patch",
    "patches/qemu-m5stack-peripherals/0127-unit-dac-fast-mode-write.patch",
    "patches/qemu-m5stack-peripherals/0128-unit-ameter-eeprom-layout.patch",
    "patches/qemu-m5stack-peripherals/0129-unit-batch2b-write-offset.patch",
    "patches/qemu-m5stack-peripherals/0131-unit-batch3c.patch",
    "patches/qemu-m5stack-peripherals/0134-unit-batch4ab.patch",
    "patches/qemu-m5stack-peripherals/0136-unit-batch4c.patch",
    "patches/qemu-m5stack-peripherals/0130-unit-batch3ab.patch",
    "patches/qemu-m5stack-peripherals/0133-unit-vmeter-default-config.patch",
    "patches/qemu-m5stack-peripherals/0135-unit-batch3ab-fixes.patch",
    "patches/qemu-m5stack-peripherals/0132-unit-batch3c-fixes.patch",
    "patches/qemu-m5stack-peripherals/0137-unit-batch5a.patch",
    "patches/qemu-m5stack-peripherals/0138-unit-batch4-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0139-unit-batch5b.patch",
    "patches/qemu-m5stack-peripherals/0140-unit-batch6a.patch",
    "patches/qemu-m5stack-peripherals/0141-unit-batch5-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0142-unit-batch6b.patch",
    "patches/qemu-m5stack-peripherals/0143-unit-batch7a.patch",
    "patches/qemu-m5stack-peripherals/0144-unit-batch6-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0145-unit-batch7b.patch",
    "patches/qemu-m5stack-peripherals/0146-unit-batch8a.patch",
    "patches/qemu-m5stack-peripherals/0147-unit-batch6b-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0148-unit-batch8b.patch",
    "patches/qemu-m5stack-peripherals/0149-unit-batch9a.patch",
    "patches/qemu-m5stack-peripherals/0150-unit-batch7-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0151-unit-batch9b.patch",
    "patches/qemu-m5stack-peripherals/0152-unit-batch10ab.patch",
    "patches/qemu-m5stack-peripherals/0153-unit-batch8-evidence-lcd-read.patch",
    "patches/qemu-m5stack-peripherals/0154-unit-batch10-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0156-unit-id-atecc-wake.patch",
    "patches/qemu-m5stack-peripherals/0157-unit-glass-m5gfx-protocol.patch",
    "patches/qemu-m5stack-peripherals/0158-unit-batch12a.patch",
    "patches/qemu-m5stack-peripherals/0159-unit-batch12b.patch",
    "patches/qemu-m5stack-peripherals/0160-unit-batch12a-evidence-fixes.patch",
    "patches/qemu-m5stack-peripherals/0161-unit-batch12c-chain-frames.patch",
    "patches/qemu-m5stack-peripherals/0162-axp2101-charger-state.patch",
    "patches/qemu-m5stack-peripherals/0163-ed2208-partial-window.patch",
    "patches/qemu-m5stack-peripherals/0164-atoms3-st7735-variant.patch",
    "patches/qemu-m5stack-peripherals/0165-cardputer-adv-explicit-caps.patch",
    "patches/qemu-m5stack-peripherals/0166-spi-sd-card-init-state.patch",
    "patches/qemu-m5stack-peripherals/0167-core2-panel-refresh.patch",
    "patches/qemu-m5stack-peripherals/0168-papers3-paperdiy-et047tc1.patch",
    "patches/qemu-m5stack-peripherals/0169-cardputer-k132-board.patch",
    "patches/qemu-m5stack-peripherals/0170-paper-gt911-contact-ready.patch",
    "patches/qemu-m5stack-peripherals/0171-sticks3-pm1-iap-boot-out.patch",
    "patches/qemu-m5stack-peripherals/0172-sticks3-usb-otg-device.patch",
    "patches/qemu-m5stack-peripherals/0173-sticks3-usb-serial-jtag-cdc-tx.patch",
    "patches/qemu-m5stack-peripherals/0174-sticks3-usb-otg-reset-fence.patch",
    "patches/qemu-m5stack-peripherals/0175-sticks3-wifi-raw-monitor-fixture.patch",
    "patches/qemu-m5stack-peripherals/0176-sticks3-wifi-raw-window-qos.patch",
    "patches/qemu-m5stack-peripherals/0177-sticks3-usb-serial-jtag-host-timing.patch",
    "patches/qemu-m5stack-peripherals/0178-s3-vhci-idle-callback-dispatch.patch",
    "patches/qemu-m5stack-peripherals/0179-esp32-spi-dma-link-latch.patch",
    "patches/qemu-m5stack-peripherals/0180-papercolor-usb-otg.patch",
    "patches/qemu-m5stack-peripherals/0181-atoms3-gc9107-runtime-override.patch",
)
DEPS = (
    ("pkgconf", "2.4.3", "https://distfiles.ariadne.space/pkgconf/pkgconf-2.4.3.tar.xz",
     "51203d99ed573fa7344bf07ca626f10c7cc094e0846ac4aa0023bd0c83c25a41"),
    ("libgpg-error", "1.51", "https://gnupg.org/ftp/gcrypt/libgpg-error/libgpg-error-1.51.tar.bz2",
     "be0f1b2db6b93eed55369cdf79f19f72750c8c7c39fc20b577e724545427e6b2"),
    ("libgcrypt", "1.11.0", "https://gnupg.org/ftp/gcrypt/libgcrypt/libgcrypt-1.11.0.tar.bz2",
     "09120c9867ce7f2081d6aaa1775386b98c2f2f246135761aae47d81f58685b9c"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, *, cwd=None, env=None):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def clone(url: str, target: Path, commit: str, tag: str | None = None):
    if target.exists():
        raise RuntimeError(f"refusing to reset an existing unowned source tree: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone", "--filter=blob:none"]
    if tag:
        args += ["--depth", "1", "--branch", tag, "--single-branch"]
    run(args + [url, target])
    run(["git", "checkout", "--detach", commit], cwd=target)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=target, text=True).strip()
    if actual != commit:
        raise RuntimeError("source commit verification failed")


def source_files(patches: list[Path]) -> set[str]:
    return {
        line[6:]
        for patch in patches for line in patch.read_text().splitlines()
        if line.startswith("+++ b/")
    }


def verify_source(source: Path, patches: list[Path]):
    receipt = source / ".m5-unit-runtime-source.json"
    if not receipt.is_file():
        raise RuntimeError(f"existing source has no owned receipt: {source}")
    record = json.loads(receipt.read_text())
    patch_hashes = {str(p.relative_to(ROOT)): digest(p) for p in patches}
    if record.get("patches") != patch_hashes:
        raise RuntimeError("patches changed; use a new --source-dir instead of resetting this tree")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if actual != QEMU_COMMIT or record.get("qemu", {}).get("commit") != QEMU_COMMIT:
        raise RuntimeError("existing source HEAD does not match the pinned QEMU commit")
    expected_files = source_files(patches)
    if set(record.get("files", {})) != expected_files:
        raise RuntimeError("source receipt does not cover the complete patch file set")
    for name, expected in record["files"].items():
        if not (source / name).is_file() or digest(source / name) != expected:
            raise RuntimeError(f"source has local changes; refusing to overwrite {name}")
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", "HEAD"], cwd=source
    ).decode().split("\0")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=source
    ).decode().split("\0")
    # Meson 1.12 creates this lock in the source-side wrap directory. It is
    # generated build plumbing, not a QEMU source input or user edit.
    generated = {"subprojects/.wraplock"}
    unexpected = (set(changed + untracked) - {"", receipt.name} - generated) - expected_files
    if unexpected:
        raise RuntimeError("source has unrelated changes: " + ", ".join(sorted(unexpected)))
    return record


def prepare_source(source: Path, patches: list[Path]):
    receipt = source / ".m5-unit-runtime-source.json"
    patch_hashes = {str(p.relative_to(ROOT)): digest(p) for p in patches}
    if receipt.is_file():
        return verify_source(source, patches)
    clone(QEMU_URL, source, QEMU_COMMIT, QEMU_TAG)
    for patch in patches:
        run(["git", "apply", "--check", patch], cwd=source)
        run(["git", "apply", patch], cwd=source)
    # Overlapping historical patches must be reversed in the complete reverse
    # sequence; the separate source-replay receipt records that validation.
    record = {
        "schema_version": 1,
        "qemu": {"url": QEMU_URL, "tag": QEMU_TAG, "commit": QEMU_COMMIT},
        "patches": patch_hashes,
        "files": {name: digest(source / name) for name in sorted(source_files(patches))},
    }
    receipt.write_text(json.dumps(record, indent=2) + "\n")
    return record


def download(url: str, path: Path, expected: str):
    if not path.is_file() or digest(path) != expected:
        temporary = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if digest(temporary) != expected:
            raise RuntimeError(f"download SHA256 mismatch: {path.name}")
        temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / ".work/unit-runtime-source/qemu")
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".work/unit-runtime-build")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--check", action="store_true", help="check local patch/source receipts without downloading")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10+ is required; run this script with a matching Python interpreter")
    patches = [ROOT / name for name in PATCHES]
    for patch in patches:
        if not patch.is_file():
            raise RuntimeError(f"required source patch is missing: {patch.relative_to(ROOT)}")
    if args.check:
        source = args.source_dir.resolve()
        record = verify_source(source, patches) if source.exists() else None
        print(json.dumps({"qemu_commit": QEMU_COMMIT,
                          "patches": {str(p.relative_to(ROOT)): digest(p) for p in patches},
                          "source_status": "verified" if record else "not-prepared",
                          "source_files": len(record["files"]) if record else 0}, indent=2))
        return 0
    if args.jobs < 1 or args.jobs > 64:
        parser.error("--jobs must be between 1 and 64")
    source = args.source_dir.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    record = prepare_source(source, patches)
    if args.prepare_only:
        print(f"Prepared pinned source: {source}")
        return 0
    venv = work / "venv"
    if not (venv / "bin/python").exists():
        run([sys.executable, "-m", "venv", venv])
        run([venv / "bin/python", "-m", "pip", "install", "ninja==1.13.2", "meson==1.12.1", "pycotap==1.3.1"])
    prefix = work / "deps"
    prefix.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PATH"] = f"{venv}/bin:{prefix}/bin:/opt/homebrew/bin:" + env.get("PATH", "")
    env["PKG_CONFIG_PATH"] = f"{prefix}/lib/pkgconfig:/opt/homebrew/lib/pkgconfig:" + env.get("PKG_CONFIG_PATH", "")
    archives = work / "downloads"
    archives.mkdir(exist_ok=True)
    for name, version, url, checksum in DEPS:
        archive = archives / url.rsplit("/", 1)[-1]
        download(url, archive, checksum)
        dep_source = work / f"{name}-{version}"
        if not dep_source.exists():
            with tarfile.open(archive) as tar:
                for member in tar.getmembers():
                    destination = (work / member.name).resolve()
                    if work not in destination.parents or member.issym() or member.islnk():
                        raise RuntimeError("unsafe dependency archive member")
                tar.extractall(work)
        sentinel = prefix / ("bin/pkgconf" if name == "pkgconf" else f"lib/lib{name.removeprefix('lib')}.a")
        if not sentinel.exists():
            options = [f"--prefix={prefix}", "--disable-shared", "--enable-static"]
            if name != "pkgconf":
                options += ["--with-pic", "--disable-doc"]
            if name == "libgpg-error":
                options += ["--disable-tests", "--disable-nls"]
            if name == "libgcrypt":
                options += [f"--with-libgpg-error-prefix={prefix}", "--disable-asm"]
            run(["./configure", *options], cwd=dep_source, env=env)
            run(["make", f"-j{args.jobs}"], cwd=dep_source, env=env)
            run(["make", "install"], cwd=dep_source, env=env)
    pkg_config = prefix / "bin/pkg-config"
    if not pkg_config.exists():
        pkg_config.symlink_to("pkgconf")
    slirp = work / "libslirp"
    if not slirp.exists():
        clone(SLIRP_URL, slirp, SLIRP_COMMIT)
    if not (prefix / "lib/libslirp.a").exists():
        run([venv / "bin/meson", "setup", slirp / "build", slirp,
             f"--prefix={prefix}", "--default-library=static", "-Dbuildtype=release"], env=env)
        run([venv / "bin/ninja", "-C", slirp / "build", f"-j{args.jobs}"], env=env)
        run([venv / "bin/meson", "install", "-C", slirp / "build"], env=env)
    # glib/pixman are existing host dependencies. No brew/apt/global install is run.
    run([pkg_config, "--exists", "glib-2.0", "pixman-1", "slirp"], env=env)
    build = source / "build"
    build.mkdir(exist_ok=True)
    flags = ["--target-list=xtensa-softmmu", f"--python={venv}/bin/python", "--enable-gcrypt",
             "--enable-slirp", "--disable-docs", "--disable-werror", "--disable-gtk",
             "--disable-gnutls", "--disable-nettle", "--disable-vnc", "--disable-curl",
             "--disable-libssh", "--disable-zstd", "--disable-bzip2", "--disable-curses",
             "--disable-auth-pam", "--disable-dbus-display", "--disable-tpm", "--disable-sdl",
             "--disable-cocoa", "--disable-png", f"--extra-cflags=-I{prefix}/include",
             f"--extra-ldflags={prefix}/lib/libgcrypt.a {prefix}/lib/libgpg-error.a"]
    run([source / "configure", *flags], cwd=build, env=env)
    run([venv / "bin/ninja", f"-j{args.jobs}", "qemu-system-xtensa"], cwd=build, env=env)
    binary = build / "qemu-system-xtensa"
    record.update({"binary": str(binary), "binary_sha256": digest(binary),
                   "slirp_commit": SLIRP_COMMIT, "source_only_validation": True})
    (work / "build-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Built: {binary}\nSHA256: {digest(binary)}\nUse Device Service for functional validation.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"bootstrap failed: {error}", file=sys.stderr)
        raise SystemExit(1)

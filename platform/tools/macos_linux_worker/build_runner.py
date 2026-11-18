"""Build and ad-hoc sign the ARM64 macOS Virtualization runner locally."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "runner.swift"
ENTITLEMENTS = HERE / "runner.entitlements.plist"
VIRTUALIZATION = "com.apple.security.virtualization"
TARGET = "arm64-apple-macosx26.0"
XCRUN = ("/usr/bin/xcrun", "--sdk", "macosx")
CODESIGN = "/usr/bin/codesign"


def sha256(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def check_entitlements(content):
    entitlements = plistlib.loads(content)
    if (not isinstance(entitlements, dict) or set(entitlements) != {VIRTUALIZATION}
            or entitlements[VIRTUALIZATION] is not True):
        raise ValueError("Expected exactly the Apple virtualization entitlement")


def build(output):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Building the runner requires ARM64 macOS with Xcode command-line tools")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Runner output already exists: {output}")
    check_entitlements(ENTITLEMENTS.read_bytes())
    source_sha = sha256(SOURCE)
    entitlements_sha = sha256(ENTITLEMENTS)
    with TemporaryDirectory(prefix=".m5-vz-build-", dir=output.parent) as scratch:
        binary = Path(scratch) / "vz-managed-runner"
        subprocess.run(
            [*XCRUN, "swiftc", "-O", "-swift-version", "5", "-warnings-as-errors",
             "-target", TARGET, "-o", binary, SOURCE],
            check=True,
        )
        binary.chmod(0o700)
        subprocess.run(
            [CODESIGN, "--force", "--sign", "-", "--timestamp=none", "--entitlements", ENTITLEMENTS, binary],
            check=True,
        )
        subprocess.run([CODESIGN, "--verify", "--strict", binary], check=True)
        check_entitlements(subprocess.check_output(
            [CODESIGN, "--display", "--xml", "--entitlements", "-", binary]
        ))
        if subprocess.check_output([*XCRUN, "lipo", "-archs", binary]).strip() != b"arm64":
            raise RuntimeError("Built runner is not an ARM64 executable")
        runner_sha = sha256(binary)
        if sha256(SOURCE) != source_sha or sha256(ENTITLEMENTS) != entitlements_sha:
            raise RuntimeError("Runner source or entitlements changed during the build")
        os.link(binary, output, follow_symlinks=False)
    return {"runner_sha256": runner_sha, "source_sha256": source_sha, "entitlements_sha256": entitlements_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Path for the new executable")
    args = parser.parse_args()
    try:
        result = build(args.output.expanduser())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Runner build failed: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

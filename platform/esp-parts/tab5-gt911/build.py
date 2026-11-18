"""Build the pinned Tab5 co-sim board module with Rust 1.88.0."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGET = "wasm32-unknown-unknown"
MODULE = "m5_tab5_gt911.wasm"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument(
        "--codec-control", action="store_true", help="include Tab5 audio codec I2C controls"
    )
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    target_dir = output / "cargo-target"
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    launch = dict(os.environ, CARGO_HOME=str(cargo_home), CARGO_ENCODED_RUSTFLAGS="\x1f".join((
        f"--remap-path-prefix={ROOT}=/m5-gt911-source",
        f"--remap-path-prefix={cargo_home}=/m5-gt911-cargo",
        f"--remap-path-prefix={target_dir}=/m5-gt911-target",
    )))
    command = [
        args.cargo, "build", "--locked", "--release", "--target", TARGET,
        "--target-dir", str(target_dir), "--manifest-path", str(HERE / "Cargo.toml"),
    ]
    if args.codec_control:
        command.extend(["--features", "codec-control"])
    subprocess.run(command, cwd=HERE, env=launch, check=True)
    module = output / MODULE
    shutil.copyfile(target_dir / TARGET / "release" / MODULE, module)
    shutil.copyfile(HERE / "board.json", output / "board.json")
    print(hashlib.sha256(module.read_bytes()).hexdigest(), module.name)


if __name__ == "__main__":
    main()

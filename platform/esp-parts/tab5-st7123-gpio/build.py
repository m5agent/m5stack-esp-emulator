"""Build the pinned Tab5 GPIO I2C board module with Rust 1.88.0."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGET = "wasm32-unknown-unknown"
MODULE = "m5_tab5_gpio_i2c.wasm"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    target_dir = output / "cargo-target"
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    launch = dict(os.environ, CARGO_HOME=str(cargo_home), CARGO_ENCODED_RUSTFLAGS="\x1f".join((
        f"--remap-path-prefix={ROOT}=/m5-tab5-gpio-i2c-source",
        f"--remap-path-prefix={cargo_home}=/m5-tab5-gpio-i2c-cargo",
        f"--remap-path-prefix={target_dir}=/m5-tab5-gpio-i2c-target",
    )))
    subprocess.run([
        args.cargo, "build", "--locked", "--release", "--target", TARGET,
        "--target-dir", str(target_dir), "--manifest-path", str(HERE / "Cargo.toml"),
    ], cwd=HERE, env=launch, check=True)
    module = output / MODULE
    shutil.copyfile(target_dir / TARGET / "release" / MODULE, module)
    shutil.copyfile(HERE / "board.json", output / "board.json")
    print(hashlib.sha256(module.read_bytes()).hexdigest(), module.name)


if __name__ == "__main__":
    main()

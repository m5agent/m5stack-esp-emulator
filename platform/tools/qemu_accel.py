"""Shared deterministic QEMU accelerator arguments for Core2."""
from __future__ import annotations

CORE2_TCG_TB_SIZE_MIB = 128


def core2_accel_args() -> list[str]:
    """Bound per-session TCG translation memory for deterministic LX6 runs."""
    return [
        "-accel",
        f"tcg,thread=single,tb-size={CORE2_TCG_TB_SIZE_MIB}",
        "-icount",
        "shift=auto,align=off,sleep=off",
    ]

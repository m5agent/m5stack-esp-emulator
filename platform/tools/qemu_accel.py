"""Shared deterministic QEMU accelerator arguments for Core2."""
from __future__ import annotations

import os

CORE2_TCG_TB_SIZE_MIB = 128
CORE2_ICOUNT_SHIFT = 5
CORE2_ICOUNT_SHIFT_ENV = "M5_CORE2_ICOUNT_SHIFT"
CORE2_ICOUNT_MODE = (
    f"shift={CORE2_ICOUNT_SHIFT},align=off,sleep=off"
)


def core2_accel_args() -> list[str]:
    """Bound per-session TCG translation memory for deterministic LX6 runs."""
    shift = os.environ.get(
        CORE2_ICOUNT_SHIFT_ENV,
        str(CORE2_ICOUNT_SHIFT),
    )
    if shift != "auto":
        try:
            value = int(shift)
        except ValueError as error:
            raise ValueError(
                f"{CORE2_ICOUNT_SHIFT_ENV} must be auto or 0-10"
            ) from error
        if not 0 <= value <= 10:
            raise ValueError(
                f"{CORE2_ICOUNT_SHIFT_ENV} must be auto or 0-10"
            )
        shift = str(value)
    return [
        "-accel",
        f"tcg,thread=single,tb-size={CORE2_TCG_TB_SIZE_MIB}",
        "-icount",
        f"shift={shift},align=off,sleep=off",
    ]

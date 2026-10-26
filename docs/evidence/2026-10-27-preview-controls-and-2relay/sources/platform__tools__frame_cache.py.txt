"""Per-session, demand-driven framebuffer sharing without background workers.

The default max_age_ms=0 always performs this caller's own capture. Opt-in
bounded-age readers share a successful sample or one in-flight capture for the
same generation. A capture failure is delivered to its waiters, never replaced
with an older successful sample.

Generation values must be stable immutable identities. The session must call
invalidate() under its own state lock when reset, stop or program identity
changes, and supply is_current to fence the gap before entering get(). Neither
capture nor is_current is called while the cache condition is held, so session
code may acquire its own lock in those callbacks and invalidate while holding it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import threading
import time
from typing import Callable, Hashable


MAX_AGE_MS = 1000


class FrameGenerationChanged(RuntimeError):
    """The requested lifecycle/program identity stopped owning this capture."""


@dataclass(frozen=True)
class CaptureResult:
    png: bytes
    width: int
    height: int
    source: str = "live"
    captured_at: str | None = None
    nonblack_pixels: int | None = None
    unique_colors: int | None = None
    execution_id: str | None = None
    revision_id: str | None = None
    program_state: str | None = None
    captured_monotonic: float | None = None


@dataclass(frozen=True)
class FrameSample:
    png: bytes
    width: int
    height: int
    source: str
    captured_at: str | None
    capture_seq: int
    sha256: str
    generation: Hashable
    nonblack_pixels: int | None = None
    unique_colors: int | None = None
    execution_id: str | None = None
    revision_id: str | None = None
    program_state: str | None = None

    def as_dict(self) -> dict:
        """Return an independent metrics mapping; PNG storage is immutable."""
        result = {
            "png": self.png,
            "width": self.width,
            "height": self.height,
            "png_bytes": len(self.png),
            "source": self.source,
            "captured_at": self.captured_at,
            "capture_seq": self.capture_seq,
            "sha256": self.sha256,
            "execution_id": self.execution_id,
            "revision_id": self.revision_id,
            "program_state": self.program_state,
        }
        for key in ("nonblack_pixels", "unique_colors"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass
class _Flight:
    generation: Hashable
    epoch: int
    done: bool = False
    sample: FrameSample | None = None
    captured_monotonic: float = 0.0
    error: BaseException | None = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FrameCache:
    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], str] = _utcnow,
    ):
        self._condition = threading.Condition()
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._epoch = 0
        self._capture_seq = 0
        self._sample: FrameSample | None = None
        self._captured_monotonic = 0.0
        self._flight: _Flight | None = None

    def invalidate(self) -> None:
        """Discard reuse and prevent an older in-flight result being published.

        This does not cancel the source operation or start another capture in
        parallel with it. Its owner still clears the flight on completion.
        """
        with self._condition:
            self._epoch += 1
            self._sample = None
            self._condition.notify_all()

    @staticmethod
    def _check_current(generation, is_current) -> None:
        if is_current is not None and not is_current(generation):
            raise FrameGenerationChanged("frame generation changed")

    def _check_epoch(self, epoch: int) -> None:
        if self._epoch != epoch:
            raise FrameGenerationChanged("frame capture was invalidated")

    @staticmethod
    def _normalize(result: CaptureResult) -> CaptureResult:
        if not isinstance(result, CaptureResult):
            raise TypeError("capture must return CaptureResult")
        if not isinstance(result.png, (bytes, bytearray, memoryview)) or not result.png:
            raise ValueError("capture PNG must contain bytes")
        if any(type(value) is not int or value <= 0 for value in (result.width, result.height)):
            raise ValueError("capture dimensions must be positive integers")
        if result.source not in {"live", "persisted"}:
            raise ValueError("capture source must be live or persisted")
        if result.captured_at is not None and (
            not isinstance(result.captured_at, str) or not result.captured_at
        ):
            raise ValueError("captured_at must be a nonempty timestamp or None")
        for value in (result.nonblack_pixels, result.unique_colors):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("capture metrics must be nonnegative integers")
        for value in (result.execution_id, result.revision_id, result.program_state):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError("capture program identity must be nonempty strings or None")
        if result.captured_monotonic is not None and (
            type(result.captured_monotonic) not in {int, float}
            or not math.isfinite(result.captured_monotonic)
        ):
            raise ValueError("captured_monotonic must be finite or None")
        return CaptureResult(
            png=bytes(result.png), width=result.width, height=result.height,
            source=result.source, captured_at=result.captured_at,
            nonblack_pixels=result.nonblack_pixels, unique_colors=result.unique_colors,
            execution_id=result.execution_id, revision_id=result.revision_id,
            program_state=result.program_state,
            captured_monotonic=result.captured_monotonic,
        )

    def get(
        self,
        capture: Callable[[], CaptureResult],
        *,
        generation: Hashable,
        max_age_ms: int | float = 0,
        is_current: Callable[[Hashable], bool] | None = None,
    ) -> FrameSample:
        """Capture or reuse one immutable sample for this exact generation.

        Reuse TTL uses a live source's captured_monotonic when supplied, so PNG
        encoding cannot extend freshness; otherwise it starts at successful
        source completion. This monotonic value never leaves the cache.
        captured_at is supplied by the source when available; only a *live*
        capture without a timestamp gets the current UTC time. Historical
        timestamps, including an unknown time on legacy frames, stay unchanged.

        A sequence counts successfully published captures, not pixel changes;
        equal PNGs therefore share SHA-256 but have distinct capture sequences.
        A zero-age caller waits for other source work and then captures itself.
        A positive-age waiter receives its joined capture's error, if any.
        """
        if (
            type(max_age_ms) not in {int, float}
            or not 0 <= max_age_ms <= MAX_AGE_MS
        ):
            raise ValueError(f"max_age_ms must be between 0 and {MAX_AGE_MS}")
        hash(generation)
        self._check_current(generation, is_current)
        with self._condition:
            epoch = self._epoch
        while True:
            self._check_current(generation, is_current)
            sample = None
            owner = False
            error = None
            with self._condition:
                self._check_epoch(epoch)
                if (
                    max_age_ms > 0 and self._sample is not None
                    and self._sample.generation == generation
                    and (self._monotonic() - self._captured_monotonic) * 1000 < max_age_ms
                ):
                    sample = self._sample
                elif self._flight is not None:
                    flight = self._flight
                    join = max_age_ms > 0 and flight.generation == generation and flight.epoch == epoch
                    while not flight.done:
                        self._condition.wait()
                        self._check_epoch(epoch)
                    if join:
                        error = flight.error
                        if error is None and (
                            self._monotonic() - flight.captured_monotonic
                        ) * 1000 < max_age_ms:
                            sample = flight.sample
                else:
                    flight = _Flight(generation=generation, epoch=epoch)
                    self._flight = flight
                    owner = True
            if error is not None:
                raise error
            if sample is not None:
                self._check_current(generation, is_current)
                with self._condition:
                    self._check_epoch(epoch)
                return sample
            if owner:
                break

        try:
            self._check_current(generation, is_current)
            result = capture()
            captured_monotonic = self._monotonic()
            result = self._normalize(result)
            if result.source == "live" and result.captured_monotonic is not None:
                captured_monotonic = result.captured_monotonic
            captured_at = result.captured_at
            if captured_at is None and result.source == "live":
                captured_at = self._utcnow()
            digest = hashlib.sha256(result.png).hexdigest()
            self._check_current(generation, is_current)
            with self._condition:
                self._check_epoch(epoch)
                self._capture_seq += 1
                sample = FrameSample(
                    png=result.png, width=result.width, height=result.height,
                    source=result.source, captured_at=captured_at,
                    capture_seq=self._capture_seq, sha256=digest,
                    generation=generation, nonblack_pixels=result.nonblack_pixels,
                    unique_colors=result.unique_colors,
                    execution_id=result.execution_id, revision_id=result.revision_id,
                    program_state=result.program_state,
                )
                self._sample = sample
                self._captured_monotonic = captured_monotonic
                flight.sample = sample
                flight.captured_monotonic = captured_monotonic
                flight.done = True
                self._flight = None
                self._condition.notify_all()
        except BaseException as error:
            # Source failures and generation changes invalidate older success.
            # A later independent request may retry; joined readers see failure.
            with self._condition:
                self._sample = None
                flight.error = error
                flight.done = True
                self._flight = None
                self._condition.notify_all()
            raise
        self._check_current(generation, is_current)
        with self._condition:
            self._check_epoch(epoch)
        return sample

"""Controller-derived presentation hints; raw framebuffer coordinates stay physical.

This describes the inverse of the emulated controller's address transform, not
an OCR guess about text or a promise that an application has finished redrawing.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import struct
import zlib

from device_service_errors import ServiceError


@dataclass(frozen=True)
class FramePresentation:
    status: str = "unknown"
    rotation_cw: int | None = None
    mirrored: bool | None = None
    controller: tuple = ()

    def as_dict(self) -> dict:
        return {"schema_version": 1, "status": self.status,
                "rotation_cw": self.rotation_cw, "mirrored": self.mirrored,
                "controller": dict(self.controller)}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            return cls()
        if value.get("status") == "unstable":
            return cls(status="unstable")
        return presentation_from_controller(value.get("controller"))


def presentation_from_controller(value) -> FramePresentation:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return FramePresentation()
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return FramePresentation()
    if value.get("supported") is not True or type(value.get("apply_madctl")) is not bool:
        return FramePresentation()
    limits = {"generation": (0, 2**64 - 1), "madctl": (0, 255),
              "glass_rotation": (0, 3), "memory_width": (1, 16384),
              "memory_height": (1, 16384), "width": (1, 16384),
              "height": (1, 16384), "offset_x": (0, 16384), "offset_y": (0, 16384)}
    if any(type(value.get(key)) is not int or not lo <= value[key] <= hi
           for key, (lo, hi) in limits.items()):
        return FramePresentation()
    # A maps guest address axes to controller RAM. B maps raw surface axes to
    # RAM (the board's fixed glass mount). A^-1 B maps raw to logical axes.
    bits = value["madctl"] if value["apply_madctl"] else 0
    sx, sy = (-1 if bits & 0x40 else 1), (-1 if bits & 0x80 else 1)
    inverse = ((0, sy), (sx, 0)) if bits & 0x20 else ((sx, 0), (0, sy))
    glass = (((1, 0), (0, 1)), ((0, 1), (-1, 0)),
             ((-1, 0), (0, -1)), ((0, -1), (1, 0)))[value["glass_rotation"]]
    matrix = tuple(tuple(sum(inverse[r][k] * glass[k][c] for k in range(2))
                         for c in range(2)) for r in range(2))
    rotations = {((1, 0), (0, 1)): 0, ((0, -1), (1, 0)): 90,
                 ((-1, 0), (0, -1)): 180, ((0, 1), (-1, 0)): 270}
    rotation = rotations.get(matrix)
    controller = tuple((key, value[key]) for key in
                       ("schema_version", "supported", "apply_madctl", *limits))
    return FramePresentation("known" if rotation is not None else "mirrored",
                             rotation, rotation is None, controller)


def bind_presentation(before: FramePresentation, after: FramePresentation,
                      width: int, height: int) -> FramePresentation:
    if before != after:
        return FramePresentation(status="unstable")
    if before.controller:
        state = dict(before.controller)
        if state["width"] != width or state["height"] != height:
            return FramePresentation()
    return before


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def _rotate_png(png: bytes, width: int, height: int, rotation: int) -> tuple[bytes, int, int]:
    """Rotate only the bounded RGB8/filter-0 PNG format produced by this service."""
    if rotation == 0:
        return png, width, height
    if not 0 < width * height <= 16 * 1024 * 1024 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid service PNG")
    offset, compressed, header, ended = 8, bytearray(), None, False
    while offset + 12 <= len(png):
        size = struct.unpack(">I", png[offset:offset + 4])[0]
        kind = png[offset + 4:offset + 8]
        end = offset + 8 + size
        if end + 4 > len(png) or zlib.crc32(png[offset + 4:end]) & 0xffffffff != struct.unpack(">I", png[end:end + 4])[0]:
            raise ValueError("invalid service PNG chunk")
        data = png[offset + 8:end]
        if kind == b"IHDR":
            if header is not None:
                raise ValueError("duplicate PNG header")
            header = data
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            ended = True
            break
        offset = end + 4
    if not ended or header != struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0):
        raise ValueError("unsupported service PNG format")
    expected = height * (width * 3 + 1)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(compressed), expected + 1)
    if len(raw) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError("invalid service PNG pixels")
    stride = width * 3 + 1
    if any(raw[y * stride] != 0 for y in range(height)):
        raise ValueError("unsupported service PNG filter")
    out_width, out_height = (height, width) if rotation in (90, 270) else (width, height)
    output = bytearray(out_height * (out_width * 3 + 1))
    for y in range(height):
        for x in range(width):
            dx, dy = ((height - 1 - y, x) if rotation == 90 else
                      (width - 1 - x, height - 1 - y) if rotation == 180 else
                      (y, width - 1 - x))
            src, dst = y * stride + 1 + x * 3, dy * (out_width * 3 + 1) + 1 + dx * 3
            output[dst:dst + 3] = raw[src:src + 3]
    ihdr = struct.pack(">IIBBBBB", out_width, out_height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(output, 9)) + _chunk(b"IEND", b""), out_width, out_height)


def frame_representation(frame: dict, orient: str = "panel") -> dict:
    if orient not in {"panel", "display"}:
        raise ServiceError("invalid_frame_orientation", "orient must be panel or display", 400)
    result = dict(frame)
    presentation = FramePresentation.from_dict(frame.get("presentation"))
    result["presentation"] = presentation.as_dict()
    result["coordinate_space"] = orient
    result["raw_sha256"] = hashlib.sha256(frame["png"]).hexdigest()
    if orient == "display":
        if presentation.status != "known":
            raise ServiceError("frame_orientation_unavailable", "this capture has no stable non-mirrored controller orientation; request orient=panel", 409)
        try:
            result["png"], result["width"], result["height"] = _rotate_png(
                frame["png"], frame["width"], frame["height"], presentation.rotation_cw)
        except (ValueError, zlib.error) as error:
            raise ServiceError("frame_orientation_unavailable", "retained frame cannot be losslessly oriented", 409) from error
    result["sha256"] = hashlib.sha256(result["png"]).hexdigest()
    result["png_bytes"] = len(result["png"])
    return result


def presentation_headers(frame: dict) -> dict[str, str]:
    presentation = frame["presentation"]
    result = {"X-Frame-Coordinate-Space": frame["coordinate_space"],
              "X-Frame-Orientation": presentation["status"],
              "X-Frame-Raw-SHA256": frame["raw_sha256"],
              "X-Frame-Presentation": json.dumps(presentation, separators=(",", ":"))}
    if presentation["rotation_cw"] is not None:
        result["X-Frame-Rotation"] = str(presentation["rotation_cw"])
    return result

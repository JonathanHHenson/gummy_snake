"""Deterministic, network-independent inputs for the Canvas benchmark suite.

The fixtures are generated from fixed formulas rather than downloaded assets.  The
manifest validates the exact bytes consumed by workloads, including text and OBJ
source, so a benchmark cannot silently use a changed fixture.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class RgbaFixture:
    """Packed top-left RGBA fixture data."""

    name: str
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("RGBA fixture dimensions must be positive")
        if len(self.pixels) != self.width * self.height * 4:
            raise ValueError("RGBA fixture byte length does not match its dimensions")


@dataclass(frozen=True, slots=True)
class PathRecord:
    """A deterministic primitive or path input expressed in logical coordinates."""

    kind: str
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class FixtureManifestEntry:
    """Expected content identity for one generated fixture."""

    name: str
    byte_length: int
    sha256: str


def _rgba(width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int, int]]) -> bytes:
    return bytes(
        component for y in range(height) for x in range(width) for component in pixel(x, y)
    )


def _checker_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    return (244, 80, 72, 255) if (x // 2 + y // 2) % 2 == 0 else (31, 132, 217, 255)


def _sprite_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    tile_x, tile_y = x // 4, y // 4
    palette = ((255, 204, 0), (0, 184, 148), (108, 92, 231), (214, 48, 49))
    red, green, blue = palette[(tile_x + tile_y * 2) % len(palette)]
    alpha = 255 if (x + y) % 3 else 192
    return red, green, blue, alpha


CHECKERBOARD = RgbaFixture("checkerboard-8", 8, 8, _rgba(8, 8, _checker_pixel))
SPRITE_SHEET = RgbaFixture("sprite-sheet-8", 8, 8, _rgba(8, 8, _sprite_pixel))
PIXEL_BUFFER = RgbaFixture(
    "pixel-buffer-4",
    4,
    4,
    _rgba(4, 4, lambda x, y: (x * 61, y * 61, (x + y) * 31, 255)),
)
MEDIA_FRAME_RGBA = RgbaFixture(
    "media-frame-6",
    6,
    4,
    _rgba(6, 4, lambda x, y: (17 * x + 13 * y, 29 * x, 47 * y, 255)),
)

PATH_RECORDS = (
    PathRecord("rect", ((2, 2), (14, 2), (14, 10), (2, 10))),
    PathRecord("triangle", ((18, 2), (30, 10), (18, 10))),
    PathRecord("polyline", ((2, 18), (8, 13), (14, 21), (20, 15), (30, 22))),
    PathRecord("clip", ((4, 26), (28, 26), (28, 38), (4, 38))),
)

TEXT_CORPUS: Mapping[str, tuple[str, ...]] = {
    "ascii": ("Gummy Snake", "frame 001", "cache cache cache"),
    "combining": ("Cafe\u0301", "A\u0308ngstrom"),
    "rtl": ("\u0645\u0631\u062d\u0628\u0627",),
    "cjk": ("\u30ad\u30e3\u30f3\u30d0\u30b9",),
    "multiline": ("first line\nsecond line",),
}

MINIMAL_OBJ = (
    """# deterministic benchmark triangle\nv 0.0 0.0 0.0\nv 1.0 0.0 0.0\nv 0.0 1.0 0.0\nf 1 2 3\n"""
)


def _path_bytes(records: tuple[PathRecord, ...]) -> bytes:
    payload = [{"kind": record.kind, "points": record.points} for record in records]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _text_bytes(corpus: Mapping[str, tuple[str, ...]]) -> bytes:
    return json.dumps(corpus, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


FIXTURE_BYTES: Mapping[str, bytes] = {
    CHECKERBOARD.name: CHECKERBOARD.pixels,
    SPRITE_SHEET.name: SPRITE_SHEET.pixels,
    PIXEL_BUFFER.name: PIXEL_BUFFER.pixels,
    MEDIA_FRAME_RGBA.name: MEDIA_FRAME_RGBA.pixels,
    "path-records": _path_bytes(PATH_RECORDS),
    "text-corpus": _text_bytes(TEXT_CORPUS),
    "minimal-triangle-obj": MINIMAL_OBJ.encode("utf-8"),
}

FIXTURE_MANIFEST = tuple(
    FixtureManifestEntry(name, len(payload), sha256(payload).hexdigest())
    for name, payload in sorted(FIXTURE_BYTES.items())
)


def fixture_manifest() -> tuple[FixtureManifestEntry, ...]:
    """Return the reviewed fixture manifest in stable name order."""

    return FIXTURE_MANIFEST


def validate_manifest(
    manifest: tuple[FixtureManifestEntry, ...] = FIXTURE_MANIFEST,
    payloads: Mapping[str, bytes] = FIXTURE_BYTES,
) -> None:
    """Fail if generated fixture bytes differ from the reviewed manifest."""

    expected_names = {entry.name for entry in manifest}
    if expected_names != set(payloads):
        raise ValueError("fixture manifest names do not match generated fixture names")
    for entry in manifest:
        payload = payloads[entry.name]
        if len(payload) != entry.byte_length:
            raise ValueError(f"fixture length mismatch for {entry.name}")
        if sha256(payload).hexdigest() != entry.sha256:
            raise ValueError(f"fixture hash mismatch for {entry.name}")


def sprite_image() -> object:
    """Create the public Gummy Snake image used by sprite workloads.

    Importing Gummy Snake occurs only when a real workload runs, keeping fixture
    validation independent of the native canvas extension.
    """

    from gummysnake import Image

    return Image(SPRITE_SHEET.width, SPRITE_SHEET.height, SPRITE_SHEET.pixels)


__all__ = [
    "CHECKERBOARD",
    "FIXTURE_BYTES",
    "FIXTURE_MANIFEST",
    "MEDIA_FRAME_RGBA",
    "MINIMAL_OBJ",
    "PATH_RECORDS",
    "PIXEL_BUFFER",
    "RgbaFixture",
    "SPRITE_SHEET",
    "TEXT_CORPUS",
    "FixtureManifestEntry",
    "PathRecord",
    "fixture_manifest",
    "sprite_image",
    "validate_manifest",
]

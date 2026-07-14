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
class MediaFrameFixture:
    """A decoded grayscale, BGR, or BGRA buffer with its reviewed RGBA result."""

    name: str
    width: int
    height: int
    channels: int
    pixels: bytes
    expected_rgba: RgbaFixture

    def __post_init__(self) -> None:
        if self.channels not in {1, 3, 4}:
            raise ValueError("media frame fixtures require 1, 3, or 4 channels")
        if self.width != self.expected_rgba.width or self.height != self.expected_rgba.height:
            raise ValueError("media frame fixture dimensions must match its RGBA result")
        if len(self.pixels) != self.width * self.height * self.channels:
            raise ValueError("media frame byte length does not match its dimensions")


@dataclass(frozen=True, slots=True)
class ObjFixture:
    """A reviewed local OBJ payload and its exact parsed triangle topology."""

    name: str
    source: str
    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]

    @property
    def payload(self) -> bytes:
        """Return the UTF-8 OBJ bytes tracked by the fixture manifest."""

        return self.source.encode("utf-8")


@dataclass(frozen=True, slots=True)
class TextCorpusFixture:
    """A reviewed Unicode corpus used for deterministic text-input coverage."""

    name: str
    corpus: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if not self.name or not self.corpus:
            raise ValueError("text corpus fixtures require a name and at least one category")
        if any(
            not category or not values or any(not value for value in values)
            for category, values in self.corpus.items()
        ):
            raise ValueError("text corpus fixture categories must contain non-empty strings")

    @property
    def payload(self) -> bytes:
        """Return canonical UTF-8 corpus bytes tracked by the fixture manifest."""

        return _text_bytes(self.corpus)


@dataclass(frozen=True, slots=True)
class PathRecord:
    """A deterministic primitive or path input expressed in logical coordinates."""

    kind: str
    points: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if not self.kind or not self.points:
            raise ValueError("path records require a kind and at least one point")


@dataclass(frozen=True, slots=True)
class PrimitivePathFixture:
    """Reviewed ordered primitive/path records in logical coordinates."""

    name: str
    records: tuple[PathRecord, ...]

    @property
    def payload(self) -> bytes:
        """Return canonical JSON bytes tracked by the fixture manifest."""

        return _path_bytes(self.records)


@dataclass(frozen=True, slots=True)
class FixtureQualification:
    """Explicit marker for reviewed binary fixture families not bundled here."""

    family: str
    status: str
    reason: str

    def __post_init__(self) -> None:
        if not self.family or not self.status or not self.reason:
            raise ValueError("fixture qualification values must be non-empty")


@dataclass(frozen=True, slots=True)
class FixtureManifestEntry:
    """Expected content identity for one generated fixture."""

    name: str
    byte_length: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ResourceCounterFamily:
    """Public resident and peak diagnostic paths for one retained resource family."""

    name: str
    resident_counter: str
    peak_counter: str

    def __post_init__(self) -> None:
        if not self.name or not self.resident_counter or not self.peak_counter:
            raise ValueError("resource counter family values must be non-empty")


@dataclass(frozen=True, slots=True)
class ResourceResetFixture:
    """A deterministic warm-cache reset contract based on a reviewed RGBA source."""

    name: str
    source: RgbaFixture
    retained_families: tuple[ResourceCounterFamily, ...]
    reset_activity_counters: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("resource reset fixture name must be non-empty")
        if not self.retained_families:
            raise ValueError("resource reset fixture requires retained resource families")
        if not self.reset_activity_counters or not all(self.reset_activity_counters):
            raise ValueError("resource reset fixture requires reset activity counters")

    @property
    def required_counters(self) -> tuple[str, ...]:
        """Return the exact public counters the reset oracle may inspect."""

        return tuple(
            dict.fromkeys(
                counter
                for family in self.retained_families
                for counter in (family.resident_counter, family.peak_counter)
            )
            | dict.fromkeys(self.reset_activity_counters)
        )


def _rgba(width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int, int]]) -> bytes:
    return bytes(
        component for y in range(height) for x in range(width) for component in pixel(x, y)
    )


def generated_rgba_fixture(width: int, height: int, *, seed: int = 0) -> RgbaFixture:
    """Generate exact, non-uniform RGBA input at a declared workload size."""

    if not 1 <= width <= 4_096 or not 1 <= height <= 4_096:
        raise ValueError("generated RGBA fixture dimensions must be in [1, 4096]")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 255:
        raise ValueError("generated RGBA fixture seed must be an integer in [0, 255]")
    pixels = _rgba(
        width,
        height,
        lambda x, y: (
            (17 * x + 13 * y + seed) % 256,
            (29 * x + 7 * y + seed * 3) % 256,
            (11 * x + 47 * y + seed * 5) % 256,
            64 + (x * 37 + y * 19 + seed) % 192,
        ),
    )
    return RgbaFixture(f"generated-rgba-{width}x{height}-s{seed}", width, height, pixels)


def generated_media_frame(
    width: int, height: int, channels: int, *, seed: int = 0
) -> MediaFrameFixture:
    """Generate a deterministic grayscale/BGR/BGRA frame and exact RGBA result."""

    rgba = generated_rgba_fixture(width, height, seed=seed)
    if channels == 1:
        gray = bytes((17 * x + 13 * y + seed) % 256 for y in range(height) for x in range(width))
        expected = RgbaFixture(
            f"generated-gray-rgba-{width}x{height}-s{seed}",
            width,
            height,
            bytes(component for value in gray for component in (value, value, value, 255)),
        )
        return MediaFrameFixture(
            f"generated-gray-{width}x{height}-s{seed}", width, height, 1, gray, expected
        )
    if channels == 3:
        opaque_pixels = bytearray(rgba.pixels)
        opaque_pixels[3::4] = b"\xff" * (width * height)
        opaque = RgbaFixture(
            f"generated-bgr-rgba-{width}x{height}-s{seed}",
            width,
            height,
            bytes(opaque_pixels),
        )
        return MediaFrameFixture(
            f"generated-bgr-{width}x{height}-s{seed}",
            width,
            height,
            3,
            _bgr_pixels(opaque.pixels),
            opaque,
        )
    if channels == 4:
        return MediaFrameFixture(
            f"generated-bgra-{width}x{height}-s{seed}",
            width,
            height,
            4,
            _bgra_pixels(rgba.pixels),
            rgba,
        )
    raise ValueError("generated media frame channels must be 1, 3, or 4")


def _checker_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    return (244, 80, 72, 255) if (x // 2 + y // 2) % 2 == 0 else (31, 132, 217, 255)


def _sprite_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    tile_x, tile_y = x // 4, y // 4
    palette = ((255, 204, 0), (0, 184, 148), (108, 92, 231), (214, 48, 49))
    red, green, blue = palette[(tile_x + tile_y * 2) % len(palette)]
    alpha = 255 if (x + y) % 3 else 192
    return red, green, blue, alpha


def _bgr_pixels(rgba: bytes) -> bytes:
    return bytes(
        component
        for offset in range(0, len(rgba), 4)
        for component in (rgba[offset + 2], rgba[offset + 1], rgba[offset])
    )


def _bgra_pixels(rgba: bytes) -> bytes:
    return bytes(
        component
        for offset in range(0, len(rgba), 4)
        for component in (rgba[offset + 2], rgba[offset + 1], rgba[offset], rgba[offset + 3])
    )


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
MEDIA_FRAME_BGR = MediaFrameFixture(
    "media-frame-bgr-6",
    6,
    4,
    3,
    _bgr_pixels(MEDIA_FRAME_RGBA.pixels),
    expected_rgba=MEDIA_FRAME_RGBA,
)
MEDIA_FRAME_BGRA_RGBA = RgbaFixture(
    "media-frame-bgra-rgba-6",
    6,
    4,
    _rgba(6, 4, lambda x, y: (17 * x + 13 * y, 29 * x, 47 * y, 64 + (x * 37 + y * 19) % 192)),
)
MEDIA_FRAME_BGRA = MediaFrameFixture(
    "media-frame-bgra-6",
    6,
    4,
    4,
    _bgra_pixels(MEDIA_FRAME_BGRA_RGBA.pixels),
    expected_rgba=MEDIA_FRAME_BGRA_RGBA,
)
_MEDIA_FRAME_GRAY = bytes(17 * x + 13 * y for y in range(4) for x in range(6))
MEDIA_FRAME_GRAY_RGBA = RgbaFixture(
    "media-frame-gray-rgba-6",
    6,
    4,
    bytes(component for value in _MEDIA_FRAME_GRAY for component in (value, value, value, 255)),
)
MEDIA_FRAME_GRAY = MediaFrameFixture(
    "media-frame-gray-6",
    6,
    4,
    1,
    _MEDIA_FRAME_GRAY,
    expected_rgba=MEDIA_FRAME_GRAY_RGBA,
)

SPRITE_CACHE_RESET = ResourceResetFixture(
    "sprite-cache-reset",
    source=SPRITE_SHEET,
    retained_families=(
        ResourceCounterFamily(
            "texture",
            resident_counter="texture_resident_bytes",
            peak_counter="texture_peak_bytes",
        ),
        ResourceCounterFamily(
            "image-atlas",
            resident_counter="image_atlas_resident_bytes",
            peak_counter="image_atlas_peak_bytes",
        ),
    ),
    reset_activity_counters=(
        "image_cache_evictions",
        "texture_uploads",
        "texture_upload_bytes",
        "texture_dirty_uploads",
        "texture_cache_evictions",
        "texture_destructions",
        "image_atlas_evictions",
        "image_atlas_destructions",
    ),
)

PATH_RECORDS = (
    PathRecord("rect", ((2, 2), (14, 2), (14, 10), (2, 10))),
    PathRecord("triangle", ((18, 2), (30, 10), (18, 10))),
    PathRecord("polyline", ((2, 18), (8, 13), (14, 21), (20, 15), (30, 22))),
    PathRecord("clip", ((4, 26), (28, 26), (28, 38), (4, 38))),
)
PRIMITIVE_PATH_FIXTURE = PrimitivePathFixture("path-records", PATH_RECORDS)

TEXT_CORPUS: Mapping[str, tuple[str, ...]] = {
    "ascii": ("Gummy Snake", "frame 001", "cache cache cache"),
    "combining": ("Cafe\u0301", "A\u0308ngstrom"),
    "rtl": ("\u0645\u0631\u062d\u0628\u0627",),
    "cjk": ("\u30ad\u30e3\u30f3\u30d0\u30b9",),
    "multiline": ("first line\nsecond line",),
}
TEXT_CORPUS_FIXTURE = TextCorpusFixture("text-corpus", TEXT_CORPUS)

MINIMAL_OBJ = (
    """# deterministic benchmark triangle\nv 0.0 0.0 0.0\nv 1.0 0.0 0.0\nv 0.0 1.0 0.0\nf 1 2 3\n"""
)
MINIMAL_OBJ_FIXTURE = ObjFixture(
    "minimal-triangle-obj",
    MINIMAL_OBJ,
    vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    faces=((0, 1, 2),),
)

# No font or encoded-media fixture exists under the repository's reviewed test
# fixtures. Keep that limitation machine-readable rather than importing examples
# or treating a host font/codec as deterministic benchmark evidence.
BINARY_FIXTURE_QUALIFICATIONS = (
    FixtureQualification(
        "font",
        "not-bundled-no-reviewed-repository-fixture",
        "Text corpora are deterministic, but host font rasterization is not "
        "cross-platform qualified.",
    ),
    FixtureQualification(
        "codec",
        "not-bundled-no-reviewed-repository-fixture",
        "Generated decoded media buffers are covered; encoded codec fixtures are not qualified.",
    ),
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
    MEDIA_FRAME_BGR.name: MEDIA_FRAME_BGR.pixels,
    MEDIA_FRAME_BGRA.name: MEDIA_FRAME_BGRA.pixels,
    MEDIA_FRAME_BGRA_RGBA.name: MEDIA_FRAME_BGRA_RGBA.pixels,
    MEDIA_FRAME_GRAY.name: MEDIA_FRAME_GRAY.pixels,
    MEDIA_FRAME_GRAY_RGBA.name: MEDIA_FRAME_GRAY_RGBA.pixels,
    PRIMITIVE_PATH_FIXTURE.name: PRIMITIVE_PATH_FIXTURE.payload,
    TEXT_CORPUS_FIXTURE.name: TEXT_CORPUS_FIXTURE.payload,
    MINIMAL_OBJ_FIXTURE.name: MINIMAL_OBJ_FIXTURE.payload,
}

# These values are intentionally literal review points, not hashes derived from
# the current payloads. ``validate_manifest`` therefore catches fixture changes.
FIXTURE_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "rgba": (
        CHECKERBOARD.name,
        SPRITE_SHEET.name,
        PIXEL_BUFFER.name,
    ),
    "media": (
        MEDIA_FRAME_RGBA.name,
        MEDIA_FRAME_BGR.name,
        MEDIA_FRAME_BGRA.name,
        MEDIA_FRAME_BGRA_RGBA.name,
        MEDIA_FRAME_GRAY.name,
        MEDIA_FRAME_GRAY_RGBA.name,
    ),
    "obj": (MINIMAL_OBJ_FIXTURE.name,),
    "primitive-path": (PRIMITIVE_PATH_FIXTURE.name,),
    "text": (TEXT_CORPUS_FIXTURE.name,),
}

FIXTURE_MANIFEST = (
    FixtureManifestEntry(
        "checkerboard-8", 256, "a814e5420f755241e10a600f2f923fa59603152d80b244449aa0b607492bdd3a"
    ),
    FixtureManifestEntry(
        "media-frame-6", 96, "003d90b999daa6d6427977c8aec2d2e250da6601239e1196075efccb256c9c8d"
    ),
    FixtureManifestEntry(
        "media-frame-bgr-6", 72, "768ec65187c53f0b581bd0523eb4f53706d9ade9312e57a9a0f1b159989cee11"
    ),
    FixtureManifestEntry(
        "media-frame-bgra-6", 96, "117176d15a581e3182f2fafb7bbc4f6f3560b28ba3274d7683d585e1b57a3aae"
    ),
    FixtureManifestEntry(
        "media-frame-bgra-rgba-6",
        96,
        "3f684ad8586634155fa91c71baf819da2fe560a0305c81d29b0084855519ed49",
    ),
    FixtureManifestEntry(
        "media-frame-gray-6", 24, "860c5318721c2242c657866c71161a1e19bade9d5d9c6426e3af38191ba79b1a"
    ),
    FixtureManifestEntry(
        "media-frame-gray-rgba-6",
        96,
        "8b8b7b4c92c5f6173cbb037bc27b82800338f59fa4849e060848c8e93bad8ad7",
    ),
    FixtureManifestEntry(
        "minimal-triangle-obj",
        85,
        "507c6fbd5d8beea9865e5c79d34de3fe174838a40492bc920785dc3203c2a921",
    ),
    FixtureManifestEntry(
        "path-records", 236, "f9ec696d79e51788ee9e1bbbcb8a41062a6e6d2fae7e4d4347f97d24de711144"
    ),
    FixtureManifestEntry(
        "pixel-buffer-4", 64, "cf91d64b3432565aa81aa1ad3a2cd0bc25ed2f6ad53c874b48b88581a240a042"
    ),
    FixtureManifestEntry(
        "sprite-sheet-8", 256, "285444ab4568c7087a86f565640595bafe24160611d1867ded78ff43e81198d3"
    ),
    FixtureManifestEntry(
        "text-corpus", 180, "549750faa57043f60c867da92f266c3053b58f00509c6de9b0dce4f0ef4de3b9"
    ),
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
    family_names = tuple(name for names in FIXTURE_FAMILIES.values() for name in names)
    if len(family_names) != len(set(family_names)) or set(family_names) != expected_names:
        raise ValueError("fixture families must cover every manifest entry exactly once")
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
    "BINARY_FIXTURE_QUALIFICATIONS",
    "CHECKERBOARD",
    "FIXTURE_BYTES",
    "FIXTURE_FAMILIES",
    "FIXTURE_MANIFEST",
    "MEDIA_FRAME_BGR",
    "MEDIA_FRAME_BGRA",
    "MEDIA_FRAME_BGRA_RGBA",
    "MEDIA_FRAME_GRAY",
    "MEDIA_FRAME_GRAY_RGBA",
    "MEDIA_FRAME_RGBA",
    "MINIMAL_OBJ",
    "MINIMAL_OBJ_FIXTURE",
    "MediaFrameFixture",
    "ObjFixture",
    "PATH_RECORDS",
    "PRIMITIVE_PATH_FIXTURE",
    "PIXEL_BUFFER",
    "PrimitivePathFixture",
    "RgbaFixture",
    "ResourceCounterFamily",
    "ResourceResetFixture",
    "SPRITE_CACHE_RESET",
    "SPRITE_SHEET",
    "TEXT_CORPUS",
    "TEXT_CORPUS_FIXTURE",
    "TextCorpusFixture",
    "FixtureManifestEntry",
    "generated_media_frame",
    "generated_rgba_fixture",
    "FixtureQualification",
    "PathRecord",
    "fixture_manifest",
    "sprite_image",
    "validate_manifest",
]

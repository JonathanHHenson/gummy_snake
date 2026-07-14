"""Required Rust canvas runtime bridge.

Gummy Snake uses :mod:`gummysnake.rust._canvas` for canvas-backed drawing.
This module imports and validates that runtime module and turns missing, stale,
or capability-limited builds into package-specific errors.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Protocol, cast

from gummysnake.exceptions import BackendCapabilityError

GUMMY_CANVAS_BUILD_COMMAND = (
    "uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml "
    "--features extension-module"
)
EXPECTED_CANVAS_ABI_VERSION = 22


class _RustCanvasImage(Protocol):
    width: int
    height: int
    version: int
    key: int

    @staticmethod
    def from_file(path: str) -> _RustCanvasImage: ...

    @staticmethod
    def from_rgba_bytes(width: int, height: int, pixels: bytes) -> _RustCanvasImage: ...

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]: ...

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, a: int) -> None: ...

    def replace_rgba_bytes(self, pixels: bytes) -> None: ...

    def copy(self) -> _RustCanvasImage: ...

    def crop(self, sx: int, sy: int, sw: int, sh: int) -> _RustCanvasImage: ...

    def resize(self, width: int, height: int) -> None: ...

    def mask(self, mask: _RustCanvasImage) -> None: ...

    def filter(self, mode: str, value: float | None = None) -> None: ...

    def alpha_composite(self, source: _RustCanvasImage, dx: int, dy: int) -> None: ...

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


class _RustCanvasSound(Protocol):
    path: str
    duration: float
    byte_len: int
    sample_rate: int
    frame_count: int

    @staticmethod
    def from_file(path: str) -> _RustCanvasSound: ...

    @staticmethod
    def from_bytes(path: str, payload: bytes) -> _RustCanvasSound: ...

    def to_bytes(self) -> bytes: ...

    def play(
        self,
        volume: float = 1.0,
        rate: float = 1.0,
        pan: float = 0.0,
        looping: bool = False,
        position: float = 0.0,
    ) -> _RustCanvasAudioPlayback: ...


class _RustCanvasSynthProgram(Protocol):
    sample_rate: int
    duration: float
    duration_frames: int
    event_count: int

    @staticmethod
    def from_serialized(payload: bytes, sample_rate: int) -> _RustCanvasSynthProgram: ...

    def render_wav(self) -> bytes: ...

    def render_wav_file(self, path: str) -> bytes: ...


class _RustCanvasAudioPlayback(Protocol):
    duration: float
    error: str | None

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...

    def looping(self, value: bool | None = None) -> bool: ...

    def set_volume(self, value: float) -> None: ...

    def set_rate(self, value: float) -> None: ...

    def set_pan(self, value: float) -> None: ...

    def seek(self, seconds: float) -> None: ...

    def time(self) -> float: ...

    def wait_until_stop(self, timeout: float | None = None) -> bool: ...

    def is_playing(self) -> bool: ...

    def is_paused(self) -> bool: ...

    def take_ended(self) -> bool: ...

    def diagnostics(self) -> dict[str, Any]: ...


class _CanvasModule(Protocol):
    Matrix2D: type[Any]
    Canvas: type[Any]
    CanvasImage: type[_RustCanvasImage]
    CanvasMediaFrameSink: type[Any]
    CanvasVideo: type[Any]
    GpuStorageBuffer: type[Any]
    GpuComputeShader: type[Any]
    CanvasSound: type[_RustCanvasSound]
    CanvasSynthProgram: type[_RustCanvasSynthProgram]
    SketchContextState: type[Any]

    def health_check(self) -> str: ...

    def canvas_abi_version(self) -> int: ...

    def native_window_available(self) -> bool: ...

    def gpu_available(self) -> bool: ...

    def webgpu_context_info(self) -> dict[str, Any]: ...

    def gpu_resource_diagnostics(self) -> dict[str, int]: ...

    def reset_gpu_resource_diagnostics(self) -> None: ...

    def image_resize_rgba(
        self, width: int, height: int, pixels: bytes, target_width: int, target_height: int
    ) -> bytes: ...

    def image_crop_rgba(
        self, width: int, height: int, pixels: bytes, sx: int, sy: int, sw: int, sh: int
    ) -> bytes: ...

    def image_alpha_composite_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        source_width: int,
        source_height: int,
        source_pixels: bytes,
        dx: int,
        dy: int,
    ) -> bytes: ...

    def image_mask_rgba(
        self,
        width: int,
        height: int,
        pixels: bytes,
        mask_width: int,
        mask_height: int,
        mask_pixels: bytes,
    ) -> bytes: ...

    def image_filter_rgba(
        self, width: int, height: int, pixels: bytes, mode: str, value: float | None = None
    ) -> bytes: ...

    def media_frame_to_rgba(
        self, width: int, height: int, channels: int, pixels: bytes
    ) -> bytes: ...

    def parse_obj_model_handle(self, text: str, source: str, normalize: bool) -> Any: ...

    def create_model3d_handle(
        self, meshes: list[Any], source: str = "gummy_snake_model"
    ) -> Any: ...

    def project_shade_model_handle(
        self,
        model: Any,
        camera: dict[str, Any],
        projection: dict[str, Any],
        viewport_width: float,
        viewport_height: float,
        material: dict[str, Any],
        lights: list[dict[str, Any]],
        normal_material: bool,
        cull_backfaces: bool,
        transform: list[float] | tuple[float, ...] | None = None,
    ) -> list[dict[str, Any]]: ...

    def rasterize_faces_rgba(
        self, width: int, height: int, faces: list[dict[str, Any]]
    ) -> bytes: ...

    def synth_play_compiled_program(
        self, program: _RustCanvasSynthProgram, looping: bool = False
    ) -> _RustCanvasAudioPlayback: ...

    def synth_render_event_wav(self, event: dict[str, Any], sample_rate: int) -> bytes: ...

    def synth_render_plan_wav(
        self, events: list[dict[str, Any]], duration_seconds: float, sample_rate: int
    ) -> bytes: ...

    def synth_render_serialized_plan_wav(self, payload: bytes, sample_rate: int) -> bytes: ...

    def synth_render_serialized_plan_wav_file(
        self, payload: bytes, sample_rate: int, path: str
    ) -> bytes: ...

    def synth_write_wav_file(self, payload: bytes, path: str) -> None: ...

    def synth_set_worker_count(self, worker_count: int | str) -> int: ...

    def synth_diagnostics(self) -> dict[str, Any]: ...

    def synth_reset_diagnostics(self) -> None: ...

    def synth_play_serialized_plan(
        self, payload: bytes, sample_rate: int, looping: bool = False
    ) -> _RustCanvasAudioPlayback: ...

    def synth_play_wav_bytes(self, payload: bytes) -> _RustCanvasAudioPlayback: ...

    def synth_sample_duration(self, value: Any) -> float: ...


_loaded_canvas: ModuleType | None
_CANVAS_IMPORT_ERROR: ImportError | None

try:
    _loaded_canvas = import_module("gummysnake.rust._canvas")
except ImportError as exc:
    _loaded_canvas = None
    _CANVAS_IMPORT_ERROR = exc
else:
    _CANVAS_IMPORT_ERROR = None

_canvas = cast(_CanvasModule | None, _loaded_canvas)


def is_canvas_runtime_available() -> bool:
    """Return whether the required Rust canvas module imported successfully."""
    return _canvas is not None


def canvas_import_error() -> ImportError | None:
    """Return the import error from loading the Rust canvas runtime, if any."""
    return _CANVAS_IMPORT_ERROR


def canvas_health_check() -> str:
    """Return a short status string from the Rust canvas runtime."""
    if _canvas is None:
        return "unavailable"
    try:
        return str(_canvas.health_check())
    except Exception as exc:
        return f"unhealthy: {exc}"


def canvas_abi_version() -> int | None:
    """Return the canvas ABI version exposed by the Rust runtime."""
    if _canvas is None:
        return None
    marker = getattr(_canvas, "canvas_abi_version", None)
    if not callable(marker):
        return None
    try:
        value: Any = marker()
    except Exception:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def canvas_native_window_available() -> bool:
    """Return whether the Rust canvas runtime can open native windows."""
    if _canvas is None:
        return False
    native_window_available = getattr(_canvas, "native_window_available", None)
    return bool(native_window_available()) if callable(native_window_available) else False


def canvas_gpu_available() -> bool:
    """Return whether GPU drawing is available in the Rust canvas runtime."""
    if _canvas is None:
        return False
    gpu_available = getattr(_canvas, "gpu_available", None)
    return bool(gpu_available()) if callable(gpu_available) else False


def canvas_gpu_status() -> str:
    """Return a human-readable GPU availability status."""
    if _canvas is None:
        return "unavailable: gummysnake.rust._canvas runtime is not installed"
    try:
        available = canvas_gpu_available()
    except Exception as exc:
        return f"unavailable: GPU capability probe failed: {exc}"
    if available:
        return "available"
    return (
        "unavailable: headless rendering can continue through Rust CPU-backed canvas paths, "
        "but native interactive presentation and GPU-accelerated drawing may be disabled "
        "or slower on this machine/build."
    )


def require_canvas_runtime() -> _CanvasModule:
    """Return the Rust canvas runtime or raise a capability error with rebuild guidance."""
    if _canvas is not None:
        _validate_canvas_runtime(_canvas)
        return _canvas

    detail = f" Import failed: {_CANVAS_IMPORT_ERROR}" if _CANVAS_IMPORT_ERROR else ""
    raise BackendCapabilityError(
        "Gummy Snake requires the Rust canvas runtime gummysnake.rust._canvas. "
        f"Build it locally with `{GUMMY_CANVAS_BUILD_COMMAND}`; bounded runs use "
        f"headless=True or max_frames, while interactive runs require a canvas runtime "
        f"built with native window support.{detail}"
    )


def _validate_canvas_runtime(module: _CanvasModule) -> None:
    marker = canvas_abi_version()
    if marker != EXPECTED_CANVAS_ABI_VERSION:
        found = "missing" if marker is None else str(marker)
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime is incompatible with this "
            f"Gummy Snake build (expected canvas ABI {EXPECTED_CANVAS_ABI_VERSION}, "
            f"found {found}). "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}` or reinstall gummy-snake so the "
            "Python package and Rust canvas runtime come from the same build."
        )

    health_check = getattr(module, "health_check", None)
    if not callable(health_check):
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime is missing health_check(). "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    try:
        health = health_check()
    except Exception as exc:
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime failed its health check. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`. Health check error: {exc}"
        ) from exc
    if not isinstance(health, str) or not health.strip() or health == "unavailable":
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime reported an unhealthy runtime "
            f"state ({health!r}). Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )

    required_classes = (
        "Matrix2D",
        "Canvas",
        "CanvasImage",
        "CanvasMediaFrameSink",
        "CanvasVideo",
        "GpuStorageBuffer",
        "GpuComputeShader",
        "CanvasModel3D",
        "CanvasMesh3D",
        "CanvasSound",
        "CanvasSynthProgram",
        "SketchContextState",
    )
    missing_classes = [
        name for name in required_classes if not isinstance(getattr(module, name, None), type)
    ]
    if missing_classes:
        missing_names = ", ".join(missing_classes)
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime is missing required runtime "
            f"asset/canvas classes ({missing_names}). Rebuild it with "
            f"`{GUMMY_CANVAS_BUILD_COMMAND}`."
        )

    required_functions = (
        "parse_obj_model_handle",
        "webgpu_context_info",
        "gpu_resource_diagnostics",
        "reset_gpu_resource_diagnostics",
    )
    missing_functions = [
        name for name in required_functions if not callable(getattr(module, name, None))
    ]
    if missing_functions:
        missing_names = ", ".join(missing_functions)
        raise BackendCapabilityError(
            "The installed gummysnake.rust._canvas runtime is missing required runtime "
            f"asset functions ({missing_names}). Rebuild it with "
            f"`{GUMMY_CANVAS_BUILD_COMMAND}`."
        )


__all__ = [
    "GUMMY_CANVAS_BUILD_COMMAND",
    "EXPECTED_CANVAS_ABI_VERSION",
    "canvas_abi_version",
    "canvas_health_check",
    "canvas_gpu_available",
    "canvas_gpu_status",
    "canvas_native_window_available",
    "canvas_import_error",
    "is_canvas_runtime_available",
    "require_canvas_runtime",
]

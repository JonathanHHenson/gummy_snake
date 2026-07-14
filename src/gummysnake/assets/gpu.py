"""Rust/WGPU storage buffers and compute shaders.

Python owns argument validation and small typed wrappers only. Canonical buffer
bytes, WGSL modules, pipelines, bind groups, dispatch, mapping, and resource
lifecycle are owned by the mandatory ``gummy_canvas`` runtime.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Iterable
from typing import Any, Protocol, TypedDict, cast

from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from gummysnake.rust.canvas import GUMMY_CANVAS_BUILD_COMMAND, require_canvas_runtime

Number = int | float
ComputeCallback = Callable[[tuple[int, int, int], dict[str, "StorageBuffer"]], None]


class WebGpuContextInfo(TypedDict):
    """Capabilities reported by :func:`webgpu_context`."""

    backend: str
    adapter: str
    native_gpu: bool
    storage_buffers: bool
    compute_shaders: bool
    browser_context: bool
    max_buffer_size: int
    max_storage_buffers_per_shader_stage: int


class _NativeStorageBuffer(Protocol):
    size: int
    dtype: str
    closed: bool

    def update_bytes(self, payload: bytes, offset: int) -> None: ...

    def read_bytes(self) -> bytes: ...

    def close(self) -> None: ...


class _NativeComputeShader(Protocol):
    def dispatch(
        self, buffers: list[_NativeStorageBuffer], x: int, y: int = 1, z: int = 1
    ) -> None: ...


def _runtime_resource_class(name: str) -> type[Any]:
    runtime = require_canvas_runtime()
    resource_type = getattr(runtime, name, None)
    if not isinstance(resource_type, type):
        raise BackendCapabilityError(
            f"The installed gummysnake.rust._canvas runtime does not expose {name}. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    return resource_type


def _coerce_values(values: Iterable[Number], dtype: str) -> list[Number]:
    if dtype == "float":
        result: list[Number] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ArgumentValidationError("StorageBuffer values must be numeric.")
            result.append(float(value))
        return result
    if dtype == "int":
        result = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ArgumentValidationError("StorageBuffer values must be numeric.")
            integer = int(value)
            if integer < -(2**31) or integer >= 2**31:
                raise ArgumentValidationError(
                    "Integer StorageBuffer values must fit in a signed 32-bit integer."
                )
            result.append(integer)
        return result
    raise ArgumentValidationError("StorageBuffer dtype must be 'float' or 'int'.")


def _pack_values(values: list[Number], dtype: str) -> bytes:
    if not values:
        return b""
    code = "f" if dtype == "float" else "i"
    return struct.pack(f"<{len(values)}{code}", *values)


def _unpack_values(payload: bytes, dtype: str) -> tuple[Number, ...]:
    if not payload:
        return ()
    code = "f" if dtype == "float" else "i"
    return cast(tuple[Number, ...], struct.unpack(f"<{len(payload) // 4}{code}", payload))


class StorageBuffer:
    """Typed numeric storage buffer backed by a Rust-owned WGPU allocation."""

    __slots__ = ("_native", "dtype")

    def __init__(self, data: Iterable[Number] | int, *, dtype: str = "float") -> None:
        """Create a native storage buffer from initial values or an element count."""

        if isinstance(data, bool):
            raise ArgumentValidationError("StorageBuffer size must be an integer, not bool.")
        if isinstance(data, int):
            if data < 0:
                raise ArgumentValidationError("StorageBuffer size cannot be negative.")
            raw_values: Iterable[Number] = [0] * data
        else:
            raw_values = data
        values = _coerce_values(raw_values, dtype)
        native_type = _runtime_resource_class("GpuStorageBuffer")
        try:
            self._native = cast(
                _NativeStorageBuffer,
                native_type.from_bytes(_pack_values(values, dtype), len(values), dtype),
            )
        except (RuntimeError, ValueError) as exc:
            raise BackendCapabilityError(
                "Native WGPU storage-buffer creation failed. No CPU storage fallback is used. "
                f"Runtime detail: {exc}"
            ) from exc
        self.dtype = dtype

    @property
    def size(self) -> int:
        """Return the number of 32-bit elements in the buffer."""

        return int(self._native.size)

    @property
    def closed(self) -> bool:
        """Return whether the native allocation has been released."""

        return bool(self._native.closed)

    def read(self) -> tuple[Number, ...]:
        """Map and copy the current native storage-buffer contents."""

        try:
            return _unpack_values(bytes(self._native.read_bytes()), self.dtype)
        except (RuntimeError, ValueError) as exc:
            raise BackendCapabilityError(f"Native storage-buffer readback failed: {exc}") from exc

    def update(self, data: Iterable[Number], *, offset: int = 0) -> None:
        """Upload a range of values into the native storage buffer."""

        start = int(offset)
        if start < 0:
            raise ArgumentValidationError("StorageBuffer update offset cannot be negative.")
        values = _coerce_values(data, self.dtype)
        if start + len(values) > self.size:
            raise ArgumentValidationError("StorageBuffer update exceeds buffer size.")
        try:
            self._native.update_bytes(_pack_values(values, self.dtype), start)
        except (RuntimeError, ValueError) as exc:
            raise BackendCapabilityError(f"Native storage-buffer upload failed: {exc}") from exc

    def close(self) -> None:
        """Release the native WGPU allocation deterministically."""

        self._native.close()


class ComputeShader:
    """Compiled Rust/WGPU WGSL compute shader."""

    __slots__ = ("_native", "source", "entry_point", "label")

    def __init__(
        self,
        *,
        source: str,
        entry_point: str = "main",
        label: str | None = None,
    ) -> None:
        if not source.strip():
            raise ArgumentValidationError("ComputeShader WGSL source cannot be empty.")
        if not entry_point.strip():
            raise ArgumentValidationError("ComputeShader entry_point cannot be empty.")
        native_type = _runtime_resource_class("GpuComputeShader")
        try:
            self._native = cast(
                _NativeComputeShader,
                native_type.from_wgsl(source, entry_point, label),
            )
        except (RuntimeError, ValueError) as exc:
            raise BackendCapabilityError(
                f"WGSL compute shader compilation failed for entry point {entry_point!r}: {exc}"
            ) from exc
        self.source = source
        self.entry_point = entry_point
        self.label = label

    def dispatch(self, x: int, y: int = 1, z: int = 1, **buffers: StorageBuffer) -> None:
        """Dispatch native WGPU workgroups with bindings in keyword insertion order."""

        dimensions = (int(x), int(y), int(z))
        if any(dimension <= 0 for dimension in dimensions):
            raise ArgumentValidationError("Compute dispatch dimensions must be positive.")
        if not buffers:
            raise ArgumentValidationError("Compute dispatch requires at least one storage buffer.")
        native_buffers: list[_NativeStorageBuffer] = []
        for name, buffer in buffers.items():
            if not isinstance(buffer, StorageBuffer):
                raise ArgumentValidationError(
                    f"Compute binding {name!r} must be a StorageBuffer value."
                )
            if buffer.closed:
                raise ArgumentValidationError(f"Compute binding {name!r} has been closed.")
            native_buffers.append(buffer._native)
        try:
            self._native.dispatch(native_buffers, *dimensions)
        except (RuntimeError, ValueError) as exc:
            raise BackendCapabilityError(
                f"Native WGPU compute dispatch failed for {self.entry_point!r}: {exc}"
            ) from exc


def create_storage_buffer(data: Iterable[Number] | int, *, dtype: str = "float") -> StorageBuffer:
    """Create a Rust/WGPU storage buffer."""

    return StorageBuffer(data, dtype=dtype)


def update_storage_buffer(
    buffer: StorageBuffer, data: Iterable[Number], *, offset: int = 0
) -> None:
    """Upload numeric values into an existing native storage buffer."""

    if not isinstance(buffer, StorageBuffer):
        raise ArgumentValidationError("update_storage_buffer() requires a StorageBuffer.")
    buffer.update(data, offset=offset)


def read_storage_buffer(buffer: StorageBuffer) -> tuple[Number, ...]:
    """Read all values from a native storage buffer."""

    if not isinstance(buffer, StorageBuffer):
        raise ArgumentValidationError("read_storage_buffer() requires a StorageBuffer.")
    return buffer.read()


def create_compute_shader(
    callback: ComputeCallback | None = None,
    *,
    source: str | None = None,
    entry_point: str = "main",
    label: str | None = None,
) -> ComputeShader:
    """Compile a WGSL compute shader in the Rust/WGPU runtime.

    Python callbacks were removed by Epic 280 because they executed canonical
    compute work on the CPU. Pass WGSL ``source`` instead.
    """

    if callback is not None:
        raise ArgumentValidationError(
            "Python compute callbacks were removed by Epic 280. Pass WGSL source=...; "
            "Gummy Snake does not provide a CPU compute fallback."
        )
    if source is None or not source.strip():
        raise ArgumentValidationError("create_compute_shader() requires non-empty WGSL source.")
    return ComputeShader(source=source, entry_point=entry_point, label=label)


def dispatch_compute(
    shader: ComputeShader, x: int, y: int = 1, z: int = 1, **buffers: StorageBuffer
) -> None:
    """Dispatch a native WGSL compute shader."""

    if not isinstance(shader, ComputeShader):
        raise ArgumentValidationError("dispatch_compute() requires a ComputeShader.")
    shader.dispatch(x, y, z, **buffers)


def webgpu_context() -> WebGpuContextInfo:
    """Return shared native WGPU adapter limits and capability information."""

    runtime = require_canvas_runtime()
    callback = getattr(runtime, "webgpu_context_info", None)
    if not callable(callback):
        raise BackendCapabilityError(
            "The installed canvas runtime does not expose native WGPU resource information. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    try:
        return cast(WebGpuContextInfo, cast(dict[str, object], callback()))
    except (RuntimeError, ValueError) as exc:
        raise BackendCapabilityError(
            "Native WGPU resources are unavailable and no CPU fallback is enabled. "
            f"Runtime detail: {exc}"
        ) from exc


def gpu_resource_diagnostics() -> dict[str, int]:
    """Return Rust-owned storage/compute allocation and dispatch diagnostics."""

    runtime = require_canvas_runtime()
    callback = getattr(runtime, "gpu_resource_diagnostics", None)
    if not callable(callback):
        raise BackendCapabilityError(
            "The installed canvas runtime does not expose GPU resource diagnostics. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    payload = cast(dict[str, object], callback())
    return {
        str(key): int(value)
        for key, value in payload.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def reset_gpu_resource_diagnostics() -> None:
    """Reset Rust-owned GPU resource counters without releasing live resources."""

    runtime = require_canvas_runtime()
    callback = getattr(runtime, "reset_gpu_resource_diagnostics", None)
    if not callable(callback):
        raise BackendCapabilityError(
            "The installed canvas runtime does not expose GPU resource diagnostic reset. "
            f"Rebuild it with `{GUMMY_CANVAS_BUILD_COMMAND}`."
        )
    callback()


__all__ = [
    "ComputeShader",
    "StorageBuffer",
    "create_compute_shader",
    "create_storage_buffer",
    "dispatch_compute",
    "gpu_resource_diagnostics",
    "read_storage_buffer",
    "reset_gpu_resource_diagnostics",
    "update_storage_buffer",
    "webgpu_context",
    "WebGpuContextInfo",
]

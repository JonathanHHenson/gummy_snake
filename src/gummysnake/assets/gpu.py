"""Safe native compute/storage helpers.

The public API is intentionally Pythonic and CPU-backed today. It gives sketches
and tests deterministic storage-buffer semantics without exposing browser WebGPU
contexts or JavaScript shader objects.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypedDict

from gummysnake.exceptions import ArgumentValidationError

Number = int | float
ComputeCallback = Callable[[tuple[int, int, int], dict[str, "StorageBuffer"]], None]


class WebGpuContextInfo(TypedDict):
    """Capabilities reported by ``webgpu_context()``.

    Attributes:
        backend: Name of the deterministic native compute backend.
        native_gpu: Whether this helper exposes native GPU execution.
        storage_buffers: Whether storage-buffer helpers are available.
        compute_shaders: Whether compute dispatch helpers are available.
        browser_context: ``False`` because Gummy Snake does not expose browser APIs.
    """

    backend: str
    native_gpu: bool
    storage_buffers: bool
    compute_shaders: bool
    browser_context: bool


class StorageBuffer:
    """Typed numeric storage buffer with explicit read/update operations."""

    def __init__(self, data: Iterable[Number] | int, *, dtype: str = "float") -> None:
        """Create a numeric storage buffer from initial values or a size."""
        if dtype not in {"float", "int"}:
            raise ArgumentValidationError("StorageBuffer dtype must be 'float' or 'int'.")
        self.dtype = dtype
        if isinstance(data, int):
            if data < 0:
                raise ArgumentValidationError("StorageBuffer size cannot be negative.")
            values: Iterable[Number] = [0] * data
        else:
            values = data
        self._values = [self._coerce(value) for value in values]
        self.closed = False

    @property
    def size(self) -> int:
        """Return the number of numeric elements in the buffer."""

        return len(self._values)

    def read(self) -> tuple[Number, ...]:
        """Copy the current buffer contents.

        Returns:
            Stored numeric values in buffer order.
        """

        self._ensure_open()
        return tuple(self._values)

    def update(self, data: Iterable[Number], *, offset: int = 0) -> None:
        """Replace a range of buffer values.

        Args:
            data: Numeric values to write.
            offset: First element index to update.
        """

        self._ensure_open()
        start = int(offset)
        if start < 0:
            raise ArgumentValidationError("StorageBuffer update offset cannot be negative.")
        incoming = [self._coerce(value) for value in data]
        end = start + len(incoming)
        if end > len(self._values):
            raise ArgumentValidationError("StorageBuffer update exceeds buffer size.")
        self._values[start:end] = incoming

    def close(self) -> None:
        """Close the buffer and release stored values."""

        self.closed = True
        self._values.clear()

    def _coerce(self, value: Number) -> Number:
        return int(value) if self.dtype == "int" else float(value)

    def _ensure_open(self) -> None:
        if self.closed:
            raise ArgumentValidationError("StorageBuffer has been closed.")


@dataclass(slots=True)
class ComputeShader:
    """CPU-backed compute shader wrapper.

    Pass a Python callable accepting ``global_id`` and bound buffers. Source text
    may be stored as metadata for future native compilers, but dispatch requires a
    callable so execution is explicit, safe, and deterministic.
    """

    callback: ComputeCallback | None = None
    source: str | None = None
    label: str | None = None

    def dispatch(self, x: int, y: int = 1, z: int = 1, **buffers: StorageBuffer) -> None:
        """Run the compute callback for each global invocation id.

        Args:
            x: Number of invocations in the x dimension.
            y: Number of invocations in the y dimension.
            z: Number of invocations in the z dimension.
            **buffers: Named storage buffers available to the callback.
        """

        if self.callback is None:
            raise ArgumentValidationError(
                "ComputeShader dispatch requires a Python callback in the current native API."
            )
        for dimension in (x, y, z):
            if dimension < 0:
                raise ArgumentValidationError("Compute dispatch dimensions cannot be negative.")
        for buffer in buffers.values():
            if not isinstance(buffer, StorageBuffer):
                raise ArgumentValidationError("ComputeShader buffers must be StorageBuffer values.")
        for gx in range(int(x)):
            for gy in range(int(y)):
                for gz in range(int(z)):
                    self.callback((gx, gy, gz), buffers)


def create_storage_buffer(data: Iterable[Number] | int, *, dtype: str = "float") -> StorageBuffer:
    """Create a deterministic numeric storage buffer.

    Args:
        data: Initial numeric values, or an integer size for a zero-filled buffer.
        dtype: ``"float"`` or ``"int"`` coercion mode.

    Returns:
        A ``StorageBuffer`` for compute callbacks.
    """

    return StorageBuffer(data, dtype=dtype)


def update_storage_buffer(
    buffer: StorageBuffer, data: Iterable[Number], *, offset: int = 0
) -> None:
    """Write numeric values into an existing storage buffer.

    Args:
        buffer: Buffer to update.
        data: Numeric values to write.
        offset: First element index to update.
    """

    if not isinstance(buffer, StorageBuffer):
        raise ArgumentValidationError("update_storage_buffer() requires a StorageBuffer.")
    buffer.update(data, offset=offset)


def read_storage_buffer(buffer: StorageBuffer) -> tuple[Number, ...]:
    """Read all values from a storage buffer.

    Args:
        buffer: Buffer to read.

    Returns:
        Stored numeric values in buffer order.
    """

    if not isinstance(buffer, StorageBuffer):
        raise ArgumentValidationError("read_storage_buffer() requires a StorageBuffer.")
    return buffer.read()


def create_compute_shader(
    callback: ComputeCallback | None = None,
    *,
    source: str | None = None,
    label: str | None = None,
) -> ComputeShader:
    """Create a CPU-backed compute shader wrapper.

    Args:
        callback: Python function called once per dispatch invocation.
        source: Optional source text stored as metadata for future native compilers.
        label: Optional human-readable name for diagnostics.

    Returns:
        A ``ComputeShader`` that can be passed to ``dispatch_compute()``.
    """

    if callback is None and (source is None or not source.strip()):
        raise ArgumentValidationError(
            "create_compute_shader() requires a callback or source metadata."
        )
    if callback is not None and not callable(callback):
        raise ArgumentValidationError("create_compute_shader() callback must be callable.")
    return ComputeShader(callback=callback, source=source, label=label)


def dispatch_compute(
    shader: ComputeShader, x: int, y: int = 1, z: int = 1, **buffers: StorageBuffer
) -> None:
    """Run a compute shader over a 1D, 2D, or 3D dispatch grid.

    Args:
        shader: Compute shader created by ``create_compute_shader()``.
        x: Number of invocations in the x dimension.
        y: Number of invocations in the y dimension.
        z: Number of invocations in the z dimension.
        **buffers: Named storage buffers available to the shader callback.
    """

    if not isinstance(shader, ComputeShader):
        raise ArgumentValidationError("dispatch_compute() requires a ComputeShader.")
    shader.dispatch(x, y, z, **buffers)


def webgpu_context() -> WebGpuContextInfo:
    """Return compute/storage capability information.

    Returns:
        A dictionary describing Gummy Snake's deterministic native compute helper.
    """

    return {
        "backend": "gummy-snake-native-cpu-compute",
        "native_gpu": False,
        "storage_buffers": True,
        "compute_shaders": True,
        "browser_context": False,
    }


__all__ = [
    "ComputeShader",
    "StorageBuffer",
    "create_compute_shader",
    "create_storage_buffer",
    "dispatch_compute",
    "read_storage_buffer",
    "update_storage_buffer",
    "webgpu_context",
    "WebGpuContextInfo",
]

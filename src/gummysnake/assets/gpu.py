"""Safe native compute/storage helpers.

The public API is intentionally Pythonic and CPU-backed today. It gives sketches
and tests deterministic storage-buffer semantics without exposing browser WebGPU
contexts or JavaScript shader objects.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from gummysnake.exceptions import ArgumentValidationError

Number = int | float
ComputeCallback = Callable[[tuple[int, int, int], dict[str, "StorageBuffer"]], None]


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
        """Return this StorageBuffer's size.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return len(self._values)

    def read(self) -> tuple[Number, ...]:
        """Read for this StorageBuffer.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[Number, ...]`.
        """
        self._ensure_open()
        return tuple(self._values)

    def update(self, data: Iterable[Number], *, offset: int = 0) -> None:
        """Update for this StorageBuffer.
        
        Args:
            data: The data value. Expected type: `Iterable[Number]`.
            offset: The offset value. Expected type: `int`. Defaults to `0`.
        
        Returns:
            None.
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
        """Close this StorageBuffer.
        
        Args:
            None.
        
        Returns:
            None.
        """
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
        """Dispatch for this ComputeShader.
        
        Args:
            x: The x value. Expected type: `int`.
            y: The y value. Expected type: `int`. Defaults to `1`.
            z: The z value. Expected type: `int`. Defaults to `1`.
            **buffers: Additional keyword arguments. Expected type: `StorageBuffer`.
        
        Returns:
            None.
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
    """Create and return a storage buffer value.
    
    Args:
        data: The data value. Expected type: `Iterable[Number] | int`.
        dtype: The dtype value. Expected type: `str`. Defaults to `'float'`.
    
    Returns:
        The return value. Type: `StorageBuffer`.
    """
    return StorageBuffer(data, dtype=dtype)


def update_storage_buffer(
    buffer: StorageBuffer, data: Iterable[Number], *, offset: int = 0
) -> None:
    """Update storage buffer using the active gpu context.
    
    Args:
        buffer: The buffer value. Expected type: `StorageBuffer`.
        data: The data value. Expected type: `Iterable[Number]`.
        offset: The offset value. Expected type: `int`. Defaults to `0`.
    
    Returns:
        None.
    """
    if not isinstance(buffer, StorageBuffer):
        raise ArgumentValidationError("update_storage_buffer() requires a StorageBuffer.")
    buffer.update(data, offset=offset)


def read_storage_buffer(buffer: StorageBuffer) -> tuple[Number, ...]:
    """Read storage buffer using the active gpu context.
    
    Args:
        buffer: The buffer value. Expected type: `StorageBuffer`.
    
    Returns:
        The return value. Type: `tuple[Number, ...]`.
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
    """Create and return a compute shader value.
    
    Args:
        callback: The callback value. Expected type: `ComputeCallback | None`. Defaults to `None`.
        source: The source value. Expected type: `str | None`. Defaults to `None`.
        label: The label value. Expected type: `str | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `ComputeShader`.
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
    """Dispatch compute using the active gpu context.
    
    Args:
        shader: The shader value. Expected type: `ComputeShader`.
        x: The x value. Expected type: `int`.
        y: The y value. Expected type: `int`. Defaults to `1`.
        z: The z value. Expected type: `int`. Defaults to `1`.
        **buffers: Additional keyword arguments. Expected type: `StorageBuffer`.
    
    Returns:
        None.
    """
    if not isinstance(shader, ComputeShader):
        raise ArgumentValidationError("dispatch_compute() requires a ComputeShader.")
    shader.dispatch(x, y, z, **buffers)


def webgpu_context() -> dict[str, object]:
    """Webgpu context using the active gpu context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `dict[str, object]`.
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
]

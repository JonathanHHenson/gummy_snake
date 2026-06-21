"""Structural protocols for composed canvas renderer mixins."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, Protocol

from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

MatrixPayload = tuple[float, float, float, float, float, float]
TextMetricKey = tuple[str, str | None, tuple[tuple[str, Hashable], ...]]


class CanvasRendererHost(Protocol):
    _line_batch: list[tuple[float, float, float, float]]
    _line_batch_style: dict[str, object] | None
    _line_batch_matrix: MatrixPayload | None
    _image_cache_versions: OrderedDict[int, int]

    def _flush_line_batch(self) -> None: ...
    def _count(self, name: str, amount: int = 1) -> None: ...
    def _call(self, operation: str, callback: Callable[..., Any], *args: object) -> Any: ...
    def _require_canvas(self) -> Any: ...
    def _style_payload(self, style: StyleState) -> dict[str, object]: ...
    def _matrix_payload(self, transform: Matrix2D) -> MatrixPayload: ...
    def _remember_image_cache_version(self, image_key: int, version: int) -> None: ...
    def _cached_text_metric(
        self,
        key: TextMetricKey,
        operation: str,
        callback: Callable[..., Any],
        *args: object,
    ) -> float: ...

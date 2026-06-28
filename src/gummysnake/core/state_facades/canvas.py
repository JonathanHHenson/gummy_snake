"""Canvas lifecycle state facade."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c


class CanvasState:
    """Compatibility facade for Rust-owned canvas lifecycle state."""

    __slots__ = ("_rust",)

    def __init__(self, rust_state: Any) -> None:
        self._rust = rust_state

    @property
    def width(self) -> int:
        """Width.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust.width)

    @width.setter
    def width(self, value: int) -> None:
        """Width.
        
        Args:
            value: The value value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust.width = int(value)

    @property
    def height(self) -> int:
        """Height.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust.height)

    @height.setter
    def height(self, value: int) -> None:
        """Height.
        
        Args:
            value: The value value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust.height = int(value)

    @property
    def physical_width(self) -> int:
        """Physical width.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust.physical_width)

    @physical_width.setter
    def physical_width(self, value: int) -> None:
        """Physical width.
        
        Args:
            value: The value value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust.physical_width = int(value)

    @property
    def physical_height(self) -> int:
        """Physical height.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust.physical_height)

    @physical_height.setter
    def physical_height(self, value: int) -> None:
        """Physical height.
        
        Args:
            value: The value value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust.physical_height = int(value)

    @property
    def pixel_density(self) -> float:
        """Pixel density.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return float(self._rust.pixel_density)

    @pixel_density.setter
    def pixel_density(self, value: float) -> None:
        """Pixel density.
        
        Args:
            value: The value value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._rust.pixel_density = float(value)

    @property
    def renderer(self) -> c.RendererMode:
        """Renderer.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `c.RendererMode`.
        """
        return c.RendererMode(str(self._rust.renderer))

    @renderer.setter
    def renderer(self, value: c.RendererMode | str) -> None:
        """Renderer.
        
        Args:
            value: The value value. Expected type: `c.RendererMode | str`.
        
        Returns:
            None.
        """
        self._rust.renderer = c.RendererMode(str(value)).value

    @property
    def created(self) -> bool:
        """Created.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return bool(self._rust.created)

    @created.setter
    def created(self, value: bool) -> None:
        """Created.
        
        Args:
            value: The value value. Expected type: `bool`.
        
        Returns:
            None.
        """
        self._rust.created = bool(value)

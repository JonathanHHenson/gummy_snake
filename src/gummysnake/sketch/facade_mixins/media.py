"""Image, text, pixel, and compositing forwards for object sketches."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any, Literal, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.api.sound import get_audio_context as _get_audio_context
from gummysnake.assets.audio import (
    FFT,
    Amplitude,
    AudioBuffer,
    AudioFilter,
    AudioInput,
    Envelope,
    Oscillator,
)
from gummysnake.assets.audio import (
    create_amplitude as _create_amplitude,
)
from gummysnake.assets.audio import (
    create_audio_in as _create_audio_in,
)
from gummysnake.assets.audio import (
    create_envelope as _create_envelope,
)
from gummysnake.assets.audio import (
    create_fft as _create_fft,
)
from gummysnake.assets.audio import (
    create_filter as _create_filter,
)
from gummysnake.assets.audio import (
    create_oscillator as _create_oscillator,
)
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.assets.media import (
    AudioVideoCapture,
    Capture,
    Video,
)
from gummysnake.assets.media import (
    create_capture as _create_capture,
)
from gummysnake.assets.media import (
    create_capture_async as _create_capture_async,
)
from gummysnake.assets.media import (
    create_video as _create_video,
)
from gummysnake.assets.media import (
    create_video_async as _create_video_async,
)
from gummysnake.assets.sound import Sound
from gummysnake.assets.sound import load_sound as _load_sound
from gummysnake.assets.sound import load_sound_async as _load_sound_async
from gummysnake.assets.text import Font
from gummysnake.core.color import Color
from gummysnake.core.pixels import PixelBuffer
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin, SupportsText


class TextProperties(TypedDict, total=False):
    """Public TextProperties value."""
    direction: str
    wrap: str
    weight: int


type PixelValue = Color | tuple[int, int, int] | tuple[int, int, int, int] | Image


class SketchFacadeMediaMixin(SketchFacadeBaseMixin):
    """Public SketchFacadeMediaMixin value."""
    def create_video(self, path: str | Path) -> Video:
        """Create and return a video value.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Video`.
        """
        return _create_video(path)

    async def create_video_async(self, path: str | Path) -> Video:
        """Create and return a video async value.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Video`.
        """
        return await _create_video_async(path)

    def create_capture(
        self,
        kind: str = "video",
        *,
        device: int | str = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> Capture | AudioInput | AudioVideoCapture:
        """Create and return a capture value.
        
        Args:
            kind: The kind value. Expected type: `str`. Defaults to `'video'`.
            device: The device value. Expected type: `int | str`. Defaults to `0`.
            width: The width value. Expected type: `int | None`. Defaults to `None`.
            height: The height value. Expected type: `int | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Capture | AudioInput | AudioVideoCapture`.
        """
        return _create_capture(kind, device=device, width=width, height=height)

    async def create_capture_async(
        self,
        kind: str = "video",
        *,
        device: int | str = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> Capture | AudioInput | AudioVideoCapture:
        """Create and return a capture async value.
        
        Args:
            kind: The kind value. Expected type: `str`. Defaults to `'video'`.
            device: The device value. Expected type: `int | str`. Defaults to `0`.
            width: The width value. Expected type: `int | None`. Defaults to `None`.
            height: The height value. Expected type: `int | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Capture | AudioInput | AudioVideoCapture`.
        """
        return await _create_capture_async(kind, device=device, width=width, height=height)

    def load_sound(self, path: str | Path) -> Sound:
        """Load and return sound.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Sound`.
        """
        return _load_sound(path)

    async def load_sound_async(self, path: str | Path) -> Sound:
        """Load and return sound asynchronously.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Sound`.
        """
        return await _load_sound_async(path)

    def create_audio(self, path: str | Path) -> Sound:
        """Create and return a audio value.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `Sound`.
        """
        return _load_sound(path)

    def create_amplitude(
        self, source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
    ) -> Amplitude:
        """Create and return a amplitude value.
        
        Args:
            source: The source value. Expected type: `Sound | AudioBuffer | Sequence[float] | None`.
                Defaults to `None`.
            smoothing: The smoothing value. Expected type: `float`. Defaults to `0.0`.
        
        Returns:
            The return value. Type: `Amplitude`.
        """
        return _create_amplitude(source, smoothing=smoothing)

    def create_fft(
        self,
        source: Sound | AudioBuffer | Sequence[float] | None = None,
        *,
        bins: int = 1024,
        smoothing: float = 0.0,
    ) -> FFT:
        """Create and return a fft value.
        
        Args:
            source: The source value. Expected type: `Sound | AudioBuffer | Sequence[float] | None`.
                Defaults to `None`.
            bins: The bins value. Expected type: `int`. Defaults to `1024`.
            smoothing: The smoothing value. Expected type: `float`. Defaults to `0.0`.
        
        Returns:
            The return value. Type: `FFT`.
        """
        return _create_fft(source, bins=bins, smoothing=smoothing)

    def create_oscillator(
        self, waveform: str = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
    ) -> Oscillator:
        """Create and return a oscillator value.
        
        Args:
            waveform: The waveform value. Expected type: `str`. Defaults to `'sine'`.
            frequency: The frequency value. Expected type: `float`. Defaults to `440.0`.
            amplitude: The amplitude value. Expected type: `float`. Defaults to `1.0`.
        
        Returns:
            The return value. Type: `Oscillator`.
        """
        return _create_oscillator(cast(Any, waveform), frequency=frequency, amplitude=amplitude)

    def create_envelope(
        self, attack: float = 0.01, decay: float = 0.1, sustain: float = 0.7, release: float = 0.2
    ) -> Envelope:
        """Create and return a envelope value.
        
        Args:
            attack: The attack value. Expected type: `float`. Defaults to `0.01`.
            decay: The decay value. Expected type: `float`. Defaults to `0.1`.
            sustain: The sustain value. Expected type: `float`. Defaults to `0.7`.
            release: The release value. Expected type: `float`. Defaults to `0.2`.
        
        Returns:
            The return value. Type: `Envelope`.
        """
        return _create_envelope(attack=attack, decay=decay, sustain=sustain, release=release)

    def create_filter(
        self, filter_type: str = "lowpass", *, frequency: float = 1_000.0, resonance: float = 0.0
    ) -> AudioFilter:
        """Create and return a filter value.
        
        Args:
            filter_type: The filter type value. Expected type: `str`. Defaults to `'lowpass'`.
            frequency: The frequency value. Expected type: `float`. Defaults to `1000.0`.
            resonance: The resonance value. Expected type: `float`. Defaults to `0.0`.
        
        Returns:
            The return value. Type: `AudioFilter`.
        """
        return _create_filter(cast(Any, filter_type), frequency=frequency, resonance=resonance)

    def create_audio_in(self, *, sample_rate: int = 44_100) -> AudioInput:
        """Create and return a audio in value.
        
        Args:
            sample_rate: The sample rate value. Expected type: `int`. Defaults to `44100`.
        
        Returns:
            The return value. Type: `AudioInput`.
        """
        return _create_audio_in(sample_rate=sample_rate)

    def get_audio_context(self) -> dict[str, object]:
        """Return the current audio context value.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, object]`.
        """
        return _get_audio_context()

    @overload
    def image(self, image: Image | CanvasImage, x: float, y: float, /) -> None:
        ...

    @overload
    def image(
        self, image: Image | CanvasImage, x: float, y: float, width: float, height: float, /
    ) -> None:
        ...

    @overload
    def image(
        self,
        image: Image | CanvasImage,
        x: float,
        y: float,
        width: float,
        height: float,
        sx: float,
        sy: float,
        sw: float,
        sh: float,
        /,
    ) -> None:
        ...

    def image(self, *args: Any) -> None:
        """Image for this SketchFacadeMediaMixin.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        cast(Any, self._ctx).image(*args)

    def text(self, value: SupportsText, x: float, y: float) -> None:
        """Text for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `SupportsText`.
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.text(value, x, y)

    def text_batch(self, items: Sequence[tuple[SupportsText, float, float]]) -> None:
        """Text batch for this SketchFacadeMediaMixin.
        
        Args:
            items: The items value. Expected type: `Sequence[tuple[SupportsText, float, float]]`.
        
        Returns:
            None.
        """
        context = self._ctx
        context.renderer.text_batch(
            [(str(value), float(x), float(y)) for value, x, y in items],
            context.state.style,
            context.state.transform.matrix,
        )

    def text_size(self, size: float | None = None) -> float:
        """Text size for this SketchFacadeMediaMixin.
        
        Args:
            size: The size value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.text_size(size)

    def text_font(self, font: Font | str | None = None) -> Font:
        """Text font for this SketchFacadeMediaMixin.
        
        Args:
            font: The font value. Expected type: `Font | str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Font`.
        """
        return self._ctx.text_font(font)

    def text_style(self, style: c.TextStyle | None = None) -> c.TextStyle:
        """Text style for this SketchFacadeMediaMixin.
        
        Args:
            style: The style value. Expected type: `c.TextStyle | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `c.TextStyle`.
        """
        return self._ctx.text_style(style)

    def text_align(self, horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
        """Text align for this SketchFacadeMediaMixin.
        
        Args:
            horizontal: The horizontal value. Expected type: `c.TextAlign`.
            vertical: The vertical value. Expected type: `c.TextAlign | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._ctx.text_align(horizontal, vertical)

    def text_leading(self, value: float | None = None) -> float:
        """Text leading for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.text_leading(value)

    def text_width(self, value: SupportsText) -> float:
        """Text width for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `SupportsText`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.text_width(value)

    def text_widths(self, values: Sequence[SupportsText]) -> tuple[float, ...]:
        """Text widths for this SketchFacadeMediaMixin.
        
        Args:
            values: The values value. Expected type: `Sequence[SupportsText]`.
        
        Returns:
            The return value. Type: `tuple[float, ...]`.
        """
        context = self._ctx
        style = context.state.style
        return tuple(context.renderer.text_width(str(value), style) for value in values)

    def text_ascent(self) -> float:
        """Text ascent for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.text_ascent()

    def text_descent(self) -> float:
        """Text descent for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.text_descent()

    def font_ascent(self, font: Font | str | None = None) -> float:
        """Font ascent for this SketchFacadeMediaMixin.
        
        Args:
            font: The font value. Expected type: `Font | str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.font_ascent(font)

    def font_descent(self, font: Font | str | None = None) -> float:
        """Font descent for this SketchFacadeMediaMixin.
        
        Args:
            font: The font value. Expected type: `Font | str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.font_descent(font)

    def font_width(self, value: SupportsText, font: Font | str | None = None) -> float:
        """Font width for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `SupportsText`.
            font: The font value. Expected type: `Font | str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.font_width(value, font)

    def text_bounds(self, value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
        """Text bounds for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `SupportsText`.
            x: The x value. Expected type: `float`. Defaults to `0.0`.
            y: The y value. Expected type: `float`. Defaults to `0.0`.
        
        Returns:
            The return value. Type: `dict[str, float]`.
        """
        return self._ctx.text_bounds(value, x, y)

    def font_bounds(
        self,
        value: SupportsText,
        x: float = 0.0,
        y: float = 0.0,
        font: Font | str | None = None,
    ) -> dict[str, float]:
        """Font bounds for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `SupportsText`.
            x: The x value. Expected type: `float`. Defaults to `0.0`.
            y: The y value. Expected type: `float`. Defaults to `0.0`.
            font: The font value. Expected type: `Font | str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `dict[str, float]`.
        """
        return self._ctx.font_bounds(value, x, y, font)

    def text_direction(self, value: str | None = None) -> str:
        """Text direction for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `str`.
        """
        return self._ctx.text_direction(value)

    def text_wrap(self, value: str | None = None) -> str:
        """Text wrap for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `str`.
        """
        return self._ctx.text_wrap(value)

    def text_weight(self, value: int | None = None) -> int:
        """Text weight for this SketchFacadeMediaMixin.
        
        Args:
            value: The value value. Expected type: `int | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `int`.
        """
        return self._ctx.text_weight(value)

    @overload
    def text_property(self, name: Literal["direction"], value: str | None = None) -> str:
        ...

    @overload
    def text_property(self, name: Literal["wrap"], value: str | None = None) -> str:
        ...

    @overload
    def text_property(self, name: Literal["weight"], value: int | None = None) -> int:
        ...

    def text_property(self, name: str, value: str | int | None = None) -> str | int:
        """Text property for this SketchFacadeMediaMixin.
        
        Args:
            name: The name value. Expected type: `str`.
            value: The value value. Expected type: `str | int | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `str | int`.
        """
        return cast(str | int, cast(Any, self._ctx).text_property(name, value))

    def text_properties(
        self, **properties: Unpack[TextProperties]
    ) -> dict[str, str | int | float | c.TextStyle]:
        """Text properties for this SketchFacadeMediaMixin.
        
        Args:
            **properties: Additional keyword arguments. Expected type: `Unpack[TextProperties]`.
        
        Returns:
            The return value. Type: `dict[str, str | int | float | c.TextStyle]`.
        """
        return cast(
            dict[str, str | int | float | c.TextStyle],
            cast(Any, self._ctx).text_properties(**properties),
        )

    def describe(self, description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
        """Describe for this SketchFacadeMediaMixin.
        
        Args:
            description: The description value. Expected type: `SupportsText`.
            label: The label value. Expected type: `str`. Defaults to `'canvas'`.
        
        Returns:
            The return value. Type: `dict[str, str]`.
        """
        return self._ctx.describe(description, label=label)

    def describe_element(self, name: SupportsText, description: SupportsText) -> dict[str, str]:
        """Describe element for this SketchFacadeMediaMixin.
        
        Args:
            name: The name value. Expected type: `SupportsText`.
            description: The description value. Expected type: `SupportsText`.
        
        Returns:
            The return value. Type: `dict[str, str]`.
        """
        return self._ctx.describe_element(name, description)

    def text_output(self) -> list[dict[str, str]]:
        """Text output for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `list[dict[str, str]]`.
        """
        return self._ctx.text_output()

    def grid_output(self) -> list[dict[str, str]]:
        """Grid output for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `list[dict[str, str]]`.
        """
        return self._ctx.grid_output()

    def load_pixels(self) -> PixelBuffer:
        """Load and return pixels.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `PixelBuffer`.
        """
        return self._ctx.load_pixels()

    def load_pixel_bytes(self) -> bytes:
        """Load and return pixel bytes.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bytes`.
        """
        return self._ctx.load_pixel_bytes()

    def pixels(self) -> Sequence[int]:
        """Pixels for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Sequence[int]`.
        """
        context = self._ctx
        return cast(Sequence[int], context.pixels or context.load_pixels())

    def pixel_array(self) -> list[list[tuple[int, int, int, int]]]:
        """Pixel array for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `list[list[tuple[int, int, int, int]]]`.
        """
        return self._ctx.pixel_array()

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        """Update pixels for this SketchFacadeMediaMixin.
        
        Args:
            pixels: The pixels value. Expected type: `Sequence[int] | Buffer | None`. Defaults to
                `None`.
        
        Returns:
            None.
        """
        self._ctx.update_pixels(pixels)

    @overload
    def get(self) -> Image:
        ...

    @overload
    def get(self, x: int, y: int) -> Color:
        ...

    @overload
    def get(self, x: int, y: int, w: int, h: int) -> Image:
        ...

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ) -> Color | Image:
        """Get for this SketchFacadeMediaMixin.
        
        Args:
            x: The x value. Expected type: `int | None`. Defaults to `None`.
            y: The y value. Expected type: `int | None`. Defaults to `None`.
            w: The w value. Expected type: `int | None`. Defaults to `None`.
            h: The h value. Expected type: `int | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Color | Image`.
        """
        return cast(Color | Image, cast(Any, self._ctx).get(x, y, w, h))

    def set(self, x: int, y: int, value: PixelValue) -> None:
        """Set for this SketchFacadeMediaMixin.
        
        Args:
            x: The x value. Expected type: `int`.
            y: The y value. Expected type: `int`.
            value: The value value. Expected type: `PixelValue`.
        
        Returns:
            None.
        """
        self._ctx.set(x, y, value)

    @overload
    def copy(self) -> Image:
        ...

    @overload
    def copy(self, sx: int, sy: int, sw: int, sh: int, /) -> Image:
        ...

    @overload
    def copy(
        self, sx: int, sy: int, sw: int, sh: int, dx: int, dy: int, dw: int, dh: int, /
    ) -> None:
        ...

    @overload
    def copy(
        self,
        image: Image,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        /,
    ) -> None:
        ...

    def copy(self, *args: Any) -> Image | None:
        """Copy for this SketchFacadeMediaMixin.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Image | None`.
        """
        return cast(Image | None, cast(Any, self._ctx).copy(*args))

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
        """Filter for this SketchFacadeMediaMixin.
        
        Args:
            mode: The mode value. Expected type: `c.ImageFilter`.
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._ctx.filter(mode, value)

    def save_canvas(
        self, path: str | Path, *, extension: str | None = None, overwrite: bool = True
    ) -> Path:
        """Save canvas data to the requested destination.
        
        Args:
            path: The path value. Expected type: `str | Path`.
            extension: The extension value. Expected type: `str | None`. Defaults to `None`.
            overwrite: The overwrite value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            The return value. Type: `Path`.
        """
        return self._ctx.save_canvas(path, extension=extension, overwrite=overwrite)

    def save_frames(
        self,
        path_pattern: str | Path,
        *,
        extension: str = "png",
        count: int = 1,
        duration: float | None = None,
        callback: Any = None,
        overwrite: bool = True,
    ) -> list[dict[str, object]]:
        """Save frames data to the requested destination.
        
        Args:
            path_pattern: The path pattern value. Expected type: `str | Path`.
            extension: The extension value. Expected type: `str`. Defaults to `'png'`.
            count: The count value. Expected type: `int`. Defaults to `1`.
            duration: The duration value. Expected type: `float | None`. Defaults to `None`.
            callback: The callback value. Expected type: `Any`. Defaults to `None`.
            overwrite: The overwrite value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            The return value. Type: `list[dict[str, object]]`.
        """
        return self._ctx.save_frames(
            path_pattern,
            extension=extension,
            count=count,
            duration=duration,
            callback=callback,
            overwrite=overwrite,
        )

    def save_gif(
        self,
        path: str | Path,
        *,
        count: int = 1,
        duration: float | None = None,
        overwrite: bool = True,
    ) -> Path:
        """Save gif data to the requested destination.
        
        Args:
            path: The path value. Expected type: `str | Path`.
            count: The count value. Expected type: `int`. Defaults to `1`.
            duration: The duration value. Expected type: `float | None`. Defaults to `None`.
            overwrite: The overwrite value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            The return value. Type: `Path`.
        """
        return self._ctx.save_gif(path, count=count, duration=duration, overwrite=overwrite)

    def blend_mode(self, mode: c.BlendMode) -> None:
        """Blend mode for this SketchFacadeMediaMixin.
        
        Args:
            mode: The mode value. Expected type: `c.BlendMode`.
        
        Returns:
            None.
        """
        self._ctx.blend_mode(mode)

    @overload
    def blend(
        self,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None:
        ...

    @overload
    def blend(
        self,
        image: Image,
        sx: int,
        sy: int,
        sw: int,
        sh: int,
        dx: int,
        dy: int,
        dw: int,
        dh: int,
        mode: c.BlendMode,
        /,
    ) -> None:
        ...

    def blend(self, *args: Any) -> None:
        """Blend for this SketchFacadeMediaMixin.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            None.
        """
        cast(Any, self._ctx).blend(*args)

    def erase(self) -> None:
        """Erase for this SketchFacadeMediaMixin.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.erase()

    def no_erase(self) -> None:
        """Disable erase.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.no_erase()

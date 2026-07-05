"""Image, text, pixel, and compositing forwards for object sketches."""

from __future__ import annotations

from collections.abc import Buffer, Callable, Sequence
from pathlib import Path
from typing import Literal, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.api.sound import get_audio_context as _get_audio_context
from gummysnake.assets.audio import (
    FFT,
    Amplitude,
    AudioBuffer,
    AudioFilter,
    AudioInput,
    Envelope,
    FilterType,
    Oscillator,
    WaveformName,
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
type ImageCallArg = Image | CanvasImage | float
type CopyArg = Image | int
type BlendArg = Image | int | c.BlendMode


class SketchFacadeMediaMixin(SketchFacadeBaseMixin):
    """Public SketchFacadeMediaMixin value."""

    def create_video(self, path: str | Path) -> Video:
        return _create_video(path)

    async def create_video_async(self, path: str | Path) -> Video:
        return await _create_video_async(path)

    def create_capture(
        self,
        kind: str = "video",
        *,
        device: int | str = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> Capture | AudioInput | AudioVideoCapture:
        return _create_capture(kind, device=device, width=width, height=height)

    async def create_capture_async(
        self,
        kind: str = "video",
        *,
        device: int | str = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> Capture | AudioInput | AudioVideoCapture:
        return await _create_capture_async(kind, device=device, width=width, height=height)

    def load_sound(self, path: str | Path) -> Sound:
        return _load_sound(path)

    async def load_sound_async(self, path: str | Path) -> Sound:
        return await _load_sound_async(path)

    def create_audio(self, path: str | Path) -> Sound:
        return _load_sound(path)

    def create_amplitude(
        self, source: Sound | AudioBuffer | Sequence[float] | None = None, *, smoothing: float = 0.0
    ) -> Amplitude:
        return _create_amplitude(source, smoothing=smoothing)

    def create_fft(
        self,
        source: Sound | AudioBuffer | Sequence[float] | None = None,
        *,
        bins: int = 1024,
        smoothing: float = 0.0,
    ) -> FFT:
        return _create_fft(source, bins=bins, smoothing=smoothing)

    def create_oscillator(
        self, waveform: WaveformName = "sine", *, frequency: float = 440.0, amplitude: float = 1.0
    ) -> Oscillator:
        return _create_oscillator(waveform, frequency=frequency, amplitude=amplitude)

    def create_envelope(
        self, attack: float = 0.01, decay: float = 0.1, sustain: float = 0.7, release: float = 0.2
    ) -> Envelope:
        return _create_envelope(attack=attack, decay=decay, sustain=sustain, release=release)

    def create_filter(
        self,
        filter_type: FilterType = "lowpass",
        *,
        frequency: float = 1_000.0,
        resonance: float = 0.0,
    ) -> AudioFilter:
        return _create_filter(filter_type, frequency=frequency, resonance=resonance)

    def create_audio_in(self, *, sample_rate: int = 44_100) -> AudioInput:
        return _create_audio_in(sample_rate=sample_rate)

    def get_audio_context(self) -> dict[str, object]:
        return _get_audio_context()

    @overload
    def image(self, image: Image | CanvasImage, x: float, y: float, /) -> None: ...

    @overload
    def image(
        self, image: Image | CanvasImage, x: float, y: float, width: float, height: float, /
    ) -> None: ...

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
    ) -> None: ...

    def image(self, *args: ImageCallArg) -> None:
        self._ctx_call("image", *args)

    def text(self, value: SupportsText, x: float, y: float) -> None:
        self._ctx.text(value, x, y)

    def text_batch(self, items: Sequence[tuple[SupportsText, float, float]]) -> None:
        context = self._ctx
        context.renderer.text_batch(
            [(str(value), float(x), float(y)) for value, x, y in items],
            context.state.style,
            context.state.transform.matrix,
        )

    def text_size(self, size: float | None = None) -> float:
        return self._ctx.text_size(size)

    def text_font(self, font: Font | str | None = None) -> Font:
        return self._ctx.text_font(font)

    def text_style(self, style: c.TextStyle | None = None) -> c.TextStyle:
        return self._ctx.text_style(style)

    def text_align(self, horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
        self._ctx.text_align(horizontal, vertical)

    def text_leading(self, value: float | None = None) -> float:
        return self._ctx.text_leading(value)

    def text_width(self, value: SupportsText) -> float:
        return self._ctx.text_width(value)

    def text_widths(self, values: Sequence[SupportsText]) -> tuple[float, ...]:
        context = self._ctx
        style = context.state.style
        return tuple(context.renderer.text_width(str(value), style) for value in values)

    def text_ascent(self) -> float:
        return self._ctx.text_ascent()

    def text_descent(self) -> float:
        return self._ctx.text_descent()

    def font_ascent(self, font: Font | str | None = None) -> float:
        return self._ctx.font_ascent(font)

    def font_descent(self, font: Font | str | None = None) -> float:
        return self._ctx.font_descent(font)

    def font_width(self, value: SupportsText, font: Font | str | None = None) -> float:
        return self._ctx.font_width(value, font)

    def text_bounds(self, value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
        return self._ctx.text_bounds(value, x, y)

    def font_bounds(
        self,
        value: SupportsText,
        x: float = 0.0,
        y: float = 0.0,
        font: Font | str | None = None,
    ) -> dict[str, float]:
        return self._ctx.font_bounds(value, x, y, font)

    def text_direction(self, value: str | None = None) -> str:
        return self._ctx.text_direction(value)

    def text_wrap(self, value: str | None = None) -> str:
        return self._ctx.text_wrap(value)

    def text_weight(self, value: int | None = None) -> int:
        return self._ctx.text_weight(value)

    @overload
    def text_property(self, name: Literal["direction"], value: str | None = None) -> str: ...

    @overload
    def text_property(self, name: Literal["wrap"], value: str | None = None) -> str: ...

    @overload
    def text_property(self, name: Literal["weight"], value: int | None = None) -> int: ...

    def text_property(self, name: str, value: str | int | None = None) -> str | int:
        return cast(str | int, self._ctx_call("text_property", name, value))

    def text_properties(
        self, **properties: Unpack[TextProperties]
    ) -> dict[str, str | int | float | c.TextStyle]:
        return cast(
            dict[str, str | int | float | c.TextStyle],
            self._ctx_call("text_properties", **properties),
        )

    def describe(self, description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
        return self._ctx.describe(description, label=label)

    def describe_element(self, name: SupportsText, description: SupportsText) -> dict[str, str]:
        return self._ctx.describe_element(name, description)

    def text_output(self) -> list[dict[str, str]]:
        return self._ctx.text_output()

    def grid_output(self) -> list[dict[str, str]]:
        return self._ctx.grid_output()

    def load_pixels(self) -> PixelBuffer:
        return self._ctx.load_pixels()

    def load_pixel_bytes(self) -> bytes:
        return self._ctx.load_pixel_bytes()

    def pixels(self) -> Sequence[int]:
        context = self._ctx
        return cast(Sequence[int], context.pixels or context.load_pixels())

    def pixel_array(self) -> list[list[tuple[int, int, int, int]]]:
        return self._ctx.pixel_array()

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        self._ctx.update_pixels(pixels)

    @overload
    def get(self) -> Image: ...

    @overload
    def get(self, x: int, y: int) -> Color: ...

    @overload
    def get(self, x: int, y: int, w: int, h: int) -> Image: ...

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ) -> Color | Image:
        return cast(Color | Image, self._ctx_call("get", x, y, w, h))

    def set(self, x: int, y: int, value: PixelValue) -> None:
        self._ctx.set(x, y, value)

    @overload
    def copy(self) -> Image: ...

    @overload
    def copy(self, sx: int, sy: int, sw: int, sh: int, /) -> Image: ...

    @overload
    def copy(
        self, sx: int, sy: int, sw: int, sh: int, dx: int, dy: int, dw: int, dh: int, /
    ) -> None: ...

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
    ) -> None: ...

    def copy(self, *args: CopyArg) -> Image | None:
        return cast(Image | None, self._ctx_call("copy", *args))

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
        self._ctx.filter(mode, value)

    def save_canvas(
        self, path: str | Path, *, extension: str | None = None, overwrite: bool = True
    ) -> Path:
        return self._ctx.save_canvas(path, extension=extension, overwrite=overwrite)

    def save_frames(
        self,
        path_pattern: str | Path,
        *,
        extension: str = "png",
        count: int = 1,
        duration: float | None = None,
        callback: Callable[[list[dict[str, object]]], object] | None = None,
        overwrite: bool = True,
    ) -> list[dict[str, object]]:
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
        return self._ctx.save_gif(path, count=count, duration=duration, overwrite=overwrite)

    def blend_mode(self, mode: c.BlendMode) -> None:
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
    ) -> None: ...

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
    ) -> None: ...

    def blend(self, *args: BlendArg) -> None:
        self._ctx_call("blend", *args)

    def erase(self) -> None:
        self._ctx.erase()

    def no_erase(self) -> None:
        self._ctx.no_erase()

# Canvas touch, sound, and native text

This note tracks the canvas migration work for touch input, sound/media, and native text.

## Touch input

The Rust canvas runtime normalizes winit touch events into mapping payloads with:

- `type`: `touch_started`, `touch_moved`, `touch_ended`, or `touch_cancelled`
- `id`: stable touch identifier
- `x`/`y`: physical runtime coordinates unless `coordinates="logical"` is provided
- `pressure`, `phase`, `timestamp`, and `device` when available

`CanvasBackend` converts those payloads into `TouchEvent` and `TouchPoint` values, updates
`touches()`, and dispatches the public sketch callbacks through `SketchContext`. The backend
advertises `touch=True` only when the native window runtime is available.

## Sound and media

Sound loading no longer imports or wraps Pyglet. `load_sound()` and `create_audio()` now return a
backend-neutral `Sound` object backed by local-file metadata and a small platform player protocol.
WAV duration is read with the Python standard library. Playback uses an available platform command
such as `afplay`, `paplay`, `aplay`, or `ffplay`; if no player is available, `play()` raises
`BackendCapabilityError` while metadata and control state remain usable.

Video playback and camera capture remain backend-neutral through the optional OpenCV media extra.
Headless environments, missing devices, denied permissions, missing codecs, and missing optional
dependencies continue to fail through package-specific errors.

## Native text

Canvas text drawing and metrics now run through the Rust canvas extension. The Rust path uses
`ab_glyph` for font loading, glyph metrics, rasterization, and cached text image upload. Python no
longer calls `PillowRenderer` for canvas text metrics.

Default font fallback searches common macOS, Linux, and Windows system fonts. Explicit font paths
from the public style state are loaded by Rust and cached by path.

## Performance checks

The new interactive examples are covered by opt-in benchmark tests:

```sh
uv run pytest -m benchmark tests/benchmark/test_canvas_migration_feature_perf.py
```

Those tests run the canvas and Pyglet backends in subprocesses and require the canvas backend to be
at least 10 percent faster for the new touch, sound, and native-text examples.

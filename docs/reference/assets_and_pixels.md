# Images, Pixels, and Assets

## Images

- `load_image(path)`
- `load_image_async(path)`
- `create_image(width, height)`
- `image(img, x, y, width=None, height=None, ...)`
- `image_mode(mode)`
- `image_sampling(mode)`
- `smooth()`
- `no_smooth()`
- `tint(*color)`
- `no_tint()`

Images are loaded by the Rust canvas runtime. There is no Pillow fallback.
Async loader variants are awaitable and useful from `async def preload()` or
`async def setup()` callbacks.

`load_image()` and `create_image()` return the normal Python `Image` type, but
RGBA storage is backed by a Rust-managed `CanvasImage` handle. Drawing images
uses the renderer's canvas-owned sprite path, and mutations such as `set()`,
`update_pixels()`, `resize()`, `mask()`, or `filter()` update the Rust image
handle instead of switching to Python-owned pixel storage. Bulk image-local work
such as resize, mask, filter, crop/copy, and alpha compositing is handled by the
Rust canvas runtime so the public Python API does not run nested per-pixel loops
for normal image sizes. Image-local `GRAY`, `INVERT`, `THRESHOLD`, `BLUR`,
`POSTERIZE`, `ERODE`, and `DILATE` all execute in that Rust-owned kernel;
threshold defaults to `0.5`, posterize defaults to four levels, and morphological
filters preserve source alpha while operating on RGB channels.

`smooth()` and `image_sampling(LINEAR)` request linear sampling.
`no_smooth()` and `image_sampling(NEAREST)` request nearest-neighbor sampling.
The renderer may choose the fastest supported path for the current sampling
mode, transform, blend mode, and backend capabilities.
Dense sprite loops are internally batched where ordering permits. Alternating
draws from a small set of images can use a runtime-managed atlas path while
preserving public `image()` semantics, tint, source rectangles, and sampling
mode.

`tint()` multiplies image RGB and alpha during drawing without changing the
source image. `no_tint()` restores untinted drawing, and `push()`/`pop()` preserve
the tint state like other style settings.

Image objects also support Python indexing:

```python
color = img[x, y]
img[x, y] = gs.Color(255, 0, 0)
tile = img[x0:x1, y0:y1]
```

## Pixels

- `load_pixels()`
- `load_pixel_bytes()`
- `update_pixels()`
- `pixels()`
- `pixel_array()`
- `get(...)`
- `set(...)`

Pixel buffers are physical RGBA buffers. When `pixel_density()` is greater than
`1`, the physical pixel size is larger than the logical canvas size.

`load_pixels()` returns `gummysnake.core.pixels.PixelBuffer`, a mutable
list-like RGBA byte buffer that tracks dirty byte ranges. Use
`load_pixel_bytes()` for performance-sensitive readback when a bytes-like RGBA
buffer is enough.
`update_pixels()` accepts the `PixelBuffer` returned by `load_pixels()`, plain
lists for compatibility, and efficient buffer-like inputs such as `bytes`,
`bytearray`, and `memoryview`.

Performance diagnostics can be enabled when investigating slow pixel or image
paths:

```python
gs.enable_performance_diagnostics()
pixels = gs.load_pixels()
report = gs.performance_diagnostics()
```

The report contains counters and short public-language messages for readback,
`PixelBuffer`/list compatibility conversion, pixel upload, texture upload/cache
hits, and CPU compositing fallback helpers such as canvas `get()`, `set()`, and
`filter()`.
Small canvas `get(x, y)`, `get(x, y, w, h)`, and `set(...)` operations route
through Rust region APIs and avoid reconstructing a full Python `Image` for
region work. Full-canvas `load_pixels()` remains a full physical-buffer readback
and returns `gummysnake.core.pixels.PixelBuffer`, a mutable byte buffer that
preserves list-like slice/equality behavior while tracking dirty regions for efficient
`update_pixels()` uploads when supported by the runtime.

Renderer/runtime counters are available separately:

```python
gs.reset_renderer_performance_counters()
# draw representative frames
report = gs.renderer_performance_counters()
```

Text-heavy sketches can inspect `text_cache_hits`, `text_cache_misses`,
`text_cache_evictions`, and `text_measurements` in that report to spot dynamic
text churn. Dense label overlays should prefer `text_batch()` and `text_widths()`
so repeated labels can stay on the Rust-owned text path with fewer Python bridge
calls. The renderer may use direct GPU glyph-atlas text or cached line textures
internally depending on ordering, style, transform, and font requirements.

For native interactive timing, enable frame pacing diagnostics and inspect
`frame_pacing_diagnostics()` for draw, present, frame-interval, and input-poll
timings.

## Export

- `save_canvas(path=None)`
- `save_frames(path_pattern, count=1, duration=None, callback=None)`
- `save_gif(path, count=1, duration=None)`
- `save_bytes(data, path)`
- `save_json(data, path)`
- `save_strings(lines, path)`
- `create_writer(path)`

Still-image exports (`Image.save()`, `save_canvas()`, and `save_frames()`) use
Rust-owned PNG encoding. A suffixless destination receives `.png`; other
still-image suffixes are rejected rather than writing mismatched file contents.
`save_frames()` writes a deterministic PNG sequence from the current canvas
state. Patterns may use `{index}`, `{frame}`, or `{frame_count}` placeholders;
without placeholders, files are named with a zero-padded suffix. `save_gif()`
uses the Rust canvas runtime to encode an animated GIF from the current canvas
image; it accepts a suffixless or `.gif` destination, `count` repeats that
captured image, and `duration` must produce a positive finite frame duration.

## Data and Text Assets

- `load_json(path)`
- `load_json_async(path)`
- `load_strings(path)`
- `load_strings_async(path)`
- `load_bytes(path)`
- `load_bytes_async(path)`
- `load_font(path)`
- `load_font_async(path)`

## Sound and Media

- `load_sound(path)`
- `load_sound_async(path)`
- `create_audio(...)`
- `create_amplitude(source=None, smoothing=0.0)`
- `create_fft(source=None, bins=1024, smoothing=0.0)`
- `create_oscillator(waveform="sine", frequency=440.0, amplitude=1.0)`
- `create_envelope(attack=0.01, decay=0.1, sustain=0.7, release=0.2)`
- `create_filter(filter_type="lowpass", frequency=1000.0, resonance=0.0)`
- `create_audio_in(sample_rate=44100)`
- `get_audio_context()`
- `create_capture(...)`
- `create_capture_async(...)`
- `create_video(...)`
- `create_video_async(...)`

`load_sound()` is the stable public loading authority and returns the public
`Sound` wrapper with a Rust-managed `CanvasSound` audio asset attached. Mono and
stereo 16-bit PCM WAV bytes, decoded planar PCM, metadata, and stable asset
identity stay in Rust until code explicitly asks for `sound.to_bytes()`. Loaded
and generated/rendered sounds share one process-local SDL3 device manager and
voice mixer. Each `play()` creates independent native voice state while reusing
the immutable decoded asset. `pause()`, `stop()`, `close()`, `loop()`,
`no_loop()`, `looping(...)`, `seek(seconds)`, `time()`, `is_playing()`,
`is_paused()`, `volume()`, `rate()`, and `pan()` are synchronized at native mixer
frame boundaries; rate/device conversion uses the canonical band-limited
resampler. `on_ended()` callbacks are queued by Rust and drained on the Python
owner thread when state is observed. `playback_diagnostics()` reports per-voice
block/frame/state data. Loading and metadata access do not open a device. Missing
devices and unsupported formats fail clearly; playback never creates temporary
files, launches subprocesses, synthesizes silence, or selects another player.

Audio analysis and synthesis are deterministic, headless-safe Pythonic helpers.
`AudioBuffer` stores sample tuples, `Amplitude` computes RMS levels, `FFT`
returns fixed-size waveforms and spectra, `Oscillator` can generate sample
buffers or `Sound` objects, `Envelope` applies ADSR curves, `AudioFilter`
processes low-pass/high-pass buffers, and `AudioInput` is an explicit input
buffer for tests and audio-reactive sketches. Gummy Snake does not expose Web
Audio node graphs or browser audio contexts.

`create_video()` currently decodes self-contained GIF files in the mandatory Rust
canvas runtime and does not select an OpenCV or platform decoder. External decoder
integrations may use the optional `media` extra to supply contiguous unsigned-byte
grayscale, BGR, BGRA, or explicit RGBA frames; conversion then remains in the Rust
canvas runtime. `MediaFrameSink(width, height)`
is the public integration API for repeatedly updating one stable `Image` from
such buffers without allocating a new Python image wrapper for each frame. Use
`sink.update(frame, format=None, stride=None)`, `sink.image`, and
`sink.diagnostics()` to update, access, and inspect that reusable image.

`create_video()` rejects unsupported codecs clearly and returns a `Video` with explicit `play()`, `pause()`, `stop()`,
`loop()`, `no_loop()`, `looping(...)`, `seek(seconds)`, `time()`, `speed(...)`,
`read()`, `current_frame()`, and `close()` methods. `speed()` records the
intended playback rate for clock-driven integrations; explicit `read()` calls
still pull one decoded frame at a time. `read()` returns a Gummy Snake `Image`,
so video frames can be passed to `image()` and to texture-capable 3D paths like
other images.

`create_capture("audio")` returns a started deterministic `AudioInput`. Rust-native
camera/video capture is not available in the current build, so `"video"` and
combined audio/video requests raise an actionable `BackendCapabilityError` rather
than selecting OpenCV, a synthetic camera, or another platform decoder. Physical
camera availability and cross-platform hardware evidence are not required for the
headless media contract. Browser permission APIs and DOM media elements are not
exposed.

## Offscreen Graphics, Framebuffers, and Compute

- `create_graphics(width, height, renderer=gs.P2D, pixel_density=None)`
- `create_framebuffer(width, height, renderer=gs.P2D, pixel_density=None, depth=True)`
- `webgpu_context()`
- `create_storage_buffer(data_or_size, dtype="float")`
- `update_storage_buffer(buffer, data, offset=0)`
- `read_storage_buffer(buffer)`
- `create_compute_shader(source=..., entry_point="main", label=None)`
- `dispatch_compute(shader, x, y=1, z=1, **buffers)`
- `gpu_resource_diagnostics()`
- `reset_gpu_resource_diagnostics()`

`Graphics` is an offscreen canvas with isolated style, transform, pixel, and 3D
state, built by the mandatory canvas backend. Its `drawing` property provides a
statically visible drawing surface; direct calls such as `graphics.background()`
and `graphics.rect()` remain supported. Use `snapshot()`, `to_rgba_bytes()`,
`save()`, or `image(graphics, x, y)` on another canvas. `pixel_density()` applies
to the offscreen canvas backing buffer, and `remove()` releases its backend.
`Framebuffer` extends `Graphics` with depth metadata for render-target workflows.
There is no Python image or interactive fallback.

The `WEBGPU` compute helpers use Rust-owned WGPU storage buffers and compiled
WGSL shaders without exposing browser WebGPU contexts or JavaScript shader
objects. `dispatch_compute()` binds storage buffers in keyword insertion order;
Python callback execution and CPU compute fallbacks are not supported. Missing
GPU capabilities fail with an actionable `BackendCapabilityError`.
`gpu_resource_diagnostics()` reports Rust-owned allocation, upload, readback,
compile, dispatch, and release counters. `reset_gpu_resource_diagnostics()`
resets those counters without releasing live resources.

3D asset helpers also include awaitable variants:

- `load_model_async(path, normalize=False, package=None)`
- `load_shader_async(vertex_path, fragment_path)`

Wavefront OBJ parsing, normalization, primitive model generation, GPU-ready
triangle packing, and OBJ/STL export are handled by the Rust canvas runtime.
`Model3D` and `Mesh3D` keep Rust-managed handles as canonical storage and expose
immutable Python tuple buffers plus optional lazy NumPy views for inspection and
interchange. Built-in WEBGL drawing reuses retained GPU vertex/index buffers
when GPU acceleration is available, with transform/projection, depth testing,
texture sampling, and material lighting handled by GPU pipelines.

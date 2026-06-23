# Feature Scope Decisions

This page records native Gummy Snake scope decisions for features whose p5
reference surface is browser- or device-specific. These decisions are part of
the public API contract: unsupported names stay absent from `gummysnake.__all__`
until a native backend and tests exist.

## 3D And WEBGL

`WEBGL` means Gummy Snake's Rust canvas 3D path, not a browser WebGL context.
The canvas backend reports `three_d=True` and `software_three_d=True` today.
`native_three_d` remains false until a broader native 3D feature set exists.

Built-in primitive/model GPU pipelines may use shaders internally, but that does
not imply user-programmable native shader support. The shader capability split is:

- `shaders`: Python shader objects and shader-style binding calls are accepted.
- `native_shaders`: user shader source is compiled or interpreted by the native
  renderer.

The canvas backend currently keeps `native_shaders=False`. Browser context
objects, WebGL2 context attributes, and drawing-context escape hatches are not
public APIs.

## Offscreen Render Targets

Browser canvas helpers such as `create_graphics()` and `create_framebuffer()`
remain absent until native render-target semantics are complete. A future native
target must define ownership, pixel density, camera/projection state, color and
depth attachments, readback, resize, and cleanup behavior without exposing DOM
or browser canvas objects.

## WebGPU And Compute

WebGPU-like compute/storage APIs are out of public scope for now. Names such as
`webgpu_context`, `create_storage_buffer`, `update_storage_buffer`,
`read_storage_buffer`, `create_compute_shader`, and `dispatch_compute` must stay
absent. A future implementation must be Rust-owned, capability-gated, bounded by
resource limits, and tested for synchronization and cleanup before exposing
Python APIs.

## Sound

Core sound assets are native Gummy Snake assets. `load_sound()` returns a
`Sound` wrapper backed by a Rust-managed `CanvasSound` handle when supported.
Playback controls on `Sound` are backend-neutral and safe to call even when a
real audio output backend is not installed.

Audio analysis and synthesis are deferred. Amplitude, FFT, audio input,
oscillator, envelope, and filter APIs stay absent until deterministic DSP tests,
fake-backend lifecycle tests, and optional real-time backend capability checks
exist. Gummy Snake does not expose Web Audio contexts.

## Media Playback And Capture

Video playback and camera capture use optional native media dependencies. Media
objects expose decoded frame data as Gummy Snake image buffers and do not expose
DOM media elements or browser permission APIs. Audio capture remains deferred
until it can integrate with a native sound analysis/input model.

## Device Sensors

Acceleration/orientation sensors are deferred on desktop and headless builds.
Sensor APIs stay absent until a provider interface defines units, axes,
timestamps, lifecycle, privacy errors, non-blocking polling, and deterministic
sample injection tests.

## Accessibility Output

Canvas accessibility output is native metadata. `describe()` and
`describe_element()` record sketch or region descriptions, and deterministic
headless readback is available through `text_output()` and `grid_output()`.
These helpers do not create DOM nodes.

Future shape/text/grid output should remain opt-in so disabled recording has no
meaningful overhead in dense drawing loops.

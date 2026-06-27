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

The current public 3D surface is listed in `docs/reference/three_d.md` and
includes camera helpers such as `set_camera()`, `roll()`, `frustum()`,
`world_to_screen()`, and `screen_to_world()`; light/material helpers such as
`lights()`, `no_lights()`, `spot_light()`, `image_light()`, `panorama()`,
`light_falloff()`, `specular_color()`, `emissive_material()`, and
`metalness()`; texture helpers such as `texture_mode()` and `texture_wrap()`;
and geometry helpers such as `normal()`, `vertex_property()`,
`build_geometry()`, `free_geometry()`, `flip_u()`, and `flip_v()`. These are
native Gummy Snake APIs over the Rust canvas 3D path, not browser context
objects. Internal primitive/model GPU pipelines may use Rust-owned buffers and
shaders for built-in rendering; user-programmable native shader execution is
still represented by the separate `native_shaders` capability.

## Offscreen Render Targets

`create_graphics()` and `create_framebuffer()` are public native offscreen
render targets. They create isolated headless canvas contexts with their own
style, transform, pixel, and 3D state; `Graphics.snapshot()`/`to_rgba_bytes()`
provide readback, and `remove()` releases the offscreen backend. `Framebuffer`
extends `Graphics` with depth-attachment metadata for render-target workflows.
No DOM or browser canvas objects are exposed.

## WebGPU And Compute

`WEBGPU` is a public renderer constant for WebGPU-compatible native sketches.
The current implementation keeps canvas presentation on the Rust canvas runtime
and exposes deterministic Pythonic compute/storage helpers: `webgpu_context()`,
`create_storage_buffer()`, `update_storage_buffer()`, `read_storage_buffer()`,
`create_compute_shader()`, and `dispatch_compute()`. These helpers are
CPU-backed in headless/CI runs so behavior is deterministic and does not require
a browser adapter. `webgpu_context()` reports the current safe backend and makes
clear that no DOM/WebGPU context object is exposed.

The public resource model remains bounded: storage buffers have explicit dtype,
size, update, read, and close operations; compute dispatch requires an explicit
Python callback today; invalid dimensions, closed buffers, and invalid bindings
raise Gummy Snake validation errors.

## Sound

Core sound assets are native Gummy Snake assets. `load_sound()` returns a
`Sound` wrapper backed by a Rust-managed `CanvasSound` handle when supported.
Metadata and byte access do not require an audio output device. Playback is a
small native convenience layer over available platform players (`afplay`,
`paplay`, `aplay`, or `ffplay`); if no player is available, `play()` raises a
Gummy Snake capability error while non-audio sketches and metadata workflows can
continue.

Audio analysis and synthesis are public deterministic helpers. `AudioBuffer`,
`Amplitude`, `FFT`, `Oscillator`, `Envelope`, `AudioFilter`, and `AudioInput`
cover headless-safe sample buffers, RMS/DFT analysis, oscillator sample
generation, ADSR envelopes, simple filters, and explicit synthetic audio input.
`get_audio_context()` reports the native Gummy Snake audio feature set; it is not
a Web Audio context and does not expose browser nodes.

## Media Playback And Capture

Video playback and camera capture use optional native media dependencies. Media
objects expose decoded frame data as Gummy Snake image buffers and do not expose
DOM media elements or browser permission APIs. Camera access can fail in
headless, privacy-restricted, or device-less environments with package-specific
capability errors. `create_capture("audio")` returns a started `AudioInput`, and
`create_capture("audio+video")` returns `AudioVideoCapture`, a composite object
with a camera `Capture` plus an `AudioInput` for analysis workflows.

## Device Sensors

Acceleration/orientation sensor APIs are public and deterministic. Current
native desktop/headless behavior uses explicit sample injection via
`inject_sensor_sample()` / `Sketch.inject_sensor_sample()`; state getters expose
`acceleration_x/y/z`, previous acceleration, `rotation_x/y/z`, previous
rotation, `device_orientation`, and `turn_axis`. Threshold helpers
`set_move_threshold()` and `set_shake_threshold()` control dispatch of
`device_moved`, `device_turned`, and `device_shaken` callbacks. Future native
providers must feed the same state/callback contract without blocking the sketch
frame loop or triggering platform permission prompts in headless runs.

## Accessibility Output

Canvas accessibility output is native metadata. `describe()` and
`describe_element()` record sketch or region descriptions, validate non-empty
labels/descriptions, and replace repeated labels deterministically so per-frame
updates do not grow unbounded. Headless readback is available through
`text_output()` and `grid_output()`. These helpers do not create DOM nodes.

Accessibility output is explicit and deterministic today. Sketches can record
canvas and element descriptions with `describe()` and `describe_element()` and
read them back with `text_output()` / `grid_output()` in headless tests. Richer
native-window hooks may build on that metadata, but the public output helpers are
implemented and validated without DOM nodes.

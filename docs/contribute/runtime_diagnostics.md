# Runtime Diagnostics

Runtime diagnostics explain where time goes without exposing private Rust
implementation details in public sketch APIs.

## Renderer Counters

Use `renderer_performance_counters()` after drawing representative frames:

```python
gs.reset_renderer_performance_counters()
# draw work
report = gs.renderer_performance_counters()
```

The stable top-level counters are:

| Counter | Meaning |
| --- | --- |
| `gpu_draws` | Drawing commands queued for the renderer/GPU-oriented path. |
| `cpu_fallbacks` | Operations that require CPU compositing or CPU pixel work. |
| `pixel_readbacks` | Canvas pixel reads into Python or CPU memory. |
| `pixel_uploads` | Full pixel or texture uploads back to the canvas. |
| `gpu_blend_commands` | Non-default blend commands that stayed in the GPU command stream. |
| `gpu_region_effect_passes` | Bounded GPU region-effect passes, such as internal pixel-prefix mutation. |
| `image_cache_hits` / `image_cache_misses` | Legacy Python image byte-cache reuse or upload; Rust-backed `Image` draws normally bypass this path. |
| `texture_cache_hits` / `texture_uploads` | Native texture reuse or upload, including canvas-managed image handles. |
| `text_cache_hits` / `text_cache_misses` | Text metric or glyph cache reuse. |
| `text_cache_evictions` | Bounded text or text-metric cache entries evicted during dynamic text churn. |
| `text_measurements` | Native text measurement calls. |
| `bridge_calls` | Python-to-canvas bridge calls made by the adapter. |
| `frames_presented` | Frames presented by the renderer/backend. |
| `gpu_frames_rendered` | Offscreen GPU frame resolves. |
| `event_polls` | Native input/event polling calls. |
| `direct_model_draws` | Rust-owned model-handle draws that project, shade, and submit untextured triangles without Python face dictionaries. |
| `python_face_payloads` | Legacy/fallback shaded-face payloads materialized as Python dictionaries. |
| `direct_shape_finalizations` | Rust-owned `begin_shape()` buffers finalized directly into draw or clip operations. |
| `shape_buffer_extractions` | Shape buffers extracted into Python lists for compatibility fallback paths. |
| `pixel_payload_copies` | Pixel uploads that required Python list/sequence conversion before reaching the runtime. |

When the installed Rust canvas exposes native counters, the Python report also
contains a `native` dictionary. Treat that dictionary as diagnostic detail; use
the top-level keys in tests and docs.

Native diagnostics may also include GPU render-loop counters:
`gpu_vertex_buffer_allocations`, `gpu_vertex_uploads`, `gpu_primitive_batches`,
and `gpu_image_batches`. Allocations should grow with peak frame demand rather
than with every frame; uploads and batches track actual draw work.

## GPU Region Effects

GPU region effects are internal renderer operations that snapshot the current
canvas texture into a temporary texture, run a bounded shader pass, and write
the result back to the canvas texture without mapping pixels into CPU memory.
They preserve draw order by resolving pending draw commands before the effect
and then continuing future commands against the updated canvas texture.

The current region-effect framework is used for benchmark pixel-prefix mutation
and reports through `gpu_region_effect_passes`. That path should not increment
`pixel_readbacks` or `pixel_uploads` when a GPU renderer is available.

Destination-sampling blend modes use the same ordered source/target discipline:
the command encoder flushes earlier draw commands, snapshots the canvas texture,
runs the shader effect, and then continues later commands against the updated
canvas texture. They should report through `gpu_blend_commands` and
`gpu_region_effect_passes` rather than `pixel_readbacks` or `pixel_uploads`
when the effect shape is supported by the GPU path.

## Fallback Matrix

| Public operation or state | Typical path | Cost boundary | Preferred pattern |
| --- | --- | --- | --- |
| `background()`, `clear()`, basic primitives with `BLEND` | GPU-oriented draw | Low synchronization pressure | Keep normal style state for dense primitive loops; primitives must remain visible after text/image commands. |
| Batched `line()` calls with same style/transform | Batched GPU-oriented draw | Low bridge overhead | Use `gs.fast()` or local method bindings in dense loops. |
| `ADD` / `REPLACE` blend modes | Fixed-function GPU pipelines | Low synchronization pressure | Prefer these modes over destination-sampling modes in hot animation loops when they express the same visual result. |
| Destination-sampling blend modes such as `MULTIPLY`, `SCREEN`, `DIFFERENCE`, `EXCLUSION`, `DARKEST`, and `LIGHTEST` on supported filled ellipses | Ordered GPU shader region pass | Extra render pass and canvas texture snapshot, but no CPU read/merge/upload | Keep shapes simple and unclipped when these modes are used in hot animation loops. |
| `erase()` / `no_erase()` drawing | CPU compositing fallback | Requires alpha-modifying pixel work | Prefer normal alpha drawing unless erasure semantics are required. |
| Loaded images drawn unchanged | Cached texture path | First draw uploads, later draws reuse | Reuse `Image` objects and avoid per-frame mutation. |
| Mutated images drawn each frame | Texture upload path | Uploads changed image data | Batch mutations or draw with primitives when possible. |
| Rotated/scaled images | GPU texture path when cached; CPU fallback when unsupported | First texture upload, then draw cost | Reuse images; avoid changing pixels while transforming. |
| Text drawing and metrics | Glyphon-backed GPU text path for untransformed default-font text, with cached shaped buffers and a GPU glyph atlas; Rust metric cache for measurements | First glyph/layout use is expensive; mixed text then primitive drawing exercises GPU pipeline switching | Reuse text strings/styles where practical and validate primitives after text when changing renderer batching. |
| `load_pixels()` / `pixels()` | Readback plus list conversion | Synchronizes canvas data and allocates Python list | Use `load_pixel_bytes()` for bytes workflows. |
| `load_pixel_bytes()` | Byte readback | Synchronizes canvas data but does not populate `context.pixels` | Keep data as `bytes`/`memoryview` and pass it back to bulk APIs when possible. |
| `update_pixels()` | Full or dirty-region pixel upload | Buffer-like inputs reach Rust through the Python buffer protocol; list inputs are copied for compatibility | Use `bytes`, `bytearray`, `memoryview`, or the `PixelBuffer` returned by `load_pixels()`; prefer dirty row-aligned updates over full-canvas uploads. |
| `get()`, `set()`, canvas `filter()` | CPU compositing fallback | Canvas-to-image copy plus upload | Prefer renderer-native drawing or image-local work. |
| `begin_shape()` / `end_shape()` and clip paths | Rust shape-buffer finalization | Normal canvas paths avoid Python vertex-list extraction | Keep shape construction in the captured shape APIs; use diagnostics to catch fallback extraction. |
| Software `WEBGL` model drawing | Rust projection/shading with Rust-owned model handles; untextured unstroked faces use direct GPU triangles, textured/stroked faces use fallback raster/stroke paths | Projected points are logical coordinates and direct GPU submission must scale by `pixel_density()`; unsupported paths should fail with canvas capability errors | Reuse primitive/model objects so caches avoid repeated topology allocation. |
| `save_obj()` / `save_stl()` | Streaming text writer | Writes incrementally instead of assembling unbounded `list[str]` payloads | Use direct export helpers for large generated meshes. |

## Frame Pacing

Frame pacing diagnostics are opt-in:

```python
gs.enable_frame_pacing_diagnostics()
# run frames
report = gs.frame_pacing_diagnostics()
```

The report includes frame count, event poll count, last/max/mean draw duration,
present duration, event poll duration, and frame interval. The backend records
these values in both bounded and interactive runs when enabled.

## Manual Interactive Validation

Use a desktop build with native window support.

1. Build the current canvas runtime:

   ```sh
   uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
   ```

2. Run an interactive sketch with pacing diagnostics enabled in setup:

   ```python
   def setup():
       gs.create_canvas(720, 480)
       gs.enable_frame_pacing_diagnostics()
   ```

3. Exercise `loop()`, `no_loop()`, `redraw()`, resize the SDL3 window if supported,
   and move/press input devices for at least 30 seconds. Include a sketch that
   draws text before primitives, such as `examples/05_interaction/lifecycle_controls.py`,
   to validate mixed image/text and primitive GPU ordering.

4. Inspect `frame_pacing_diagnostics()` after closing or through a debug print.
   Check that input remains responsive, close requests are observed, idle
   sketches do not busy-wait, primitives drawn after text/images remain visible,
   and frame intervals are close to the target frame rate except during
   intentional resize or heavy rendering work.

5. If frame intervals drift upward, compare renderer counters for readback,
   upload, CPU fallback, and text/image cache misses before changing scheduling
   thresholds.

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
| `image_cache_hits` / `image_cache_misses` | Python image cache reuse or upload. |
| `texture_cache_hits` / `texture_uploads` | Native texture reuse or upload. |
| `text_cache_hits` / `text_cache_misses` | Text metric or glyph cache reuse. |
| `text_cache_evictions` | Bounded text or text-metric cache entries evicted during dynamic text churn. |
| `text_measurements` | Native text measurement calls. |
| `bridge_calls` | Python-to-canvas bridge calls made by the adapter. |
| `frames_presented` | Frames presented by the renderer/backend. |
| `gpu_frames_rendered` | Offscreen GPU frame resolves. |
| `event_polls` | Native input/event polling calls. |

When the installed Rust canvas exposes native counters, the Python report also
contains a `native` dictionary. Treat that dictionary as diagnostic detail; use
the top-level keys in tests and docs.

## Fallback Matrix

| Public operation or state | Typical path | Cost boundary | Preferred pattern |
| --- | --- | --- | --- |
| `background()`, `clear()`, basic primitives with `BLEND` | GPU-oriented draw | Low synchronization pressure | Keep normal style state for dense primitive loops. |
| Batched `line()` calls with same style/transform | Batched GPU-oriented draw | Low bridge overhead | Use `gs.fast()` or local method bindings in dense loops. |
| Non-`BLEND` blend modes | CPU compositing fallback | May read/merge/upload pixel regions | Use sparingly in animation hot loops; isolate blended layers when possible. |
| `erase()` / `no_erase()` drawing | CPU compositing fallback | Requires alpha-modifying pixel work | Prefer normal alpha drawing unless erasure semantics are required. |
| Loaded images drawn unchanged | Cached texture path | First draw uploads, later draws reuse | Reuse `Image` objects and avoid per-frame mutation. |
| Mutated images drawn each frame | Texture upload path | Uploads changed image data | Batch mutations or draw with primitives when possible. |
| Rotated/scaled images | GPU texture path when cached; CPU fallback when unsupported | First texture upload, then draw cost | Reuse images; avoid changing pixels while transforming. |
| Text drawing and metrics | Native text/cache path | First glyph/metric use is expensive | Reuse text strings/styles where practical. |
| `load_pixels()` / `pixels()` | Readback plus list conversion | Synchronizes canvas data and allocates Python list | Use `load_pixel_bytes()` for bytes workflows. |
| `update_pixels()` | Full pixel upload | Sends entire physical RGBA buffer | Use bytes-like inputs and avoid per-frame full-canvas uploads. |
| `get()`, `set()`, canvas `filter()` | CPU compositing fallback | Canvas-to-image copy plus upload | Prefer renderer-native drawing or image-local work. |

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

1. Build the current canvas extension:

   ```sh
   uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --module-name gummysnake.rust._canvas --python-source src --features extension-module
   ```

2. Run an interactive sketch with pacing diagnostics enabled in setup:

   ```python
   def setup():
       gs.create_canvas(720, 480)
       gs.enable_frame_pacing_diagnostics()
   ```

3. Exercise `loop()`, `no_loop()`, `redraw()`, resize the window if supported,
   and move/press input devices for at least 30 seconds.

4. Inspect `frame_pacing_diagnostics()` after closing or through a debug print.
   Check that input remains responsive, idle sketches do not busy-wait, and
   frame intervals are close to the target frame rate except during intentional
   resize or heavy rendering work.

5. If frame intervals drift upward, compare renderer counters for readback,
   upload, CPU fallback, and text/image cache misses before changing scheduling
   thresholds.

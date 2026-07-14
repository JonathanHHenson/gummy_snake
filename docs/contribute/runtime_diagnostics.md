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
| `pixel_readback_requested_bytes` / `pixel_readback_copied_bytes` | RGBA bytes callers requested and bytes copied into the returned readback buffer. They distinguish a small requested region from the amount actually returned without estimating hidden GPU work. |
| `pixel_uploads` | Full pixel or texture uploads back to the canvas. |
| `gpu_blend_commands` | Non-default blend commands that stayed in the GPU command stream. |
| `gpu_region_effect_passes` | Bounded GPU region-effect passes, such as internal pixel-prefix mutation. |
| `image_cache_hits` / `image_cache_misses` | Bounded legacy image-cache reuse or insertion. Rust `CanvasImage` entries retain shared immutable payload ownership rather than cloning RGBA bytes. |
| `image_source_clones_avoided` / `image_source_clone_bytes_avoided` | Full RGBA source clones avoided when ordered batches and cache entries retain shared Rust image payloads. |
| `image_cache_resident_bytes` / `image_cache_peak_bytes` | Current and peak logical RGBA bytes retained by the bounded CPU image cache. Shared `Arc` payloads are counted once per cache entry even when the canonical handle also owns the same allocation. |
| `image_cache_evictions` / `image_cache_evicted_bytes` | CPU image-cache entries and logical payload bytes released to satisfy count or byte limits. |
| `texture_cache_hits` / `texture_uploads` | Native texture reuse or upload, including canvas-managed image handles and the existing ordered image atlas path. |
| `texture_upload_bytes` / `texture_dirty_uploads` | RGBA bytes uploaded and uploads caused by an existing stable texture key advancing to a new image/atlas generation. |
| `texture_resident_bytes` / `texture_peak_bytes` | Current and peak GPU RGBA texture bytes tracked by the bounded texture cache. |
| `texture_cache_evictions` / `texture_destructions` | Texture-cache evictions and actual resources removed/replaced in the GPU texture map. Resources referenced by pending ordered commands remain frame-pinned until a later safe eviction opportunity. |
| `image_atlas_resident_bytes` / `image_atlas_peak_bytes` | Current and peak bytes belonging to textures produced by the single ordered image/text atlas path. |
| `image_atlas_evictions` / `image_atlas_destructions` | Atlas entries evicted and actual atlas GPU resources removed or replaced. |
| `text_cache_hits` / `text_cache_misses` | Text metric or glyph cache reuse. |
| `text_cache_evictions` | Bounded text or text-metric cache entries evicted during dynamic text churn. |
| `text_measurements` | Native text measurement calls. |
| `bridge_calls` | Python-to-canvas bridge calls made by the adapter. |
| `frames_presented` | Frames presented by the renderer/backend. |
| `gpu_frames_rendered` | Offscreen GPU frame resolves. |
| `event_polls` | Native input/event polling calls. Interactive execution performs one poll at the start of each tick; drawing and presentation do not add opportunistic polls. |
| `direct_model_draws` | Rust-owned model-handle draws that avoid Python face dictionaries; GPU builds use retained model buffers and built-in model pipelines. |
| `python_face_payloads` | Legacy/fallback shaded-face payloads materialized as Python dictionaries. |
| `direct_shape_finalizations` | Rust-owned `begin_shape()` buffers finalized directly into draw or clip operations. |
| `shape_buffer_extractions` | Shape buffers extracted into Python lists for compatibility fallback paths. |
| `pixel_payload_copies` | Pixel uploads that required Python list/sequence conversion before reaching the runtime. |
| `pixel_noop_upload_skips` | Full-canvas byte payload uploads skipped because they were the exact fresh `load_pixel_bytes()` result. |
| `primitive_batch_records` | Python-side primitive records flushed through compact fill, current-state, or mixed primitive batch bridges. |
| `primitive_batch_flushes` | Python-side compact primitive batch bridge calls. |
| `primitive_batch_max_records` | Largest primitive batch flushed in the current counter window; low values in dense scenes usually indicate accidental segmentation. |
| `primitive_batch_fallbacks` | Primitive records replayed through legacy per-shape calls because the native batch ABI was unavailable. |
| `image_batch_records` | Python-side image records flushed through compact image batch bridges, including transformed sprite records. |
| `image_batch_flushes` | Python-side compact image batch bridge calls. |
| `image_batch_max_records` | Largest image batch flushed in the current counter window; sprite fields should usually coalesce into large batches. |
| `image_batch_fallbacks` | Image records replayed through legacy per-image calls because the native batch ABI was unavailable. |

When the installed Rust canvas exposes native counters, the Python report also
contains a `native` dictionary. Treat that dictionary as diagnostic detail; use
the top-level keys in tests and docs. Image ownership, texture upload, byte
residency, eviction, and destruction counters listed above are promoted from the
native report to those stable top-level keys.

Native diagnostics may also include GPU render-loop counters:
`gpu_vertex_buffer_allocations`, `gpu_vertex_uploads`, `gpu_primitive_batches`,
`gpu_uploaded_vertex_bytes`, `gpu_image_batches`, `gpu_encode_time_ms`,
`gpu_present_time_ms`, `gpu_command_clone_count`, `gpu_command_clone_bytes`, and
`gpu_command_segment_allocation_count`. The three command-stream allocation
counters should remain zero on normal borrowed-range encoding and retained
replay paths; a nonzero value indicates that full-stream cloning or owned
command-segment materialization has been reintroduced. Native command-stream
diagnostics include
`native_draw_commands`, `native_triangle_commands`, `native_ellipse_commands`,
`native_image_commands`, `native_text_commands`, `native_model_commands`,
`native_erase_commands`, `native_region_effect_commands`,
`native_primitive_instance_commands`, `native_staged_primitive_vertices`,
`native_staged_image_vertices`, `native_primitive_records`,
`native_primitive_batches`, `packed_primitive_records`,
`packed_primitive_bytes`, and `native_command_ingest_time_ms`. Packed primitive
records use ABI-19 fixed-width little-endian layouts: 32-byte lines, 56-byte
styled/current primitive records, 60-byte fill records, and 64-byte mixed
records with `u32` style/matrix side-table indices. Pixel pipeline
diagnostics include `gpu_pixel_readbacks`, `pixel_bytes_created`,
`pixel_readback_requested_bytes`, `pixel_readback_copied_bytes`,
`pixel_noop_upload_skips`, `pixel_full_uploads`, and `pixel_region_uploads`.
Retained reuse diagnostics include `retained_batch_cache_hits`,
`retained_batch_cache_misses`, `retained_batch_cache_evictions`, and
`retained_batch_reused_bytes`.
Allocations should grow with peak frame demand rather than with every frame;
uploads and batches track actual draw work. Use max-record counters together
with flush counters: a recovered dense primitive or sprite scene should show a
small number of flushes and a large largest-batch value, not one flush per local
style or transform change.

Use these counters after representative bounded or interactive runs to correlate
renderer work with observed behavior. Keep `python_bridge_calls` and
`native_bridge_calls` separate when triaging adapter dispatch and Rust command
ingest. Normal interactive frames should keep `pixel_readbacks` at zero unless
user code calls an explicit readback or export API. Sprite- and text-heavy
stress scenes should show texture-cache and text-cache reuse after their first
unique layouts have been shaped.

## Synth Diagnostics

Use the synth-scoped diagnostics around bounded offline work:

```python
from gummysnake import synth as sy

sy.configure_workers("auto")  # or 1, 2, 4, 8
sy.reset_synth_diagnostics()
# compile, render, decode, or save
report = sy.synth_diagnostics()
```

`worker_count` is the resolved active-task limit, `worker_mode` distinguishes
explicit and automatic selection, and `worker_pool_capacity` is the fixed bound on
the one process-wide persistent pool. `worker_pool_initializations` is a lifetime
counter and must never exceed one. `gil_released_*` counters identify validated
pure-Rust compile, render, decode, and WAV-write calls that ran outside the Python
GIL. `parallel_regions`, `parallel_tasks`, and `parallel_events` describe profitable
independent dry-event work; `serial_events` includes small or dependency-ineligible
events. `parallel_scratch_peak_bytes` must not exceed
`parallel_scratch_limit_bytes`, and `parallel_min_scratch_bytes` records the current
threshold used to avoid scheduling tiny regions.

Diagnostics are process-wide and intended for tests and benchmark metadata.
Worker selection affects only performance: indexed event outputs are reduced in
stable event/FX order. Realtime/device window rendering is not counted as parallel
work because it remains serial until deadline-safe behavior is separately
qualified.

## ECS Diagnostics

Use `ecs_diagnostics()` after ECS frames to inspect scheduler, physical-plan,
ambiguity, resource/event, UDF, and spatial behavior:

```python
gs.reset_ecs_diagnostics()
# run frames
report = gs.ecs_diagnostics()
```

Common stable counters include:

| Counter | Meaning |
| --- | --- |
| `ecs_systems_registered` / `ecs_systems_enabled` | Current schedule surface. |
| `ecs_schedule_rebuilds` | System registration, removal, enable state, dependencies, or group configuration changed schedule ordering. |
| `ecs_system_frame_runs` | ECS group phases executed on drawn frames. This should advance with drawn frames. |
| `ecs_canvas_commands` | Canvas draw commands emitted by Rust-executed ECS systems and replayed into the canvas runtime. |
| `ecs_physical_plan_compiles` | Logical action trees serialized and compiled into Rust physical plans. |
| `ecs_steady_physical_plan_reuses` / `ecs_dynamic_change_plan_recompiles` | Cached plan reuse versus current Python `allowed_entities` recompilation for change-filtered plans. The dynamic counter remains a migration gap until Rust change journals own those filters. |
| `ecs_rust_compiled_plans` | Rust physical-plan handles cached by the world. |
| `ecs_physical_system_runs` | Non-UDF systems executed through Rust physical plans. It should advance when validating a Rust-executed hot path. |
| `ecs_physical_rows_scanned` | Rows scanned by the Rust physical executor. |
| `ecs_physical_fields_written` / `ecs_physical_resource_fields_written` | Component/resource field writes performed by Rust physical execution. |
| `ecs_physical_plan_errors` / `ecs_physical_execution_errors` | Unsupported or failing non-UDF plans. These should fail loudly; they must not fall back to Python execution. |
| `ecs_udf_calls` | Explicit Python UDF action or iterable-source invocations. These are flexibility boundaries, not accelerated work. |
| `ecs_ambiguity_warnings` / `ecs_ambiguity_warnings_suppressed` | Deterministic last-write-wins situations in non-strict mode. Suppression only hides logs; diagnostics still count. |
| `ecs_strict_mode_errors` | Duplicate/ambiguous writes rejected in strict mode. |
| `ecs_events_emitted` / `ecs_events_read` | Canonical Rust-owned typed event records emitted/read. |
| `ecs_event_records_total` / `ecs_event_records_pruned` / `ecs_event_records_cleared` | Current Rust queue size and lifecycle removals. |
| `ecs_python_event_mirror_entries` / `ecs_python_event_payload_materializations` | Prohibited Python event paths; both remain zero. |
| `ecs_diagnostic_messages_deduplicated` / `ecs_diagnostic_messages_dropped` | Repeated messages and unique messages evicted from the bounded Rust store. Exact warning/error counters are unaffected. |
| `ecs_entities_alive` / `ecs_rust_entities_alive` | Public and Rust-side live entity counts; these should agree. |
| `ecs_spatial_indexes_built` / `ecs_spatial_index_reuses` | Rust spatial-index construction and reuse. |
| `ecs_spatial_candidate_rows` / `ecs_spatial_exact_rows` / `ecs_spatial_false_positive_rows` | Broad-phase and exact-filter spatial relation shape. |
| `ecs_spatial_deduplicated_pairs` | Self-pairs skipped by unique unordered pair policies. |
| `ecs_spatial_algorithm_hash_grid`, `ecs_spatial_algorithm_quadtree`, `ecs_spatial_algorithm_octree`, `ecs_spatial_algorithm_hilbert_curve` | Per-algorithm Rust spatial index usage. |
| `ecs_spatial_parallel_workers` / `ecs_spatial_parallel_chunks` | Parallel spatial execution shape where the runtime used worker chunks. |

The public snapshot exposes canonical Rust values as both `ecs_<name>` and
`ecs_rust_<name>` while Python lifecycle/UDF boundary counters retain their existing
`ecs_*` names. `reset_ecs_diagnostics()` resets Rust counters/messages and Python-only
boundary counters without clearing event data, entities, resources, plans, or caches.
Core storage counters include entity generation reuse, query cache refreshes, matched
archetypes/rows, resources, and event queue totals.

When debugging a system, start with `system.explain()` to inspect the action tree
and relation/aggregate shape, then compare diagnostics before and after a small
bounded run. Ambiguity counters indicate deterministic last-write-wins behavior;
strict mode turns those into plan errors. Unsupported non-UDF plan nodes should
raise during Rust physical-plan compilation rather than running a Python fallback.
Python constructs logical plans and explicit UDF boundaries; Rust owns canonical
ECS storage and compiled physical execution.

## Primitive Batch Boundaries

The Python canvas adapter may queue simple `rect()`, `triangle()`, `ellipse()`, 
`circle()`, and compatible `line()` calls into compact primitive batches when a
native batch ABI is available. The current preferred path is a mixed primitive
batch that carries each record's kind, coordinates, resolved style, and 2D
affine transform so small local style/matrix changes do not force one bridge
call per shape. Queues are ordered; switching between primitive, line, text,
image, pixel, clip, background/clear, state stack, resize, frame-end, present,
close, 3D/model, or CPU fallback paths must flush pending batches before
continuing.

Fill-only compact primitive batches use the procedural GPU path when all
records can be represented as rect, triangle, or axis-aligned ellipse
instances. The shader expands each record to a quad on the GPU and applies
analytic triangle or ellipse coverage in the fragment stage, avoiding per-frame
CPU generation of rectangle vertices or 64-segment ellipse meshes. Mixed batches
may combine fill-only, stroked, fill+stroke, and line records and use procedural
instances where possible while falling back to vertex-expanded records for cases
that require it. Rotated or sheared rectangles/ellipses keep the existing vertex
fallback so transformed output remains correct.

Image draws may similarly queue through `batch_canvas_images_transformed` or the
older matrix-grouped `batch_canvas_images` bridge. The transformed path carries
each sprite's own affine matrix, destination rectangle, optional source
rectangle, tint/sampling/blend style, and Rust image handle, so sketches that use
`with pushed(): translate(); rotate(); image(...)` can still produce one large
ordered batch. The Rust runtime can pack small compatible image batches into an
internal atlas texture so alternating sprites from a small texture set remain
ordered while avoiding one GPU image batch per sprite. Internal stress paths may
use compact binary sprite records for repeated image handles and motion terms so
dynamic sprite batches avoid per-sprite Python tuple allocation while preserving
the public image API.

Text batching is also layered. Direct glyphon/cosmic-text rendering is used for
untransformed default-font text when ordering permits a contiguous text segment.
Large overlays or later text after intervening images/primitives/effects should
use the cached line-texture path, but those cached line images can now be packed
into ordered atlas-backed image batches instead of one texture draw/upload per
label. `text_widths()` should use the batch metric path for shared style rather
than one bridge call per string.

Retained reuse is layered. Static compact primitive batches keep a retained
native batch key and replay shared instance/vertex payloads after warmup.
Static full-frame image or mixed image/primitive command streams are reused by
the GPU renderer when the ordered command stream and clip generation are
unchanged; resize and pixel-density changes invalidate that retained replay and
increment eviction diagnostics when a previous retained stream existed. Dynamic
image batches continue through the atlas/upload path and report texture and
image batch counters normally.

## GPU Region Effects

GPU region effects are internal renderer operations that snapshot the current
canvas texture into a temporary texture, run a bounded shader pass, and write
the result back to the canvas texture without mapping pixels into CPU memory.
They preserve draw order by resolving pending draw commands before the effect
and then continuing future commands against the updated canvas texture.

The current region-effect framework reports through `gpu_region_effect_passes`.
That path should not increment
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
| Loaded images drawn unchanged | Cached texture path with transformed image batching when sprites share compatible style | First draw uploads, later draws reuse; batches carry per-record transform/source data | Reuse `Image` objects and avoid per-frame mutation. |
| Mutated images drawn each frame | Texture upload path within ordered image batches | Uploads changed image data while preserving batch shape for unchanged sprites | Batch mutations or draw with primitives when possible. |
| Rotated/scaled images | GPU texture/atlas path when cached; CPU fallback when unsupported | First texture upload, then draw cost; transformed batches avoid one flush per local matrix | Reuse images; avoid changing pixels while transforming. |
| Text drawing and metrics | Glyphon-backed GPU text path for untransformed default-font text when direct text remains one contiguous ordered segment; batched cached line-texture atlas fallback for later text or large overlays; Rust metric cache, bulk text calls, and repeated clear+text frame reuse | First unique glyph/layout use is expensive; mixed text/primitive/text ordering may switch later text to the line-texture atlas path to avoid multiple mutable glyphon atlas passes | Reuse text strings/styles, prefer `text_batch()` / `text_widths()` for dense overlays, and validate text before and after primitives/images when changing renderer batching. |
| `load_pixels()` / `pixels()` | Readback into `PixelBuffer` plus list-compatible access | Synchronizes canvas data and allocates a mutable Python buffer wrapper | Use `load_pixel_bytes()` for bytes workflows; keep dirty `PixelBuffer` edits row-aligned when uploading back. |
| `load_pixel_bytes()` | Byte readback | Synchronizes canvas data but does not populate `context.pixels` | Keep data as `bytes`/`memoryview` and pass it back to bulk APIs when possible. |
| `update_pixels()` | Full or dirty-region pixel upload | Buffer-like inputs reach Rust through the Python buffer protocol; list inputs are copied for compatibility | Use `bytes`, `bytearray`, `memoryview`, or the `PixelBuffer` returned by `load_pixels()`; prefer dirty row-aligned updates over full-canvas uploads. |
| `get()`, `set()`, canvas `filter()` | CPU compositing fallback | Canvas-to-image copy plus upload | Prefer renderer-native drawing or image-local work. |
| `begin_shape()` / `end_shape()` and clip paths | Rust shape-buffer finalization | Normal canvas paths avoid Python vertex-list extraction | Keep shape construction in the captured shape APIs; use diagnostics to catch fallback extraction. |
| WEBGL model drawing | Rust-owned model handles; unstroked built-in primitive/model draws use retained GPU vertex/index buffers with GPU transform/projection/depth/material/texture pipelines when GPU drawing is available | First draw may upload model buffers and textures; fallback projected points are logical coordinates and direct GPU primitive fallback must scale by `pixel_density()` | Reuse primitive/model and image objects so retained buffers and texture caches stay hot. |
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
   and move/press input devices for at least 30 seconds. Include sketches that
   draw text before primitives/images and then draw later text again, such as
   `examples/04_text/typography_accessibility.py`, to validate mixed text and
   primitive/image ordering.

4. Inspect `frame_pacing_diagnostics()` after closing or through a debug print.
   Check that input remains responsive, close requests are observed, idle
   sketches do not busy-wait, primitives drawn after text/images remain visible,
   and frame intervals are close to the target frame rate except during
   intentional resize or heavy rendering work.

5. If frame intervals drift upward, compare renderer counters for readback,
   upload, CPU fallback, and text/image cache misses before changing scheduling
   thresholds.

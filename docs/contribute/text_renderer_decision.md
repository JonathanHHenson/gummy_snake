# Text Renderer Decision

Gummy Snake should migrate text rendering to a mature Rust GPU text stack rather
than hand-rolling shaping, atlas packing, and glyph batching.

## Decision

Use `glyphon`, backed by `cosmic-text`, for the Rust canvas GPU text path.

`glyphon` is the best fit because it already owns the hard parts Gummy Snake
needs to stop maintaining locally:

- shaping and layout through `cosmic-text`
- a GPU glyph atlas
- `wgpu` device and queue integration
- batched text rendering
- font system integration that can work in headless/offscreen renderers

The public Python API should not expose `glyphon` or `cosmic-text` types. Python
continues to call `text()`, `text_width()`, `text_ascent()`, `text_descent()`,
and font/style setters through `SketchContext` and `CanvasRenderer`; the Rust
canvas runtime owns the layout cache, glyph atlas, metrics, and draw batches.

## Compared Options

| Option | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| `glyphon` / `cosmic-text` | Mature shaping, atlas, `wgpu` integration, batched draws, active ecosystem | Adds dependencies and requires careful adapter work around offscreen targets and deterministic tests | Selected |
| Current `ab_glyph` bitmap path | Small dependency surface, already integrated, deterministic for simple Latin text | No full shaping engine, line textures upload too often, atlas/batching would become custom renderer work | Keep only as migration fallback while `glyphon` lands |
| Custom atlas over `ab_glyph` | Lowest conceptual dependency churn | Still hand-rolls shaping gaps, atlas eviction, batching, and metrics consistency | Reject |

## Integration Plan

1. `glyphon 0.9` is integrated in `gummy_canvas` because it matches the current
   `wgpu 25` renderer.
2. The GPU renderer owns the `FontSystem`, `SwashCache`, `TextAtlas`,
   `TextRenderer`, viewport, and shaped text buffer cache.
3. Untransformed default-font text commands use glyphon batches that preserve
   ordering with primitives, images, erase, blend shader passes, and region
   effects.
4. The existing cached line-texture path remains as the internal fallback for
   custom font paths, transformed text, clips, erasing, and other unsupported
   cases.
5. Metrics remain Rust-owned and cached. Default text drawing and cached glyph
   rendering share the Rust runtime boundary, while future work can route all
   custom-font metrics through glyphon once custom font registration is wired.

## Validation

Required validation for the migration:

- deterministic headless render tests for alignment, baseline, multiline text,
  font size, font path/name fallback, and HiDPI scaling
- Unicode shaping tests where suitable fonts are available in CI
- ordering tests for text before and after primitives/images
- `mixed_text_pixels` and `text_only` benchmark checks for reduced texture
  uploads and text/image batches
- export/readback tests proving saved PNGs match the offscreen render target

## Risks

The main risks are binary size, platform font discovery differences, and
determinism across machines. Gummy Snake should treat bundled or explicitly
loaded fonts as the deterministic test surface and document platform font
fallback as environment-dependent unless a stable bundled fallback font is
introduced.

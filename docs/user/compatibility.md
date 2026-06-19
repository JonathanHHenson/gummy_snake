# Compatibility and Pythonic differences

`p5-py` borrows p5's sketching model while intentionally presenting an opinionated Pythonic API rather than a browser-compatible API surface.

## Naming

Public APIs use `snake_case` only:

- `create_canvas()`
- `frame_rate()`
- `no_loop()`
- `pixel_density()`

p5.js-style camelCase aliases such as `createCanvas()`, `frameRate()`, `noLoop()`, and `pixelDensity()` are intentionally not exported.

## Same ideas, different runtime

Expected differences from browser p5.js include:

- no DOM helpers
- no HTML elements
- no browser event loop
- no browser fetch/storage assumptions
- Python exceptions instead of loose browser-style failures

## Unsupported and excluded APIs

The package intentionally excludes browser-only areas such as:

- DOM element helpers such as `create_div()` and `create_button()`
- DOM form/file-input helpers such as `create_input()`, `create_slider()`, `create_select()`, and `create_file_input()`
- `p5.XML`
- `p5.Table` and `p5.TableRow`
- browser Blob/client-side-save, URL, and storage helpers
- browser pointer lock
- browser-only APIs with no native Python equivalent

These compatibility stubs raise explicit `p5` exceptions so unsupported features fail clearly.

Device sensors, advanced shader variants, WebGPU/storage-buffer/compute APIs, sound analysis/synthesis, and audio capture are deferred rather than silently omitted. The exported snake_case stubs raise `UnsupportedFeatureError` until a native Python or Rust canvas runtime design exists.

Text metrics use the native canvas runtime for `text_width()`, ascent/descent, and bounds helpers. Repeated measurements are cached per renderer with a bounded cache. Font outline/path helpers such as `Font.text_to_points()`, `Font.text_to_paths()`, `Font.text_to_contours()`, and `Font.text_to_model()` are explicit deferred APIs until native font shaping and outline extraction are available.

## Migration guidance

When porting small p5.js sketches:

1. keep the `setup()`/`draw()` structure
2. switch imports to `import p5`
3. convert p5.js-style camelCase calls to p5-py's snake_case API
4. replace browser/DOM code with native Python alternatives or remove it
5. use `headless` for deterministic tests while porting

See `tests/unit/test_compatibility.py` for representative compatibility expectations.

# New Rust canvas backend examples

These examples exercise the experimental `backend="canvas"` Rust renderer introduced for the `p5_canvas` backend work.

With the native runtime bridge built, running these examples with no `--frames` limit opens an interactive Rust-backed window. Passing `--frames N` keeps the older bounded offscreen/export path.

The canvas backend currently supports an interactive and headless/offscreen P2D subset:

- canvas sizing and pixel density
- `background()` and `clear()`
- `point()`, `line()`, `rect()`, `triangle()`, `quad()`, `circle()`, `ellipse()`, and `arc()`
- fill, stroke, stroke weight, transforms, and `BLEND` compositing
- `load_pixels()`, `update_pixels()`, and `save_canvas()`

It now provides a native `winit` + `softbuffer` interactive window/event-loop layer, but it still does not yet support text, images, arbitrary blend modes, or WEBGL.

Build the Rust extension before running these examples with `backend="canvas"`:

```sh
uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml
```

Run interactively:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py
uv run python examples/new_rust_backend/canvas_transforms_density.py
uv run python examples/new_rust_backend/canvas_pixels_export.py
```

Run bounded offscreen/export passes:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py --frames 1
uv run python examples/new_rust_backend/canvas_transforms_density.py --frames 1
uv run python examples/new_rust_backend/canvas_pixels_export.py --frames 1
```

For comparison against the Pillow/headless renderer, pass `--backend headless`:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py --backend headless --frames 1
```

Each example saves a PNG by default when run with a bounded frame count. Output is written under `examples/output/new_rust_backend/`.

Interactive runs do not save by default unless you also pass a finite `--frames` value.

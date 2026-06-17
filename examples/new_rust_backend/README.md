# New Rust canvas backend examples

These examples exercise the experimental `backend="canvas"` Rust renderer introduced for the `p5_canvas` backend work.

The canvas backend currently supports a headless/offscreen P2D subset:

- canvas sizing and pixel density
- `background()` and `clear()`
- `point()`, `line()`, `rect()`, `triangle()`, `quad()`, `circle()`, `ellipse()`, and `arc()`
- fill, stroke, stroke weight, transforms, and `BLEND` compositing
- `load_pixels()`, `update_pixels()`, and `save_canvas()`

It does not yet support interactive windows, text, images, arbitrary blend modes, or WEBGL.

Build the Rust extension before running these examples with `backend="canvas"`:

```sh
uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml
```

Run examples:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py --frames 1
uv run python examples/new_rust_backend/canvas_transforms_density.py --frames 1
uv run python examples/new_rust_backend/canvas_pixels_export.py --frames 1
```

For comparison against the Pillow renderer, pass `--backend headless`:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py --backend headless --frames 1
```

PNG output is written under `examples/output/new_rust_backend/`.

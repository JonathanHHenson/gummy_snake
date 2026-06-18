# New Rust canvas backend examples

These examples exercise the experimental `backend="canvas"` Rust renderer introduced for the `p5_canvas` backend work.

With the native runtime bridge built, running these examples with no `--frames` limit opens an interactive Rust-backed window. Passing `--frames N` keeps the older bounded offscreen/export path.

The canvas backend currently supports an interactive and headless/offscreen P2D subset:

- canvas sizing and pixel density
- `background()` and `clear()`
- `point()`, `line()`, `rect()`, `triangle()`, `quad()`, `circle()`, `ellipse()`, and `arc()`
- fill, stroke, stroke weight, transforms, and advertised 2D blend modes
- image drawing, source cropping, destination scaling, and text rendering/metrics
- `load_pixels()`, `update_pixels()`, and `save_canvas()`
- WEBGL-mode software-projected 3D primitives, model drawing, materials/lights, and shader
  object/uniform APIs rendered through the canvas GPU-backed 2D path

It now provides a native `winit` + `wgpu` interactive window/event-loop layer. Canvas WEBGL support currently uses the established software-projected 3D path and presents through the Rust canvas renderer; a Rust-native 3D pipeline remains a later optimization milestone.

Build the Rust extension before running these examples with `backend="canvas"`:

```sh
uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml
```

Run interactively:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py
uv run python examples/new_rust_backend/canvas_transforms_density.py
uv run python examples/new_rust_backend/canvas_pixels_export.py
uv run python examples/new_rust_backend/canvas_assets_text.py
uv run python examples/new_rust_backend/canvas_blend_erase.py
uv run python examples/new_rust_backend/canvas_asteroids.py
uv run python examples/new_rust_backend/canvas_webgl_primitives.py
uv run python examples/new_rust_backend/canvas_webgl_shader.py
```

Run bounded offscreen/export passes:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py --frames 1
uv run python examples/new_rust_backend/canvas_transforms_density.py --frames 1
uv run python examples/new_rust_backend/canvas_pixels_export.py --frames 1
uv run python examples/new_rust_backend/canvas_assets_text.py --frames 1
uv run python examples/new_rust_backend/canvas_blend_erase.py --frames 1
uv run python examples/new_rust_backend/canvas_asteroids.py --frames 1
uv run python examples/new_rust_backend/canvas_webgl_primitives.py --frames 1
uv run python examples/new_rust_backend/canvas_webgl_shader.py --frames 1
```

For comparison against the Pillow/headless renderer, pass `--backend headless`:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py --backend headless --frames 1
```

Run the interactive WEBGL canvas-versus-Pyglet benchmark with:

```sh
uv run pytest tests/benchmark/test_canvas_webgl_backend_perf.py --run-benchmarks -s
```

Each example saves a PNG by default when run with a bounded frame count. Output is written under `examples/output/new_rust_backend/`.

Interactive runs do not save by default unless you also pass a finite `--frames` value.

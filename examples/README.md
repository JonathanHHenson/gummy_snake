# Gummy Snake examples

These examples are grouped by feature area and all use the current canvas-first runtime.
Examples in `10_ecs` also use the Rust-owned ECS runtime for entity/component
storage, system execution, resources, events, and spatial queries before drawing.

New examples prefer Pythonic Gummy Snake conveniences: decorator callbacks
(`@gs.setup`, `@gs.draw`, `@gs.on(...)`), property facades such as
`gs.current` and `gs.mouse`, context managers such as `gs.style(...)` and
`gs.transform(...)`, and awaitable asset helpers from async callbacks.
Older examples may still pass callbacks directly to `gs.run(...)`; both forms
are supported.

Run any sketch interactively:

```sh
uv run python examples/01_getting_started/basic_shapes.py --interactive
```

Run a bounded headless preview and save an output image:

```sh
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
```

Most examples save to `examples/output/` when `--frames` is provided. Pass `--no-save` to skip image export.

## Groups

- `01_getting_started`: first sketches, timing, and drawing basics.
- `02_drawing`: primitives, curves, transforms, color, compositing, and pixels.
- `03_assets`: images, generated images, data files, sound metadata, audio analysis/synthesis, offscreen graphics, framebuffers, and storage-buffer compute.
- `04_text`: text rendering, measurement, and accessibility descriptions.
- `05_interaction`: mouse, keyboard, touch state, device sensors, environment state, and lifecycle controls.
- `06_math`: vectors, random numbers, noise, mapping, and interpolation.
- `07_plugins`: plugin hook ordering and plugin-provided APIs.
- `08_3d`: WEBGL/WEBGPU-style primitives, cameras, projections, lights, materials, geometry, model loading, and textures.
- `09_performance`: dense 60 FPS load showcases, particle-force attractors, ECS-backed 3D boids, and retained 3D performance sketches.
- `10_ecs`: Rust ECS examples with dataclass components/resources, ordered systems, typed entity views, and spatial joins.
- `games`: small sprite-based games using the included assets.

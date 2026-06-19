# p5-py examples

These examples are grouped by feature area and all use the current canvas-first runtime.

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
- `03_assets`: images, generated images, data files, and sound asset metadata.
- `04_text`: text rendering, measurement, and accessibility descriptions.
- `05_interaction`: mouse, keyboard, touch state, and lifecycle controls.
- `06_math`: vectors, random numbers, noise, mapping, and interpolation.
- `07_plugins`: plugin hook ordering and plugin-provided APIs.
- `08_3d`: current WEBGL primitives, lights, materials, model loading, and textures.
- `games`: small sprite-based games using the included assets.

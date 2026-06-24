# Examples

Examples live in [../../examples](../../examples).

Useful starting points:

- `examples/01_getting_started/basic_shapes.py`
- `examples/01_getting_started/timing_and_animation.py`
- `examples/02_drawing/shapes_curves.py`
- `examples/02_drawing/contours_clipping_tint_export.py`
- `examples/02_drawing/transforms_and_modes.py`
- `examples/02_drawing/pixels_and_export.py`
- `examples/03_assets/data_files.py`
- `examples/03_assets/images_and_sprites.py`
- `examples/05_interaction/input_state.py`
- `examples/08_3d/webgl_scene.py`
- `examples/09_performance/sixty_fps_load_showcase.py`
- `examples/09_performance/lorenz_attractor_3d.py`
- `examples/games/asteroids.py`

The first sketch, asset, interaction, and transform examples show the preferred
Pythonic APIs: decorators, async loaders, property facades, and context
managers.
The performance examples are good starting points when you want to see dense
public drawing loops using `gs.fast()`, internal primitive batching, sprite
batching, or retained WEBGL model drawing while targeting 60 FPS.

Run an example interactively:

```sh
uv run python examples/01_getting_started/basic_shapes.py --interactive
```

Run a bounded headless preview:

```sh
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
```

Most examples save output to `examples/output/` when `--frames` is provided.
Pass `--no-save` to skip image export.

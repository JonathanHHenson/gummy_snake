# p5-py examples

These examples are Python-only sketches using the current p5-py MVP API.

Run an interactive sketch with the default Pyglet backend:

```sh
uv run python examples/basic_shapes.py
```

Run an example without opening a window:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
```

Export examples save PNG files when run headlessly or when their draw loop reaches the configured frame count.

## Examples

- `basic_shapes.py` demonstrates canvas creation, colors, fills, strokes, primitives, arcs, and export.
- `bouncing_ball.py` demonstrates animation state, frame drawing, and simple physics.
- `transforms.py` demonstrates `push`, `pop`, `translate`, `rotate`, `scale`, and angle mode.
- `custom_shape.py` demonstrates `begin_shape`, `vertex`, `quadratic_vertex`, `bezier`, and shape export.

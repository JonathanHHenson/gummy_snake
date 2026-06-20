# Canvas and Drawing

## Background and Clearing

- `background(*color)`
- `clear()`

## 2D Primitives

- `point(x, y)`
- `line(x1, y1, x2, y2)`
- `rect(x, y, width, height=None)`
- `square(x, y, size)`
- `ellipse(x, y, width, height=None)`
- `circle(x, y, diameter)`
- `triangle(x1, y1, x2, y2, x3, y3)`
- `quad(x1, y1, x2, y2, x3, y3, x4, y4)`
- `arc(...)`

`point`, `line`, `triangle`, and `quad` also accept vector-like point objects:

```python
gs.line(gs.Vector(10, 20), gs.Vector(90, 80))
gs.triangle(a, b, c)
```

For dense loops, bind the frame-local fast facade once and call its strict
coordinate methods:

```python
def draw():
    gs.background(245)
    draw_fast = gs.fast()
    for x, y, dx, dy in vectors:
        draw_fast.line(x, y, x + dx, y + dy)
```

`fast()` keeps current public style and transform state, including surrounding
`style()`, `transform()`, and `pushed()` context managers. It skips global-mode
context lookup and flexible vector-like argument normalization, so it is meant
for hot loops rather than as the only style for simple sketches.

## Paths and Curves

- `begin_shape(kind=None)`
- `vertex(x, y)`
- `bezier_vertex(...)`
- `quadratic_vertex(...)`
- `spline_vertex(...)`
- `end_shape(mode=None)`
- `bezier_point(...)`
- `bezier_tangent(...)`
- `spline_point(...)`
- `spline_tangent(...)`

## Images and Regions

- `image(img, x, y, width=None, height=None, ...)`
- `copy(...)`
- `get(...)`
- `set(...)`

## Compositing

- `blend_mode(mode)`
- `blend(...)`
- `erase(alpha=255, detail_alpha=255)`
- `no_erase()`
- `filter(kind, value=None)`

## WEBGL-Style 3D

- `create_canvas(width, height, WEBGL)`
- `camera(...)`
- `perspective(...)`
- `ortho(...)`
- `ambient_light(...)`
- `directional_light(...)`
- `point_light(...)`
- `ambient_material(...)`
- `specular_material(...)`
- `normal_material()`
- `texture(image)`
- `plane(...)`
- `box(...)`
- `sphere(...)`
- `ellipsoid(...)`
- `cylinder(...)`
- `cone(...)`
- `torus(...)`
- `load_model(path, normalize=False)`
- `model(shape)`

Current WEBGL support is a deterministic Rust-backed software 3D path. It is useful
for small sketches, tests, examples, model loading, materials, lights, texture
coordinates, and Python API coverage, but it is not yet native accelerated
3D rendering. Backend capabilities distinguish `software_three_d` from
`native_three_d`; the canvas backend currently reports software 3D support.

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
- `shape(mode=OPEN, *, kind=None)`
- `begin_contour()`
- `contour()`
- `vertex(x, y)`
- `bezier_vertex(...)`
- `quadratic_vertex(...)`
- `spline_vertex(...)`
- `end_contour()`
- `end_shape(mode=None)`
- `bezier_point(...)`
- `bezier_tangent(...)`
- `spline_point(...)`
- `spline_tangent(...)`

Contours must be declared inside an active freeform shape after the outer path
has at least three vertices. Filled contours are treated as holes by the Rust
canvas runtime; invalid nesting raises `ArgumentValidationError`.

`shape()` and `contour()` are context-manager forms of the same path capture
API. `shape()` calls `begin_shape()` on entry and `end_shape(mode)` on normal
exit; `contour()` calls `begin_contour()` and `end_contour()`.

```python
with gs.shape(gs.CLOSE):
    gs.vertex(20, 20)
    gs.vertex(90, 20)
    gs.vertex(90, 90)
    gs.vertex(20, 90)
    with gs.contour():
        gs.vertex(44, 44)
        gs.vertex(66, 44)
        gs.vertex(66, 66)
        gs.vertex(44, 66)
```

## Clipping

- `begin_clip()`
- `clip_path()`
- `clip()`
- `end_clip()`

`begin_clip()` captures a path with the same `vertex()` and contour helpers as
`begin_shape()`. `clip()` applies that path to subsequent renderer-owned drawing
until `end_clip()` or until a surrounding `push()`/`pop()` restores the previous
clip stack. Older canvas runtimes that do not expose native clip operations raise
`BackendCapabilityError` with rebuild guidance.

`clip_path()` is the context-manager form for constructing and applying the clip
path. It calls `begin_clip()` on entry and `clip()` on normal exit; the active
clip still remains in force until `end_clip()`.

```python
with gs.clip_path():
    gs.vertex(30, 30)
    gs.vertex(140, 30)
    gs.vertex(140, 100)
    gs.vertex(30, 100)
gs.image(texture, 0, 0)
gs.end_clip()
```

## Images and Regions

- `image(img, x, y, width=None, height=None, ...)`
- `tint(*color)`
- `no_tint()`
- `copy(...)`
- `get(...)`
- `set(...)`

`tint()` applies a color and alpha multiplier when drawing images. It does not
mutate the source `Image`; bulk RGBA work stays inside the Rust canvas runtime.

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

Current WEBGL support is a deterministic Rust-backed software 3D path. It is
useful for small sketches, tests, examples, model loading, materials, lights,
texture coordinates, and Python API coverage, but it is not yet native
accelerated 3D rendering. Rust owns model handles, projection, shading, face
sorting, and rasterization; untextured shaded faces may use the GPU primitive
path when available. Backend capabilities distinguish `software_three_d` from
`native_three_d`; the canvas backend currently reports software 3D support.

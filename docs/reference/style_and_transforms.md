# Color, Style, and Transforms

## Color

- `color(*args)`
- `color_mode(mode, max1=None, max2=None, max3=None, max_alpha=None)`
- `lerp_color(start, stop, amount)`
- `red(color)`
- `green(color)`
- `blue(color)`
- `alpha(color)`
- `hue(color)`
- `saturation(color)`
- `brightness(color)`
- `lightness(color)`

## Style

- `fill(*color)`
- `no_fill()`
- `stroke(*color)`
- `no_stroke()`
- `stroke_weight(weight)`
- `stroke_cap(cap)`
- `stroke_join(join)`
- `rect_mode(mode)`
- `ellipse_mode(mode)`
- `image_mode(mode)`
- `smooth()`
- `no_smooth()`

Use `style()` to scope temporary style changes:

```python
with gs.style(fill=(255, 0, 0), stroke=None, stroke_weight=4):
    gs.circle(100, 100, 50)
```

## Transforms

- `push()`
- `pop()`
- `translate(x, y)`
- `rotate(angle)`
- `scale(x, y=None)`
- `shear_x(angle)`
- `shear_y(angle)`
- `reset_matrix()`
- `apply_matrix(...)`

Use `transform()` to scope temporary transforms:

```python
with gs.transform(translate=(200, 100), rotate=0.5, scale=1.2):
    gs.rect(0, 0, 80, 40)
```

`with gs.pushed():` remains available when you want to group arbitrary style and
transform calls manually.

## Text

- `text(value, x, y, width=None, height=None)`
- `text_batch(items)` where each item is `(value, x, y)`
- `text_size(size)`
- `text_font(font)`
- `text_align(horizontal, vertical=None)`
- `text_style(style)`
- `text_width(value)`
- `text_widths(values)`
- `text_ascent()`
- `text_descent()`
- `text_bounds(value, x=0, y=0)`
- `describe(text)`
- `describe_element(name, text)`

`describe()` and `describe_element()` record native accessibility metadata on
the active sketch context. They do not create DOM nodes. Headless tests can read
the metadata deterministically with `text_output()` and `grid_output()`, and
native windows may surface it through backend hooks as those capabilities are
added. Automatic shape summaries remain deferred until they can be implemented
as native metadata without adding overhead when disabled.

Use `text_batch()` and `text_widths()` for dense label overlays where many
strings share the current style and transform. They keep the Python API
Pythonic while reducing per-label dispatch overhead.

Text metrics use the active text style at the time they are called. For example,
`text_bounds(value, x, y)` returns bounds for the same size, font, and alignment
state that a following `text(value, x, y)` call will use unless your sketch
changes style in between. Headless and interactive rendering both preserve draw
order when text is mixed with shapes or images; the renderer may choose a GPU
text path or an internal cached line-texture fallback to keep the visible result
consistent.

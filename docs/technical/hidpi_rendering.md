# HiDPI and pixel-density rendering

p5-py uses a p5-style distinction between logical canvas coordinates and physical device pixels.

For example, on a Retina display, this sketch creates a logical canvas of `640 x 420`:

```python
create_canvas(640, 420)
```

If the active display density is `2`, the interactive Pyglet backend renders into a physical backing buffer of `1280 x 840` while preserving the logical p5 coordinate system. A call like this still uses logical coordinates:

```python
circle(320, 210, 100)
```

Internally, renderers scale drawing coordinates, transforms, images, pixel buffers, and stroke weights by the active pixel density before rasterizing or presenting. The Pyglet renderer uses native Pyglet drawing for normal frames and lazily switches to a physical-size parity surface for pixel/compositing workflows that require exact headless-backend semantics. See `docs/technical/native_pyglet_renderer.md`.

## APIs

```python
pixel_density()
pixel_density(2)
display_density()
```

p5.js-style aliases are also available:

```python
pixelDensity()
pixelDensity(2)
displayDensity()
```

## Backend behavior

- The headless backend defaults to pixel density `1` unless a sketch explicitly requests another density.
- The Pyglet backend defaults to the native window/display density when creating a canvas.
- `width()` and `height()` return logical canvas dimensions.
- The renderer tracks physical backing-buffer dimensions separately.
- `load_pixels()` and `update_pixels()` operate on the physical backing buffer, so the pixel list length is `logical_width * logical_height * pixel_density * pixel_density * 4` for RGBA data.
- `save_canvas()` exports the physical backing buffer, which keeps output sharp on HiDPI displays.

## Example

```python
from p5_py import *


def setup():
    create_canvas(640, 420)
    print(width(), height())          # 640 420
    print(pixel_density())            # often 2.0 on Retina displays


def draw():
    background(245)
    circle(width() / 2, height() / 2, 120)


run()
```

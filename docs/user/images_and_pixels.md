# Images and pixels

`p5-py` supports deterministic image and pixel workflows designed for native Python use.

## Images

Useful image APIs include:

- `load_image()`
- `create_image()`
- `image()`
- `image_mode()`

The `Image` type also supports pixel-oriented operations such as `get()`, `set()`, `copy()`, `resize()`, `mask()`, and common filters.

## Pixels

Useful pixel APIs include:

- `load_pixels()`
- `pixels()`
- `pixel_array()`
- `update_pixels()`
- `save_canvas()`

Current pixel buffers operate on physical RGBA data. This matters on HiDPI displays because the physical backing buffer may be larger than the logical sketch size.

## Recommended workflow

For deterministic tests and export work:

1. run with `backend="headless"`
2. call `load_pixels()` after drawing
3. mutate the returned buffer or inspect it
4. call `update_pixels()` if you changed pixel data
5. call `save_canvas()` when you want an output file

## Examples

- `examples/image_text_data.py`
- `examples/color_style_filters.py`
- `examples/pixels_blend_export.py`
- `examples/accelerated_noise_pixels.py`

## Related docs

- `docs/technical/hidpi_rendering.md`
- `docs/technical/native_pyglet_renderer.md`
- `docs/technical/rust_acceleration.md`

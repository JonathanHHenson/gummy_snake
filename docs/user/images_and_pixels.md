# Images and pixels

`p5-py` supports deterministic image and pixel workflows designed for native Python use.

## Images

Useful image APIs include:

- `load_image()`
- `create_image()`
- `image()`
- `image_mode()`
- `image_sampling()`
- `smooth()`
- `no_smooth()`

The `Image` type also supports pixel-oriented operations such as `get()`, `set()`, `copy()`, `resize()`, `mask()`, `load_pixels()`, `update_pixels()`, `pixels`, and common filters.

`Image.pixel_density()` currently reports `1.0`. Image-local HiDPI buffers, `Image.blend()`, and animated image frame controls such as `delay()`, `play()`, `pause()`, `reset()`, and `set_frame()` are explicit deferred APIs until the Rust canvas runtime exposes image-level density, local blend-mode, and animated-frame semantics. Static images report `num_frames() == 1`.

Image file loading and saving are owned by the Rust `p5_canvas` runtime through `p5.rust._canvas`. Published wheels must include that extension; there is no supported Pillow fallback.

`image_sampling()` controls how `image()` scales textures. Use `p5.NEAREST` or `no_smooth()` for crisp pixel-art scaling, and `p5.LINEAR` or `smooth()` for interpolated scaling.

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
- `examples/image_flip_sampling.py`
- `examples/color_style_filters.py`
- `examples/pixels_blend_export.py`
- `examples/accelerated_noise_pixels.py`

## Related docs

- `docs/technical/hidpi_rendering.md`
- `docs/technical/native_pyglet_renderer.md`
- `docs/technical/rust_acceleration.md`

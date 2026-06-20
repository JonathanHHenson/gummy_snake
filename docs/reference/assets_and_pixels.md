# Images, Pixels, and Assets

## Images

- `load_image(path)`
- `load_image_async(path)`
- `create_image(width, height)`
- `image(img, x, y, width=None, height=None, ...)`
- `image_mode(mode)`
- `image_sampling(mode)`
- `smooth()`
- `no_smooth()`

Images are loaded by the Rust canvas runtime. There is no Pillow fallback.
Async loader variants are awaitable and useful from `async def preload()` or
`async def setup()` callbacks.

`load_image()` returns the normal Python `Image` type, but the object keeps its
Rust-managed asset internally until the first pixel mutation. Drawing an
untouched loaded image can therefore stay on the renderer's fast sprite path.
Calling `set()`, `update_pixels()`, `resize()`, `mask()`, or `filter()` makes
the image mutable Python pixel data and future draws upload the changed version
through the bounded image cache.

`smooth()` and `image_sampling(LINEAR)` request linear sampling.
`no_smooth()` and `image_sampling(NEAREST)` request nearest-neighbor sampling.
The renderer may choose the fastest supported path for the current sampling
mode, transform, blend mode, and backend capabilities.

Image objects also support Python indexing:

```python
color = img[x, y]
img[x, y] = p5.Color(255, 0, 0)
tile = img[x0:x1, y0:y1]
```

## Pixels

- `load_pixels()`
- `load_pixel_bytes()`
- `update_pixels()`
- `pixels()`
- `pixel_array()`
- `get(...)`
- `set(...)`

Pixel buffers are physical RGBA buffers. When `pixel_density()` is greater than
`1`, the physical pixel size is larger than the logical canvas size.

`load_pixels()` returns a compatibility `list[int]`. Use `load_pixel_bytes()`
for performance-sensitive readback when a bytes-like RGBA buffer is enough.
`update_pixels()` accepts the list returned by `load_pixels()` and efficient
buffer-like inputs such as `bytes`, `bytearray`, and `memoryview`.

## Export

- `save_canvas(path=None)`
- `save_bytes(data, path)`
- `save_json(data, path)`
- `save_strings(lines, path)`
- `create_writer(path)`

## Data and Text Assets

- `load_json(path)`
- `load_json_async(path)`
- `load_strings(path)`
- `load_strings_async(path)`
- `load_bytes(path)`
- `load_bytes_async(path)`
- `load_font(path)`
- `load_font_async(path)`

## Sound and Media

- `load_sound(path)`
- `load_sound_async(path)`
- `create_audio(...)`
- `create_capture(...)`
- `create_capture_async(...)`
- `create_video(...)`
- `create_video_async(...)`

Some media helpers require installing the `media` extra.

3D asset helpers also include awaitable variants:

- `load_model_async(path, normalize=False, package=None)`
- `load_shader_async(vertex_path, fragment_path)`

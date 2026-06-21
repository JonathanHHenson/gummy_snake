# pyright: reportWildcardImportFromLibrary=false
# ruff: noqa: F401,F403,A001
"""Global-mode Gummy Snake-style API wrappers."""

from __future__ import annotations

from gummysnake.api._environment_input import (
    cursor,
    delta_time,
    display_height,
    display_width,
    focused,
    frame_count,
    frame_rate,
    get_target_frame_rate,
    is_looping,
    key,
    key_code,
    key_is_down,
    key_is_pressed,
    loop,
    millis,
    mouse_button,
    mouse_is_pressed,
    mouse_x,
    mouse_y,
    moved_x,
    moved_y,
    no_cursor,
    no_loop,
    pmouse_x,
    pmouse_y,
    redraw,
    touches,
    window_height,
    window_width,
)
from gummysnake.api._facades import current, keyboard, mouse
from gummysnake.api._lifecycle import draw, on, preload, run, setup, sketch
from gummysnake.api._media_text_pixels import (
    blend,
    blend_mode,
    copy,
    describe,
    describe_element,
    erase,
    filter,
    font_ascent,
    font_bounds,
    font_descent,
    font_width,
    get,
    grid_output,
    image,
    load_pixel_bytes,
    load_pixels,
    no_erase,
    pixel_array,
    pixels,
    save_canvas,
    set,
    text,
    text_align,
    text_ascent,
    text_bounds,
    text_descent,
    text_direction,
    text_font,
    text_leading,
    text_output,
    text_properties,
    text_property,
    text_size,
    text_style,
    text_weight,
    text_width,
    text_wrap,
    update_pixels,
)
from gummysnake.api.global_mode.canvas import *
from gummysnake.api.global_mode.contexts import *
from gummysnake.api.global_mode.exports import __all__
from gummysnake.api.global_mode.shapes import *
from gummysnake.assets.data import (
    create_writer,
    load_bytes,
    load_bytes_async,
    load_json,
    load_json_async,
    load_strings,
    load_strings_async,
    save_bytes,
    save_json,
    save_strings,
)
from gummysnake.assets.image import create_image, load_image, load_image_async
from gummysnake.assets.text import load_font, load_font_async
from gummysnake.core.data import shuffle
from gummysnake.core.math import (
    acos,
    asin,
    atan,
    atan2,
    constrain,
    cos,
    degrees,
    dist,
    fract,
    lerp,
    mag,
    map_value,
    max_value,
    min_value,
    norm,
    radians,
    sin,
    sq,
    tan,
)
from gummysnake.core.math import (
    map_value as map,
)
from gummysnake.core.random import (
    noise,
    noise_detail,
    noise_seed,
    random,
    random_gaussian,
    random_seed,
)
from gummysnake.core.vector import create_vector

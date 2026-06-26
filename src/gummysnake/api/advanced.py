"""Compatibility re-exports for advanced API topics.

Implementation lives in topic modules such as `three_d`, `models`, `shaders`,
`sound`, and `media`.
"""

from __future__ import annotations

from gummysnake.api.media import (
    create_capture,
    create_capture_async,
    create_video,
    create_video_async,
)
from gummysnake.api.models import (
    load_model,
    load_model_async,
    save_obj,
    save_stl,
)
from gummysnake.api.shaders import (
    create_shader,
    load_shader,
    load_shader_async,
    reset_shader,
    shader,
)
from gummysnake.api.sound import (
    create_audio,
    load_sound,
    load_sound_async,
)
from gummysnake.api.three_d import (
    ambient_light,
    ambient_material,
    box,
    camera,
    cone,
    create_camera,
    create_model,
    cylinder,
    directional_light,
    ellipsoid,
    model,
    normal_material,
    orbit_control,
    ortho,
    perspective,
    plane,
    point_light,
    shininess,
    specular_material,
    sphere,
    texture,
    torus,
)

__all__ = [
    "create_video",
    "create_video_async",
    "create_capture",
    "create_capture_async",
    "save_obj",
    "save_stl",
    "load_model",
    "load_model_async",
    "load_shader",
    "load_shader_async",
    "create_shader",
    "shader",
    "reset_shader",
    "load_sound",
    "load_sound_async",
    "create_audio",
    "create_camera",
    "camera",
    "perspective",
    "ortho",
    "orbit_control",
    "ambient_light",
    "directional_light",
    "point_light",
    "normal_material",
    "ambient_material",
    "specular_material",
    "shininess",
    "texture",
    "plane",
    "box",
    "sphere",
    "ellipsoid",
    "cylinder",
    "cone",
    "torus",
    "create_model",
    "model",
]

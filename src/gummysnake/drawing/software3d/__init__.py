"""Software-projected 3D helpers used by the first 3D renderer milestone."""

from __future__ import annotations

from gummysnake.drawing.software3d.export import save_obj, save_stl
from gummysnake.drawing.software3d.primitives import (
    box_model,
    clear_primitive_model_cache,
    cone_model,
    cylinder_model,
    ellipsoid_model,
    plane_model,
    primitive_model_cache_info,
    sphere_model,
    torus_model,
)
from gummysnake.drawing.software3d.raster import (
    rasterize_face_payload_region,
    rasterize_faces_image,
    rasterize_faces_image_region,
)
from gummysnake.drawing.software3d.shading import project_model_faces, shade_model_faces
from gummysnake.drawing.software3d.transform import transform_model
from gummysnake.drawing.software3d.types import ProjectedFace, ShadedFace

__all__ = [
    "ProjectedFace",
    "ShadedFace",
    "box_model",
    "clear_primitive_model_cache",
    "cone_model",
    "cylinder_model",
    "ellipsoid_model",
    "plane_model",
    "primitive_model_cache_info",
    "project_model_faces",
    "rasterize_faces_image",
    "rasterize_face_payload_region",
    "rasterize_faces_image_region",
    "save_obj",
    "save_stl",
    "shade_model_faces",
    "sphere_model",
    "torus_model",
    "transform_model",
]

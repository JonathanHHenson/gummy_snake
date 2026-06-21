# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""3D model rendering method for SketchContext."""

from __future__ import annotations

from typing import Any

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
)
from gummysnake.drawing.software3d import (
    ShadedFace,
    rasterize_faces_image_region,
    shade_model_faces,
    transform_model,
)
from gummysnake.exceptions import ArgumentValidationError


class ThreeDModelMixin:
    renderer: Any
    state: Any
    _camera3d: Camera3D
    _projection3d: PerspectiveProjection | OrthographicProjection
    _lights3d: list[Light3D]
    _material3d: Material3D | None
    _normal_material3d: bool
    _shader3d: Shader3D | None

    @property
    def width(self) -> int:
        raise NotImplementedError

    @property
    def height(self) -> int:
        raise NotImplementedError

    def model(self, shape: object) -> None:
        self._require_webgl_mode("model")
        if isinstance(shape, Mesh3D):
            model = Model3D(meshes=(shape,))
        elif isinstance(shape, Model3D):
            model = shape
        else:
            raise ArgumentValidationError("model() requires a Mesh3D or Model3D value.")

        native_renderer = self.renderer if getattr(self.renderer, "three_d", False) else None
        if native_renderer is not None:
            material = self._effective_3d_material()
            native_renderer.set_camera(self._camera3d)
            native_renderer.set_projection(self._projection3d)
            native_renderer.set_lights(tuple(self._lights3d))
            native_renderer.set_material(material)
            native_renderer.set_texture(material.texture)
            native_renderer.use_shader(self._shader3d)
            native_renderer.draw_model(model)
            return

        model_transform = self.state.transform.matrix
        faces = shade_model_faces(
            transform_model(model, model_transform),
            self._camera3d,
            self._projection3d,
            viewport_width=float(self.width),
            viewport_height=float(self.height),
            base_material=self._effective_3d_material(),
            lights=tuple(self._lights3d),
            normal_material=self._normal_material3d,
            cache_identity=(
                id(model),
                model_transform.a,
                model_transform.b,
                model_transform.c,
                model_transform.d,
                model_transform.e,
                model_transform.f,
            ),
        )
        screen_transform = Matrix2D.identity()
        draw_fill = (
            self._normal_material3d
            or self._material3d is not None
            or self.state.style.fill_color is not None
        )
        if draw_fill:
            self._draw_rasterized_3d_faces(faces, screen_transform)
        if self.state.style.stroke_color is not None:
            self._stroke_3d_faces(faces, screen_transform)

    def _draw_rasterized_3d_faces(
        self, faces: list[ShadedFace], screen_transform: Matrix2D
    ) -> None:
        overlay, overlay_x, overlay_y = rasterize_faces_image_region(
            faces,
            viewport_width=float(self.width),
            viewport_height=float(self.height),
        )
        overlay_style = self.state.style.copy()
        overlay_style.fill_color = None
        overlay_style.stroke_color = None
        self.renderer.draw_image(
            overlay,
            float(overlay_x),
            float(overlay_y),
            float(overlay.width),
            float(overlay.height),
            overlay_style,
            screen_transform,
        )

    def _stroke_3d_faces(self, faces: list[ShadedFace], screen_transform: Matrix2D) -> None:
        stroke_style = self.state.style.copy()
        stroke_style.fill_color = None
        for face in faces:
            self.renderer.polygon(list(face.points), stroke_style, screen_transform, close=True)

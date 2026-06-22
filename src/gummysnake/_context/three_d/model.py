"""3D model rendering method for SketchContext."""

from __future__ import annotations

from typing import Any, cast

from gummysnake._context.three_d._protocols import ThreeDContextHost
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
    _model_rust_handle,
)
from gummysnake.drawing.software3d import (
    ShadedFace,
    rasterize_face_payload_region,
    rasterize_faces_image_region,
)
from gummysnake.drawing.software3d.rust_bridge import rust_project_shade_faces
from gummysnake.drawing.software3d.shading import texture_image
from gummysnake.exceptions import ArgumentValidationError


def _three_d(self: Any) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)


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

    def model(self, shape: Mesh3D | Model3D) -> None:
        _three_d(self)._require_webgl_mode("model")
        if isinstance(shape, Mesh3D):
            model = Model3D(meshes=(shape,))
        elif isinstance(shape, Model3D):
            model = shape
        else:
            raise ArgumentValidationError("model() requires a Mesh3D or Model3D value.")

        native_renderer = self.renderer if getattr(self.renderer, "three_d", False) else None
        if native_renderer is not None:
            material = _three_d(self)._effective_3d_material()
            native_renderer.set_camera(self._camera3d)
            native_renderer.set_projection(self._projection3d)
            native_renderer.set_lights(tuple(self._lights3d))
            native_renderer.set_material(material)
            native_renderer.set_texture(material.texture)
            native_renderer.use_shader(self._shader3d)
            native_renderer.draw_model(model)
            return

        model_transform = self.state.transform.matrix
        material = _three_d(self)._effective_3d_material()
        draw_fill = (
            self._normal_material3d
            or self._material3d is not None
            or self.state.style.fill_color is not None
        )
        texture = None if self._normal_material3d else texture_image(material)
        if (
            draw_fill
            and texture is None
            and self.state.style.stroke_color is None
            and self._draw_model_shaded_direct(model, material, model_transform)
        ):
            return

        faces = rust_project_shade_faces(
            model,
            self._camera3d,
            self._projection3d,
            viewport_width=float(self.width),
            viewport_height=float(self.height),
            base_material=material,
            lights=tuple(self._lights3d),
            normal_material=self._normal_material3d,
            cull_backfaces=True,
            model_transform=model_transform,
        )
        screen_transform = Matrix2D.identity()
        if draw_fill:
            if texture is None and self._draw_shaded_faces_direct(faces):
                pass
            else:
                self._draw_rasterized_3d_payload(
                    faces,
                    screen_transform,
                    texture=texture,
                )
        if self.state.style.stroke_color is not None:
            shaded_faces = [
                ShadedFace(
                    points=tuple((float(x), float(y)) for x, y in face["points"]),
                    color=cast(tuple[float, float, float, float], tuple(face["color"])),
                    depth=float(face["depth"]),
                    texcoords=None,
                    texture=None,
                )
                for face in faces
            ]
            self._stroke_3d_faces(shaded_faces, screen_transform)

    def _draw_model_shaded_direct(
        self,
        model: Model3D,
        material: Material3D,
        model_transform: Matrix2D | None,
    ) -> bool:
        handle = _model_rust_handle(model)
        if handle is None:
            return False
        require_canvas = getattr(self.renderer, "_require_canvas", None)
        flush_line_batch = getattr(self.renderer, "_flush_line_batch", None)
        if not callable(require_canvas):
            return False
        canvas = require_canvas()
        draw = getattr(canvas, "draw_model_shaded", None)
        if not callable(draw):
            return False
        transform_payload: tuple[float, float, float, float, float, float] | None = None
        if model_transform is not None and model_transform != Matrix2D.identity():
            transform_payload = (
                model_transform.a,
                model_transform.b,
                model_transform.c,
                model_transform.d,
                model_transform.e,
                model_transform.f,
            )
        if callable(flush_line_batch):
            flush_line_batch()
        draw(
            handle,
            self._camera_payload(),
            self._projection_payload(),
            float(self.width),
            float(self.height),
            self._material_payload(material),
            self._light_payloads(),
            self._normal_material3d,
            True,
            transform_payload,
        )
        return True

    def _camera_payload(self) -> dict[str, tuple[float, float, float]]:
        return {
            "eye": (self._camera3d.eye.x, self._camera3d.eye.y, self._camera3d.eye.z),
            "target": (
                self._camera3d.target.x,
                self._camera3d.target.y,
                self._camera3d.target.z,
            ),
            "up": (self._camera3d.up.x, self._camera3d.up.y, self._camera3d.up.z),
        }

    def _projection_payload(self) -> dict[str, Any]:
        if isinstance(self._projection3d, PerspectiveProjection):
            return {
                "kind": "perspective",
                "fov_y": self._projection3d.fov_y,
                "aspect": self._projection3d.aspect,
                "near": self._projection3d.near,
                "far": self._projection3d.far,
            }
        return {
            "kind": "orthographic",
            "width": self._projection3d.width,
            "height": self._projection3d.height,
            "near": self._projection3d.near,
            "far": self._projection3d.far,
        }

    def _material_payload(self, material: Material3D) -> dict[str, Any]:
        return {
            "base_color": material.base_color,
            "emissive_color": material.emissive_color,
            "specular_color": material.specular_color,
            "shininess": material.shininess,
        }

    def _light_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": light.kind.value,
                "color": light.color,
                "intensity": light.intensity,
                "position": None
                if light.position is None
                else (light.position.x, light.position.y, light.position.z),
                "direction": None
                if light.direction is None
                else (light.direction.x, light.direction.y, light.direction.z),
            }
            for light in self._lights3d
        ]

    def _draw_shaded_faces_direct(self, faces: list[dict[str, Any]]) -> bool:
        require_canvas = getattr(self.renderer, "_require_canvas", None)
        flush_line_batch = getattr(self.renderer, "_flush_line_batch", None)
        if not callable(require_canvas):
            return False
        canvas = require_canvas()
        draw = getattr(canvas, "shaded_faces", None)
        if not callable(draw):
            return False
        if callable(flush_line_batch):
            flush_line_batch()
        draw(faces)
        return True

    def _draw_rasterized_3d_payload(
        self,
        faces: list[dict[str, Any]],
        screen_transform: Matrix2D,
        *,
        texture: Any | None,
    ) -> None:
        overlay, overlay_x, overlay_y = rasterize_face_payload_region(
            faces,
            viewport_width=float(self.width),
            viewport_height=float(self.height),
            texture=texture,
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

"""3D camera, lighting, material, shader, and model methods for SketchContext."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    LightKind,
    Material3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
    ShaderUniformValue,
    Texture3D,
    Vec3,
)
from gummysnake.drawing.software3d import (
    box_model,
    cone_model,
    cylinder_model,
    ellipsoid_model,
    plane_model,
    rasterize_faces_image_region,
    shade_model_faces,
    sphere_model,
    torus_model,
    transform_model,
)
from gummysnake.drawing.software3d import save_obj as save_obj_model
from gummysnake.drawing.software3d import save_stl as save_stl_model
from gummysnake.exceptions import (
    ArgumentValidationError,
    BackendCapabilityError,
    ShaderUniformError,
)


class ThreeDContextMixin:
    backend: Any
    renderer: Any
    state: Any
    _camera3d: Camera3D
    _projection3d: PerspectiveProjection | OrthographicProjection
    _lights3d: list[Light3D]
    _material3d: Material3D | None
    _normal_material3d: bool
    _shader3d: Shader3D | None
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float

    @property
    def width(self) -> int:
        raise NotImplementedError

    @property
    def height(self) -> int:
        raise NotImplementedError

    def _require_webgl_mode(self, api_name: str) -> None:
        raise NotImplementedError

    def _numeric_values(self, values: Any) -> tuple[float, ...]:
        raise NotImplementedError

    def _angle(self, value: float) -> float:
        raise NotImplementedError

    def color(self, *args: object) -> Color:
        raise NotImplementedError

    def _color_to_rgba(self, color: Color) -> tuple[float, float, float, float]:
        raise NotImplementedError

    def _split_color_args(
        self, args: Any, *, tail_count: int
    ) -> tuple[Color, tuple[float, ...]]:
        raise NotImplementedError

    def _replace_material(
        self,
        *,
        base_color: tuple[float, float, float, float] | None = None,
        specular_color: tuple[float, float, float, float] | None = None,
        shininess: float | None = None,
        texture: Texture3D | None | object = None,
    ) -> Material3D:
        raise NotImplementedError

    def _effective_3d_material(self) -> Material3D:
        raise NotImplementedError

    def create_camera(self, *args: object) -> Camera3D:
        return self.camera(*args)

    def camera(self, *args: object) -> Camera3D:
        self._require_webgl_mode("camera")
        if len(args) == 0:
            camera = Camera3D()
        elif len(args) == 1 and isinstance(args[0], Camera3D):
            camera = args[0]
        elif len(args) == 9 and all(isinstance(value, int | float) for value in args):
            numeric_args = self._numeric_values(args)
            camera = Camera3D(
                eye=Vec3(numeric_args[0], numeric_args[1], numeric_args[2]),
                target=Vec3(numeric_args[3], numeric_args[4], numeric_args[5]),
                up=Vec3(numeric_args[6], numeric_args[7], numeric_args[8]),
            )
        else:
            raise ArgumentValidationError(
                "camera() accepts no arguments, a Camera3D, or nine numeric values."
            )
        self._camera3d = camera
        return camera

    def perspective(self, *args: object) -> PerspectiveProjection:
        self._require_webgl_mode("perspective")
        if len(args) > 4 or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "perspective() accepts fov, aspect, near, and far numeric values."
            )
        numeric_args = self._numeric_values(args)
        fov_y = 60.0 if len(numeric_args) == 0 else math.degrees(self._angle(numeric_args[0]))
        aspect = None if len(numeric_args) < 2 else numeric_args[1]
        near = 0.1 if len(numeric_args) < 3 else numeric_args[2]
        far = 10_000.0 if len(numeric_args) < 4 else numeric_args[3]
        projection = PerspectiveProjection(fov_y=fov_y, aspect=aspect, near=near, far=far)
        self._projection3d = projection
        return projection

    def ortho(self, *args: object) -> OrthographicProjection:
        self._require_webgl_mode("ortho")
        if len(args) not in {0, 2, 4} or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "ortho() accepts no arguments, width/height, or width/height/near/far."
            )
        numeric_args = self._numeric_values(args)
        ortho_width = float(self.width) if len(numeric_args) == 0 else numeric_args[0]
        ortho_height = float(self.height) if len(numeric_args) == 0 else numeric_args[1]
        near = 0.1 if len(numeric_args) < 4 else numeric_args[2]
        far = 10_000.0 if len(numeric_args) < 4 else numeric_args[3]
        projection = OrthographicProjection(
            width=ortho_width,
            height=ortho_height,
            near=near,
            far=far,
        )
        self._projection3d = projection
        return projection

    def orbit_control(self, *args: object) -> Camera3D:
        self._require_webgl_mode("orbit_control")
        if len(args) > 3 or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "orbit_control() accepts up to three numeric sensitivity values."
            )
        numeric_args = self._numeric_values(args)
        sensitivity_x = 1.0 if len(numeric_args) == 0 else numeric_args[0]
        sensitivity_y = sensitivity_x if len(numeric_args) < 2 else numeric_args[1]
        sensitivity_z = 1.0 if len(numeric_args) < 3 else numeric_args[2]
        if sensitivity_x <= 0 or sensitivity_y <= 0 or sensitivity_z <= 0:
            raise ArgumentValidationError("orbit_control() sensitivities must be positive.")

        dx = self._frame_mouse_dx
        dy = self._frame_mouse_dy
        scroll_y = self._frame_scroll_y
        offset = Vec3(
            self._camera3d.eye.x - self._camera3d.target.x,
            self._camera3d.eye.y - self._camera3d.target.y,
            self._camera3d.eye.z - self._camera3d.target.z,
        )
        radius = math.sqrt(offset.x * offset.x + offset.y * offset.y + offset.z * offset.z)
        if radius <= 0:
            raise ArgumentValidationError("orbit_control() requires a non-zero camera distance.")

        azimuth = math.atan2(offset.x, offset.z)
        polar = math.acos(max(-1.0, min(1.0, offset.y / radius)))
        if self.state.input.mouse_is_pressed:
            azimuth -= dx * 0.01 * sensitivity_x
            polar = max(1e-3, min(math.pi - 1e-3, polar + dy * 0.01 * sensitivity_y))
        if scroll_y != 0.0:
            radius = max(1.0, radius * math.exp(-scroll_y * 0.1 * sensitivity_z))

        sin_polar = math.sin(polar)
        new_eye = Vec3(
            self._camera3d.target.x + radius * sin_polar * math.sin(azimuth),
            self._camera3d.target.y + radius * math.cos(polar),
            self._camera3d.target.z + radius * sin_polar * math.cos(azimuth),
        )
        self._camera3d = Camera3D(eye=new_eye, target=self._camera3d.target, up=Vec3(0.0, 1.0, 0.0))
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        return self._camera3d

    def ambient_light(self, *args: object) -> None:
        self._require_webgl_mode("ambient_light")
        self._lights3d.append(
            Light3D(kind=LightKind.AMBIENT, color=self._color_to_rgba(self.color(*args)))
        )

    def directional_light(self, *args: object) -> None:
        self._require_webgl_mode("directional_light")
        color, tail = self._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind=LightKind.DIRECTIONAL,
                color=self._color_to_rgba(color),
                direction=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    def point_light(self, *args: object) -> None:
        self._require_webgl_mode("point_light")
        color, tail = self._split_color_args(args, tail_count=3)
        self._lights3d.append(
            Light3D(
                kind=LightKind.POINT,
                color=self._color_to_rgba(color),
                position=Vec3(float(tail[0]), float(tail[1]), float(tail[2])),
            )
        )

    def normal_material(self) -> None:
        self._require_webgl_mode("normal_material")
        self._material3d = None
        self._normal_material3d = True

    def ambient_material(self, *args: object) -> None:
        self._require_webgl_mode("ambient_material")
        self._material3d = self._replace_material(
            base_color=self._color_to_rgba(self.color(*args)),
            texture=None,
        )
        self._normal_material3d = False

    def specular_material(self, *args: object) -> None:
        self._require_webgl_mode("specular_material")
        color = self._color_to_rgba(self.color(*args))
        self._material3d = self._replace_material(
            base_color=color,
            specular_color=color,
            texture=None,
        )
        self._normal_material3d = False

    def shininess(self, value: float) -> None:
        self._require_webgl_mode("shininess")
        if value <= 0:
            raise ArgumentValidationError("shininess() must be positive.")
        self._material3d = self._replace_material(shininess=float(value))

    def texture(self, image: Image) -> None:
        self._require_webgl_mode("texture")
        if not isinstance(image, Image):
            raise ArgumentValidationError("texture() requires a Gummy Snake Image object.")
        self._material3d = self._replace_material(
            texture=Texture3D(source=image, width=image.width, height=image.height)
        )
        self._normal_material3d = False

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        from gummysnake.assets.shader import load_shader as _load_shader

        return _load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        from gummysnake.assets.shader import create_shader as _create_shader

        return _create_shader(vertex_source, fragment_source)

    def shader(self, shader: Shader3D) -> None:
        self._require_webgl_mode("shader")
        if not self.backend.capabilities.shaders:
            enable_native_webgl = getattr(self.backend, "enable_native_webgl", None)
            if callable(enable_native_webgl) and enable_native_webgl():
                self.renderer = self.backend.renderer
        if not self.backend.capabilities.shaders:
            raise BackendCapabilityError(
                f"Backend {self.backend.name!r} does not support shader()."
            )
        if not isinstance(shader, Shader3D):
            raise ArgumentValidationError("shader() requires a Shader3D value.")
        self._shader3d = shader

    def reset_shader(self) -> None:
        self._require_webgl_mode("reset_shader")
        self._shader3d = None

    def set_shader_uniform(self, name: str, value: object) -> None:
        self._require_webgl_mode("set_shader_uniform")
        if self._shader3d is None:
            raise ShaderUniformError(
                f"Cannot set uniform {name!r} without an active shader. Call shader(...) first."
            )
        self._shader3d.set_uniform(name, cast("ShaderUniformValue", value))

    def plane(self, width: float, height: float | None = None) -> None:
        self.model(plane_model(float(width), None if height is None else float(height)))

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self.model(
            box_model(
                float(width),
                None if height is None else float(height),
                None if depth is None else float(depth),
            )
        )

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self.model(sphere_model(float(radius), int(detail_x), int(detail_y)))

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        self.model(
            ellipsoid_model(
                float(radius_x),
                None if radius_y is None else float(radius_y),
                None if radius_z is None else float(radius_z),
                int(detail_x),
                int(detail_y),
            )
        )

    def cylinder(
        self,
        radius: float,
        height: float,
        detail_x: int = 24,
        detail_y: int = 1,
        *,
        bottom_cap: bool = True,
        top_cap: bool = True,
    ) -> None:
        self.model(
            cylinder_model(
                float(radius),
                float(height),
                int(detail_x),
                int(detail_y),
                bottom_cap=bottom_cap,
                top_cap=top_cap,
            )
        )

    def cone(
        self,
        radius: float,
        height: float,
        detail_x: int = 24,
        detail_y: int = 1,
        *,
        cap: bool = True,
    ) -> None:
        self.model(cone_model(float(radius), float(height), int(detail_x), int(detail_y), cap=cap))

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        self.model(
            torus_model(
                float(radius),
                None if tube_radius is None else float(tube_radius),
                int(detail_x),
                int(detail_y),
            )
        )

    def create_model(self, mesh: object) -> Model3D:
        if isinstance(mesh, Model3D):
            return mesh
        if isinstance(mesh, Mesh3D):
            return Model3D(meshes=(mesh,))
        raise ArgumentValidationError("create_model() requires a Mesh3D or Model3D value.")

    def save_obj(self, model: Model3D, path: str | Path) -> Path:
        return save_obj_model(model, path)

    def save_stl(self, model: Model3D, path: str | Path) -> Path:
        return save_stl_model(model, path)

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
        projected_model = transform_model(model, model_transform)
        screen_transform = Matrix2D.identity()
        faces = shade_model_faces(
            projected_model,
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
        draw_fill = (
            self._normal_material3d
            or self._material3d is not None
            or self.state.style.fill_color is not None
        )
        if draw_fill:
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
        if self.state.style.stroke_color is not None:
            stroke_style = self.state.style.copy()
            stroke_style.fill_color = None
            for face in faces:
                self.renderer.polygon(
                    list(face.points),
                    stroke_style,
                    screen_transform,
                    close=True,
                )


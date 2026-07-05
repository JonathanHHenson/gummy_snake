"""3D camera, light, material, model, and shader forwards for object sketches."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import overload

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.assets.model import load_model as _load_model
from gummysnake.assets.model import load_model_async as _load_model_async
from gummysnake.assets.shader import load_shader_async as _load_shader_async
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    Shader3D,
    ShaderUniformValue,
    Vec3,
)
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)
from gummysnake.sketch.facade_mixins.base import ColorValue, Number, SketchFacadeBaseMixin

CameraArg = Camera3D | Number
ColorArg = ColorValue | Number


class SketchFacadeThreeDMixin(SketchFacadeBaseMixin):
    """Object-mode forwards for 3D, model, and shader APIs."""

    @overload
    def create_camera(self) -> Camera3D: ...

    @overload
    def create_camera(self, camera: Camera3D, /) -> Camera3D: ...

    @overload
    def create_camera(
        self,
        eye_x: Number,
        eye_y: Number,
        eye_z: Number,
        center_x: Number,
        center_y: Number,
        center_z: Number,
        up_x: Number,
        up_y: Number,
        up_z: Number,
        /,
    ) -> Camera3D: ...

    def create_camera(self, *args: CameraArg) -> Camera3D:
        return self._ctx.create_camera(*args)

    @overload
    def camera(self) -> Camera3D: ...

    @overload
    def camera(self, camera: Camera3D, /) -> Camera3D: ...

    @overload
    def camera(
        self,
        eye_x: Number,
        eye_y: Number,
        eye_z: Number,
        center_x: Number,
        center_y: Number,
        center_z: Number,
        up_x: Number,
        up_y: Number,
        up_z: Number,
        /,
    ) -> Camera3D: ...

    def camera(self, *args: CameraArg) -> Camera3D:
        return self._ctx.camera(*args)

    def set_camera(self, camera: Camera3D) -> Camera3D:
        return self._ctx.set_camera(camera)

    def roll(self, angle: Number) -> Camera3D:
        return self._ctx.roll(angle)

    def world_to_screen(self, x: Number, y: Number, z: Number) -> tuple[float, float, float]:
        return self._ctx.world_to_screen(x, y, z)

    def screen_to_world(self, x: Number, y: Number, depth: Number = 0.0) -> Vec3:
        return self._ctx.screen_to_world(x, y, depth)

    @overload
    def perspective(self) -> PerspectiveProjection: ...

    @overload
    def perspective(self, fov: Number, /) -> PerspectiveProjection: ...

    @overload
    def perspective(self, fov: Number, aspect: Number, /) -> PerspectiveProjection: ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, /
    ) -> PerspectiveProjection: ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, far: Number, /
    ) -> PerspectiveProjection: ...

    def perspective(self, *args: Number) -> PerspectiveProjection:
        return self._ctx.perspective(*args)

    @overload
    def ortho(self) -> OrthographicProjection: ...

    @overload
    def ortho(self, width: Number, height: Number, /) -> OrthographicProjection: ...

    @overload
    def ortho(
        self, width: Number, height: Number, near: Number, far: Number, /
    ) -> OrthographicProjection: ...

    def ortho(self, *args: Number) -> OrthographicProjection:
        return self._ctx.ortho(*args)

    def frustum(
        self,
        left: Number,
        right: Number,
        bottom: Number,
        top: Number,
        near: Number = 0.1,
        far: Number = 10_000.0,
    ) -> FrustumProjection:
        return self._ctx.frustum(left, right, bottom, top, near, far)

    @overload
    def orbit_control(self) -> Camera3D: ...

    @overload
    def orbit_control(self, sensitivity_x: Number, /) -> Camera3D: ...

    @overload
    def orbit_control(self, sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D: ...

    @overload
    def orbit_control(
        self, sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
    ) -> Camera3D: ...

    def orbit_control(self, *args: Number) -> Camera3D:
        return self._ctx.orbit_control(*args)

    @overload
    def ambient_light(self, value: ColorValue, /) -> None: ...

    @overload
    def ambient_light(self, gray: Number, /) -> None: ...

    @overload
    def ambient_light(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def ambient_light(self, *args: ColorArg) -> None:
        self._ctx_call("ambient_light", *args)

    def lights(self) -> None:
        self._ctx.lights()

    def no_lights(self) -> None:
        self._ctx.no_lights()

    @overload
    def directional_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def directional_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def directional_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def directional_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def directional_light(
        self,
        v1: Number,
        v2: Number,
        v3: Number,
        alpha: Number,
        x: Number,
        y: Number,
        z: Number,
        /,
    ) -> None: ...

    def directional_light(self, *args: ColorArg) -> None:
        self._ctx_call("directional_light", *args)

    @overload
    def point_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def point_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None: ...

    @overload
    def point_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def point_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None: ...

    @overload
    def point_light(
        self,
        v1: Number,
        v2: Number,
        v3: Number,
        alpha: Number,
        x: Number,
        y: Number,
        z: Number,
        /,
    ) -> None: ...

    def point_light(self, *args: ColorArg) -> None:
        self._ctx_call("point_light", *args)

    def spot_light(self, *args: ColorArg) -> None:
        self._ctx_call("spot_light", *args)

    def image_light(self, image: Image, intensity: float = 1.0) -> None:
        self._ctx.image_light(image, intensity)

    def panorama(self, image: Image | None = None) -> Image | None:
        return self._ctx.panorama(image)

    def light_falloff(self, constant: float, linear: float, quadratic: float) -> None:
        self._ctx.light_falloff(constant, linear, quadratic)

    def specular_color(self, *args: ColorArg) -> None:
        self._ctx_call("specular_color", *args)

    def normal_material(self) -> None:
        self._ctx.normal_material()

    @overload
    def ambient_material(self, value: ColorValue, /) -> None: ...

    @overload
    def ambient_material(self, gray: Number, /) -> None: ...

    @overload
    def ambient_material(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def ambient_material(self, *args: ColorArg) -> None:
        self._ctx_call("ambient_material", *args)

    @overload
    def specular_material(self, value: ColorValue, /) -> None: ...

    @overload
    def specular_material(self, gray: Number, /) -> None: ...

    @overload
    def specular_material(self, gray: Number, alpha: Number, /) -> None: ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, /) -> None: ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None: ...

    def specular_material(self, *args: ColorArg) -> None:
        self._ctx_call("specular_material", *args)

    def shininess(self, value: float) -> None:
        self._ctx.shininess(value)

    def emissive_material(self, *args: ColorArg) -> None:
        self._ctx_call("emissive_material", *args)

    def metalness(self, value: float) -> None:
        self._ctx.metalness(value)

    def texture_mode(
        self, mode: c.TextureCoordinateMode | str | None = None
    ) -> c.TextureCoordinateMode:
        return self._ctx.texture_mode(mode)

    def texture_wrap(
        self,
        wrap_x: c.TextureWrapMode | str | None = None,
        wrap_y: c.TextureWrapMode | str | None = None,
    ) -> tuple[c.TextureWrapMode, c.TextureWrapMode]:
        return self._ctx.texture_wrap(wrap_x, wrap_y)

    def texture(self, image: Image) -> None:
        self._ctx.texture(image)

    def plane(self, width: float, height: float | None = None) -> None:
        self._ctx.plane(width, height)

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self._ctx.box(width, height, depth)

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self._ctx.sphere(radius, detail_x, detail_y)

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        self._ctx.ellipsoid(radius_x, radius_y, radius_z, detail_x, detail_y)

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
        self._ctx.cylinder(
            radius, height, detail_x, detail_y, bottom_cap=bottom_cap, top_cap=top_cap
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
        self._ctx.cone(radius, height, detail_x, detail_y, cap=cap)

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        self._ctx.torus(radius, tube_radius, detail_x, detail_y)

    def create_model(self, mesh: Mesh3D | Model3D) -> Model3D:
        return self._ctx.create_model(mesh)

    def normal(self, x: float, y: float, z: float) -> None:
        self._ctx.normal(x, y, z)

    def vertex_property(self, name: str, value: object) -> None:
        self._ctx.vertex_property(name, value)

    def build_geometry(self, callback: Callable[[], object]) -> Model3D:
        return self._ctx.build_geometry(callback)

    def free_geometry(self, model_value: Model3D) -> None:
        self._ctx.free_geometry(model_value)

    def flip_u(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        return self._ctx.flip_u(mesh_or_model)

    def flip_v(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        return self._ctx.flip_v(mesh_or_model)

    def load_model(
        self, path: str | Path, normalize: bool = False, *, package: str | None = None
    ) -> Model3D:
        return _load_model(path, normalize, package=package)

    async def load_model_async(
        self, path: str | Path, normalize: bool = False, *, package: str | None = None
    ) -> Model3D:
        return await _load_model_async(path, normalize, package=package)

    def model(self, shape: Mesh3D | Model3D) -> None:
        self._ctx.model(shape)

    def save_obj(self, model_value: Model3D, path: str | Path) -> Path:
        return self._ctx.save_obj(model_value, path)

    def save_stl(self, model_value: Model3D, path: str | Path) -> Path:
        return self._ctx.save_stl(model_value, path)

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        return self._ctx.load_shader(vertex_path, fragment_path)

    async def load_shader_async(
        self, vertex_path: str | Path, fragment_path: str | Path
    ) -> Shader3D:
        return await _load_shader_async(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        return self._ctx.create_shader(vertex_source, fragment_source)

    def shader(self, shader_program: Shader3D) -> None:
        self._ctx.shader(shader_program)

    def reset_shader(self) -> None:
        self._ctx.reset_shader()

    def set_shader_uniform(self, name: str, value: ShaderUniformValue) -> None:
        self._ctx.set_shader_uniform(name, value)

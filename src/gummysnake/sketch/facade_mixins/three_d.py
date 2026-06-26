"""3D camera, light, material, model, and shader forwards for object sketches."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast, overload

from gummysnake.assets.image import Image
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
)
from gummysnake.sketch.facade_mixins.base import ColorValue, Number, SketchFacadeBaseMixin


class SketchFacadeThreeDMixin(SketchFacadeBaseMixin):
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

    def create_camera(self, *args: Any) -> Camera3D:
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

    def camera(self, *args: Any) -> Camera3D:
        return self._ctx.camera(*args)

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

    def perspective(self, *args: Any) -> PerspectiveProjection:
        return self._ctx.perspective(*args)

    @overload
    def ortho(self) -> OrthographicProjection: ...

    @overload
    def ortho(self, width: Number, height: Number, /) -> OrthographicProjection: ...

    @overload
    def ortho(
        self, width: Number, height: Number, near: Number, far: Number, /
    ) -> OrthographicProjection: ...

    def ortho(self, *args: Any) -> OrthographicProjection:
        return self._ctx.ortho(*args)

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

    def orbit_control(self, *args: Any) -> Camera3D:
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

    def ambient_light(self, *args: Any) -> None:
        cast(Any, self._ctx).ambient_light(*args)

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

    def directional_light(self, *args: Any) -> None:
        cast(Any, self._ctx).directional_light(*args)

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

    def point_light(self, *args: Any) -> None:
        cast(Any, self._ctx).point_light(*args)

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

    def ambient_material(self, *args: Any) -> None:
        cast(Any, self._ctx).ambient_material(*args)

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

    def specular_material(self, *args: Any) -> None:
        cast(Any, self._ctx).specular_material(*args)

    def shininess(self, value: float) -> None:
        self._ctx.shininess(value)

    def texture(self, image: Image) -> None:
        self._ctx.texture(image)

    def plane(self, width: float, height: float | None = None) -> None:
        self._ctx.plane(width, height)

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self._ctx.box(width, height, depth)

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self._ctx.sphere(radius, detail_x, detail_y)

    def model(self, shape: Mesh3D | Model3D) -> None:
        self._ctx.model(shape)

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        return self._ctx.load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        return self._ctx.create_shader(vertex_source, fragment_source)

    def shader(self, shader_program: Shader3D) -> None:
        self._ctx.shader(shader_program)

    def reset_shader(self) -> None:
        self._ctx.reset_shader()

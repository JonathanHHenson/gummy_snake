"""Camera and projection forwards for object-mode 3D sketches."""

from __future__ import annotations

from typing import overload

from gummysnake.drawing.renderer3d import Camera3D, Vec3
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)
from gummysnake.sketch.facade_mixins.base import Number, SketchFacadeBaseMixin

type CameraArg = Camera3D | Number


class SketchFacadeCameraMixin(SketchFacadeBaseMixin):
    """Create, select, and project with the active 3D camera."""

    __facade_doc_topic__ = "Configure the active 3D camera or its projection."

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

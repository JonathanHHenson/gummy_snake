"""3D camera, light, material, model, and shader forwards for object sketches."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast, overload

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


class SketchFacadeThreeDMixin(SketchFacadeBaseMixin):
    """Object-mode forwards for 3D, model, and shader APIs."""

    @overload
    def create_camera(self) -> Camera3D:
        ...

    @overload
    def create_camera(self, camera: Camera3D, /) -> Camera3D:
        ...

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
    ) -> Camera3D:
        ...

    def create_camera(self, *args: Any) -> Camera3D:
        """Create and return a camera value.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            The return value. Type: `Camera3D`.
        """
        return self._ctx.create_camera(*args)

    @overload
    def camera(self) -> Camera3D:
        ...

    @overload
    def camera(self, camera: Camera3D, /) -> Camera3D:
        ...

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
    ) -> Camera3D:
        ...

    def camera(self, *args: Any) -> Camera3D:
        """Camera for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            The return value. Type: `Camera3D`.
        """
        return self._ctx.camera(*args)

    def set_camera(self, camera: Camera3D) -> Camera3D:
        """Set the camera value.

        Args:
            camera: The camera value. Expected type: `Camera3D`.

        Returns:
            The return value. Type: `Camera3D`.
        """
        return self._ctx.set_camera(camera)

    def roll(self, angle: Number) -> Camera3D:
        """Roll for this SketchFacadeThreeDMixin.

        Args:
            angle: The angle value. Expected type: `Number`.

        Returns:
            The return value. Type: `Camera3D`.
        """
        return self._ctx.roll(angle)

    def world_to_screen(self, x: Number, y: Number, z: Number) -> tuple[float, float, float]:
        """World to screen for this SketchFacadeThreeDMixin.

        Args:
            x: The x value. Expected type: `Number`.
            y: The y value. Expected type: `Number`.
            z: The z value. Expected type: `Number`.

        Returns:
            The return value. Type: `tuple[float, float, float]`.
        """
        return self._ctx.world_to_screen(x, y, z)

    def screen_to_world(self, x: Number, y: Number, depth: Number = 0.0) -> Vec3:
        """Screen to world for this SketchFacadeThreeDMixin.

        Args:
            x: The x value. Expected type: `Number`.
            y: The y value. Expected type: `Number`.
            depth: The depth value. Expected type: `Number`. Defaults to `0.0`.

        Returns:
            The return value. Type: `Vec3`.
        """
        return self._ctx.screen_to_world(x, y, depth)

    @overload
    def perspective(self) -> PerspectiveProjection:
        ...

    @overload
    def perspective(self, fov: Number, /) -> PerspectiveProjection:
        ...

    @overload
    def perspective(self, fov: Number, aspect: Number, /) -> PerspectiveProjection:
        ...

    @overload
    def perspective(self, fov: Number, aspect: Number, near: Number, /) -> PerspectiveProjection:
        ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, far: Number, /
    ) -> PerspectiveProjection:
        ...

    def perspective(self, *args: Any) -> PerspectiveProjection:
        """Perspective for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
        return self._ctx.perspective(*args)

    @overload
    def ortho(self) -> OrthographicProjection:
        ...

    @overload
    def ortho(self, width: Number, height: Number, /) -> OrthographicProjection:
        ...

    @overload
    def ortho(
        self, width: Number, height: Number, near: Number, far: Number, /
    ) -> OrthographicProjection:
        ...

    def ortho(self, *args: Any) -> OrthographicProjection:
        """Ortho for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            The return value. Type: `OrthographicProjection`.
        """
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
        """Frustum for this SketchFacadeThreeDMixin.

        Args:
            left: The left value. Expected type: `Number`.
            right: The right value. Expected type: `Number`.
            bottom: The bottom value. Expected type: `Number`.
            top: The top value. Expected type: `Number`.
            near: The near value. Expected type: `Number`. Defaults to `0.1`.
            far: The far value. Expected type: `Number`. Defaults to `10000.0`.

        Returns:
            The return value. Type: `FrustumProjection`.
        """
        return self._ctx.frustum(left, right, bottom, top, near, far)

    @overload
    def orbit_control(self) -> Camera3D:
        ...

    @overload
    def orbit_control(self, sensitivity_x: Number, /) -> Camera3D:
        ...

    @overload
    def orbit_control(self, sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D:
        ...

    @overload
    def orbit_control(
        self, sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
    ) -> Camera3D:
        ...

    def orbit_control(self, *args: Any) -> Camera3D:
        """Orbit control for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            The return value. Type: `Camera3D`.
        """
        return self._ctx.orbit_control(*args)

    @overload
    def ambient_light(self, value: ColorValue, /) -> None:
        ...

    @overload
    def ambient_light(self, gray: Number, /) -> None:
        ...

    @overload
    def ambient_light(self, gray: Number, alpha: Number, /) -> None:
        ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, /) -> None:
        ...

    @overload
    def ambient_light(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
        ...

    def ambient_light(self, *args: Any) -> None:
        """Ambient light for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).ambient_light(*args)

    def lights(self) -> None:
        """Lights for this SketchFacadeThreeDMixin.

        Args:
            None.

        Returns:
            None.
        """
        self._ctx.lights()

    def no_lights(self) -> None:
        """Disable lights.

        Args:
            None.

        Returns:
            None.
        """
        self._ctx.no_lights()

    @overload
    def directional_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None:
        ...

    @overload
    def directional_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None:
        ...

    @overload
    def directional_light(
        self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /
    ) -> None:
        ...

    @overload
    def directional_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None:
        ...

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
    ) -> None:
        ...

    def directional_light(self, *args: Any) -> None:
        """Directional light for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).directional_light(*args)

    @overload
    def point_light(self, value: ColorValue, x: Number, y: Number, z: Number, /) -> None:
        ...

    @overload
    def point_light(self, gray: Number, x: Number, y: Number, z: Number, /) -> None:
        ...

    @overload
    def point_light(self, gray: Number, alpha: Number, x: Number, y: Number, z: Number, /) -> None:
        ...

    @overload
    def point_light(
        self, v1: Number, v2: Number, v3: Number, x: Number, y: Number, z: Number, /
    ) -> None:
        ...

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
    ) -> None:
        ...

    def point_light(self, *args: Any) -> None:
        """Point light for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).point_light(*args)

    def spot_light(self, *args: Any) -> None:
        """Spot light for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).spot_light(*args)

    def image_light(self, image: Image, intensity: float = 1.0) -> None:
        """Image light for this SketchFacadeThreeDMixin.

        Args:
            image: The image value. Expected type: `Image`.
            intensity: The intensity value. Expected type: `float`. Defaults to `1.0`.

        Returns:
            None.
        """
        self._ctx.image_light(image, intensity)

    def panorama(self, image: Image | None = None) -> Image | None:
        """Panorama for this SketchFacadeThreeDMixin.

        Args:
            image: The image value. Expected type: `Image | None`. Defaults to `None`.

        Returns:
            The return value. Type: `Image | None`.
        """
        return self._ctx.panorama(image)

    def light_falloff(self, constant: float, linear: float, quadratic: float) -> None:
        """Light falloff for this SketchFacadeThreeDMixin.

        Args:
            constant: The constant value. Expected type: `float`.
            linear: The linear value. Expected type: `float`.
            quadratic: The quadratic value. Expected type: `float`.

        Returns:
            None.
        """
        self._ctx.light_falloff(constant, linear, quadratic)

    def specular_color(self, *args: Any) -> None:
        """Specular color for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).specular_color(*args)

    def normal_material(self) -> None:
        """Normal material for this SketchFacadeThreeDMixin.

        Args:
            None.

        Returns:
            None.
        """
        self._ctx.normal_material()

    @overload
    def ambient_material(self, value: ColorValue, /) -> None:
        ...

    @overload
    def ambient_material(self, gray: Number, /) -> None:
        ...

    @overload
    def ambient_material(self, gray: Number, alpha: Number, /) -> None:
        ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, /) -> None:
        ...

    @overload
    def ambient_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
        ...

    def ambient_material(self, *args: Any) -> None:
        """Ambient material for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).ambient_material(*args)

    @overload
    def specular_material(self, value: ColorValue, /) -> None:
        ...

    @overload
    def specular_material(self, gray: Number, /) -> None:
        ...

    @overload
    def specular_material(self, gray: Number, alpha: Number, /) -> None:
        ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, /) -> None:
        ...

    @overload
    def specular_material(self, v1: Number, v2: Number, v3: Number, alpha: Number, /) -> None:
        ...

    def specular_material(self, *args: Any) -> None:
        """Specular material for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).specular_material(*args)

    def shininess(self, value: float) -> None:
        """Shininess for this SketchFacadeThreeDMixin.

        Args:
            value: The value value. Expected type: `float`.

        Returns:
            None.
        """
        self._ctx.shininess(value)

    def emissive_material(self, *args: Any) -> None:
        """Emissive material for this SketchFacadeThreeDMixin.

        Args:
            *args: Additional positional arguments. Expected type: `Any`.

        Returns:
            None.
        """
        cast(Any, self._ctx).emissive_material(*args)

    def metalness(self, value: float) -> None:
        """Metalness for this SketchFacadeThreeDMixin.

        Args:
            value: The value value. Expected type: `float`.

        Returns:
            None.
        """
        self._ctx.metalness(value)

    def texture_mode(self, mode: Any = None) -> Any:
        """Texture mode for this SketchFacadeThreeDMixin.

        Args:
            mode: The mode value. Expected type: `Any`. Defaults to `None`.

        Returns:
            The return value. Type: `Any`.
        """
        return self._ctx.texture_mode(mode)

    def texture_wrap(self, wrap_x: Any = None, wrap_y: Any = None) -> Any:
        """Texture wrap for this SketchFacadeThreeDMixin.

        Args:
            wrap_x: The wrap x value. Expected type: `Any`. Defaults to `None`.
            wrap_y: The wrap y value. Expected type: `Any`. Defaults to `None`.

        Returns:
            The return value. Type: `Any`.
        """
        return self._ctx.texture_wrap(wrap_x, wrap_y)

    def texture(self, image: Image) -> None:
        """Texture for this SketchFacadeThreeDMixin.

        Args:
            image: The image value. Expected type: `Image`.

        Returns:
            None.
        """
        self._ctx.texture(image)

    def plane(self, width: float, height: float | None = None) -> None:
        """Plane for this SketchFacadeThreeDMixin.

        Args:
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.

        Returns:
            None.
        """
        self._ctx.plane(width, height)

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        """Box for this SketchFacadeThreeDMixin.

        Args:
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
            depth: The depth value. Expected type: `float | None`. Defaults to `None`.

        Returns:
            None.
        """
        self._ctx.box(width, height, depth)

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        """Sphere for this SketchFacadeThreeDMixin.

        Args:
            radius: The radius value. Expected type: `float`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `16`.

        Returns:
            None.
        """
        self._ctx.sphere(radius, detail_x, detail_y)

    def ellipsoid(
        self,
        radius_x: float,
        radius_y: float | None = None,
        radius_z: float | None = None,
        detail_x: int = 24,
        detail_y: int = 16,
    ) -> None:
        """Ellipsoid for this SketchFacadeThreeDMixin.

        Args:
            radius_x: The radius x value. Expected type: `float`.
            radius_y: The radius y value. Expected type: `float | None`. Defaults to `None`.
            radius_z: The radius z value. Expected type: `float | None`. Defaults to `None`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `16`.

        Returns:
            None.
        """
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
        """Cylinder for this SketchFacadeThreeDMixin.

        Args:
            radius: The radius value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
            bottom_cap: The bottom cap value. Expected type: `bool`. Defaults to `True`.
            top_cap: The top cap value. Expected type: `bool`. Defaults to `True`.

        Returns:
            None.
        """
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
        """Cone for this SketchFacadeThreeDMixin.

        Args:
            radius: The radius value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `1`.
            cap: The cap value. Expected type: `bool`. Defaults to `True`.

        Returns:
            None.
        """
        self._ctx.cone(radius, height, detail_x, detail_y, cap=cap)

    def torus(
        self,
        radius: float,
        tube_radius: float | None = None,
        detail_x: int = 24,
        detail_y: int = 12,
    ) -> None:
        """Torus for this SketchFacadeThreeDMixin.

        Args:
            radius: The radius value. Expected type: `float`.
            tube_radius: The tube radius value. Expected type: `float | None`. Defaults to `None`.
            detail_x: The detail x value. Expected type: `int`. Defaults to `24`.
            detail_y: The detail y value. Expected type: `int`. Defaults to `12`.

        Returns:
            None.
        """
        self._ctx.torus(radius, tube_radius, detail_x, detail_y)

    def create_model(self, mesh: Mesh3D | Model3D) -> Model3D:
        """Create and return a model value.

        Args:
            mesh: The mesh value. Expected type: `Mesh3D | Model3D`.

        Returns:
            The return value. Type: `Model3D`.
        """
        return self._ctx.create_model(mesh)

    def normal(self, x: float, y: float, z: float) -> None:
        """Normal for this SketchFacadeThreeDMixin.

        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            z: The z value. Expected type: `float`.

        Returns:
            None.
        """
        self._ctx.normal(x, y, z)

    def vertex_property(self, name: str, value: object) -> None:
        """Vertex property for this SketchFacadeThreeDMixin.

        Args:
            name: The name value. Expected type: `str`.
            value: The value value. Expected type: `object`.

        Returns:
            None.
        """
        self._ctx.vertex_property(name, value)

    def build_geometry(self, callback: Any) -> Model3D:
        """Build geometry for this SketchFacadeThreeDMixin.

        Args:
            callback: The callback value. Expected type: `Any`.

        Returns:
            The return value. Type: `Model3D`.
        """
        return self._ctx.build_geometry(callback)

    def free_geometry(self, model_value: Model3D) -> None:
        """Free geometry for this SketchFacadeThreeDMixin.

        Args:
            model_value: The model value value. Expected type: `Model3D`.

        Returns:
            None.
        """
        self._ctx.free_geometry(model_value)

    def flip_u(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        """Flip u for this SketchFacadeThreeDMixin.

        Args:
            mesh_or_model: The mesh or model value. Expected type: `Mesh3D | Model3D`.

        Returns:
            The return value. Type: `Mesh3D | Model3D`.
        """
        return self._ctx.flip_u(mesh_or_model)

    def flip_v(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        """Flip v for this SketchFacadeThreeDMixin.

        Args:
            mesh_or_model: The mesh or model value. Expected type: `Mesh3D | Model3D`.

        Returns:
            The return value. Type: `Mesh3D | Model3D`.
        """
        return self._ctx.flip_v(mesh_or_model)

    def load_model(
        self, path: str | Path, normalize: bool = False, *, package: str | None = None
    ) -> Model3D:
        """Load and return model.

        Args:
            path: The path value. Expected type: `str | Path`.
            normalize: The normalize value. Expected type: `bool`. Defaults to `False`.
            package: The package value. Expected type: `str | None`. Defaults to `None`.

        Returns:
            The return value. Type: `Model3D`.
        """
        return _load_model(path, normalize, package=package)

    async def load_model_async(
        self, path: str | Path, normalize: bool = False, *, package: str | None = None
    ) -> Model3D:
        """Load and return model asynchronously.

        Args:
            path: The path value. Expected type: `str | Path`.
            normalize: The normalize value. Expected type: `bool`. Defaults to `False`.
            package: The package value. Expected type: `str | None`. Defaults to `None`.

        Returns:
            The return value. Type: `Model3D`.
        """
        return await _load_model_async(path, normalize, package=package)

    def model(self, shape: Mesh3D | Model3D) -> None:
        """Model for this SketchFacadeThreeDMixin.

        Args:
            shape: The shape value. Expected type: `Mesh3D | Model3D`.

        Returns:
            None.
        """
        self._ctx.model(shape)

    def save_obj(self, model_value: Model3D, path: str | Path) -> Path:
        """Save obj data to the requested destination.

        Args:
            model_value: The model value value. Expected type: `Model3D`.
            path: The path value. Expected type: `str | Path`.

        Returns:
            The return value. Type: `Path`.
        """
        return self._ctx.save_obj(model_value, path)

    def save_stl(self, model_value: Model3D, path: str | Path) -> Path:
        """Save stl data to the requested destination.

        Args:
            model_value: The model value value. Expected type: `Model3D`.
            path: The path value. Expected type: `str | Path`.

        Returns:
            The return value. Type: `Path`.
        """
        return self._ctx.save_stl(model_value, path)

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        """Load and return shader.

        Args:
            vertex_path: The vertex path value. Expected type: `str | Path`.
            fragment_path: The fragment path value. Expected type: `str | Path`.

        Returns:
            The return value. Type: `Shader3D`.
        """
        return self._ctx.load_shader(vertex_path, fragment_path)

    async def load_shader_async(
        self, vertex_path: str | Path, fragment_path: str | Path
    ) -> Shader3D:
        """Load and return shader asynchronously.

        Args:
            vertex_path: The vertex path value. Expected type: `str | Path`.
            fragment_path: The fragment path value. Expected type: `str | Path`.

        Returns:
            The return value. Type: `Shader3D`.
        """
        return await _load_shader_async(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        """Create and return a shader value.

        Args:
            vertex_source: The vertex source value. Expected type: `str`.
            fragment_source: The fragment source value. Expected type: `str`.

        Returns:
            The return value. Type: `Shader3D`.
        """
        return self._ctx.create_shader(vertex_source, fragment_source)

    def shader(self, shader_program: Shader3D) -> None:
        """Shader for this SketchFacadeThreeDMixin.

        Args:
            shader_program: The shader program value. Expected type: `Shader3D`.

        Returns:
            None.
        """
        self._ctx.shader(shader_program)

    def reset_shader(self) -> None:
        """Reset shader for this SketchFacadeThreeDMixin.

        Args:
            None.

        Returns:
            None.
        """
        self._ctx.reset_shader()

    def set_shader_uniform(self, name: str, value: ShaderUniformValue) -> None:
        """Set the shader uniform value.

        Args:
            name: The name value. Expected type: `str`.
            value: The value value. Expected type: `ShaderUniformValue`.

        Returns:
            None.
        """
        self._ctx.set_shader_uniform(name, value)

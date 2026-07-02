"""3D model rendering method for SketchContext."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from gummysnake.backend.canvas_runtime.renderer.batch_state import ModelBatchKey
from gummysnake.context_mixins.three_d._protocols import ThreeDContextHost
from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Mesh3D,
    Model3D,
    Shader3D,
    _model_rust_handle,
)
from gummysnake.drawing.renderer3d.model import _ensure_model_rust_handle
from gummysnake.drawing.renderer3d.types import (
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
)
from gummysnake.drawing.software3d import (
    ShadedFace,
    rasterize_face_payload_region,
    rasterize_faces_image_region,
)
from gummysnake.drawing.software3d.payloads import (
    camera_payload,
    light_payloads,
    material_payload,
    model_transform_payload,
    projection_payload,
)
from gummysnake.drawing.software3d.shading import texture_image
from gummysnake.exceptions import ArgumentValidationError, UnsupportedFeatureError


def _three_d(self: Any) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)


_IDENTITY_MODEL_TRANSFORM: tuple[float, ...] = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


class ThreeDModelMixin:
    renderer: Any
    state: Any
    _camera3d: Camera3D
    _projection3d: PerspectiveProjection | OrthographicProjection | FrustumProjection
    _lights3d: list[Light3D]
    _geometry_build_models: list[Model3D] | None
    _material3d: Material3D | None
    _normal_material3d: bool
    _shader3d: Shader3D | None

    @property
    def width(self) -> int:
        """Width.

        Args:
            None.

        Returns:
            The return value. Type: `int`.
        """
        raise NotImplementedError

    @property
    def height(self) -> int:
        """Height.

        Args:
            None.

        Returns:
            The return value. Type: `int`.
        """
        raise NotImplementedError

    def model(self, shape: Mesh3D | Model3D) -> None:
        """Model.

        Args:
            shape: The shape value. Expected type: `Mesh3D | Model3D`.

        Returns:
            None.
        """
        _three_d(self)._require_webgl_mode("model")
        if isinstance(shape, Mesh3D):
            model = Model3D(meshes=(shape,))
        elif isinstance(shape, Model3D):
            model = shape
        else:
            raise ArgumentValidationError("model() requires a Mesh3D or Model3D value.")

        if self._geometry_build_models is not None:
            self._geometry_build_models.append(model)
            return

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
        if self.state.style.stroke_color is not None:
            raise UnsupportedFeatureError(
                "model() stroke outlines require a retained GPU model-stroke "
                "implementation; CPU projected-face stroke fallback is disabled. "
                "Call no_stroke() before drawing retained GPU models."
            )
        if not draw_fill:
            return
        if texture is not None:
            if self._draw_model_textured_direct(model, texture, material, model_transform):
                return
            raise UnsupportedFeatureError(
                "model() textured drawing requires retained GPU textured-model support; "
                "CPU projected-face texture fallback is disabled."
            )

        handle = _ensure_model_rust_handle(model)
        transform_payload = model_transform_payload(model_transform)
        if handle is not None and self._queue_model_shaded_direct(
            handle,
            material,
            transform_payload,
        ):
            return
        if self._draw_model_shaded_direct(model, material, model_transform):
            return
        raise UnsupportedFeatureError(
            "model() requires retained GPU model drawing; CPU projected-face payload "
            "drawing is disabled."
        )

    def _draw_model_fast(
        self, shape: Mesh3D | Model3D, *, model_transform: Any | None = None
    ) -> None:
        _three_d(self)._require_webgl_mode("model")
        if isinstance(shape, Mesh3D):
            model = Model3D(meshes=(shape,))
        elif isinstance(shape, Model3D):
            model = shape
        else:
            raise ArgumentValidationError("model() requires a Mesh3D or Model3D value.")

        if self._geometry_build_models is not None:
            self._geometry_build_models.append(model)
            return

        material = _three_d(self)._effective_3d_material()
        draw_fill = (
            self._normal_material3d
            or self._material3d is not None
            or self.state.style.fill_color is not None
        )
        texture = None if self._normal_material3d else texture_image(material)
        if draw_fill and self.state.style.stroke_color is None:
            handle = _ensure_model_rust_handle(model)
            effective_transform = (
                self.state.transform.matrix if model_transform is None else model_transform
            )
            if texture is not None and self._draw_model_textured_direct(
                model, texture, material, effective_transform
            ):
                return
            if texture is None and handle is not None:
                if isinstance(effective_transform, tuple) and len(effective_transform) == 16:
                    transform_payload = (
                        None
                        if effective_transform == _IDENTITY_MODEL_TRANSFORM
                        else effective_transform
                    )
                else:
                    transform_payload = model_transform_payload(effective_transform)
                if self._queue_model_shaded_direct(handle, material, transform_payload):
                    return
                if self._draw_model_shaded_direct(model, material, effective_transform):
                    return

        self.model(model)

    def _queue_model_shaded_direct(
        self,
        handle: Any,
        material: Material3D,
        transform_payload: tuple[float, ...] | None,
    ) -> bool:
        queue = getattr(self.renderer, "_queue_model_batch", None)
        if not callable(queue):
            return False
        transform = transform_payload or _IDENTITY_MODEL_TRANSFORM
        source_signature = (
            id(handle),
            id(self._camera3d),
            id(self._projection3d),
            id(material),
            id(self._lights3d),
            len(self._lights3d),
            self._normal_material3d,
        )
        batch_state = getattr(self.renderer, "_model_batch_state", None)
        existing_key = getattr(batch_state, "key", None)
        if (
            existing_key is not None
            and getattr(existing_key, "source_signature", None) == source_signature
        ):
            return bool(queue(existing_key, transform))
        key = ModelBatchKey(
            model_handle=handle,
            camera=camera_payload(self._camera3d),
            projection=projection_payload(self._projection3d),
            viewport_width=float(self.width),
            viewport_height=float(self.height),
            material=material_payload(material),
            lights=light_payloads(self._lights3d),
            normal_material=self._normal_material3d,
            cull_backfaces=True,
            source_signature=source_signature,
        )
        return bool(queue(key, transform))

    def _rust_model_draw_resources(
        self, model: Model3D, method_name: str
    ) -> tuple[Any, Callable[..., Any]] | None:
        handle = _model_rust_handle(model)
        if handle is None:
            return None
        require_canvas = getattr(self.renderer, "_require_canvas", None)
        if not callable(require_canvas):
            return None
        draw = getattr(require_canvas(), method_name, None)
        if not callable(draw):
            return None
        flush_model_batch = getattr(self.renderer, "_flush_model_batch", None)
        if callable(flush_model_batch):
            flush_model_batch()
        flush_line_batch = getattr(self.renderer, "_flush_line_batch", None)
        if callable(flush_line_batch):
            flush_line_batch()
        return handle, draw

    def _count_renderer_counter(self, name: str, amount: int = 1) -> None:
        count = getattr(self.renderer, "_count", None)
        if callable(count):
            count(name, amount)

    def _draw_model_shaded_direct(
        self,
        model: Model3D,
        material: Material3D,
        model_transform: Any | None,
    ) -> bool:
        resources = self._rust_model_draw_resources(model, "draw_model_shaded")
        if resources is None:
            return False
        handle, draw = resources
        transform_payload = model_transform_payload(model_transform)
        draw(
            handle,
            camera_payload(self._camera3d),
            projection_payload(self._projection3d),
            float(self.width),
            float(self.height),
            material_payload(material),
            light_payloads(self._lights3d),
            self._normal_material3d,
            True,
            transform_payload,
        )
        self._count_renderer_counter("direct_model_draws")
        return True

    def _draw_model_textured_direct(
        self,
        model: Model3D,
        texture: Any,
        material: Material3D,
        model_transform: Any | None,
    ) -> bool:
        rust_image = getattr(texture, "rust_image", None)
        rust_image = getattr(rust_image, "_rust_image", None)
        if rust_image is None:
            return False
        resources = self._rust_model_draw_resources(model, "draw_model_textured")
        if resources is None:
            return False
        handle, draw = resources
        transform_payload = model_transform_payload(model_transform)
        drawn = bool(
            draw(
                handle,
                rust_image,
                camera_payload(self._camera3d),
                projection_payload(self._projection3d),
                float(self.width),
                float(self.height),
                material_payload(material),
                light_payloads(self._lights3d),
                self._normal_material3d,
                True,
                transform_payload,
            )
        )
        if drawn:
            self._count_renderer_counter("direct_model_draws")
        return drawn

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

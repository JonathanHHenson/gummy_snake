# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
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
    VertexPropertyValue,
)
from gummysnake.sketch.facade_mixins.base import ColorValue, Number, SketchFacadeBaseMixin

CameraArg = Camera3D | Number
ColorArg = ColorValue | Number

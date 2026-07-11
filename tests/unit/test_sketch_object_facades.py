"""Characterization tests for the explicit object-mode sketch facade."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, cast, get_overloads

import gummysnake as gs
from gummysnake.sketch.facade_mixins.media import SketchFacadeMediaMixin
from gummysnake.sketch.facade_mixins.media_audio import SketchFacadeAudioMixin
from gummysnake.sketch.facade_mixins.media_capture import SketchFacadeCaptureMixin
from gummysnake.sketch.facade_mixins.media_compositing import SketchFacadeCompositingMixin
from gummysnake.sketch.facade_mixins.media_image import SketchFacadeImageMixin
from gummysnake.sketch.facade_mixins.media_pixels import SketchFacadePixelsMixin
from gummysnake.sketch.facade_mixins.media_text import SketchFacadeTextMixin
from gummysnake.sketch.facade_mixins.three_d_facade.camera import SketchFacadeCameraMixin
from gummysnake.sketch.facade_mixins.three_d_facade.controls import SketchFacadeControlsMixin
from gummysnake.sketch.facade_mixins.three_d_facade.geometry import SketchFacadeGeometryMixin
from gummysnake.sketch.facade_mixins.three_d_facade.lighting import SketchFacadeLightingMixin
from gummysnake.sketch.facade_mixins.three_d_facade.materials import SketchFacadeMaterialsMixin
from gummysnake.sketch.facade_mixins.three_d_facade.mixin import SketchFacadeThreeDMixin
from gummysnake.sketch.facade_mixins.three_d_facade.models import SketchFacadeModelsMixin
from gummysnake.sketch.facade_mixins.three_d_facade.primitives import SketchFacadePrimitivesMixin


def test_media_and_three_d_capability_compositions_are_explicit() -> None:
    """The stable facade names compose focused, non-overlapping capability groups."""
    assert SketchFacadeMediaMixin.__bases__ == (
        SketchFacadeCaptureMixin,
        SketchFacadeAudioMixin,
        SketchFacadeImageMixin,
        SketchFacadeTextMixin,
        SketchFacadePixelsMixin,
        SketchFacadeCompositingMixin,
    )
    assert SketchFacadeThreeDMixin.__bases__ == (
        SketchFacadeCameraMixin,
        SketchFacadeControlsMixin,
        SketchFacadeLightingMixin,
        SketchFacadeMaterialsMixin,
        SketchFacadeGeometryMixin,
        SketchFacadePrimitivesMixin,
        SketchFacadeModelsMixin,
    )


def test_facade_package_has_no_same_stem_module_package_collisions() -> None:
    """Focused facade modules do not shadow packages with the same stem."""
    root = Path(gs.__file__).parent / "sketch" / "facade_mixins"
    for module in root.glob("*.py"):
        assert not (root / module.stem).is_dir(), module.stem
    three_d_root = root / "three_d_facade"
    for module in three_d_root.glob("*.py"):
        assert not (three_d_root / module.stem).is_dir(), module.stem


def test_object_facade_preserves_overload_facing_methods_and_signatures() -> None:
    """Representative overloaded forwards retain their public call contracts."""
    assert str(inspect.signature(gs.Sketch.image)) == "(self, *args: 'ImageCallArg') -> 'None'"
    assert str(inspect.signature(gs.Sketch.copy)) == "(self, *args: 'CopyArg') -> 'Image | None'"
    assert (
        str(inspect.signature(gs.Sketch.create_camera))
        == "(self, *args: 'CameraArg') -> 'Camera3D'"
    )
    assert len(get_overloads(gs.Sketch.image)) == 3
    assert len(get_overloads(gs.Sketch.copy)) == 4
    assert len(get_overloads(gs.Sketch.text_property)) == 3
    assert len(get_overloads(gs.Sketch.ambient_light)) == 5
    assert len(get_overloads(gs.Sketch.directional_light)) == 5
    assert len(get_overloads(gs.Sketch.point_light)) == 5
    assert len(get_overloads(gs.Sketch.ambient_material)) == 5
    assert len(get_overloads(gs.Sketch.specular_material)) == 5


def test_public_sketch_methods_have_editor_help_docstrings() -> None:
    """All public object-mode methods expose help without relying on inheritance gaps."""
    undocumented = [
        name
        for name, member in inspect.getmembers(gs.Sketch, inspect.isfunction)
        if not name.startswith("_") and not inspect.getdoc(member)
    ]
    assert undocumented == []


def test_media_and_three_d_forwards_delegate_to_the_active_context() -> None:
    """The split keeps forwarding ownership in the canonical sketch context."""

    class ContextProbe:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        def __getattr__(self, name: str):
            def method(*args: object, **kwargs: object) -> str:
                self.calls.append((name, args, kwargs))
                return name

            return method

    sketch = gs.Sketch()
    probe = ContextProbe()
    sketch.context = cast(Any, probe)

    sketch.image(cast(Any, "sprite"), 1.0, 2.0)
    sketch.blend(0, 0, 1, 1, 0, 0, 1, 1, gs.BLEND)
    assert sketch.get(2, 3) == "get"
    assert sketch.camera() == "camera"
    assert sketch.orbit_control() == "orbit_control"
    sketch.ambient_light(255)
    sketch.texture(cast(Any, "texture"))
    sketch.box(2)
    sketch.model(cast(Any, "model"))
    assert [name for name, _, _ in probe.calls] == [
        "image",
        "blend",
        "get",
        "camera",
        "orbit_control",
        "ambient_light",
        "texture",
        "box",
        "model",
    ]

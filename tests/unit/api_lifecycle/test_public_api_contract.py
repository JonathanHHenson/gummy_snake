"""Freeze public Python names, signatures, and class metadata.

The fingerprints below are intentionally fixed values. Update one only after an explicit public
API decision, never by generating a snapshot as part of a refactor.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from enum import Enum
from types import ModuleType

import gummysnake as gs
import gummysnake.api.global_mode as global_mode
import gummysnake.api.three_d_api as three_d
import gummysnake.api.three_d_api.camera_api as three_d_camera
import gummysnake.api.three_d_api.controls_and_lighting as three_d_lighting
import gummysnake.api.three_d_api.materials_and_primitives as three_d_materials
import gummysnake.constants as constants
import gummysnake.ecs as ecs
import gummysnake.synth as synth

_PUBLIC_MODULES: dict[str, ModuleType] = {
    "gummysnake": gs,
    "gummysnake.api.global_mode": global_mode,
    "gummysnake.constants": constants,
    "gummysnake.ecs": ecs,
    "gummysnake.synth": synth,
}
_EXPECTED_FINGERPRINTS = {
    "gummysnake": {
        "count": 493,
        "exports": "5dca6bf8d40d10123a2528d07d7189da3cf86feae78c69f48616abf8f5fc6e2d",
        "surface": "d223cb6541a03b0ef9bcde2509f8ec53c91de01cab12e091ab9f007ad2529f01",
    },
    "gummysnake.api.global_mode": {
        "count": 330,
        "exports": "298c551e15170bb0c65f997e0720b109968adde1f5ec4732addf8805917269e8",
        "surface": "dc18ec708515c39493fbc7742b403b654e96871ff0f2a51af3288cbd1a59ae92",
    },
    "gummysnake.constants": {
        "count": 116,
        "exports": "1ea68df945829a67e2337e0123502993ff3f76020fc1bca13816ab5de37ebc10",
        "surface": "c65552d8d0f8ba8221d46abfab2b076eaedd3c7aae73b77f0ca056a1ed494405",
    },
    "gummysnake.ecs": {
        "count": 52,
        "exports": "3dc3b05179ed4446011ff5b0a7ef163f837e49447b78dd91f44b205038dfffb1",
        "surface": "deb550e17350c64ce08134c6c29b8832ed8fd36e92510695a0de8a3ce55b17f4",
    },
    "gummysnake.synth": {
        "count": 64,
        "exports": "c6630523c8a5ca57fb3e74bbbac98cd8588f5d1bbf64a044e73c3f7b9c03b0a4",
        "surface": "c110b48da4ef1df0e5e3ee28e5ad9f6b6986f25f2063d62a1271c91f592f3b9b",
    },
}
_EXPECTED_CLASS_METADATA = {
    "Sketch": ("gummysnake.sketch.runtime", "Sketch"),
    "Image": ("gummysnake.assets.image.core", "Image"),
    "Sound": ("gummysnake.assets.sound", "Sound"),
    "Entity": ("gummysnake.ecs.runtime_view_model.entity_mutation", "Entity"),
    "Track": ("gummysnake.synth.synth_runtime.playback_export.track", "Track"),
}


def _describe_public_value(value: object) -> dict[str, object | None]:
    """Return the stable public metadata included in a surface fingerprint."""

    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "module": getattr(value, "__module__", None),
        "qualname": getattr(value, "__qualname__", None),
        "signature": str(inspect.signature(value)) if inspect.isfunction(value) else None,
        "enum_value": value.value if isinstance(value, Enum) else None,
    }


def _digest(payload: object) -> str:
    serialized = json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def test_public_module_exports_and_surface_metadata_are_frozen() -> None:
    for module_name, module in _PUBLIC_MODULES.items():
        exports = list(module.__all__)
        surface = [(name, _describe_public_value(getattr(module, name))) for name in exports]

        assert {
            "count": len(exports),
            "exports": _digest(exports),
            "surface": _digest(surface),
        } == _EXPECTED_FINGERPRINTS[module_name]


def test_public_exports_are_present_and_documented() -> None:
    for module_name, module in _PUBLIC_MODULES.items():
        for name in module.__all__:
            value = getattr(module, name)
            if inspect.isfunction(value):
                assert inspect.getdoc(value), f"{module_name}.{name} needs a public docstring"


def test_global_mode_exports_are_top_level_identity_aliases() -> None:
    for name in global_mode.__all__:
        assert getattr(gs, name) is getattr(global_mode, name), name


def test_split_three_d_modules_preserve_public_object_identity() -> None:
    implementation_modules = (three_d_camera, three_d_lighting, three_d_materials)
    for name in three_d.__all__:
        public_value = getattr(three_d, name)
        assert any(
            getattr(module, name, None) is public_value for module in implementation_modules
        ), name


def test_relocated_public_class_metadata_is_explicitly_frozen() -> None:
    public_classes = {
        "Sketch": gs.Sketch,
        "Image": gs.Image,
        "Sound": gs.Sound,
        "Entity": ecs.Entity,
        "Track": synth.Track,
    }

    assert {
        name: (value.__module__, value.__qualname__) for name, value in public_classes.items()
    } == _EXPECTED_CLASS_METADATA

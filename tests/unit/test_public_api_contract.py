"""Freeze public Python names, signatures, and compatibility import paths.

The fingerprints below are intentionally fixed values. Update one only after an explicit public
compatibility decision, never by generating a snapshot as part of a refactor.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from enum import Enum
from types import ModuleType

import gummysnake as gs
import gummysnake.api.global_mode as global_mode
import gummysnake.api.three_d as three_d
import gummysnake.api.three_d_api.camera_api as three_d_camera
import gummysnake.api.three_d_api.controls_and_lighting as three_d_lighting
import gummysnake.api.three_d_api.materials_and_primitives as three_d_materials
import gummysnake.constants as constants
import gummysnake.ecs as ecs
import gummysnake.synth as synth
import gummysnake.synth.core as synth_core

_PUBLIC_MODULES: dict[str, ModuleType] = {
    "gummysnake": gs,
    "gummysnake.api.global_mode": global_mode,
    "gummysnake.constants": constants,
    "gummysnake.ecs": ecs,
    "gummysnake.synth": synth,
}
_EXPECTED_FINGERPRINTS = {
    "gummysnake": {
        "count": 491,
        "exports": "1f82440a679bc9ea277c021f791d2f548991a98e87ae60fe67cd88c51b3f2ce7",
        "surface": "18cb1303be430673d206b079f256021d5c51244c749b7d75f4663e51625c3d11",
    },
    "gummysnake.api.global_mode": {
        "count": 329,
        "exports": "85b256961688b03de29c3c2fff8c63fea8c3990b01a936e6190b6f8fbb62edd8",
        "surface": "4484001cc703e35d2b67ec636e49f40d895004249ba461369d75e51d36dbf6c6",
    },
    "gummysnake.constants": {
        "count": 116,
        "exports": "1ea68df945829a67e2337e0123502993ff3f76020fc1bca13816ab5de37ebc10",
        "surface": "c65552d8d0f8ba8221d46abfab2b076eaedd3c7aae73b77f0ca056a1ed494405",
    },
    "gummysnake.ecs": {
        "count": 53,
        "exports": "405a671c7a32ba7120bf1a8df627ba7cd634ac920b315dde797576aa852d796c",
        "surface": "80ba8a26d6371e0759e96a883cc73f82abd74ee2e97756f503a3be8d0c2fd6ae",
    },
    "gummysnake.synth": {
        "count": 60,
        "exports": "8c8ba2dfaf19f83721f9d8ab85d3608c267567f3b3bc86bb8d24732e7212b2cb",
        "surface": "c6b8a0c1755bac8aeb581d6a4b8cd4597c03d4b6ee393281e4bf0fe1ec953934",
    },
}
_COMPATIBILITY_MODULES = (
    "gummysnake.api.advanced",
    "gummysnake._fast_draw",
    "gummysnake.core.input_events",
    "gummysnake.core.state",
    "gummysnake.assets.sound",
    "gummysnake.ecs.actions",
    "gummysnake.ecs.systems",
    "gummysnake.ecs.runtime_views",
    "gummysnake.ecs.physical",
    "gummysnake.ecs.world",
    "gummysnake.drawing.renderer3d",
    "gummysnake.drawing.software3d",
    "gummysnake.rust.canvas",
    "gummysnake.rust.ecs",
)
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


def test_supported_compatibility_modules_remain_importable() -> None:
    for module_name in _COMPATIBILITY_MODULES:
        assert importlib.import_module(module_name).__name__ == module_name


def test_split_synth_and_three_d_facades_preserve_public_object_identity() -> None:
    assert synth.__all__ == synth_core.__all__
    for name in synth.__all__:
        assert getattr(synth, name) is getattr(synth_core, name), name

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

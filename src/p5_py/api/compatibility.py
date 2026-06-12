"""Compatibility metadata and unsupported browser/data APIs."""

from __future__ import annotations

from p5_py.exceptions import UnsupportedFeatureError

COMPATIBILITY_MATRIX = {
    "lifecycle": "supported",
    "global_mode": "supported",
    "canvas": "supported",
    "2d_primitives": "supported",
    "paths_and_curves": "partial",
    "color": "supported",
    "transforms": "supported",
    "mouse_keyboard_input": "partial",
    "dom": "excluded",
    "xml": "excluded",
    "table": "excluded",
    "webgl": "deferred",
    "sound": "deferred",
}


def unsupported_feature(name: str, reason: str) -> None:
    raise UnsupportedFeatureError(f"{name} is not supported by p5-py. {reason}")


def create_div(*_args, **_kwargs):
    unsupported_feature("create_div/createDiv", "DOM APIs are intentionally excluded.")


def create_button(*_args, **_kwargs):
    unsupported_feature("create_button/createButton", "DOM APIs are intentionally excluded.")


def select(*_args, **_kwargs):
    unsupported_feature("select", "DOM APIs are intentionally excluded.")


def load_xml(*_args, **_kwargs):
    unsupported_feature("load_xml/loadXML", "p5.XML is intentionally excluded.")


def load_table(*_args, **_kwargs):
    unsupported_feature(
        "load_table/loadTable",
        "p5.Table and p5.TableRow are intentionally excluded.",
    )


createDiv = create_div
createButton = create_button
loadXML = load_xml
loadTable = load_table

__all__ = [
    "COMPATIBILITY_MATRIX",
    "unsupported_feature",
    "create_div",
    "create_button",
    "select",
    "load_xml",
    "load_table",
    "createDiv",
    "createButton",
    "loadXML",
    "loadTable",
]

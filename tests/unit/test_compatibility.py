import pytest

import p5_py as p5
from p5_py import ArgumentValidationError, UnsupportedFeatureError


def test_dom_apis_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        p5.createDiv("hello")


def test_table_and_xml_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        p5.loadXML("data.xml")
    with pytest.raises(UnsupportedFeatureError):
        p5.loadTable("data.csv")


def test_advanced_3d_and_media_compatibility_matrix_entries_track_partial_and_deferred_status():
    partial_keys = {
        "webgl",
        "webgl_renderer",
        "3d_primitives",
        "camera_projection",
        "lights_materials",
        "textures",
        "models",
        "shaders",
        "sound",
        "sound_playback",
        "media_playback",
        "media_capture",
    }
    deferred_keys = {
        "sound_analysis",
        "sound_synthesis",
    }

    for key in partial_keys:
        assert p5.COMPATIBILITY_MATRIX[key] == "partial"
    for key in deferred_keys:
        assert p5.COMPATIBILITY_MATRIX[key] == "deferred"


def test_media_stubs_now_fail_with_explicit_runtime_errors(tmp_path):
    missing_video = tmp_path / "missing.mp4"

    with pytest.raises(ArgumentValidationError, match="Video file does not exist"):
        p5.createVideo(missing_video)

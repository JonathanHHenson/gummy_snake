import pytest

import gummysnake as gs
from gummysnake import ArgumentValidationError, UnsupportedFeatureError


def test_dom_apis_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        gs.create_div("hello")


def test_table_and_xml_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        gs.load_xml("data.xml")
    with pytest.raises(UnsupportedFeatureError):
        gs.load_table("data.csv")


@pytest.mark.parametrize(
    "name",
    [
        "create_button",
        "create_input",
        "create_slider",
        "create_checkbox",
        "create_select",
        "create_radio",
        "create_color_picker",
        "create_file_input",
        "select",
        "select_all",
        "remove_elements",
    ],
)
def test_dom_and_browser_file_input_stubs_raise_package_errors(name):
    with pytest.raises(UnsupportedFeatureError, match="Gummy Snake"):
        getattr(gs, name)()


@pytest.mark.parametrize(
    "name",
    [
        "load_xml",
        "load_table",
        "table_row",
        "create_blob",
        "save_blob",
        "load_blob",
        "get_url",
        "get_url_path",
        "get_url_params",
        "local_storage",
    ],
)
def test_browser_io_and_data_exclusion_stubs_raise_package_errors(name):
    with pytest.raises(UnsupportedFeatureError, match="Gummy Snake"):
        getattr(gs, name)()


@pytest.mark.parametrize(
    "name",
    [
        "request_pointer_lock",
        "exit_pointer_lock",
        "acceleration_x",
        "acceleration_y",
        "acceleration_z",
        "previous_acceleration_x",
        "previous_acceleration_y",
        "previous_acceleration_z",
        "rotation_x",
        "rotation_y",
        "rotation_z",
        "previous_rotation_x",
        "previous_rotation_y",
        "previous_rotation_z",
        "orientation_x",
        "orientation_y",
        "orientation_z",
        "device_moved",
        "device_turned",
        "device_shaken",
    ],
)
def test_pointer_lock_and_sensor_stubs_raise_package_errors(name):
    with pytest.raises(UnsupportedFeatureError, match="Gummy Snake"):
        getattr(gs, name)()


@pytest.mark.parametrize(
    "name",
    [
        "begin_contour",
        "end_contour",
        "begin_clip",
        "clip",
        "end_clip",
        "tint",
        "no_tint",
        "save_frames",
        "save_gif",
        "normal",
        "vertex_property",
        "text_to_points",
        "text_to_paths",
        "text_to_contours",
        "text_to_model",
        "drawing_context",
        "build_geometry",
        "free_geometry",
    ],
)
def test_rendering_text_and_geometry_gap_stubs_raise_package_errors(name):
    with pytest.raises(UnsupportedFeatureError, match="Gummy Snake"):
        getattr(gs, name)()


@pytest.mark.parametrize(
    "name",
    [
        "create_filter_shader",
        "filter_shader",
        "create_image_shader",
        "create_stroke_shader",
        "create_color_shader",
        "create_material_shader",
        "normal_shader",
        "webgpu_context",
        "create_storage_buffer",
        "update_storage_buffer",
        "read_storage_buffer",
        "create_compute_shader",
        "dispatch_compute",
        "strands",
    ],
)
def test_advanced_shader_webgpu_and_compute_stubs_raise_package_errors(name):
    with pytest.raises(UnsupportedFeatureError, match="Gummy Snake"):
        getattr(gs, name)()


@pytest.mark.parametrize(
    "name",
    [
        "create_amplitude",
        "create_fft",
        "create_audio_in",
        "create_audio_input",
        "create_oscillator",
        "create_envelope",
        "create_sound_filter",
        "get_audio_context",
    ],
)
def test_sound_analysis_synthesis_and_capture_stubs_raise_package_errors(name):
    with pytest.raises(UnsupportedFeatureError, match="Gummy Snake"):
        getattr(gs, name)()


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
        "device_sensors",
        "webgpu",
    }
    excluded_keys = {
        "dom",
        "xml",
        "table",
        "browser_url_storage",
        "strands_compute",
    }

    for key in partial_keys:
        assert gs.COMPATIBILITY_MATRIX[key] == "partial"
    for key in deferred_keys:
        assert gs.COMPATIBILITY_MATRIX[key] == "deferred"
    for key in excluded_keys:
        assert gs.COMPATIBILITY_MATRIX[key] == "excluded"


def test_media_stubs_now_fail_with_explicit_runtime_errors(tmp_path):
    missing_video = tmp_path / "missing.mp4"

    with pytest.raises(ArgumentValidationError, match="Video file does not exist"):
        gs.create_video(missing_video)

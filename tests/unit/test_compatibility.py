import pytest

import p5_py as p5
from p5_py import UnsupportedFeatureError


def test_dom_apis_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        p5.createDiv("hello")


def test_table_and_xml_are_explicitly_excluded():
    with pytest.raises(UnsupportedFeatureError):
        p5.loadXML("data.xml")
    with pytest.raises(UnsupportedFeatureError):
        p5.loadTable("data.csv")


def test_advanced_3d_and_media_compatibility_matrix_entries_are_deferred():
    deferred_keys = {
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
        "sound_analysis",
        "sound_synthesis",
        "media_playback",
        "media_capture",
    }

    for key in deferred_keys:
        assert p5.COMPATIBILITY_MATRIX[key] == "deferred"


def test_advanced_3d_model_shader_and_media_stubs_are_deferred():
    deferred_calls = [
        (p5.createCamera, ()),
        (p5.camera, ()),
        (p5.perspective, ()),
        (p5.ortho, ()),
        (p5.orbitControl, ()),
        (p5.ambientLight, (255,)),
        (p5.directionalLight, (255, 255, 255, 0, 0, -1)),
        (p5.pointLight, (255, 255, 255, 0, 0, 100)),
        (p5.normalMaterial, ()),
        (p5.ambientMaterial, (255,)),
        (p5.specularMaterial, (255,)),
        (p5.texture, (object(),)),
        (p5.box, (50,)),
        (p5.sphere, (25,)),
        (p5.loadModel, ("shape.obj",)),
        (p5.model, (object(),)),
        (p5.loadShader, ("shader.vert", "shader.frag")),
        (p5.createShader, ("vertex", "fragment")),
        (p5.shader, (object(),)),
        (p5.resetShader, ()),
        (p5.loadSound, ("sound.wav",)),
        (p5.createAudio, ("sound.wav",)),
        (p5.createVideo, ("movie.mp4",)),
        (p5.createCapture, ("video",)),
    ]

    for api, args in deferred_calls:
        with pytest.raises(UnsupportedFeatureError, match="deferred"):
            api(*args)

import numpy as np
import pytest

from gummysnake.drawing.prototype3d import _validate_projection, cube_model, wireframe_segments
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Vec3,
    _mesh_rust_handle,
)
from gummysnake.drawing.software3d import (
    cone_model,
    cylinder_model,
    ellipsoid_model,
    save_obj,
    save_stl,
    torus_model,
)
from gummysnake.drawing.software3d.projection import validate_projection
from gummysnake.exceptions import ArgumentValidationError


def test_mesh3d_prefers_rust_handle_for_canonical_storage(monkeypatch):
    captured: dict[str, object] = {}

    class Handle:
        def to_mesh_payload(self):
            return {
                "vertices": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                "faces": ((0, 1, 2),),
                "normals": ((0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0)),
                "texcoords": (),
            }

    class Runtime:
        def create_mesh3d_handle(self, vertices, faces, normals, texcoords):
            captured["vertices"] = vertices
            captured["faces"] = faces
            captured["normals"] = normals
            captured["texcoords"] = texcoords
            return Handle()

    monkeypatch.setattr("gummysnake.rust.canvas.require_canvas_runtime", lambda: Runtime())

    mesh = Mesh3D(
        vertices=(Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)),
        faces=((0, 1, 2),),
        normals=(Vec3(0, 0, 1), Vec3(0, 0, 1), Vec3(0, 0, 1)),
    )

    assert _mesh_rust_handle(mesh) is not None
    assert captured["vertices"] == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    assert captured["faces"] == [(0, 1, 2)]
    assert captured["normals"] == [(0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    assert mesh.vertex_array().shape == (3, 3)
    assert mesh.vertices[1] == Vec3(1.0, 0.0, 0.0)
    assert mesh.normals[0] == Vec3(0.0, 0.0, 1.0)


def test_model3d_materializes_meshes_as_rust_mesh_wrappers():
    class MeshHandle:
        def to_mesh_payload(self):
            return {
                "vertices": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                "faces": ((0, 1, 2),),
                "texcoords": (),
            }

    class ModelHandle:
        def to_mesh_handle(self):
            return MeshHandle()

        def to_mesh_payload(self):
            raise AssertionError("model payload should not be used when mesh handles are available")

    mesh = Model3D(meshes=None, rust_handle=ModelHandle()).meshes[0]

    assert _mesh_rust_handle(mesh) is not None
    assert mesh.faces == ((0, 1, 2),)


def test_mesh3d_stores_numeric_data_as_readonly_numpy_arrays_with_friendly_views():
    mesh = Mesh3D.from_arrays(
        np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float64,
        ),
        faces=((0, 1, 2), (0, 2, 3, 1)),
        texcoords=np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]),
    )

    vertices = mesh.vertex_array()
    assert isinstance(vertices, np.ndarray)
    assert vertices.shape == (4, 3)
    assert vertices.flags.writeable is False
    assert mesh.face_index_array().tolist() == [0, 1, 2, 0, 2, 3, 1]
    assert mesh.face_offset_array().tolist() == [0, 3, 7]

    assert mesh.vertices == (
        Vec3(0.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(1.0, 1.0, 0.0),
        Vec3(0.0, 1.0, 0.0),
    )
    assert mesh.faces == ((0, 1, 2), (0, 2, 3, 1))
    assert mesh.texcoords == ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    assert mesh.to_python()["vertices"] == mesh.vertices


def test_shared_projection_rules_preserve_prototype_and_software_error_contracts():
    invalid = PerspectiveProjection(near=0)

    with pytest.raises(ValueError, match="projection near plane must be positive\\."):
        _validate_projection(invalid)
    with pytest.raises(ArgumentValidationError, match="projection near plane must be positive\\."):
        validate_projection(invalid)


def test_cube_wireframe_projects_twelve_edges():
    model = cube_model(100)
    camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))
    projection = PerspectiveProjection(fov_y=60, near=1, far=1000)

    lines = wireframe_segments(
        model,
        camera,
        projection,
        viewport_width=200,
        viewport_height=200,
    )

    assert len(model.meshes) == 1
    assert len(model.meshes[0].vertices) == 8
    assert len(model.meshes[0].faces) == 6
    assert len(lines) == 12
    for line in lines:
        assert 0 <= line.start[0] <= 200
        assert 0 <= line.start[1] <= 200
        assert 0 <= line.end[0] <= 200
        assert 0 <= line.end[1] <= 200


def test_camera_and_projection_controls_change_wireframe():
    model = cube_model(100)
    camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))

    perspective_lines = wireframe_segments(
        model,
        camera,
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=200,
        viewport_height=200,
    )
    orthographic_lines = wireframe_segments(
        model,
        camera,
        OrthographicProjection(width=300, height=300, near=1, far=1000),
        viewport_width=200,
        viewport_height=200,
    )
    shifted_camera_lines = wireframe_segments(
        model,
        Camera3D(eye=Vec3(80, 0, 300), target=Vec3(0, 0, 0)),
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=200,
        viewport_height=200,
    )

    assert perspective_lines != orthographic_lines
    assert perspective_lines != shifted_camera_lines


def test_wireframe_projection_honors_far_clipping_plane():
    model = cube_model(100)
    camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))
    projection = PerspectiveProjection(fov_y=60, near=1, far=200)

    lines = wireframe_segments(
        model,
        camera,
        projection,
        viewport_width=200,
        viewport_height=200,
    )

    assert lines == []


def test_generated_3d_primitives_and_exports_are_deterministic(tmp_path):
    cylinder = cylinder_model(10, 20, detail_x=8)
    cone = cone_model(10, 20, detail_x=8)
    ellipsoid = ellipsoid_model(10, 20, 30, detail_x=8, detail_y=4)
    torus = torus_model(20, 5, detail_x=8, detail_y=6)

    assert len(cylinder.meshes[0].faces) == 24
    assert len(cone.meshes[0].faces) == 16
    assert len(ellipsoid.meshes[0].vertices) == 40
    assert len(torus.meshes[0].faces) == 48

    obj_path = save_obj(cylinder, tmp_path / "shape.obj")
    stl_path = save_stl(cone, tmp_path / "shape.stl")

    assert obj_path.read_text(encoding="utf-8").startswith("# Generated by Gummy Snake\nv ")
    assert stl_path.read_text(encoding="utf-8").startswith("solid gummy_snake_model\n")

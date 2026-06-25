import numpy as np

import gummysnake.drawing.software3d.shading as shading_module
from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.prototype3d import cube_model, wireframe_segments
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Material3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Vec3,
    _mesh_rust_handle,
    _model_rust_handle,
)
from gummysnake.drawing.software3d import (
    box_model,
    clear_primitive_model_cache,
    cone_model,
    cylinder_model,
    ellipsoid_model,
    plane_model,
    primitive_model_cache_info,
    project_model_faces,
    save_obj,
    save_stl,
    shade_model_faces,
    sphere_model,
    torus_model,
)
from gummysnake.drawing.software3d.rust_bridge import rust_project_shade_faces


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


def test_rust_project_shade_faces_applies_model_transform_in_payload(monkeypatch):
    captured: dict[str, object] = {}

    class MeshHandle:
        def __init__(self, vertices, faces, normals, texcoords):
            self._payload = {
                "vertices": vertices,
                "faces": faces,
                "normals": normals,
                "texcoords": texcoords,
            }

        def to_mesh_payload(self):
            return self._payload

    class RustMatrix:
        def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
            self.a = a
            self.b = b
            self.c = c
            self.d = d
            self.e = e
            self.f = f

        def as_tuple(self):
            return (self.a, self.b, self.c, self.d, self.e, self.f)

    class Runtime:
        Matrix2D = RustMatrix

        def create_mesh3d_handle(self, vertices, faces, normals, texcoords):
            return MeshHandle(vertices, faces, normals, texcoords)

        def project_shade_faces(self, meshes, *args):
            captured["meshes"] = meshes
            return []

    monkeypatch.setattr("gummysnake.rust.canvas.require_canvas_runtime", lambda: Runtime())
    model = Model3D(
        meshes=(
            Mesh3D(
                vertices=(Vec3(2, 3, 4),),
                faces=((0,),),
            ),
        )
    )

    rust_project_shade_faces(
        model,
        Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0)),
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=100,
        viewport_height=100,
        base_material=Material3D(),
        lights=(),
        normal_material=False,
        cull_backfaces=True,
        model_transform=Matrix2D(2, 0, 0, 3, 5, 7),
    )

    meshes = captured["meshes"]
    assert isinstance(meshes, list)
    assert meshes[0]["vertices"] == [(9, 2, 10.0)]


def test_shade_model_faces_cache_key_includes_model_transform(monkeypatch):
    shading_module._shaded_face_cache.clear()
    calls: list[tuple[float, float, float, float, float, float] | None] = []

    def fake_project_shade_faces(model, camera, projection, *, model_transform=None, **kwargs):
        transform = None if model_transform is None else model_transform.as_tuple()
        calls.append(transform)
        offset = 0.0 if transform is None else transform[4]
        return [
            {
                "points": ((offset, 0.0), (offset + 1.0, 0.0), (offset, 1.0)),
                "color": (1.0, 0.0, 0.0, 1.0),
                "depth": 0.0,
                "normal": (0.0, 0.0, 1.0),
                "center": (0.0, 0.0, 0.0),
            }
        ]

    monkeypatch.setattr(shading_module, "rust_project_shade_faces", fake_project_shade_faces)
    model = Model3D(
        meshes=(
            Mesh3D(
                vertices=(Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(0, 1, 0)),
                faces=((0, 1, 2),),
            ),
        )
    )
    camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))
    projection = PerspectiveProjection(fov_y=60, near=1, far=1000)

    first = shade_model_faces(
        model,
        camera,
        projection,
        viewport_width=100,
        viewport_height=100,
        base_material=Material3D(),
        lights=(),
        model_transform=Matrix2D(1, 0, 0, 1, 10, 0),
    )
    second = shade_model_faces(
        model,
        camera,
        projection,
        viewport_width=100,
        viewport_height=100,
        base_material=Material3D(),
        lights=(),
        model_transform=Matrix2D(1, 0, 0, 1, 20, 0),
    )

    assert len(calls) == 2
    assert first[0].points != second[0].points

def test_primitive_model_factory_wraps_rust_handle_without_materializing_meshes(monkeypatch):
    clear_primitive_model_cache()
    captured: dict[str, object] = {}

    class Handle:
        def to_mesh_payload(self):
            raise AssertionError("mesh payload should be lazy")

    class Runtime:
        def create_plane_model_handle(self, width, height):
            captured["args"] = (width, height)
            return Handle()

    monkeypatch.setattr("gummysnake.rust.canvas.require_canvas_runtime", lambda: Runtime())

    model = plane_model(20, 10)

    assert captured["args"] == (20, 10)
    assert _model_rust_handle(model) is not None


def test_rust_project_shade_faces_uses_direct_model_handle_without_mesh_payload(monkeypatch):
    captured: dict[str, object] = {}

    class Handle:
        def to_mesh_payload(self):
            raise AssertionError("direct handle projection should not materialize mesh payload")

    class RustMatrix:
        def __init__(self, a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0):
            self.a = a
            self.b = b
            self.c = c
            self.d = d
            self.e = e
            self.f = f

        def as_tuple(self):
            return (self.a, self.b, self.c, self.d, self.e, self.f)

    class Runtime:
        Matrix2D = RustMatrix

        def project_shade_model_handle(self, handle, *args):
            captured["handle"] = handle
            captured["args"] = args
            return []

    monkeypatch.setattr("gummysnake.rust.canvas.require_canvas_runtime", lambda: Runtime())
    handle = Handle()
    model = Model3D(meshes=None, rust_handle=handle)

    rust_project_shade_faces(
        model,
        Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0)),
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=100,
        viewport_height=100,
        base_material=Material3D(),
        lights=(),
        normal_material=False,
        cull_backfaces=True,
        model_transform=Matrix2D(2, 0, 0, 3, 5, 7),
    )

    assert captured["handle"] is handle
    args = captured["args"]
    assert isinstance(args, tuple)
    assert args[-1] == (2, 0, 0, 3, 5, 7)


def test_software_3d_primitive_models_are_cached_by_parameters():
    clear_primitive_model_cache()

    first = sphere_model(20, detail_x=12, detail_y=8)
    second = sphere_model(20, detail_x=12, detail_y=8)
    different = sphere_model(21, detail_x=12, detail_y=8)
    plane = plane_model(20, 10)
    box = box_model(20, 10, 5)

    assert first is second
    assert first is not different
    assert plane is plane_model(20, 10)
    assert box is box_model(20, 10, 5)
    assert isinstance(first.meshes[0].vertices, tuple)
    assert primitive_model_cache_info()["sphere"].hits >= 1


def test_box_model_faces_have_outward_winding():
    mesh = box_model(20).meshes[0]

    for face in mesh.faces:
        points = [mesh.vertices[index] for index in face]
        center = Vec3(
            sum(point.x for point in points) / len(points),
            sum(point.y for point in points) / len(points),
            sum(point.z for point in points) / len(points),
        )
        edge_a = Vec3(
            points[1].x - points[0].x,
            points[1].y - points[0].y,
            points[1].z - points[0].z,
        )
        edge_b = Vec3(
            points[2].x - points[0].x,
            points[2].y - points[0].y,
            points[2].z - points[0].z,
        )
        normal = Vec3(
            edge_a.y * edge_b.z - edge_a.z * edge_b.y,
            edge_a.z * edge_b.x - edge_a.x * edge_b.z,
            edge_a.x * edge_b.y - edge_a.y * edge_b.x,
        )

        assert normal.x * center.x + normal.y * center.y + normal.z * center.z > 0


def test_software_3d_depth_sorting_returns_far_faces_first():
    model = Model3D(
        meshes=(
            Mesh3D(
                vertices=(
                    Vec3(-10, -10, 0),
                    Vec3(10, -10, 0),
                    Vec3(10, 10, 0),
                    Vec3(-10, 10, 0),
                    Vec3(-10, -10, 100),
                    Vec3(10, -10, 100),
                    Vec3(10, 10, 100),
                    Vec3(-10, 10, 100),
                ),
                faces=((0, 1, 2, 3), (4, 5, 6, 7)),
            ),
        )
    )
    faces = project_model_faces(
        model,
        Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0)),
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=100,
        viewport_height=100,
    )

    assert len(faces) == 2
    assert faces[0].depth > faces[1].depth


def test_software_3d_backface_culling_and_clipping_are_deterministic():
    front_and_back = Model3D(
        meshes=(
            Mesh3D(
                vertices=(
                    Vec3(-10, -10, 0),
                    Vec3(10, -10, 0),
                    Vec3(10, 10, 0),
                    Vec3(-10, 10, 0),
                ),
                faces=((0, 1, 2, 3), (3, 2, 1, 0)),
            ),
        )
    )
    camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))

    culled = project_model_faces(
        front_and_back,
        camera,
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=100,
        viewport_height=100,
    )
    unclipped = project_model_faces(
        front_and_back,
        camera,
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=100,
        viewport_height=100,
        cull_backfaces=False,
    )
    clipped = project_model_faces(
        front_and_back,
        camera,
        PerspectiveProjection(fov_y=60, near=1, far=200),
        viewport_width=100,
        viewport_height=100,
        cull_backfaces=False,
    )

    assert len(culled) == 1
    assert len(unclipped) == 2
    assert clipped == []


def test_software_3d_projection_modes_change_projected_extent():
    model = plane_model(100, 100)
    camera = Camera3D(eye=Vec3(0, 0, 300), target=Vec3(0, 0, 0))
    perspective = project_model_faces(
        model,
        camera,
        PerspectiveProjection(fov_y=60, near=1, far=1000),
        viewport_width=200,
        viewport_height=200,
    )
    orthographic = project_model_faces(
        model,
        camera,
        OrthographicProjection(width=200, height=200, near=1, far=1000),
        viewport_width=200,
        viewport_height=200,
    )

    assert perspective[0].points != orthographic[0].points

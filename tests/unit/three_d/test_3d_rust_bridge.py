import gummysnake.drawing.software3d.shading as shading_module
from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Material3D,
    Mesh3D,
    Model3D,
    PerspectiveProjection,
    Vec3,
    _model_rust_handle,
)
from gummysnake.drawing.software3d import (
    clear_primitive_model_cache,
    plane_model,
    shade_model_faces,
)
from gummysnake.drawing.software3d.rust_bridge import rust_project_shade_faces


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
    assert args[-1] == (2, 0, 0.0, 0.0, 0, 3, 0.0, 0.0, 0.0, 0.0, 2.5, 0.0, 5, -7, 0.0, 1.0)

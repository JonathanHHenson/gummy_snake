from pathlib import Path

import gummysnake as gs


def test_load_model_supports_local_obj_with_negative_indices(tmp_path: Path):
    obj_path = tmp_path / "triangle.obj"
    obj_path.write_text(
        "\n".join(
            [
                "v 0 0 0",
                "v 2 0 0",
                "v 0 1 0",
                "f -3 -2 -1",
            ]
        ),
        encoding="utf-8",
    )

    model = gs.load_model(obj_path)

    assert len(model.meshes) == 1
    mesh = model.meshes[0]
    assert len(mesh.vertices) == 3
    assert mesh.faces == ((0, 1, 2),)
    assert model.source == obj_path


def test_load_model_supports_package_resources_and_normalize():
    model = gs.load_model("triangle.obj", normalize=True, package="gummysnake.testing.resources")

    mesh = model.meshes[0]
    xs = [vertex.x for vertex in mesh.vertices]
    ys = [vertex.y for vertex in mesh.vertices]
    zs = [vertex.z for vertex in mesh.vertices]

    assert max(xs) <= 1.0
    assert min(xs) >= -1.0
    assert max(ys) <= 1.0
    assert min(ys) >= -1.0
    assert max(zs) == 0.0
    assert min(zs) == 0.0

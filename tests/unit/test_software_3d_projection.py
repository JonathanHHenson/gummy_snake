from gummysnake.drawing.renderer3d import (
    Camera3D,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Vec3,
)
from gummysnake.drawing.software3d import (
    box_model,
    clear_primitive_model_cache,
    plane_model,
    primitive_model_cache_info,
    project_model_faces,
    sphere_model,
)


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

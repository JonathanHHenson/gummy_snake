from p5_py.drawing.prototype3d import cube_model, wireframe_segments
from p5_py.drawing.renderer3d import (
    Camera3D,
    OrthographicProjection,
    PerspectiveProjection,
    Vec3,
)


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

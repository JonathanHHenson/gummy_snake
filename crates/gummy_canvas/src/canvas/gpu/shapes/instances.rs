use crate::*;

const PROCEDURAL_TRANSFORMED_RECT_KIND: f32 = 5.0;
const PROCEDURAL_TRANSFORMED_TRIANGLE_KIND: f32 = 6.0;
const PROCEDURAL_TRANSFORMED_ELLIPSE_KIND: f32 = 7.0;

pub(super) fn transformed_rect_instance(
    p0: Point,
    p1: Point,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> crate::gpu::PrimitiveInstance {
    transformed_rect_like_instance(
        p0,
        p1,
        matrix,
        pixel_density,
        color,
        PROCEDURAL_TRANSFORMED_RECT_KIND,
        0.0,
    )
}

pub(super) fn transformed_polygon_fill_instances(
    points: &[Point],
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::PrimitiveInstance> {
    (1..points.len() - 1)
        .map(|index| {
            transformed_triangle_instance(
                points[0],
                points[index],
                points[index + 1],
                matrix,
                pixel_density,
                color,
            )
        })
        .collect()
}

pub(super) fn transformed_ellipse_instance(
    p0: Point,
    p1: Point,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
    stroke_width: f64,
) -> crate::gpu::PrimitiveInstance {
    transformed_rect_like_instance(
        p0,
        p1,
        matrix,
        pixel_density,
        color,
        PROCEDURAL_TRANSFORMED_ELLIPSE_KIND,
        stroke_width,
    )
}

fn transformed_rect_like_instance(
    p0: Point,
    p1: Point,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
    kind: f32,
    stroke_width: f64,
) -> crate::gpu::PrimitiveInstance {
    let (a, b, c, d, e, f) = matrix;
    crate::gpu::PrimitiveInstance {
        p0: [p0.0 as f32, p0.1 as f32],
        p1: [p1.0 as f32, p1.1 as f32],
        p2: [(a * pixel_density) as f32, (b * pixel_density) as f32],
        bounds: [
            (c * pixel_density) as f32,
            (d * pixel_density) as f32,
            (e * pixel_density) as f32,
            (f * pixel_density) as f32,
        ],
        color: crate::raster::gpu_color(color).as_float(),
        params: [kind, stroke_width as f32, 0.0, 0.0],
    }
}

pub(super) fn transformed_triangle_instance(
    p0: Point,
    p1: Point,
    p2: Point,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> crate::gpu::PrimitiveInstance {
    let (a, b, c, d, e, f) = matrix;
    crate::gpu::PrimitiveInstance {
        p0: [p0.0 as f32, p0.1 as f32],
        p1: [p1.0 as f32, p1.1 as f32],
        p2: [p2.0 as f32, p2.1 as f32],
        bounds: [
            (a * pixel_density) as f32,
            (b * pixel_density) as f32,
            (c * pixel_density) as f32,
            (d * pixel_density) as f32,
        ],
        color: crate::raster::gpu_color(color).as_float(),
        params: [
            PROCEDURAL_TRANSFORMED_TRIANGLE_KIND,
            (e * pixel_density) as f32,
            (f * pixel_density) as f32,
            0.0,
        ],
    }
}

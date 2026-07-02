use crate::raster::types::{Matrix, Point};

pub(crate) fn stroke_width(stroke_weight: f64, pixel_density: f64) -> f64 {
    (stroke_weight * pixel_density).round().max(1.0)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn image_to_canvas_matrix(
    matrix: Matrix,
    dx: f64,
    dy: f64,
    dw: f64,
    dh: f64,
    sw: usize,
    sh: usize,
    pixel_density: f64,
) -> Matrix {
    let physical = (
        matrix.0 * pixel_density,
        matrix.1 * pixel_density,
        matrix.2 * pixel_density,
        matrix.3 * pixel_density,
        matrix.4 * pixel_density,
        matrix.5 * pixel_density,
    );
    matrix_multiply(
        matrix_multiply(physical, (1.0, 0.0, 0.0, 1.0, dx, dy)),
        (dw / sw as f64, 0.0, 0.0, dh / sh as f64, 0.0, 0.0),
    )
}

fn matrix_multiply(left: Matrix, right: Matrix) -> Matrix {
    (
        left.0 * right.0 + left.2 * right.1,
        left.1 * right.0 + left.3 * right.1,
        left.0 * right.2 + left.2 * right.3,
        left.1 * right.2 + left.3 * right.3,
        left.0 * right.4 + left.2 * right.5 + left.4,
        left.1 * right.4 + left.3 * right.5 + left.5,
    )
}

pub(crate) fn matrix_transform_point(matrix: Matrix, x: f64, y: f64) -> Point {
    (
        matrix.0 * x + matrix.2 * y + matrix.4,
        matrix.1 * x + matrix.3 * y + matrix.5,
    )
}

pub(crate) fn point_to_f32(point: Point) -> [f32; 2] {
    [point.0 as f32, point.1 as f32]
}

pub(crate) fn matrix_determinant(matrix: Matrix) -> f64 {
    matrix.0 * matrix.3 - matrix.1 * matrix.2
}

pub(crate) fn clipped_source_rect(
    rect: (i64, i64, i64, i64),
    width: usize,
    height: usize,
) -> Option<(usize, usize, usize, usize)> {
    let (x, y, w, h) = rect;
    if w <= 0 || h <= 0 {
        return None;
    }
    let left = x.clamp(0, width as i64) as usize;
    let top = y.clamp(0, height as i64) as usize;
    let right = (x + w).clamp(0, width as i64) as usize;
    let bottom = (y + h).clamp(0, height as i64) as usize;
    if right <= left || bottom <= top {
        None
    } else {
        Some((left, top, right - left, bottom - top))
    }
}

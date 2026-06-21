use super::types::{Matrix, Point};

pub(crate) fn stroke_width(stroke_weight: f64, pixel_density: f64) -> f64 {
    (stroke_weight * pixel_density).round().max(1.0)
}

pub(crate) fn scale_rect(rect: (i64, i64, i64, i64), pixel_density: f64) -> (i64, i64, i64, i64) {
    (
        (rect.0 as f64 * pixel_density).round() as i64,
        (rect.1 as f64 * pixel_density).round() as i64,
        (rect.2 as f64 * pixel_density).round() as i64,
        (rect.3 as f64 * pixel_density).round() as i64,
    )
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

pub(crate) fn matrix_inverse(matrix: Matrix) -> Option<Matrix> {
    let determinant = matrix_determinant(matrix);
    if determinant.abs() <= f64::EPSILON {
        return None;
    }
    let inv_det = 1.0 / determinant;
    let a = matrix.3 * inv_det;
    let b = -matrix.1 * inv_det;
    let c = -matrix.2 * inv_det;
    let d = matrix.0 * inv_det;
    let e = -(a * matrix.4 + c * matrix.5);
    let f = -(b * matrix.4 + d * matrix.5);
    Some((a, b, c, d, e, f))
}

pub(crate) fn affine_bounds(
    matrix: Matrix,
    width: usize,
    height: usize,
    canvas_width: usize,
    canvas_height: usize,
) -> Option<(usize, usize, usize, usize)> {
    let corners = [
        matrix_transform_point(matrix, 0.0, 0.0),
        matrix_transform_point(matrix, width as f64, 0.0),
        matrix_transform_point(matrix, width as f64, height as f64),
        matrix_transform_point(matrix, 0.0, height as f64),
    ];
    let min_x = corners
        .iter()
        .map(|point| point.0)
        .fold(f64::INFINITY, f64::min)
        .floor()
        .max(0.0) as usize;
    let min_y = corners
        .iter()
        .map(|point| point.1)
        .fold(f64::INFINITY, f64::min)
        .floor()
        .max(0.0) as usize;
    let max_x = corners
        .iter()
        .map(|point| point.0)
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil()
        .min(canvas_width as f64)
        .max(0.0) as usize;
    let max_y = corners
        .iter()
        .map(|point| point.1)
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil()
        .min(canvas_height as f64)
        .max(0.0) as usize;
    if max_x <= min_x || max_y <= min_y {
        None
    } else {
        Some((min_x, min_y, max_x - min_x, max_y - min_y))
    }
}

pub(crate) fn axis_aligned_image_destination(
    matrix: Matrix,
    width: usize,
    height: usize,
    canvas_width: usize,
    canvas_height: usize,
) -> Option<(usize, usize, usize, usize)> {
    if matrix.1.abs() > f64::EPSILON || matrix.2.abs() > f64::EPSILON {
        return None;
    }
    if matrix.0 <= 0.0 || matrix.3 <= 0.0 {
        return None;
    }
    let left = matrix.4.round();
    let top = matrix.5.round();
    let dest_width = (matrix.0 * width as f64).round();
    let dest_height = (matrix.3 * height as f64).round();
    if left < 0.0 || top < 0.0 || dest_width <= 0.0 || dest_height <= 0.0 {
        return None;
    }
    let right = left + dest_width;
    let bottom = top + dest_height;
    if right > canvas_width as f64 || bottom > canvas_height as f64 {
        return None;
    }
    Some((
        left as usize,
        top as usize,
        dest_width as usize,
        dest_height as usize,
    ))
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

pub(crate) fn clipped_dest_rect(
    rect: (i64, i64, i64, i64),
    width: usize,
    height: usize,
) -> Option<(usize, usize, usize, usize)> {
    clipped_source_rect(rect, width, height)
}

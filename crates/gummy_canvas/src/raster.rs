use crate::image_ops::alpha_composite_pixel;
use crate::{
    gpu, Rgba, Style, BLEND_MODE_ADD, BLEND_MODE_BLEND, BLEND_MODE_DARKEST, BLEND_MODE_DIFFERENCE,
    BLEND_MODE_EXCLUSION, BLEND_MODE_LIGHTEST, BLEND_MODE_MULTIPLY, BLEND_MODE_REPLACE,
    BLEND_MODE_SCREEN,
};

pub(crate) type Matrix = (f64, f64, f64, f64, f64, f64);

pub(crate) type Point = (f64, f64);

pub(crate) struct OverlayRegion<'a> {
    min_x: usize,
    min_y: usize,
    width: usize,
    height: usize,
    canvas_width: usize,
    pixels: &'a mut [u8],
    present_pixels: &'a mut [u32],
    erasing: bool,
    blend_mode: &'a str,
}

impl<'a> OverlayRegion<'a> {
    pub(crate) fn from_bounds(
        bounds: (usize, usize, usize, usize),
        canvas_width: usize,
        pixels: &'a mut [u8],
        present_pixels: &'a mut [u32],
        erasing: bool,
        blend_mode: &'a str,
    ) -> Option<Self> {
        let (min_x, min_y, max_x, max_y) = bounds;
        let width = max_x.saturating_sub(min_x);
        let height = max_y.saturating_sub(min_y);
        if width == 0 || height == 0 {
            return None;
        }
        Some(Self {
            min_x,
            min_y,
            width,
            height,
            canvas_width,
            pixels,
            present_pixels,
            erasing,
            blend_mode,
        })
    }

    fn max_x(&self) -> usize {
        self.min_x + self.width
    }

    fn max_y(&self) -> usize {
        self.min_y + self.height
    }

    fn set_pixel(&mut self, x: usize, y: usize, color: Rgba) {
        let pixel_index = y * self.canvas_width + x;
        let offset = pixel_index * 4;
        let dst = &mut self.pixels[offset..offset + 4];
        let color = color.as_array();
        if self.erasing {
            dst[3] = dst[3].saturating_sub(color[3]);
        } else {
            blend_pixel(dst, &color, self.blend_mode);
        }
        self.present_pixels[pixel_index] = rgba_to_present_pixel(dst);
    }
}

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

#[allow(clippy::too_many_arguments)]
pub(crate) fn blit_scaled_region(
    dst: &mut [u8],
    present_pixels: &mut [u32],
    dst_width: usize,
    src: &[u8],
    src_width: usize,
    sx: usize,
    sy: usize,
    sw: usize,
    sh: usize,
    dx: usize,
    dy: usize,
    dw: usize,
    dh: usize,
    erasing: bool,
    blend_mode: &str,
    sampling: &str,
) {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 {
        return;
    }
    let nearest = sampling == "nearest";
    let default_blend = blend_mode == BLEND_MODE_BLEND;
    for out_y in 0..dh {
        let local_y = if nearest {
            (out_y * sh / dh).min(sh - 1) as f64
        } else {
            (out_y as f64 + 0.5) * sh as f64 / dh as f64 - 0.5
        };
        for out_x in 0..dw {
            let local_x = if nearest {
                (out_x * sw / dw).min(sw - 1) as f64
            } else {
                (out_x as f64 + 0.5) * sw as f64 / dw as f64 - 0.5
            };
            let src_pixel =
                sample_image_pixel(src, src_width, sx, sy, sw, sh, local_x, local_y, nearest);
            if src_pixel[3] == 0 {
                continue;
            }
            let dst_pixel_index = (dy + out_y) * dst_width + dx + out_x;
            let dst_offset = dst_pixel_index * 4;
            let dst_pixel = &mut dst[dst_offset..dst_offset + 4];
            if erasing {
                dst_pixel[3] = dst_pixel[3].saturating_sub(src_pixel[3]);
            } else if default_blend && src_pixel[3] == 255 {
                dst_pixel.copy_from_slice(&src_pixel);
            } else {
                blend_pixel(dst_pixel, &src_pixel, blend_mode);
            }
            present_pixels[dst_pixel_index] = rgba_to_present_pixel(dst_pixel);
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn blit_affine_region(
    dst: &mut [u8],
    present_pixels: &mut [u32],
    dst_width: usize,
    src: &[u8],
    src_width: usize,
    sx: usize,
    sy: usize,
    sw: usize,
    sh: usize,
    dx: usize,
    dy: usize,
    dw: usize,
    dh: usize,
    canvas_to_image: Matrix,
    erasing: bool,
    blend_mode: &str,
    sampling: &str,
) {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 {
        return;
    }
    let nearest = sampling == "nearest";
    let default_blend = blend_mode == BLEND_MODE_BLEND;
    let (a, b, c, d, e, f) = canvas_to_image;
    for out_y in 0..dh {
        let canvas_y = dy + out_y;
        let sample_y = canvas_y as f64 + 0.5;
        let mut local_x = a * (dx as f64 + 0.5) + c * sample_y + e;
        let mut local_y = b * (dx as f64 + 0.5) + d * sample_y + f;
        for out_x in 0..dw {
            let canvas_x = dx + out_x;
            if local_x < 0.0 || local_y < 0.0 || local_x >= sw as f64 || local_y >= sh as f64 {
                local_x += a;
                local_y += b;
                continue;
            }
            let src_pixel =
                sample_image_pixel(src, src_width, sx, sy, sw, sh, local_x, local_y, nearest);
            if src_pixel[3] == 0 {
                local_x += a;
                local_y += b;
                continue;
            }
            let dst_pixel_index = canvas_y * dst_width + canvas_x;
            let dst_offset = dst_pixel_index * 4;
            let dst_pixel = &mut dst[dst_offset..dst_offset + 4];
            if erasing {
                dst_pixel[3] = dst_pixel[3].saturating_sub(src_pixel[3]);
            } else if default_blend && src_pixel[3] == 255 {
                dst_pixel.copy_from_slice(&src_pixel);
            } else {
                blend_pixel(dst_pixel, &src_pixel, blend_mode);
            }
            present_pixels[dst_pixel_index] = rgba_to_present_pixel(dst_pixel);
            local_x += a;
            local_y += b;
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn sample_image_pixel(
    src: &[u8],
    src_width: usize,
    sx: usize,
    sy: usize,
    sw: usize,
    sh: usize,
    local_x: f64,
    local_y: f64,
    nearest: bool,
) -> [u8; 4] {
    if nearest {
        let x = sx + local_x.floor().clamp(0.0, (sw - 1) as f64) as usize;
        let y = sy + local_y.floor().clamp(0.0, (sh - 1) as f64) as usize;
        let offset = (y * src_width + x) * 4;
        return [
            src[offset],
            src[offset + 1],
            src[offset + 2],
            src[offset + 3],
        ];
    }

    let clamped_x = local_x.clamp(0.0, (sw - 1) as f64);
    let clamped_y = local_y.clamp(0.0, (sh - 1) as f64);
    let x0 = clamped_x.floor() as usize;
    let y0 = clamped_y.floor() as usize;
    let x1 = (x0 + 1).min(sw - 1);
    let y1 = (y0 + 1).min(sh - 1);
    let tx = clamped_x - x0 as f64;
    let ty = clamped_y - y0 as f64;

    let p00 = source_pixel(src, src_width, sx + x0, sy + y0);
    let p10 = source_pixel(src, src_width, sx + x1, sy + y0);
    let p01 = source_pixel(src, src_width, sx + x0, sy + y1);
    let p11 = source_pixel(src, src_width, sx + x1, sy + y1);

    let mut out = [0_u8; 4];
    for channel in 0..4 {
        let top = p00[channel] as f64 * (1.0 - tx) + p10[channel] as f64 * tx;
        let bottom = p01[channel] as f64 * (1.0 - tx) + p11[channel] as f64 * tx;
        out[channel] = (top * (1.0 - ty) + bottom * ty).round().clamp(0.0, 255.0) as u8;
    }
    out
}

fn source_pixel(src: &[u8], src_width: usize, x: usize, y: usize) -> [u8; 4] {
    let offset = (y * src_width + x) * 4;
    [
        src[offset],
        src[offset + 1],
        src[offset + 2],
        src[offset + 3],
    ]
}

pub(crate) fn draw_polygon_overlay(
    overlay: &mut OverlayRegion<'_>,
    points: &[Point],
    style: &Style,
    close: bool,
    pixel_density: f64,
) {
    if points.len() == 1 {
        let color = style.stroke.or(style.fill);
        if let Some(color) = color {
            fill_disc(
                overlay,
                points[0].0,
                points[0].1,
                (style.stroke_weight * pixel_density / 2.0).max(0.5),
                color,
            );
        }
        return;
    }

    if close && points.len() >= 3 {
        if let Some(fill) = style.fill {
            fill_polygon(overlay, points, fill);
        }
    }

    if let Some(stroke) = style.stroke {
        draw_polyline_stroke(
            overlay,
            points,
            close,
            stroke_width(style.stroke_weight, pixel_density),
            stroke,
        );
    }
}

pub(crate) fn draw_axis_aligned_ellipse(
    overlay: &mut OverlayRegion<'_>,
    cx: f64,
    cy: f64,
    rx: f64,
    ry: f64,
    style: &Style,
    pixel_density: f64,
) {
    if rx <= 0.0 || ry <= 0.0 {
        return;
    }
    if let Some(fill) = style.fill {
        fill_axis_aligned_ellipse(overlay, cx, cy, rx, ry, fill);
    }
    if let Some(stroke) = style.stroke {
        stroke_axis_aligned_ellipse(
            overlay,
            cx,
            cy,
            rx,
            ry,
            stroke_width(style.stroke_weight, pixel_density),
            stroke,
        );
    }
}

fn fill_axis_aligned_ellipse(
    overlay: &mut OverlayRegion<'_>,
    cx: f64,
    cy: f64,
    rx: f64,
    ry: f64,
    color: Rgba,
) {
    let inv_rx2 = 1.0 / (rx * rx);
    let inv_ry2 = 1.0 / (ry * ry);
    for y in overlay.min_y..overlay.max_y() {
        let dy = y as f64 + 0.5 - cy;
        let dy2 = dy * dy * inv_ry2;
        if dy2 > 1.0 {
            continue;
        }
        for x in overlay.min_x..overlay.max_x() {
            let dx = x as f64 + 0.5 - cx;
            if dx * dx * inv_rx2 + dy2 <= 1.0 {
                overlay.set_pixel(x, y, color);
            }
        }
    }
}

fn stroke_axis_aligned_ellipse(
    overlay: &mut OverlayRegion<'_>,
    cx: f64,
    cy: f64,
    rx: f64,
    ry: f64,
    stroke_width: f64,
    color: Rgba,
) {
    let half_width = (stroke_width / 2.0).max(0.5);
    let outer_rx = rx + half_width;
    let outer_ry = ry + half_width;
    let inner_rx = (rx - half_width).max(0.0);
    let inner_ry = (ry - half_width).max(0.0);
    let outer_inv_rx2 = 1.0 / (outer_rx * outer_rx);
    let outer_inv_ry2 = 1.0 / (outer_ry * outer_ry);
    let has_inner = inner_rx > 0.0 && inner_ry > 0.0;
    let inner_inv_rx2 = if has_inner {
        1.0 / (inner_rx * inner_rx)
    } else {
        0.0
    };
    let inner_inv_ry2 = if has_inner {
        1.0 / (inner_ry * inner_ry)
    } else {
        0.0
    };

    for y in overlay.min_y..overlay.max_y() {
        let dy = y as f64 + 0.5 - cy;
        let outer_dy2 = dy * dy * outer_inv_ry2;
        if outer_dy2 > 1.0 {
            continue;
        }
        let inner_dy2 = dy * dy * inner_inv_ry2;
        for x in overlay.min_x..overlay.max_x() {
            let dx = x as f64 + 0.5 - cx;
            let outer = dx * dx * outer_inv_rx2 + outer_dy2;
            if outer > 1.0 {
                continue;
            }
            let inside_inner = has_inner && dx * dx * inner_inv_rx2 + inner_dy2 <= 1.0;
            if !inside_inner {
                overlay.set_pixel(x, y, color);
            }
        }
    }
}

fn fill_polygon(overlay: &mut OverlayRegion<'_>, points: &[Point], color: Rgba) {
    for y in overlay.min_y..overlay.max_y() {
        for x in overlay.min_x..overlay.max_x() {
            let sample = (x as f64 + 0.5, y as f64 + 0.5);
            if point_in_polygon(sample, points) {
                overlay.set_pixel(x, y, color);
            }
        }
    }
}

pub(crate) fn draw_polyline_stroke(
    overlay: &mut OverlayRegion<'_>,
    points: &[Point],
    close: bool,
    stroke_width: f64,
    color: Rgba,
) {
    if points.len() < 2 {
        return;
    }
    for pair in points.windows(2) {
        stroke_segment(overlay, pair[0], pair[1], stroke_width, color);
    }
    if close {
        stroke_segment(
            overlay,
            *points.last().expect("non-empty points"),
            points[0],
            stroke_width,
            color,
        );
    }
}

pub(crate) fn stroke_segment(
    overlay: &mut OverlayRegion<'_>,
    p1: Point,
    p2: Point,
    stroke_width: f64,
    color: Rgba,
) {
    let radius = (stroke_width / 2.0).max(0.5);
    let radius_squared = radius * radius;
    for y in overlay.min_y..overlay.max_y() {
        for x in overlay.min_x..overlay.max_x() {
            let sample = (x as f64 + 0.5, y as f64 + 0.5);
            if distance_to_segment_squared(sample, p1, p2) <= radius_squared {
                overlay.set_pixel(x, y, color);
            }
        }
    }
}

pub(crate) fn fill_disc(
    overlay: &mut OverlayRegion<'_>,
    cx: f64,
    cy: f64,
    radius: f64,
    color: Rgba,
) {
    let radius_squared = radius * radius;
    for y in overlay.min_y..overlay.max_y() {
        for x in overlay.min_x..overlay.max_x() {
            let dx = x as f64 + 0.5 - cx;
            let dy = y as f64 + 0.5 - cy;
            if dx * dx + dy * dy <= radius_squared {
                overlay.set_pixel(x, y, color);
            }
        }
    }
}

pub(crate) fn ellipse_bounds(
    cx: f64,
    cy: f64,
    rx: f64,
    ry: f64,
    padding: f64,
    width: usize,
    height: usize,
) -> (usize, usize, usize, usize) {
    (
        (cx - rx - padding).floor().max(0.0) as usize,
        (cy - ry - padding).floor().max(0.0) as usize,
        (cx + rx + padding).ceil().min(width as f64).max(0.0) as usize,
        (cy + ry + padding).ceil().min(height as f64).max(0.0) as usize,
    )
}

pub(crate) fn clipped_bounds(
    points: &[Point],
    padding: f64,
    width: usize,
    height: usize,
) -> (usize, usize, usize, usize) {
    let min_x = points
        .iter()
        .map(|point| point.0)
        .fold(f64::INFINITY, f64::min)
        - padding;
    let min_y = points
        .iter()
        .map(|point| point.1)
        .fold(f64::INFINITY, f64::min)
        - padding;
    let max_x = points
        .iter()
        .map(|point| point.0)
        .fold(f64::NEG_INFINITY, f64::max)
        + padding;
    let max_y = points
        .iter()
        .map(|point| point.1)
        .fold(f64::NEG_INFINITY, f64::max)
        + padding;
    (
        min_x.floor().max(0.0) as usize,
        min_y.floor().max(0.0) as usize,
        max_x.ceil().min(width as f64).max(0.0) as usize,
        max_y.ceil().min(height as f64).max(0.0) as usize,
    )
}

pub(crate) fn point_in_polygon(sample: Point, points: &[Point]) -> bool {
    let (x, y) = sample;
    let mut inside = false;
    let mut previous = *points.last().expect("polygon has at least one point");
    for &current in points {
        let intersects = ((current.1 > y) != (previous.1 > y))
            && (x
                < (previous.0 - current.0) * (y - current.1) / (previous.1 - current.1)
                    + current.0);
        if intersects {
            inside = !inside;
        }
        previous = current;
    }
    inside
}

pub(crate) fn polygon_is_convex(points: &[Point]) -> bool {
    if points.len() < 4 {
        return true;
    }
    let mut sign = 0.0_f64;
    for index in 0..points.len() {
        let a = points[index];
        let b = points[(index + 1) % points.len()];
        let c = points[(index + 2) % points.len()];
        let cross = (b.0 - a.0) * (c.1 - b.1) - (b.1 - a.1) * (c.0 - b.0);
        if cross.abs() <= f64::EPSILON {
            continue;
        }
        if sign == 0.0 {
            sign = cross.signum();
        } else if sign != cross.signum() {
            return false;
        }
    }
    true
}

fn distance_to_segment_squared(point: Point, p1: Point, p2: Point) -> f64 {
    let vx = p2.0 - p1.0;
    let vy = p2.1 - p1.1;
    let wx = point.0 - p1.0;
    let wy = point.1 - p1.1;
    let length_squared = vx * vx + vy * vy;
    if length_squared <= f64::EPSILON {
        let dx = point.0 - p1.0;
        let dy = point.1 - p1.1;
        return dx * dx + dy * dy;
    }
    let t = ((wx * vx + wy * vy) / length_squared).clamp(0.0, 1.0);
    let projection = (p1.0 + t * vx, p1.1 + t * vy);
    let dx = point.0 - projection.0;
    let dy = point.1 - projection.1;
    dx * dx + dy * dy
}

fn blend_pixel(dst: &mut [u8], src: &[u8], mode: &str) {
    if mode == BLEND_MODE_BLEND {
        alpha_composite_pixel(dst, src);
        return;
    }
    if mode == BLEND_MODE_REPLACE {
        alpha_composite_pixel(dst, src);
        return;
    }
    let alpha = src[3] as u32;
    if alpha == 0 {
        return;
    }
    let base = [dst[0], dst[1], dst[2]];
    let blend = [
        blend_channel(base[0], src[0], mode),
        blend_channel(base[1], src[1], mode),
        blend_channel(base[2], src[2], mode),
    ];
    let inv_alpha = 255 - alpha;
    for channel in 0..3 {
        dst[channel] =
            ((blend[channel] as u32 * alpha + base[channel] as u32 * inv_alpha + 127) / 255) as u8;
    }
}

fn blend_channel(base: u8, src: u8, mode: &str) -> u8 {
    match mode {
        BLEND_MODE_ADD => base.saturating_add(src),
        BLEND_MODE_DARKEST => base.min(src),
        BLEND_MODE_LIGHTEST => base.max(src),
        BLEND_MODE_DIFFERENCE => base.abs_diff(src),
        BLEND_MODE_EXCLUSION => {
            let base = base as u32;
            let src = src as u32;
            (base + src - (2 * base * src + 127) / 255).min(255) as u8
        }
        BLEND_MODE_MULTIPLY => ((base as u32 * src as u32 + 127) / 255) as u8,
        BLEND_MODE_SCREEN => {
            let inv = (255 - base as u32) * (255 - src as u32);
            (255 - (inv + 127) / 255) as u8
        }
        _ => src,
    }
}

pub(crate) fn fill_rgba_buffer(pixels: &mut [u8], color: &[u8; 4]) {
    if pixels.is_empty() {
        return;
    }
    let first_len = pixels.len().min(4);
    pixels[..first_len].copy_from_slice(&color[..first_len]);
    let mut filled = first_len;
    while filled < pixels.len() {
        let copy_len = filled.min(pixels.len() - filled);
        pixels.copy_within(0..copy_len, filled);
        filled += copy_len;
    }
}

pub(crate) fn rgba_to_present_pixel(rgba: &[u8]) -> u32 {
    ((rgba[3] as u32) << 24) | ((rgba[0] as u32) << 16) | ((rgba[1] as u32) << 8) | rgba[2] as u32
}

pub(crate) fn gpu_color(color: Rgba) -> gpu::GpuColor {
    gpu::GpuColor {
        r: color.r,
        g: color.g,
        b: color.b,
        a: color.a,
    }
}

pub(crate) fn push_triangle(
    vertices: &mut Vec<([f32; 2], gpu::GpuColor)>,
    a: Point,
    b: Point,
    c: Point,
    color: Rgba,
) {
    let color = gpu_color(color);
    vertices.push((point_to_gpu(a), color));
    vertices.push((point_to_gpu(b), color));
    vertices.push((point_to_gpu(c), color));
}

fn point_to_gpu(point: Point) -> [f32; 2] {
    [point.0 as f32, point.1 as f32]
}

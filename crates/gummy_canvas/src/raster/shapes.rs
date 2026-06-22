use crate::{Rgba, Style};

use crate::raster::transform::stroke_width;
use crate::raster::types::{OverlayRegion, Point};

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
            fill_even_odd_polygon(overlay, &[points], fill);
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

pub(crate) fn fill_axis_aligned_ellipse(
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

pub(crate) fn fill_even_odd_polygon(
    overlay: &mut OverlayRegion<'_>,
    rings: &[&[Point]],
    color: Rgba,
) {
    for_even_odd_spans(
        (
            overlay.min_x,
            overlay.min_y,
            overlay.max_x(),
            overlay.max_y(),
        ),
        rings,
        |y, start, end| {
            for x in start..end {
                overlay.set_pixel(x, y, color);
            }
        },
    );
}

pub(crate) fn rasterize_even_odd_mask(
    mask: &mut [bool],
    width: usize,
    bounds: (usize, usize, usize, usize),
    rings: &[&[Point]],
    parent: Option<&[bool]>,
) {
    for_even_odd_spans(bounds, rings, |y, start, end| {
        for x in start..end {
            let index = y * width + x;
            if parent.is_none_or(|parent_mask| parent_mask[index]) {
                mask[index] = true;
            }
        }
    });
}

pub(crate) fn for_even_odd_spans(
    bounds: (usize, usize, usize, usize),
    rings: &[&[Point]],
    mut span: impl FnMut(usize, usize, usize),
) {
    let mut intersections = Vec::new();
    for y in bounds.1..bounds.3 {
        collect_scanline_intersections(y as f64 + 0.5, rings, &mut intersections);
        for pair in intersections.chunks_exact(2) {
            let start = (pair[0] - 0.5).ceil().max(bounds.0 as f64) as usize;
            let end = ((pair[1] - 0.5).floor() as isize + 1).max(0) as usize;
            let end = end.min(bounds.2);
            if start < end {
                span(y, start, end);
            }
        }
    }
}

fn collect_scanline_intersections(y: f64, rings: &[&[Point]], intersections: &mut Vec<f64>) {
    intersections.clear();
    for points in rings {
        if points.len() < 3 {
            continue;
        }
        let mut previous = *points.last().expect("non-empty polygon ring");
        for &current in *points {
            if (current.1 > y) != (previous.1 > y) {
                let x = (previous.0 - current.0) * (y - current.1) / (previous.1 - current.1)
                    + current.0;
                intersections.push(x);
            }
            previous = current;
        }
    }
    intersections.sort_by(|a, b| a.total_cmp(b));
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

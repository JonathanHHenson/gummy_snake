use crate::*;

const STROKE_PATH_POINT_RECORDS: f32 = 0.0;
const STROKE_PATH_SEGMENT_RECORDS: f32 = 1.0;
const STROKE_SEGMENT_LINE: f32 = 0.0;
const STROKE_SEGMENT_QUADRATIC: f32 = 1.0;
const STROKE_SEGMENT_CUBIC: f32 = 2.0;
const STROKE_SEGMENT_ARC: f32 = 3.0;
const STROKE_ARC_OPEN: f32 = 0.0;
const STROKE_ARC_CHORD: f32 = 1.0;
const STROKE_ARC_PIE: f32 = 2.0;

fn stroke_path_header(
    matrix: Matrix,
    pixel_density: f64,
    stroke_width: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let (a, b, c, d, e, f) = matrix;
    vec![
        [a as f32, b as f32, c as f32, d as f32],
        [
            e as f32,
            f as f32,
            pixel_density as f32,
            stroke_width as f32,
        ],
        crate::raster::gpu_color(color).as_float(),
    ]
}

pub(super) fn stroke_path_records(
    points: &[Point],
    close: bool,
    matrix: Matrix,
    pixel_density: f64,
    stroke_width: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let mut records = stroke_path_header(matrix, pixel_density, stroke_width, color);
    records.push([
        points.len() as f32,
        if close { 1.0 } else { 0.0 },
        STROKE_PATH_POINT_RECORDS,
        0.0,
    ]);
    records.extend(
        points
            .iter()
            .map(|point| [point.0 as f32, point.1 as f32, 0.0, 0.0]),
    );
    records
}

pub(super) fn stroke_path_arc_records(
    center: Point,
    radius: Point,
    start: f64,
    stop: f64,
    mode: &str,
    matrix: Matrix,
    pixel_density: f64,
    stroke_width: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let mut records = stroke_path_header(matrix, pixel_density, stroke_width, color);
    records.push([1.0, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    records.push([
        STROKE_SEGMENT_ARC,
        match mode {
            "pie" => STROKE_ARC_PIE,
            "chord" => STROKE_ARC_CHORD,
            _ => STROKE_ARC_OPEN,
        },
        0.0,
        0.0,
    ]);
    records.push([
        center.0 as f32,
        center.1 as f32,
        radius.0 as f32,
        radius.1 as f32,
    ]);
    records.push([start as f32, stop as f32, 0.0, 0.0]);
    records
}

pub(super) fn path_fill_segment_records(
    segments: &[crate::sketch_state::CapturedPathSegment],
    vertices: &[Point],
    close: bool,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    path_fill_segment_records_with_contours(
        segments,
        vertices,
        &[],
        close,
        matrix,
        pixel_density,
        color,
    )
}

pub(super) fn path_fill_segment_records_with_contours(
    segments: &[crate::sketch_state::CapturedPathSegment],
    vertices: &[Point],
    contours: &[Vec<Point>],
    close: bool,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let command_count = segments.len()
        + usize::from(close && vertices.len() > 1)
        + closed_contour_command_count(contours);
    let mut records = stroke_path_header(matrix, pixel_density, 0.0, color);
    records.push([command_count as f32, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    for segment in segments {
        push_stroke_segment_records(&mut records, *segment);
    }
    push_closing_segment_records(&mut records, vertices, close);
    for contour in contours {
        push_closed_line_loop_records(&mut records, contour);
    }
    records
}

pub(super) fn path_fill_polygon_records(
    outer: &[Point],
    contours: &[Vec<Point>],
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let command_count = outer.len() + closed_contour_command_count(contours);
    let mut records = stroke_path_header(matrix, pixel_density, 0.0, color);
    records.push([command_count as f32, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    push_closed_line_loop_records(&mut records, outer);
    for contour in contours {
        push_closed_line_loop_records(&mut records, contour);
    }
    records
}

pub(super) fn path_fill_arc_records(
    center: Point,
    radius: Point,
    start: f64,
    stop: f64,
    mode: &str,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let mut records = stroke_path_header(matrix, pixel_density, 0.0, color);
    records.push([1.0, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    records.push([
        STROKE_SEGMENT_ARC,
        match mode {
            "pie" => STROKE_ARC_PIE,
            _ => STROKE_ARC_CHORD,
        },
        0.0,
        0.0,
    ]);
    records.push([
        center.0 as f32,
        center.1 as f32,
        radius.0 as f32,
        radius.1 as f32,
    ]);
    records.push([start as f32, stop as f32, 0.0, 0.0]);
    records
}

fn closed_contour_command_count(contours: &[Vec<Point>]) -> usize {
    contours
        .iter()
        .filter(|contour| contour.len() > 1)
        .map(|contour| contour.len())
        .sum()
}

pub(super) fn stroke_path_segment_records(
    segments: &[crate::sketch_state::CapturedPathSegment],
    vertices: &[Point],
    close: bool,
    matrix: Matrix,
    pixel_density: f64,
    stroke_width: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let command_count = segments.len() + usize::from(close && vertices.len() > 1);
    let mut records = stroke_path_header(matrix, pixel_density, stroke_width, color);
    records.push([command_count as f32, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    for segment in segments {
        push_stroke_segment_records(&mut records, *segment);
    }
    push_closing_segment_records(&mut records, vertices, close);
    records
}

fn push_closing_segment_records(
    records: &mut Vec<crate::gpu::StrokePathRecord>,
    vertices: &[Point],
    close: bool,
) {
    if close && vertices.len() > 1 {
        push_stroke_segment_records(
            records,
            crate::sketch_state::CapturedPathSegment::Line {
                from: *vertices.last().expect("non-empty vertices"),
                to: vertices[0],
            },
        );
    }
}

fn push_closed_line_loop_records(
    records: &mut Vec<crate::gpu::StrokePathRecord>,
    points: &[Point],
) {
    if points.len() < 2 {
        return;
    }
    for pair in points.windows(2) {
        push_stroke_segment_records(
            records,
            crate::sketch_state::CapturedPathSegment::Line {
                from: pair[0],
                to: pair[1],
            },
        );
    }
    push_stroke_segment_records(
        records,
        crate::sketch_state::CapturedPathSegment::Line {
            from: *points.last().expect("non-empty contour"),
            to: points[0],
        },
    );
}

fn push_stroke_segment_records(
    records: &mut Vec<crate::gpu::StrokePathRecord>,
    segment: crate::sketch_state::CapturedPathSegment,
) {
    match segment {
        crate::sketch_state::CapturedPathSegment::Line { from, to } => {
            records.push([STROKE_SEGMENT_LINE, from.0 as f32, from.1 as f32, 0.0]);
            records.push([to.0 as f32, to.1 as f32, 0.0, 0.0]);
            records.push([0.0, 0.0, 0.0, 0.0]);
        }
        crate::sketch_state::CapturedPathSegment::Quadratic { from, control, to } => {
            records.push([STROKE_SEGMENT_QUADRATIC, from.0 as f32, from.1 as f32, 0.0]);
            records.push([control.0 as f32, control.1 as f32, to.0 as f32, to.1 as f32]);
            records.push([0.0, 0.0, 0.0, 0.0]);
        }
        crate::sketch_state::CapturedPathSegment::Cubic {
            from,
            control1,
            control2,
            to,
        } => {
            records.push([STROKE_SEGMENT_CUBIC, from.0 as f32, from.1 as f32, 0.0]);
            records.push([
                control1.0 as f32,
                control1.1 as f32,
                control2.0 as f32,
                control2.1 as f32,
            ]);
            records.push([to.0 as f32, to.1 as f32, 0.0, 0.0]);
        }
    }
}

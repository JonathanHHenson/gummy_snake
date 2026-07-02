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
const PROCEDURAL_TRANSFORMED_RECT_KIND: f32 = 5.0;
const PROCEDURAL_TRANSFORMED_TRIANGLE_KIND: f32 = 6.0;
const PROCEDURAL_TRANSFORMED_ELLIPSE_KIND: f32 = 7.0;

impl Canvas {
    pub(crate) fn draw_gpu_polyline_with_matrix(
        &mut self,
        points: &[Point],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if points.len() < 2 {
            return Ok(());
        }
        let records =
            stroke_path_records(points, close, matrix, pixel_density, stroke_width, color);
        self.draw_gpu_stroke_path(records, blend_mode)
    }

    pub(crate) fn draw_gpu_path_segments_with_matrix(
        &mut self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if segments.is_empty() {
            return Ok(());
        }
        let records = stroke_path_segment_records(
            segments,
            vertices,
            close,
            matrix,
            pixel_density,
            stroke_width,
            color,
        );
        self.draw_gpu_stroke_path(records, blend_mode)
    }

    pub(crate) fn draw_gpu_path_fill_with_matrix(
        &mut self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if segments.is_empty() || vertices.len() < 3 || !close {
            return Ok(());
        }
        let records =
            path_fill_segment_records(segments, vertices, close, matrix, pixel_density, color);
        self.draw_gpu_fill_path(records, blend_mode)
    }

    pub(crate) fn gpu_complex_path_fill_records(
        &self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        contours: &[Vec<Point>],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
    ) -> Vec<crate::gpu::StrokePathRecord> {
        path_fill_segment_records_with_contours(
            segments,
            vertices,
            contours,
            close,
            matrix,
            pixel_density,
            color,
        )
    }

    pub(crate) fn gpu_complex_polygon_fill_records(
        &self,
        outer: &[Point],
        contours: &[Vec<Point>],
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
    ) -> Vec<crate::gpu::StrokePathRecord> {
        path_fill_polygon_records(outer, contours, matrix, pixel_density, color)
    }

    pub(crate) fn draw_gpu_complex_path_fill_with_matrix(
        &mut self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        contours: &[Vec<Point>],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if vertices.len() < 3 || !close {
            return Ok(());
        }
        let records = path_fill_segment_records_with_contours(
            segments,
            vertices,
            contours,
            close,
            matrix,
            pixel_density,
            color,
        );
        self.draw_gpu_fill_path(records, blend_mode)
    }

    pub(crate) fn draw_gpu_complex_polygon_fill_with_matrix(
        &mut self,
        outer: &[Point],
        contours: &[Vec<Point>],
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if outer.len() < 3 {
            return Ok(());
        }
        let records = path_fill_polygon_records(outer, contours, matrix, pixel_density, color);
        self.draw_gpu_fill_path(records, blend_mode)
    }

    pub(crate) fn draw_gpu_erase_path_fill_with_matrix(
        &mut self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if segments.is_empty() || vertices.len() < 3 || !close {
            return Ok(());
        }
        let records = path_fill_segment_records(
            segments,
            vertices,
            close,
            matrix,
            pixel_density,
            self.erase_color,
        );
        self.draw_gpu_erase_fill_path(records)
    }

    pub(crate) fn draw_gpu_erase_complex_path_fill_with_matrix(
        &mut self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        contours: &[Vec<Point>],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if vertices.len() < 3 || !close {
            return Ok(());
        }
        let records = path_fill_segment_records_with_contours(
            segments,
            vertices,
            contours,
            close,
            matrix,
            pixel_density,
            self.erase_color,
        );
        self.draw_gpu_erase_fill_path(records)
    }

    pub(crate) fn draw_gpu_erase_complex_polygon_fill_with_matrix(
        &mut self,
        outer: &[Point],
        contours: &[Vec<Point>],
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if outer.len() < 3 {
            return Ok(());
        }
        let records =
            path_fill_polygon_records(outer, contours, matrix, pixel_density, self.erase_color);
        self.draw_gpu_erase_fill_path(records)
    }

    pub(crate) fn draw_gpu_erase_path_segments_with_matrix(
        &mut self,
        segments: &[crate::sketch_state::CapturedPathSegment],
        vertices: &[Point],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
    ) -> PyResult<()> {
        if segments.is_empty() {
            return Ok(());
        }
        let records = stroke_path_segment_records(
            segments,
            vertices,
            close,
            matrix,
            pixel_density,
            stroke_width,
            self.erase_color,
        );
        self.draw_gpu_erase_stroke_path(records)
    }

    pub(crate) fn draw_gpu_arc_stroke_with_matrix(
        &mut self,
        center: Point,
        radius: Point,
        start: f64,
        stop: f64,
        mode: &str,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if radius.0 <= 0.0 || radius.1 <= 0.0 {
            return Ok(());
        }
        let records = stroke_path_arc_records(
            center,
            radius,
            start,
            stop,
            mode,
            matrix,
            pixel_density,
            stroke_width,
            color,
        );
        self.draw_gpu_stroke_path(records, blend_mode)
    }

    pub(crate) fn draw_gpu_erase_arc_stroke_with_matrix(
        &mut self,
        center: Point,
        radius: Point,
        start: f64,
        stop: f64,
        mode: &str,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
    ) -> PyResult<()> {
        if radius.0 <= 0.0 || radius.1 <= 0.0 {
            return Ok(());
        }
        let records = stroke_path_arc_records(
            center,
            radius,
            start,
            stop,
            mode,
            matrix,
            pixel_density,
            stroke_width,
            self.erase_color,
        );
        self.draw_gpu_erase_stroke_path(records)
    }

    pub(crate) fn draw_gpu_arc_fill_with_matrix(
        &mut self,
        center: Point,
        radius: Point,
        start: f64,
        stop: f64,
        mode: &str,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if radius.0 <= 0.0 || radius.1 <= 0.0 {
            return Ok(());
        }
        let records = path_fill_arc_records(
            center,
            radius,
            start,
            stop,
            mode,
            matrix,
            pixel_density,
            color,
        );
        self.draw_gpu_fill_path(records, blend_mode)
    }

    pub(crate) fn draw_gpu_erase_arc_fill_with_matrix(
        &mut self,
        center: Point,
        radius: Point,
        start: f64,
        stop: f64,
        mode: &str,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if radius.0 <= 0.0 || radius.1 <= 0.0 {
            return Ok(());
        }
        let records = path_fill_arc_records(
            center,
            radius,
            start,
            stop,
            mode,
            matrix,
            pixel_density,
            self.erase_color,
        );
        self.draw_gpu_erase_fill_path(records)
    }

    pub(crate) fn draw_gpu_axis_aligned_ellipse(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        style: &Style,
        pixel_density: f64,
    ) -> PyResult<()> {
        if rx <= 0.0 || ry <= 0.0 {
            return Ok(());
        }
        if style.erasing {
            if !self.can_queue_gpu_erase(style) {
                return self.prepare_cpu_composite();
            }
            if style.fill.is_some() {
                self.draw_gpu_erase_transformed_ellipse(
                    cx - rx,
                    cy - ry,
                    rx * 2.0,
                    ry * 2.0,
                    (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                    1.0,
                    0.0,
                )?;
            }
            if style.stroke.is_some() {
                self.draw_gpu_erase_transformed_ellipse(
                    cx - rx,
                    cy - ry,
                    rx * 2.0,
                    ry * 2.0,
                    (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                    1.0,
                    stroke_width(style.stroke_weight, pixel_density),
                )?;
            }
            return Ok(());
        }
        if let Some(fill) = style.fill {
            self.draw_gpu_transformed_ellipse(
                cx - rx,
                cy - ry,
                rx * 2.0,
                ry * 2.0,
                (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                1.0,
                fill,
                0.0,
                style.blend_mode_kind,
            )?;
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_transformed_ellipse(
                cx - rx,
                cy - ry,
                rx * 2.0,
                ry * 2.0,
                (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
                1.0,
                stroke,
                stroke_width(style.stroke_weight, pixel_density),
                style.blend_mode_kind,
            )?;
        }
        Ok(())
    }

    pub(crate) fn draw_gpu_transformed_rect(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_primitive_instances(
            vec![transformed_rect_instance(
                (x, y),
                (x + width, y + height),
                matrix,
                pixel_density,
                color,
            )],
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_transformed_triangle(
        &mut self,
        p0: Point,
        p1: Point,
        p2: Point,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        self.draw_gpu_primitive_instances(
            vec![transformed_triangle_instance(
                p0,
                p1,
                p2,
                matrix,
                pixel_density,
                color,
            )],
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_erase_transformed_rect(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_erase_primitive_instances(vec![transformed_rect_instance(
            (x, y),
            (x + width, y + height),
            matrix,
            pixel_density,
            self.erase_color,
        )])
    }

    pub(crate) fn draw_gpu_erase_transformed_triangle(
        &mut self,
        p0: Point,
        p1: Point,
        p2: Point,
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        self.draw_gpu_erase_primitive_instances(vec![transformed_triangle_instance(
            p0,
            p1,
            p2,
            matrix,
            pixel_density,
            self.erase_color,
        )])
    }

    pub(crate) fn draw_gpu_erase_polyline_with_matrix(
        &mut self,
        points: &[Point],
        close: bool,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
    ) -> PyResult<()> {
        if points.len() < 2 {
            return Ok(());
        }
        let records = stroke_path_records(
            points,
            close,
            matrix,
            pixel_density,
            stroke_width,
            self.erase_color,
        );
        self.draw_gpu_erase_stroke_path(records)
    }

    pub(crate) fn draw_gpu_transformed_polygon_fill(
        &mut self,
        points: &[Point],
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if points.len() < 3 {
            return Ok(());
        }
        let mut instances = Vec::with_capacity(points.len() - 2);
        for index in 1..points.len() - 1 {
            instances.push(transformed_triangle_instance(
                points[0],
                points[index],
                points[index + 1],
                matrix,
                pixel_density,
                color,
            ));
        }
        self.draw_gpu_primitive_instances(instances, blend_mode)
    }

    pub(crate) fn draw_gpu_erase_transformed_polygon_fill(
        &mut self,
        points: &[Point],
        matrix: Matrix,
        pixel_density: f64,
    ) -> PyResult<()> {
        if points.len() < 3 {
            return Ok(());
        }
        let mut instances = Vec::with_capacity(points.len() - 2);
        for index in 1..points.len() - 1 {
            instances.push(transformed_triangle_instance(
                points[0],
                points[index],
                points[index + 1],
                matrix,
                pixel_density,
                self.erase_color,
            ));
        }
        self.draw_gpu_erase_primitive_instances(instances)
    }

    pub(crate) fn draw_gpu_transformed_ellipse(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
        color: Rgba,
        stroke_width: f64,
        blend_mode: BlendMode,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_primitive_instances(
            vec![transformed_ellipse_instance(
                (x, y),
                (x + width, y + height),
                matrix,
                pixel_density,
                color,
                stroke_width,
            )],
            blend_mode,
        )
    }

    pub(crate) fn draw_gpu_erase_transformed_ellipse(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        matrix: Matrix,
        pixel_density: f64,
        stroke_width: f64,
    ) -> PyResult<()> {
        if width == 0.0 || height == 0.0 {
            return Ok(());
        }
        self.draw_gpu_erase_primitive_instances(vec![transformed_ellipse_instance(
            (x, y),
            (x + width, y + height),
            matrix,
            pixel_density,
            self.erase_color,
            stroke_width,
        )])
    }

    pub(crate) fn can_draw_gpu_blend_ellipse(&self, style: &Style) -> bool {
        self.gpu.is_some()
            && !style.erasing
            && style.stroke.is_none()
            && style.fill.is_some()
            && matches!(
                style.blend_mode_kind,
                BlendMode::Multiply
                    | BlendMode::Screen
                    | BlendMode::Difference
                    | BlendMode::Exclusion
                    | BlendMode::Darkest
                    | BlendMode::Lightest
            )
            && self.clip_masks.is_empty()
    }

    pub(crate) fn can_draw_gpu_text(&self, style: &Style, matrix: Matrix) -> bool {
        self.gpu.is_some()
            && self.runtime.is_none()
            && !self.cpu_compositing_active
            && self.clip_masks.is_empty()
            && !style.erasing
            && style.fill.is_some()
            && style.stroke.is_none()
            && style.blend_mode_kind == BlendMode::Blend
            && style.text_font_path.is_none()
            && matrix == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            && self
                .gpu
                .as_ref()
                .is_none_or(|gpu| gpu.can_append_glyphon_text_command())
    }

    pub(crate) fn draw_gpu_blend_ellipse(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        style: &Style,
    ) -> PyResult<()> {
        let Some(fill) = style.fill else {
            return Ok(());
        };
        self.upload_stale_texture(false)?;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_blend_ellipse(
                cx as f32,
                cy as f32,
                rx as f32,
                ry as f32,
                crate::raster::gpu_color(fill),
                style.blend_mode_kind,
            );
            self.record_native_region_effect_draw(true);
        }
        Ok(())
    }
}

fn transformed_rect_instance(
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

fn transformed_ellipse_instance(
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

fn transformed_triangle_instance(
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

fn stroke_path_records(
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

fn stroke_path_arc_records(
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

fn path_fill_segment_records(
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

pub(crate) fn path_fill_segment_records_with_contours(
    segments: &[crate::sketch_state::CapturedPathSegment],
    vertices: &[Point],
    contours: &[Vec<Point>],
    close: bool,
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let close_segment = close && vertices.len() > 1;
    let contour_command_count: usize = contours
        .iter()
        .filter(|contour| contour.len() > 1)
        .map(|contour| contour.len())
        .sum();
    let command_count = segments.len() + usize::from(close_segment) + contour_command_count;
    let mut records = stroke_path_header(matrix, pixel_density, 0.0, color);
    records.push([command_count as f32, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    for segment in segments {
        push_stroke_segment_records(&mut records, *segment);
    }
    if close_segment {
        push_stroke_segment_records(
            &mut records,
            crate::sketch_state::CapturedPathSegment::Line {
                from: *vertices.last().expect("non-empty vertices"),
                to: vertices[0],
            },
        );
    }
    for contour in contours {
        push_closed_line_loop_records(&mut records, contour);
    }
    records
}

pub(crate) fn path_fill_polygon_records(
    outer: &[Point],
    contours: &[Vec<Point>],
    matrix: Matrix,
    pixel_density: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let contour_command_count: usize = contours
        .iter()
        .filter(|contour| contour.len() > 1)
        .map(|contour| contour.len())
        .sum();
    let command_count = outer.len() + contour_command_count;
    let mut records = stroke_path_header(matrix, pixel_density, 0.0, color);
    records.push([command_count as f32, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    push_closed_line_loop_records(&mut records, outer);
    for contour in contours {
        push_closed_line_loop_records(&mut records, contour);
    }
    records
}

fn path_fill_arc_records(
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

fn stroke_path_segment_records(
    segments: &[crate::sketch_state::CapturedPathSegment],
    vertices: &[Point],
    close: bool,
    matrix: Matrix,
    pixel_density: f64,
    stroke_width: f64,
    color: Rgba,
) -> Vec<crate::gpu::StrokePathRecord> {
    let close_segment = close && vertices.len() > 1;
    let command_count = segments.len() + usize::from(close_segment);
    let mut records = stroke_path_header(matrix, pixel_density, stroke_width, color);
    records.push([command_count as f32, 0.0, STROKE_PATH_SEGMENT_RECORDS, 0.0]);
    for segment in segments {
        push_stroke_segment_records(&mut records, *segment);
    }
    if close_segment {
        push_stroke_segment_records(
            &mut records,
            crate::sketch_state::CapturedPathSegment::Line {
                from: *vertices.last().expect("non-empty vertices"),
                to: vertices[0],
            },
        );
    }
    records
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stroke_path_records_carry_matrix_style_and_logical_points() {
        let records = stroke_path_records(
            &[(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
            true,
            (2.0, 0.5, 0.25, 3.0, 5.0, 7.0),
            2.0,
            6.0,
            Rgba {
                r: 255,
                g: 0,
                b: 0,
                a: 128,
            },
        );

        assert_eq!(records[0], [2.0, 0.5, 0.25, 3.0]);
        assert_eq!(records[1], [5.0, 7.0, 2.0, 6.0]);
        assert_eq!(records[2], [1.0, 0.0, 0.0, 128.0 / 255.0]);
        assert_eq!(records[3], [3.0, 1.0, 0.0, 0.0]);
        assert_eq!(records[4], [1.0, 2.0, 0.0, 0.0]);
        assert_eq!(records[5], [3.0, 4.0, 0.0, 0.0]);
        assert_eq!(records[6], [5.0, 6.0, 0.0, 0.0]);
    }
}

use crate::*;

use super::records::{
    path_fill_arc_records, path_fill_polygon_records, path_fill_segment_records,
    path_fill_segment_records_with_contours, stroke_path_arc_records, stroke_path_records,
    stroke_path_segment_records,
};

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
}

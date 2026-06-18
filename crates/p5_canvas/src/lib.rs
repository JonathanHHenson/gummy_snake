mod gpu;
mod runtime;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict};
use runtime::{
    native_window_available as runtime_native_window_available, InteractiveRuntime, RuntimeEvent,
};
use std::f64::consts::PI;

const SUPPORTED_RENDERER: &str = "p2d";
const SUPPORTED_MODE: &str = "headless";
const INTERACTIVE_MODE: &str = "interactive";
const SUPPORTED_BLEND_MODE: &str = "blend";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Rgba {
    r: u8,
    g: u8,
    b: u8,
    a: u8,
}

impl Rgba {
    fn from_tuple(tuple: (u8, u8, u8, u8)) -> Self {
        Self {
            r: tuple.0,
            g: tuple.1,
            b: tuple.2,
            a: tuple.3,
        }
    }

    fn as_array(self) -> [u8; 4] {
        [self.r, self.g, self.b, self.a]
    }
}

#[derive(Clone, Debug)]
struct Style {
    fill: Option<Rgba>,
    stroke: Option<Rgba>,
    stroke_weight: f64,
    blend_mode: String,
    erasing: bool,
}

type Matrix = (f64, f64, f64, f64, f64, f64);

type Point = (f64, f64);

struct OverlayRegion<'a> {
    min_x: usize,
    min_y: usize,
    width: usize,
    height: usize,
    canvas_width: usize,
    pixels: &'a mut [u8],
    present_pixels: &'a mut [u32],
    erasing: bool,
}

impl<'a> OverlayRegion<'a> {
    fn from_bounds(
        bounds: (usize, usize, usize, usize),
        canvas_width: usize,
        pixels: &'a mut [u8],
        present_pixels: &'a mut [u32],
        erasing: bool,
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
            alpha_composite_pixel(dst, &color);
        }
        self.present_pixels[pixel_index] = rgba_to_present_pixel(dst);
    }
}

#[pyclass(unsendable)]
struct Canvas {
    width: i64,
    height: i64,
    physical_width: usize,
    physical_height: usize,
    pixel_density: f64,
    mode: String,
    window_open: bool,
    closed: bool,
    pixels: Vec<u8>,
    present_pixels: Vec<u32>,
    runtime: Option<InteractiveRuntime>,
    gpu: Option<gpu::GpuRenderer>,
    gpu_error: Option<String>,
    render_dirty: bool,
    offscreen_dirty: bool,
    pixels_stale: bool,
}

#[pymethods]
impl Canvas {
    #[new]
    #[pyo3(signature = (width, height, pixel_density=1.0, mode=SUPPORTED_MODE, renderer=SUPPORTED_RENDERER))]
    fn new(
        width: i64,
        height: i64,
        pixel_density: f64,
        mode: &str,
        renderer: &str,
    ) -> PyResult<Self> {
        validate_mode_and_renderer(mode, renderer)?;
        let (physical_width, physical_height) = physical_dimensions(width, height, pixel_density)?;
        let (gpu, gpu_error) = match gpu::GpuRenderer::new(physical_width, physical_height) {
            Ok(renderer) => (Some(renderer), None),
            Err(err) => (None, Some(err)),
        };
        Ok(Self {
            width,
            height,
            physical_width,
            physical_height,
            pixel_density,
            mode: mode.to_string(),
            window_open: mode == INTERACTIVE_MODE,
            closed: false,
            pixels: vec![0; physical_width * physical_height * 4],
            present_pixels: vec![0; physical_width * physical_height],
            runtime: None,
            gpu,
            gpu_error,
            render_dirty: false,
            offscreen_dirty: false,
            pixels_stale: false,
        })
    }

    fn resize(
        &mut self,
        width: i64,
        height: i64,
        pixel_density: f64,
        renderer: &str,
    ) -> PyResult<()> {
        validate_renderer(renderer)?;
        let (physical_width, physical_height) = physical_dimensions(width, height, pixel_density)?;
        self.width = width;
        self.height = height;
        self.pixel_density = pixel_density;
        self.physical_width = physical_width;
        self.physical_height = physical_height;
        self.pixels = vec![0; physical_width * physical_height * 4];
        self.present_pixels = vec![0; physical_width * physical_height];
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.resize(physical_width, physical_height);
            gpu.clear_transparent();
            gpu.render();
        }
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .request_resize(width, height, pixel_density)
                .map_err(|err| {
                    PyValueError::new_err(format!("Failed to resize native canvas window: {err}"))
                })?;
        }
        Ok(())
    }

    fn dimensions(&self) -> (i64, i64, usize, usize, f64) {
        (
            self.width,
            self.height,
            self.physical_width,
            self.physical_height,
            self.pixel_density,
        )
    }

    fn display_density(&self) -> f64 {
        if let Some(runtime) = self.runtime.as_ref() {
            runtime.display_density()
        } else if self.window_open {
            self.pixel_density.max(1.0)
        } else {
            1.0
        }
    }

    fn native_window_available(&self) -> bool {
        runtime_native_window_available()
    }

    fn gpu_available(&self) -> bool {
        self.gpu.is_some()
    }

    fn gpu_status(&self) -> String {
        self.gpu_error
            .clone()
            .unwrap_or_else(|| "available".to_string())
    }

    fn open_window(&mut self) -> PyResult<()> {
        self.mode = INTERACTIVE_MODE.to_string();
        self.window_open = true;
        self.closed = false;
        self.runtime = Some(
            InteractiveRuntime::open(self.width, self.height).map_err(|err| {
                PyValueError::new_err(format!("Failed to open native canvas window: {err}"))
            })?,
        );
        Ok(())
    }

    fn should_close(&self) -> bool {
        self.closed
            || self
                .runtime
                .as_ref()
                .map(|runtime| runtime.should_close())
                .unwrap_or(false)
    }

    fn poll_events(&mut self) -> PyResult<Vec<Py<PyAny>>> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(Vec::new());
        };
        let events = runtime.poll_events().map_err(|err| {
            PyValueError::new_err(format!("Failed to poll native canvas events: {err}"))
        })?;
        if runtime.should_close() {
            self.closed = true;
        }
        Python::with_gil(|py| {
            events
                .into_iter()
                .map(|event| runtime_event_to_pyobject(py, event))
                .collect()
        })
    }

    fn begin_frame(&mut self) {
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = false;
    }

    fn end_frame(&mut self) {
        if self.render_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        }
    }

    fn present(&mut self) -> PyResult<()> {
        if self.render_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        }
        if let Some(runtime) = self.runtime.as_mut() {
            let window = runtime.window().ok_or_else(|| {
                PyValueError::new_err("Native canvas window is not available for presentation.")
            })?;
            let (surface_width, surface_height) = runtime.physical_size();
            let gpu = self.gpu.as_mut().ok_or_else(|| {
                PyValueError::new_err(
                    self.gpu_error
                        .clone()
                        .unwrap_or_else(|| "GPU presentation is unavailable.".to_string()),
                )
            })?;
            if self.render_dirty {
                gpu.present_to_window(window, surface_width, surface_height)
                    .map_err(|err| {
                        PyValueError::new_err(format!("Failed to present native GPU frame: {err}"))
                    })?;
                self.render_dirty = false;
                self.pixels_stale = true;
            }
            if runtime.should_close() {
                self.closed = true;
            }
        }
        Ok(())
    }

    fn close(&mut self) {
        self.closed = true;
        if let Some(runtime) = self.runtime.as_mut() {
            runtime.close();
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.drop_surface();
        }
        self.runtime = None;
    }

    fn background(&mut self, rgba: (u8, u8, u8, u8)) {
        let color = Rgba::from_tuple(rgba).as_array();
        let packed = rgba_to_present_pixel(&color);
        for (pixel, present_pixel) in self
            .pixels
            .chunks_exact_mut(4)
            .zip(self.present_pixels.iter_mut())
        {
            pixel.copy_from_slice(&color);
            *present_pixel = packed;
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.set_clear_color(gpu_color(Rgba::from_tuple(rgba)));
            self.render_dirty = true;
            self.offscreen_dirty = true;
        }
    }

    fn clear(&mut self) {
        self.pixels.fill(0);
        self.present_pixels.fill(0);
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.clear_transparent();
            self.render_dirty = true;
            self.offscreen_dirty = true;
        }
    }

    fn point(&mut self, x: f64, y: f64, style: &Bound<'_, PyAny>, matrix: Matrix) -> PyResult<()> {
        let style = parse_style(style)?;
        ensure_supported_style(&style)?;
        let color = match style.stroke.or(style.fill) {
            Some(color) => color,
            None => return Ok(()),
        };
        let (tx, ty) = self.transform_point(matrix, x, y);
        let radius = (style.stroke_weight * self.pixel_density / 2.0).max(0.5);
        let bounds = clipped_bounds(
            &[(tx, ty)],
            radius,
            self.physical_width,
            self.physical_height,
        );
        self.draw_gpu_disc(tx, ty, radius, color);
        if self.gpu.is_some() && !style.erasing {
            return Ok(());
        }
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
        ) else {
            return Ok(());
        };
        fill_disc(&mut overlay, tx, ty, radius, color);
        Ok(())
    }

    fn line(
        &mut self,
        x1: f64,
        y1: f64,
        x2: f64,
        y2: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = parse_style(style)?;
        ensure_supported_style(&style)?;
        let stroke = match style.stroke {
            Some(color) => color,
            None => return Ok(()),
        };
        let p1 = self.transform_point(matrix, x1, y1);
        let p2 = self.transform_point(matrix, x2, y2);
        let radius = stroke_width(style.stroke_weight, self.pixel_density) / 2.0;
        let bounds = clipped_bounds(&[p1, p2], radius, self.physical_width, self.physical_height);
        self.draw_gpu_segment(p1, p2, radius * 2.0, stroke);
        if self.gpu.is_some() && !style.erasing {
            return Ok(());
        }
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
        ) else {
            return Ok(());
        };
        stroke_segment(&mut overlay, p1, p2, radius * 2.0, stroke);
        Ok(())
    }

    #[pyo3(signature = (points, style, matrix, close=true))]
    fn polygon(
        &mut self,
        points: Vec<(f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let style = parse_style(style)?;
        ensure_supported_style(&style)?;
        if points.is_empty() {
            return Ok(());
        }
        let transformed: Vec<Point> = points
            .iter()
            .map(|(x, y)| self.transform_point(matrix, *x, *y))
            .collect();
        let padding = if style.stroke.is_some() {
            stroke_width(style.stroke_weight, self.pixel_density) / 2.0
        } else {
            0.0
        };
        let bounds = clipped_bounds(
            &transformed,
            padding,
            self.physical_width,
            self.physical_height,
        );
        self.draw_gpu_polygon(&transformed, &style, close, self.pixel_density);
        if self.gpu.is_some() && !style.erasing {
            return Ok(());
        }
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
        ) else {
            return Ok(());
        };
        draw_polygon_overlay(
            &mut overlay,
            &transformed,
            &style,
            close,
            self.pixel_density,
        );
        Ok(())
    }

    fn ellipse(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let parsed_style = parse_style(style)?;
        ensure_supported_style(&parsed_style)?;
        if let Some((cx, cy, rx, ry)) =
            self.axis_aligned_ellipse_geometry(matrix, x, y, width, height)
        {
            let padding = if parsed_style.stroke.is_some() {
                stroke_width(parsed_style.stroke_weight, self.pixel_density) / 2.0
            } else {
                0.0
            };
            let bounds = ellipse_bounds(
                cx,
                cy,
                rx,
                ry,
                padding,
                self.physical_width,
                self.physical_height,
            );
            self.draw_gpu_axis_aligned_ellipse(cx, cy, rx, ry, &parsed_style, self.pixel_density);
            if self.gpu.is_some() && !parsed_style.erasing {
                return Ok(());
            }
            let Some(mut overlay) = OverlayRegion::from_bounds(
                bounds,
                self.physical_width,
                &mut self.pixels,
                &mut self.present_pixels,
                parsed_style.erasing,
            ) else {
                return Ok(());
            };
            draw_axis_aligned_ellipse(
                &mut overlay,
                cx,
                cy,
                rx,
                ry,
                &parsed_style,
                self.pixel_density,
            );
            return Ok(());
        }

        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        let rx = width / 2.0;
        let ry = height / 2.0;
        let points: Vec<Point> = (0..64)
            .map(|index| {
                let t = 2.0 * PI * index as f64 / 64.0;
                (cx + t.cos() * rx, cy + t.sin() * ry)
            })
            .collect();
        self.polygon(points, style, matrix, true)
    }

    fn arc(
        &mut self,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        start: f64,
        mut stop: f64,
        mode: &str,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        let rx = width / 2.0;
        let ry = height / 2.0;
        while stop < start {
            stop += 2.0 * PI;
        }
        let steps = ((stop - start).abs() / (2.0 * PI) * 64.0).floor().max(8.0) as usize;
        let arc_points: Vec<Point> = (0..=steps)
            .map(|index| {
                let t = start + (stop - start) * index as f64 / steps as f64;
                (cx + t.cos() * rx, cy + t.sin() * ry)
            })
            .collect();
        match mode {
            "pie" => {
                let mut points = vec![(cx, cy)];
                points.extend(arc_points);
                self.polygon(points, style, matrix, true)
            }
            "chord" => self.polygon(arc_points, style, matrix, true),
            _ => {
                let parsed_style = parse_style(style)?;
                ensure_supported_style(&parsed_style)?;
                let transformed: Vec<Point> = arc_points
                    .iter()
                    .map(|(px, py)| self.transform_point(matrix, *px, *py))
                    .collect();
                let padding = if parsed_style.stroke.is_some() {
                    stroke_width(parsed_style.stroke_weight, self.pixel_density) / 2.0
                } else {
                    0.0
                };
                let bounds = clipped_bounds(
                    &transformed,
                    padding,
                    self.physical_width,
                    self.physical_height,
                );
                if parsed_style.fill.is_some() && mode != "open" {
                    self.draw_gpu_polygon(
                        &transformed,
                        &Style {
                            stroke: None,
                            ..parsed_style.clone()
                        },
                        true,
                        self.pixel_density,
                    );
                }
                if let Some(stroke) = parsed_style.stroke {
                    self.draw_gpu_polyline(
                        &transformed,
                        false,
                        stroke_width(parsed_style.stroke_weight, self.pixel_density),
                        stroke,
                    );
                }
                if self.gpu.is_some() && !parsed_style.erasing {
                    return Ok(());
                }
                let Some(mut overlay) = OverlayRegion::from_bounds(
                    bounds,
                    self.physical_width,
                    &mut self.pixels,
                    &mut self.present_pixels,
                    parsed_style.erasing,
                ) else {
                    return Ok(());
                };
                if parsed_style.fill.is_some() && mode != "open" {
                    draw_polygon_overlay(
                        &mut overlay,
                        &transformed,
                        &Style {
                            stroke: None,
                            ..parsed_style.clone()
                        },
                        true,
                        self.pixel_density,
                    );
                }
                if let Some(stroke) = parsed_style.stroke {
                    draw_polyline_stroke(
                        &mut overlay,
                        &transformed,
                        false,
                        stroke_width(parsed_style.stroke_weight, self.pixel_density),
                        stroke,
                    );
                }
                Ok(())
            }
        }
    }

    fn load_pixels(&mut self) -> Vec<u8> {
        if self.offscreen_dirty {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        self.pixels.clone()
    }

    fn update_pixels(&mut self, pixels: Vec<u8>) -> PyResult<()> {
        let expected = self.physical_width * self.physical_height * 4;
        if pixels.len() != expected {
            return Err(PyValueError::new_err(format!(
                "Pixel buffer length must be {expected}, got {}.",
                pixels.len()
            )));
        }
        self.pixels = pixels;
        self.sync_present_pixels_from_rgba();
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.upload_pixels(&self.pixels)
                .map_err(|err| PyValueError::new_err(format!("Failed to upload pixels: {err}")))?;
        }
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        Ok(())
    }

    fn save(&mut self, path: &str) -> PyResult<()> {
        if self.offscreen_dirty {
            self.render_gpu_frame(true);
        } else if self.pixels_stale {
            self.read_gpu_pixels();
        }
        image::save_buffer_with_format(
            path,
            &self.pixels,
            self.physical_width as u32,
            self.physical_height as u32,
            image::ColorType::Rgba8,
            image::ImageFormat::Png,
        )
        .map_err(|err| PyValueError::new_err(format!("Failed to save canvas: {err}")))
    }
}

impl Canvas {
    fn transform_point(&self, matrix: Matrix, x: f64, y: f64) -> Point {
        let (a, b, c, d, e, f) = matrix;
        (
            (a * x + c * y + e) * self.pixel_density,
            (b * x + d * y + f) * self.pixel_density,
        )
    }

    fn axis_aligned_ellipse_geometry(
        &self,
        matrix: Matrix,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    ) -> Option<(f64, f64, f64, f64)> {
        let (a, b, c, d, e, f) = matrix;
        if b.abs() > f64::EPSILON || c.abs() > f64::EPSILON {
            return None;
        }
        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        Some((
            (a * cx + e) * self.pixel_density,
            (d * cy + f) * self.pixel_density,
            (width * a * self.pixel_density / 2.0).abs(),
            (height * d * self.pixel_density / 2.0).abs(),
        ))
    }

    fn sync_present_pixels_from_rgba(&mut self) {
        for (index, rgba) in self.pixels.chunks_exact(4).enumerate() {
            self.present_pixels[index] = rgba_to_present_pixel(rgba);
        }
    }

    fn render_gpu_frame(&mut self, readback: bool) {
        let Some(gpu) = self.gpu.as_mut() else {
            self.render_dirty = false;
            self.offscreen_dirty = false;
            return;
        };
        gpu.render();
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = true;
        if readback {
            self.read_gpu_pixels();
        }
    }

    fn read_gpu_pixels(&mut self) {
        let Some(gpu) = self.gpu.as_ref() else {
            self.pixels_stale = false;
            return;
        };
        match gpu.read_pixels() {
            Ok(pixels) => {
                self.pixels = pixels;
                self.sync_present_pixels_from_rgba();
                self.pixels_stale = false;
            }
            Err(err) => {
                self.gpu_error = Some(err);
                self.pixels_stale = false;
            }
        }
    }

    fn draw_gpu_polygon(
        &mut self,
        points: &[Point],
        style: &Style,
        close: bool,
        pixel_density: f64,
    ) {
        if style.erasing {
            return;
        }
        if close && points.len() >= 3 {
            if let Some(fill) = style.fill {
                let mut vertices = Vec::with_capacity((points.len() - 2) * 3);
                for index in 1..points.len() - 1 {
                    push_triangle(
                        &mut vertices,
                        points[0],
                        points[index],
                        points[index + 1],
                        fill,
                    );
                }
                self.draw_gpu_triangles(vertices);
            }
        }
        if let Some(stroke) = style.stroke {
            self.draw_gpu_polyline(
                points,
                close,
                stroke_width(style.stroke_weight, pixel_density),
                stroke,
            );
        }
    }

    fn draw_gpu_polyline(&mut self, points: &[Point], close: bool, stroke_width: f64, color: Rgba) {
        if points.len() < 2 {
            return;
        }
        for pair in points.windows(2) {
            self.draw_gpu_segment(pair[0], pair[1], stroke_width, color);
        }
        if close {
            self.draw_gpu_segment(
                *points.last().expect("non-empty points"),
                points[0],
                stroke_width,
                color,
            );
        }
    }

    fn draw_gpu_segment(&mut self, p1: Point, p2: Point, stroke_width: f64, color: Rgba) {
        let dx = p2.0 - p1.0;
        let dy = p2.1 - p1.1;
        let length = (dx * dx + dy * dy).sqrt();
        if length <= f64::EPSILON {
            self.draw_gpu_disc(p1.0, p1.1, (stroke_width / 2.0).max(0.5), color);
            return;
        }
        let half = (stroke_width / 2.0).max(0.5);
        let nx = -dy / length * half;
        let ny = dx / length * half;
        let a = (p1.0 + nx, p1.1 + ny);
        let b = (p1.0 - nx, p1.1 - ny);
        let c = (p2.0 - nx, p2.1 - ny);
        let d = (p2.0 + nx, p2.1 + ny);
        let mut vertices = Vec::with_capacity(6);
        push_triangle(&mut vertices, a, b, c, color);
        push_triangle(&mut vertices, a, c, d, color);
        self.draw_gpu_triangles(vertices);
    }

    fn draw_gpu_disc(&mut self, cx: f64, cy: f64, radius: f64, color: Rgba) {
        if radius <= 0.0 {
            return;
        }
        let steps = 24usize;
        let mut vertices = Vec::with_capacity(steps * 3);
        for index in 0..steps {
            let a = 2.0 * PI * index as f64 / steps as f64;
            let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
            push_triangle(
                &mut vertices,
                (cx, cy),
                (cx + a.cos() * radius, cy + a.sin() * radius),
                (cx + b.cos() * radius, cy + b.sin() * radius),
                color,
            );
        }
        self.draw_gpu_triangles(vertices);
    }

    fn draw_gpu_axis_aligned_ellipse(
        &mut self,
        cx: f64,
        cy: f64,
        rx: f64,
        ry: f64,
        style: &Style,
        pixel_density: f64,
    ) {
        if style.erasing || rx <= 0.0 || ry <= 0.0 {
            return;
        }
        if let Some(fill) = style.fill {
            let steps = 64usize;
            let mut vertices = Vec::with_capacity(steps * 3);
            for index in 0..steps {
                let a = 2.0 * PI * index as f64 / steps as f64;
                let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
                push_triangle(
                    &mut vertices,
                    (cx, cy),
                    (cx + a.cos() * rx, cy + a.sin() * ry),
                    (cx + b.cos() * rx, cy + b.sin() * ry),
                    fill,
                );
            }
            self.draw_gpu_triangles(vertices);
        }
        if let Some(stroke) = style.stroke {
            let half_width = (stroke_width(style.stroke_weight, pixel_density) / 2.0).max(0.5);
            let outer_rx = rx + half_width;
            let outer_ry = ry + half_width;
            let inner_rx = (rx - half_width).max(0.0);
            let inner_ry = (ry - half_width).max(0.0);
            let steps = 64usize;
            let mut vertices = Vec::with_capacity(steps * 6);
            for index in 0..steps {
                let a = 2.0 * PI * index as f64 / steps as f64;
                let b = 2.0 * PI * (index + 1) as f64 / steps as f64;
                let outer_a = (cx + a.cos() * outer_rx, cy + a.sin() * outer_ry);
                let inner_a = (cx + a.cos() * inner_rx, cy + a.sin() * inner_ry);
                let inner_b = (cx + b.cos() * inner_rx, cy + b.sin() * inner_ry);
                let outer_b = (cx + b.cos() * outer_rx, cy + b.sin() * outer_ry);
                push_triangle(&mut vertices, outer_a, inner_a, inner_b, stroke);
                push_triangle(&mut vertices, outer_a, inner_b, outer_b, stroke);
            }
            self.draw_gpu_triangles(vertices);
        }
    }

    fn draw_gpu_triangles(&mut self, vertices: Vec<([f32; 2], gpu::GpuColor)>) {
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.draw_triangles(vertices);
            self.render_dirty = true;
            self.offscreen_dirty = true;
        }
    }
}

#[pyfunction]
fn health_check() -> &'static str {
    "rust-canvas"
}

#[pyfunction]
fn native_window_available() -> bool {
    runtime_native_window_available()
}

#[pyfunction]
fn gpu_available() -> bool {
    gpu::GpuRenderer::is_available()
}

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(health_check, m)?)?;
    m.add_function(wrap_pyfunction!(native_window_available, m)?)?;
    m.add_function(wrap_pyfunction!(gpu_available, m)?)?;
    m.add_class::<Canvas>()?;
    Ok(())
}

fn runtime_event_to_pyobject(py: Python<'_>, event: RuntimeEvent) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("type", event.event_type)?;
    if let Some(x) = event.x {
        dict.set_item("x", x)?;
    }
    if let Some(y) = event.y {
        dict.set_item("y", y)?;
    }
    if let Some(dx) = event.dx {
        dict.set_item("dx", dx)?;
    }
    if let Some(dy) = event.dy {
        dict.set_item("dy", dy)?;
    }
    if let Some(button) = event.button {
        dict.set_item("button", button)?;
    }
    if let Some(scroll_x) = event.scroll_x {
        dict.set_item("scroll_x", scroll_x)?;
    }
    if let Some(scroll_y) = event.scroll_y {
        dict.set_item("scroll_y", scroll_y)?;
    }
    if let Some(modifiers) = event.modifiers {
        dict.set_item("modifiers", modifiers)?;
    }
    if let Some(key) = event.key {
        if !key.is_empty() {
            dict.set_item("key", key)?;
        }
    }
    if let Some(code) = event.code {
        if !code.is_empty() {
            dict.set_item("code", code)?;
        }
    }
    if let Some(text) = event.text {
        dict.set_item("text", text)?;
    }
    if let Some(width) = event.width {
        dict.set_item("width", width)?;
    }
    if let Some(height) = event.height {
        dict.set_item("height", height)?;
    }
    if let Some(pixel_density) = event.pixel_density {
        dict.set_item("pixel_density", pixel_density)?;
    }
    if let Some(coordinates) = event.coordinates {
        dict.set_item("coordinates", coordinates)?;
    }
    Ok(dict.into_any().unbind())
}

fn validate_mode_and_renderer(mode: &str, renderer: &str) -> PyResult<()> {
    if mode != SUPPORTED_MODE && mode != INTERACTIVE_MODE {
        return Err(PyValueError::new_err(format!(
            "Unsupported canvas mode {mode:?}; supported modes are {SUPPORTED_MODE:?} and {INTERACTIVE_MODE:?}."
        )));
    }
    validate_renderer(renderer)
}

fn validate_renderer(renderer: &str) -> PyResult<()> {
    if renderer != SUPPORTED_RENDERER {
        return Err(PyValueError::new_err(format!(
            "Unsupported renderer {renderer:?}; only {SUPPORTED_RENDERER:?} is implemented."
        )));
    }
    Ok(())
}

fn physical_dimensions(width: i64, height: i64, pixel_density: f64) -> PyResult<(usize, usize)> {
    if width <= 0 || height <= 0 {
        return Err(PyValueError::new_err(
            "Canvas width and height must be positive.",
        ));
    }
    if pixel_density <= 0.0 || !pixel_density.is_finite() {
        return Err(PyValueError::new_err("Pixel density must be positive."));
    }
    let physical_width = ((width as f64 * pixel_density).round() as i64).max(1) as usize;
    let physical_height = ((height as f64 * pixel_density).round() as i64).max(1) as usize;
    Ok((physical_width, physical_height))
}

fn parse_style(style: &Bound<'_, PyAny>) -> PyResult<Style> {
    let dict = style.downcast::<PyDict>()?;
    let fill = parse_optional_rgba(dict, "fill")?;
    let stroke = parse_optional_rgba(dict, "stroke")?;
    let stroke_weight = dict
        .get_item("stroke_weight")?
        .ok_or_else(|| PyValueError::new_err("Style payload missing 'stroke_weight'."))?
        .extract::<f64>()?;
    let blend_mode = dict
        .get_item("blend_mode")?
        .ok_or_else(|| PyValueError::new_err("Style payload missing 'blend_mode'."))?
        .extract::<String>()?;
    let erasing = dict
        .get_item("erasing")?
        .ok_or_else(|| PyValueError::new_err("Style payload missing 'erasing'."))?
        .extract::<bool>()?;
    Ok(Style {
        fill,
        stroke,
        stroke_weight,
        blend_mode,
        erasing,
    })
}

fn parse_optional_rgba(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Rgba>> {
    let Some(value) = dict.get_item(key)? else {
        return Err(PyValueError::new_err(format!(
            "Style payload missing {key:?}."
        )));
    };
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(Rgba::from_tuple(value.extract::<(u8, u8, u8, u8)>()?)))
    }
}

fn ensure_supported_style(style: &Style) -> PyResult<()> {
    if style.stroke_weight < 0.0 || !style.stroke_weight.is_finite() {
        return Err(PyValueError::new_err("stroke_weight cannot be negative."));
    }
    if style.blend_mode != SUPPORTED_BLEND_MODE {
        return Err(PyValueError::new_err(format!(
            "Unsupported blend mode {:?}; only {:?} is implemented by p5_canvas.",
            style.blend_mode, SUPPORTED_BLEND_MODE
        )));
    }
    Ok(())
}

fn stroke_width(stroke_weight: f64, pixel_density: f64) -> f64 {
    (stroke_weight * pixel_density).round().max(1.0)
}

fn draw_polygon_overlay(
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

fn draw_axis_aligned_ellipse(
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

fn draw_polyline_stroke(
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

fn stroke_segment(
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

fn fill_disc(overlay: &mut OverlayRegion<'_>, cx: f64, cy: f64, radius: f64, color: Rgba) {
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

fn ellipse_bounds(
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

fn clipped_bounds(
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

fn point_in_polygon(sample: Point, points: &[Point]) -> bool {
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

fn alpha_composite_pixel(dst: &mut [u8], src: &[u8]) {
    let src_alpha = src[3] as u32;
    if src_alpha == 255 {
        dst.copy_from_slice(src);
        return;
    }
    let dst_alpha = dst[3] as u32;
    if src_alpha == 0 {
        return;
    }
    let inv_src_alpha = 255 - src_alpha;
    let out_alpha = src_alpha + (dst_alpha * inv_src_alpha + 127) / 255;
    if out_alpha == 0 {
        dst.copy_from_slice(&[0, 0, 0, 0]);
        return;
    }
    for channel in 0..3 {
        let src_premul = src[channel] as u32 * src_alpha;
        let dst_premul = dst[channel] as u32 * dst_alpha * inv_src_alpha / 255;
        dst[channel] = ((src_premul + dst_premul + out_alpha / 2) / out_alpha) as u8;
    }
    dst[3] = out_alpha as u8;
}

fn rgba_to_present_pixel(rgba: &[u8]) -> u32 {
    ((rgba[3] as u32) << 24) | ((rgba[0] as u32) << 16) | ((rgba[1] as u32) << 8) | rgba[2] as u32
}

fn gpu_color(color: Rgba) -> gpu::GpuColor {
    gpu::GpuColor {
        r: color.r,
        g: color.g,
        b: color.b,
        a: color.a,
    }
}

fn push_triangle(
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_check_reports_canvas_backend() {
        assert_eq!(health_check(), "rust-canvas");
        assert_eq!(native_window_available(), runtime_native_window_available());
    }

    #[test]
    fn canvas_tracks_logical_and_physical_dimensions() {
        let canvas = Canvas::new(10, 8, 2.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

        assert_eq!(canvas.dimensions(), (10, 8, 20, 16, 2.0));
        assert_eq!(canvas.pixels.len(), 20 * 16 * 4);
    }

    #[test]
    fn canvas_rejects_invalid_dimensions_and_density() {
        assert!(Canvas::new(0, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).is_err());
        assert!(Canvas::new(10, 8, 0.0, SUPPORTED_MODE, SUPPORTED_RENDERER).is_err());
    }

    #[test]
    fn background_clear_and_pixel_update_round_trip() {
        let mut canvas = Canvas::new(2, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
        canvas.background((10, 20, 30, 255));
        assert_eq!(canvas.load_pixels(), vec![10, 20, 30, 255, 10, 20, 30, 255]);

        canvas
            .update_pixels(vec![255, 0, 0, 255, 0, 0, 255, 255])
            .unwrap();
        assert_eq!(canvas.load_pixels(), vec![255, 0, 0, 255, 0, 0, 255, 255]);

        canvas.clear();
        assert_eq!(canvas.load_pixels(), vec![0; 8]);
    }

    #[test]
    fn gpu_status_reports_available_or_clear_error() {
        let canvas = Canvas::new(4, 4, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();

        if canvas.gpu_available() {
            assert_eq!(canvas.gpu_status(), "available");
        } else {
            assert_ne!(canvas.gpu_status(), "available");
        }
    }

    #[test]
    fn gpu_path_renders_background_and_triangle_when_available() {
        let mut canvas = Canvas::new(8, 8, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
        if !canvas.gpu_available() {
            return;
        }

        canvas.begin_frame();
        canvas.background((255, 255, 255, 255));
        canvas.draw_gpu_polygon(
            &[(1.0, 1.0), (6.0, 1.0), (1.0, 6.0)],
            &Style {
                fill: Some(Rgba {
                    r: 255,
                    g: 0,
                    b: 0,
                    a: 255,
                }),
                stroke: None,
                stroke_weight: 1.0,
                blend_mode: SUPPORTED_BLEND_MODE.to_string(),
                erasing: false,
            },
            true,
            1.0,
        );
        canvas.end_frame();

        let pixels = canvas.load_pixels();
        assert!(pixels.chunks_exact(4).any(|rgba| rgba == [255, 0, 0, 255]));
        assert!(pixels
            .chunks_exact(4)
            .any(|rgba| rgba == [255, 255, 255, 255]));
    }

    #[test]
    fn interactive_runtime_primitives_track_open_and_close_state() {
        let mut canvas = Canvas::new(10, 8, 2.0, INTERACTIVE_MODE, SUPPORTED_RENDERER).unwrap();

        assert_eq!(canvas.display_density(), 2.0);
        assert!(!canvas.should_close());
        assert!(canvas.poll_events().unwrap().is_empty());
        assert_eq!(
            canvas.native_window_available(),
            runtime_native_window_available()
        );

        canvas.close();
        assert!(canvas.should_close());
    }
}

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict};
use std::f64::consts::PI;

const SUPPORTED_RENDERER: &str = "p2d";
const SUPPORTED_MODE: &str = "headless";
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

#[pyclass]
struct Canvas {
    width: i64,
    height: i64,
    physical_width: usize,
    physical_height: usize,
    pixel_density: f64,
    pixels: Vec<u8>,
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
        Ok(Self {
            width,
            height,
            physical_width,
            physical_height,
            pixel_density,
            pixels: vec![0; physical_width * physical_height * 4],
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
        1.0
    }

    fn begin_frame(&mut self) {}

    fn end_frame(&mut self) {}

    fn present(&self) {}

    fn close(&mut self) {}

    fn background(&mut self, rgba: (u8, u8, u8, u8)) {
        let color = Rgba::from_tuple(rgba).as_array();
        for pixel in self.pixels.chunks_exact_mut(4) {
            pixel.copy_from_slice(&color);
        }
    }

    fn clear(&mut self) {
        self.pixels.fill(0);
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
        let mut overlay = self.empty_overlay();
        fill_disc(
            &mut overlay,
            self.physical_width,
            self.physical_height,
            tx,
            ty,
            radius,
            color,
        );
        self.apply_overlay(&overlay, style.erasing);
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
        let mut overlay = self.empty_overlay();
        stroke_segment(
            &mut overlay,
            self.physical_width,
            self.physical_height,
            p1,
            p2,
            stroke_width(style.stroke_weight, self.pixel_density),
            stroke,
        );
        self.apply_overlay(&overlay, style.erasing);
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
        let mut overlay = self.empty_overlay();
        draw_polygon_overlay(
            &mut overlay,
            self.physical_width,
            self.physical_height,
            &transformed,
            &style,
            close,
            self.pixel_density,
        );
        self.apply_overlay(&overlay, style.erasing);
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
                let mut overlay = self.empty_overlay();
                if parsed_style.fill.is_some() && mode != "open" {
                    draw_polygon_overlay(
                        &mut overlay,
                        self.physical_width,
                        self.physical_height,
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
                        self.physical_width,
                        self.physical_height,
                        &transformed,
                        false,
                        stroke_width(parsed_style.stroke_weight, self.pixel_density),
                        stroke,
                    );
                }
                self.apply_overlay(&overlay, parsed_style.erasing);
                Ok(())
            }
        }
    }

    fn load_pixels(&self) -> Vec<u8> {
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
        Ok(())
    }

    fn save(&self, path: &str) -> PyResult<()> {
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
    fn empty_overlay(&self) -> Vec<u8> {
        vec![0; self.physical_width * self.physical_height * 4]
    }

    fn transform_point(&self, matrix: Matrix, x: f64, y: f64) -> Point {
        let (a, b, c, d, e, f) = matrix;
        (
            (a * x + c * y + e) * self.pixel_density,
            (b * x + d * y + f) * self.pixel_density,
        )
    }

    fn apply_overlay(&mut self, overlay: &[u8], erasing: bool) {
        for (dst, src) in self
            .pixels
            .chunks_exact_mut(4)
            .zip(overlay.chunks_exact(4))
            .filter(|(_, src)| src[3] != 0)
        {
            if erasing {
                dst[3] = dst[3].saturating_sub(src[3]);
            } else {
                alpha_composite_pixel(dst, src);
            }
        }
    }
}

#[pyfunction]
fn health_check() -> &'static str {
    "rust-canvas"
}

#[pymodule]
fn _canvas(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(health_check, m)?)?;
    m.add_class::<Canvas>()?;
    Ok(())
}

fn validate_mode_and_renderer(mode: &str, renderer: &str) -> PyResult<()> {
    if mode != SUPPORTED_MODE {
        return Err(PyValueError::new_err(format!(
            "Unsupported canvas mode {mode:?}; only {SUPPORTED_MODE:?} is implemented."
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
    overlay: &mut [u8],
    width: usize,
    height: usize,
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
                width,
                height,
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
            fill_polygon(overlay, width, height, points, fill);
        }
    }

    if let Some(stroke) = style.stroke {
        draw_polyline_stroke(
            overlay,
            width,
            height,
            points,
            close,
            stroke_width(style.stroke_weight, pixel_density),
            stroke,
        );
    }
}

fn fill_polygon(overlay: &mut [u8], width: usize, height: usize, points: &[Point], color: Rgba) {
    let (min_x, min_y, max_x, max_y) = clipped_bounds(points, 0.0, width, height);
    for y in min_y..max_y {
        for x in min_x..max_x {
            let sample = (x as f64 + 0.5, y as f64 + 0.5);
            if point_in_polygon(sample, points) {
                set_pixel(overlay, width, x, y, color);
            }
        }
    }
}

fn draw_polyline_stroke(
    overlay: &mut [u8],
    width: usize,
    height: usize,
    points: &[Point],
    close: bool,
    stroke_width: f64,
    color: Rgba,
) {
    if points.len() < 2 {
        return;
    }
    for pair in points.windows(2) {
        stroke_segment(
            overlay,
            width,
            height,
            pair[0],
            pair[1],
            stroke_width,
            color,
        );
    }
    if close {
        stroke_segment(
            overlay,
            width,
            height,
            *points.last().expect("non-empty points"),
            points[0],
            stroke_width,
            color,
        );
    }
}

fn stroke_segment(
    overlay: &mut [u8],
    width: usize,
    height: usize,
    p1: Point,
    p2: Point,
    stroke_width: f64,
    color: Rgba,
) {
    let radius = (stroke_width / 2.0).max(0.5);
    let points = [p1, p2];
    let (min_x, min_y, max_x, max_y) = clipped_bounds(&points, radius, width, height);
    for y in min_y..max_y {
        for x in min_x..max_x {
            let sample = (x as f64 + 0.5, y as f64 + 0.5);
            if distance_to_segment(sample, p1, p2) <= radius {
                set_pixel(overlay, width, x, y, color);
            }
        }
    }
}

fn fill_disc(
    overlay: &mut [u8],
    width: usize,
    height: usize,
    cx: f64,
    cy: f64,
    radius: f64,
    color: Rgba,
) {
    let points = [(cx, cy)];
    let (min_x, min_y, max_x, max_y) = clipped_bounds(&points, radius, width, height);
    let radius_squared = radius * radius;
    for y in min_y..max_y {
        for x in min_x..max_x {
            let dx = x as f64 + 0.5 - cx;
            let dy = y as f64 + 0.5 - cy;
            if dx * dx + dy * dy <= radius_squared {
                set_pixel(overlay, width, x, y, color);
            }
        }
    }
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

fn distance_to_segment(point: Point, p1: Point, p2: Point) -> f64 {
    let vx = p2.0 - p1.0;
    let vy = p2.1 - p1.1;
    let wx = point.0 - p1.0;
    let wy = point.1 - p1.1;
    let length_squared = vx * vx + vy * vy;
    if length_squared <= f64::EPSILON {
        return ((point.0 - p1.0).powi(2) + (point.1 - p1.1).powi(2)).sqrt();
    }
    let t = ((wx * vx + wy * vy) / length_squared).clamp(0.0, 1.0);
    let projection = (p1.0 + t * vx, p1.1 + t * vy);
    ((point.0 - projection.0).powi(2) + (point.1 - projection.1).powi(2)).sqrt()
}

fn set_pixel(buffer: &mut [u8], width: usize, x: usize, y: usize, color: Rgba) {
    let offset = (y * width + x) * 4;
    buffer[offset..offset + 4].copy_from_slice(&color.as_array());
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_check_reports_canvas_backend() {
        assert_eq!(health_check(), "rust-canvas");
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
}

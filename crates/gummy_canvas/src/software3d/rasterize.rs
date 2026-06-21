use crate::image_ops::{alpha_composite_pixel, validate_rgba_buffer};
use crate::raster::point_in_polygon;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList};

pub(crate) fn rasterize_faces_rgba<'py>(
    py: Python<'py>,
    width: usize,
    height: usize,
    faces: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    if width == 0 || height == 0 {
        return Err(PyValueError::new_err("raster dimensions must be positive."));
    }
    let mut pixels = vec![0_u8; width * height * 4];
    let sequence = faces.downcast::<PyList>()?;
    for face in sequence.iter() {
        let dict = face.downcast::<PyDict>()?;
        let points: Vec<(f64, f64)> = dict
            .get_item("points")?
            .ok_or_else(|| PyValueError::new_err("raster face is missing points."))?
            .extract()?;
        let color_float: (f64, f64, f64, f64) = dict
            .get_item("color")?
            .ok_or_else(|| PyValueError::new_err("raster face is missing color."))?
            .extract()?;
        let color = rgba_float_to_u8(color_float);
        let texcoords_item = dict.get_item("texcoords")?;
        let texture_item = dict.get_item("texture")?;
        if let (Some(texcoords_any), Some(texture_any)) = (texcoords_item, texture_item) {
            if !texture_any.is_none() && !texcoords_any.is_none() {
                let texcoords: Vec<(f64, f64)> = texcoords_any.extract()?;
                let texture_dict = texture_any.downcast::<PyDict>()?;
                let texture_width: usize = texture_dict
                    .get_item("width")?
                    .ok_or_else(|| PyValueError::new_err("texture payload is missing width."))?
                    .extract()?;
                let texture_height: usize = texture_dict
                    .get_item("height")?
                    .ok_or_else(|| PyValueError::new_err("texture payload is missing height."))?
                    .extract()?;
                let texture_pixels: Vec<u8> = texture_dict
                    .get_item("pixels")?
                    .ok_or_else(|| PyValueError::new_err("texture payload is missing pixels."))?
                    .extract()?;
                validate_rgba_buffer(texture_pixels.len(), texture_width, texture_height)?;
                rasterize_textured_face(
                    &mut pixels,
                    width,
                    height,
                    &points,
                    &texcoords,
                    &texture_pixels,
                    texture_width,
                    texture_height,
                    color_float,
                );
                continue;
            }
        }
        rasterize_filled_polygon(&mut pixels, width, height, &points, color);
    }
    Ok(PyBytes::new_bound(py, &pixels))
}
fn rgba_float_to_u8(color: (f64, f64, f64, f64)) -> [u8; 4] {
    [
        (color.0.clamp(0.0, 1.0) * 255.0).round() as u8,
        (color.1.clamp(0.0, 1.0) * 255.0).round() as u8,
        (color.2.clamp(0.0, 1.0) * 255.0).round() as u8,
        (color.3.clamp(0.0, 1.0) * 255.0).round() as u8,
    ]
}

fn rasterize_filled_polygon(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    points: &[(f64, f64)],
    color: [u8; 4],
) {
    if points.len() < 3 {
        return;
    }
    let min_x = points
        .iter()
        .map(|point| point.0)
        .fold(f64::INFINITY, f64::min)
        .floor()
        .max(0.0) as usize;
    let max_x = points
        .iter()
        .map(|point| point.0)
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil()
        .min((width - 1) as f64) as usize;
    let min_y = points
        .iter()
        .map(|point| point.1)
        .fold(f64::INFINITY, f64::min)
        .floor()
        .max(0.0) as usize;
    let max_y = points
        .iter()
        .map(|point| point.1)
        .fold(f64::NEG_INFINITY, f64::max)
        .ceil()
        .min((height - 1) as f64) as usize;
    if min_x > max_x || min_y > max_y {
        return;
    }
    for y in min_y..=max_y {
        for x in min_x..=max_x {
            if point_in_polygon((x as f64 + 0.5, y as f64 + 0.5), points) {
                let offset = (y * width + x) * 4;
                alpha_composite_pixel(&mut pixels[offset..offset + 4], &color);
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn rasterize_textured_face(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    points: &[(f64, f64)],
    texcoords: &[(f64, f64)],
    texture: &[u8],
    texture_width: usize,
    texture_height: usize,
    modulation: (f64, f64, f64, f64),
) {
    if points.len() < 3 || points.len() != texcoords.len() {
        return;
    }
    for index in 1..points.len() - 1 {
        rasterize_textured_triangle(
            pixels,
            width,
            height,
            [points[0], points[index], points[index + 1]],
            [texcoords[0], texcoords[index], texcoords[index + 1]],
            texture,
            texture_width,
            texture_height,
            modulation,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn rasterize_textured_triangle(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    points: [(f64, f64); 3],
    texcoords: [(f64, f64); 3],
    texture: &[u8],
    texture_width: usize,
    texture_height: usize,
    modulation: (f64, f64, f64, f64),
) {
    let [(x1, y1), (x2, y2), (x3, y3)] = points;
    let denominator = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3);
    if denominator == 0.0 {
        return;
    }
    let min_x = x1.min(x2).min(x3).floor().max(0.0) as usize;
    let max_x = x1.max(x2).max(x3).ceil().min((width - 1) as f64) as usize;
    let min_y = y1.min(y2).min(y3).floor().max(0.0) as usize;
    let max_y = y1.max(y2).max(y3).ceil().min((height - 1) as f64) as usize;
    if min_x > max_x || min_y > max_y {
        return;
    }
    for py in min_y..=max_y {
        let sample_y = py as f64 + 0.5;
        for px in min_x..=max_x {
            let sample_x = px as f64 + 0.5;
            let w1 = ((y2 - y3) * (sample_x - x3) + (x3 - x2) * (sample_y - y3)) / denominator;
            let w2 = ((y3 - y1) * (sample_x - x3) + (x1 - x3) * (sample_y - y3)) / denominator;
            let w3 = 1.0 - w1 - w2;
            if w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6 {
                continue;
            }
            let u = w1 * texcoords[0].0 + w2 * texcoords[1].0 + w3 * texcoords[2].0;
            let v = w1 * texcoords[0].1 + w2 * texcoords[1].1 + w3 * texcoords[2].1;
            let tx = ((u.clamp(0.0, 1.0) * (texture_width - 1) as f64).round() as usize)
                .min(texture_width - 1);
            let ty = (((1.0 - v.clamp(0.0, 1.0)) * (texture_height - 1) as f64).round() as usize)
                .min(texture_height - 1);
            let src = (ty * texture_width + tx) * 4;
            let shaded = [
                (texture[src] as f64 * modulation.0)
                    .round()
                    .clamp(0.0, 255.0) as u8,
                (texture[src + 1] as f64 * modulation.1)
                    .round()
                    .clamp(0.0, 255.0) as u8,
                (texture[src + 2] as f64 * modulation.2)
                    .round()
                    .clamp(0.0, 255.0) as u8,
                (texture[src + 3] as f64 * modulation.3)
                    .round()
                    .clamp(0.0, 255.0) as u8,
            ];
            let dst = (py * width + px) * 4;
            alpha_composite_pixel(&mut pixels[dst..dst + 4], &shaded);
        }
    }
}

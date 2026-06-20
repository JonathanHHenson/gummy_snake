use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::f64::consts::{PI, TAU};

#[pyfunction]
fn health_check() -> &'static str {
    "rust-accelerated"
}

#[pyfunction]
#[pyo3(signature = (x = 0.0, y = 0.0, z = 0.0, seed = 0, octaves = 4, falloff = 0.5))]
fn noise3(x: f64, y: f64, z: f64, seed: i64, octaves: u32, falloff: f64) -> PyResult<f64> {
    if octaves < 1 {
        return Err(PyValueError::new_err("octaves must be at least 1."));
    }

    noise_fractal(x, y, z, seed, octaves, falloff)
}

#[pyfunction]
#[pyo3(signature = (width, height, density, time, seed = 0, octaves = 4, falloff = 0.5))]
fn animated_noise_rgba(
    py: Python<'_>,
    width: usize,
    height: usize,
    density: f64,
    time: f64,
    seed: i64,
    octaves: u32,
    falloff: f64,
) -> PyResult<Py<PyBytes>> {
    if width == 0 || height == 0 {
        return Err(PyValueError::new_err("width and height must be positive."));
    }
    if !density.is_finite() || density <= 0.0 {
        return Err(PyValueError::new_err("density must be positive."));
    }
    if octaves < 1 {
        return Err(PyValueError::new_err("octaves must be at least 1."));
    }

    let physical_width = ((width as f64 * density).round() as usize).max(1);
    let physical_height = ((height as f64 * density).round() as usize).max(1);
    let mut pixels = vec![0_u8; physical_width * physical_height * 4];

    for y in 0..physical_height {
        let logical_y = y as f64 / density;
        let ridge = logical_y / (height.saturating_sub(1).max(1) as f64);
        for x in 0..physical_width {
            let logical_x = x as f64 / density;
            let coarse = noise_fractal(
                logical_x * 0.012,
                logical_y * 0.012,
                time,
                seed,
                octaves,
                falloff,
            )?;
            let detail = noise_fractal(
                logical_x * 0.028 + 40.0,
                logical_y * 0.028 - 30.0,
                time * 1.7,
                seed,
                octaves,
                falloff,
            )?;
            let band = noise_fractal(
                logical_x * 0.004,
                time * 0.55,
                logical_y * 0.01,
                seed,
                octaves,
                falloff,
            )?;

            let offset = (y * physical_width + x) * 4;
            pixels[offset] = (18.0 + coarse * 70.0 + band * 30.0).clamp(0.0, 255.0) as u8;
            pixels[offset + 1] = (32.0 + detail * 110.0 + ridge * 40.0).clamp(0.0, 255.0) as u8;
            pixels[offset + 2] = (70.0 + coarse * 120.0 + detail * 45.0).clamp(0.0, 255.0) as u8;
            pixels[offset + 3] = 255;
        }
    }

    Ok(PyBytes::new_bound(py, &pixels).unbind())
}

fn noise_fractal(x: f64, y: f64, z: f64, seed: i64, octaves: u32, falloff: f64) -> PyResult<f64> {
    let mut total = 0.0;
    let mut amplitude = 1.0;
    let mut max_amplitude = 0.0;
    let mut frequency = 1.0;

    for _ in 0..octaves {
        total += perlin(x * frequency, y * frequency, z * frequency, seed)? * amplitude;
        max_amplitude += amplitude;
        amplitude *= falloff;
        frequency *= 2.0;
    }

    if max_amplitude == 0.0 {
        Ok(0.0)
    } else {
        Ok(total / max_amplitude)
    }
}

#[pyfunction]
fn exclusion_blend_rgb(py: Python<'_>, base: &[u8], overlay: &[u8]) -> PyResult<Py<PyBytes>> {
    if base.len() != overlay.len() {
        return Err(PyValueError::new_err(format!(
            "Buffers must have the same length, got {} and {}.",
            base.len(),
            overlay.len()
        )));
    }

    let out = exclusion_blend_rgb_bytes(base, overlay);
    Ok(PyBytes::new_bound(py, &out).unbind())
}

#[pymodule]
fn _accelerated(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(health_check, m)?)?;
    m.add_function(wrap_pyfunction!(noise3, m)?)?;
    m.add_function(wrap_pyfunction!(animated_noise_rgba, m)?)?;
    m.add_function(wrap_pyfunction!(exclusion_blend_rgb, m)?)?;
    Ok(())
}

fn perlin(x: f64, y: f64, z: f64, seed: i64) -> PyResult<f64> {
    let x0 = checked_floor(x)?;
    let y0 = checked_floor(y)?;
    let z0 = checked_floor(z)?;
    let xf = x - x0 as f64;
    let yf = y - y0 as f64;
    let zf = z - z0 as f64;
    let u = fade(xf);
    let v = fade(yf);
    let w = fade(zf);

    let d000 = dot_gradient(x0, y0, z0, xf, yf, zf, seed);
    let d100 = dot_gradient(x0 + 1, y0, z0, xf - 1.0, yf, zf, seed);
    let d010 = dot_gradient(x0, y0 + 1, z0, xf, yf - 1.0, zf, seed);
    let d110 = dot_gradient(x0 + 1, y0 + 1, z0, xf - 1.0, yf - 1.0, zf, seed);
    let d001 = dot_gradient(x0, y0, z0 + 1, xf, yf, zf - 1.0, seed);
    let d101 = dot_gradient(x0 + 1, y0, z0 + 1, xf - 1.0, yf, zf - 1.0, seed);
    let d011 = dot_gradient(x0, y0 + 1, z0 + 1, xf, yf - 1.0, zf - 1.0, seed);
    let d111 = dot_gradient(x0 + 1, y0 + 1, z0 + 1, xf - 1.0, yf - 1.0, zf - 1.0, seed);

    let x00 = lerp(d000, d100, u);
    let x10 = lerp(d010, d110, u);
    let x01 = lerp(d001, d101, u);
    let x11 = lerp(d011, d111, u);
    let y0_value = lerp(x00, x10, v);
    let y1_value = lerp(x01, x11, v);
    Ok((lerp(y0_value, y1_value, w) + 1.0) / 2.0)
}

fn checked_floor(value: f64) -> PyResult<i64> {
    if !value.is_finite() {
        return Err(PyValueError::new_err("noise coordinates must be finite."));
    }
    if value < i64::MIN as f64 || value > i64::MAX as f64 {
        return Err(PyValueError::new_err(
            "noise coordinates are outside the supported range.",
        ));
    }
    Ok(value.floor() as i64)
}

fn dot_gradient(x: i64, y: i64, z: i64, dx: f64, dy: f64, dz: f64, seed: i64) -> f64 {
    let gradient = gradient(x, y, z, seed);
    gradient.0 * dx + gradient.1 * dy + gradient.2 * dz
}

fn gradient(x: i64, y: i64, z: i64, seed: i64) -> (f64, f64, f64) {
    let hashed = hash(x, y, z, seed);
    let theta = f64::from(hashed & 0xFFFF) / f64::from(0xFFFF_u32) * TAU;
    let phi = f64::from((hashed >> 16) & 0xFFFF) / f64::from(0xFFFF_u32) * PI;
    let sin_phi = phi.sin();
    (theta.cos() * sin_phi, theta.sin() * sin_phi, phi.cos())
}

fn hash(x: i64, y: i64, z: i64, seed: i64) -> u32 {
    let mut value = (i128::from(seed) & 0xFFFF_FFFF)
        ^ (i128::from(x) * 374_761_393)
        ^ (i128::from(y) * 668_265_263)
        ^ (i128::from(z) * 2_246_822_519);
    value = (value ^ (value >> 13)) * 1_274_126_177;
    ((value ^ (value >> 16)) & 0xFFFF_FFFF) as u32
}

fn fade(t: f64) -> f64 {
    t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
}

fn lerp(a: f64, b: f64, t: f64) -> f64 {
    a + (b - a) * t
}

fn exclusion_blend_rgb_bytes(base: &[u8], overlay: &[u8]) -> Vec<u8> {
    base.iter()
        .zip(overlay.iter())
        .map(|(base, overlay)| {
            let b = u32::from(*base);
            let o = u32::from(*overlay);
            let value = b + o - (2 * b * o / 255);
            value.min(255) as u8
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn noise_is_deterministic_and_normalized() {
        let first = noise3(0.5, 0.25, 0.125, 42, 3, 0.4).unwrap();
        let second = noise3(0.5, 0.25, 0.125, 42, 3, 0.4).unwrap();
        assert_eq!(first, second);
        assert!((0.0..=1.0).contains(&first));
    }

    #[test]
    fn exclusion_blend_matches_reference_formula() {
        let base = [0, 64, 128, 255];
        let overlay = [255, 128, 64, 0];
        assert_eq!(
            exclusion_blend_rgb_bytes(&base, &overlay),
            vec![255, 128, 128, 255]
        );
    }
}

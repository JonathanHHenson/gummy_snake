use crate::images::{
    alpha_composite_rgba_region, apply_rgba_mask, crop_rgba_with_padding, filter_rgba,
    resize_rgba_nearest, validate_rgba_buffer,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

static NEXT_IMAGE_KEY: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Debug)]
pub(crate) struct CachedImage {
    pub(crate) version: u64,
    pub(crate) width: usize,
    pub(crate) height: usize,
    pub(crate) pixels: Arc<Vec<u8>>,
}

#[derive(Clone, Debug)]
pub(crate) struct CachedText {
    pub(crate) texture_key: u64,
    pub(crate) image: CachedImage,
    pub(crate) bbox_left: i32,
    pub(crate) bbox_top: i32,
    pub(crate) ascent: f64,
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct CachedTextMetrics {
    pub(crate) width: f64,
    pub(crate) ascent: f64,
    pub(crate) descent: f64,
}

#[pyclass(name = "CanvasImage", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasImage {
    pub(crate) key: u64,
    pub(crate) version: u64,
    pub(crate) width: usize,
    pub(crate) height: usize,
    pub(crate) pixels: Arc<Vec<u8>>,
}

#[pymethods]
impl CanvasImage {
    #[staticmethod]
    fn from_file(path: &str) -> PyResult<Self> {
        let image = image::open(path)
            .map_err(|err| PyValueError::new_err(format!("Could not load image {path}: {err}")))?
            .to_rgba8();
        let (width, height) = image.dimensions();
        Ok(Self::from_pixels(
            width as usize,
            height as usize,
            image.into_raw(),
        ))
    }

    #[staticmethod]
    fn from_rgba_bytes(width: usize, height: usize, pixels: Vec<u8>) -> PyResult<Self> {
        validate_rgba_buffer(pixels.len(), width, height)?;
        Ok(Self::from_pixels(width, height, pixels))
    }

    #[getter]
    fn width(&self) -> usize {
        self.width
    }

    #[getter]
    fn height(&self) -> usize {
        self.height
    }

    #[getter]
    fn version(&self) -> u64 {
        self.version
    }

    #[getter]
    fn key(&self) -> u64 {
        self.key
    }

    fn get_pixel(&self, x: usize, y: usize) -> PyResult<(u8, u8, u8, u8)> {
        let offset = self.pixel_offset(x, y)?;
        Ok((
            self.pixels[offset],
            self.pixels[offset + 1],
            self.pixels[offset + 2],
            self.pixels[offset + 3],
        ))
    }

    fn set_pixel(&mut self, x: usize, y: usize, r: u8, g: u8, b: u8, a: u8) -> PyResult<()> {
        let offset = self.pixel_offset(x, y)?;
        Arc::make_mut(&mut self.pixels)[offset..offset + 4].copy_from_slice(&[r, g, b, a]);
        self.bump_version();
        Ok(())
    }

    fn replace_rgba_bytes(&mut self, pixels: Vec<u8>) -> PyResult<()> {
        validate_rgba_buffer(pixels.len(), self.width, self.height)?;
        self.pixels = Arc::new(pixels);
        self.bump_version();
        Ok(())
    }

    fn copy(&self) -> Self {
        Self::from_pixels(self.width, self.height, self.pixels.as_ref().clone())
    }

    fn crop(&self, sx: i64, sy: i64, sw: i64, sh: i64) -> PyResult<Self> {
        if sw <= 0 || sh <= 0 {
            return Err(PyValueError::new_err(
                "Image region dimensions must be positive.",
            ));
        }
        Ok(Self::from_pixels(
            sw as usize,
            sh as usize,
            crop_rgba_with_padding(
                self.pixels.as_slice(),
                self.width,
                self.height,
                sx,
                sy,
                sw as usize,
                sh as usize,
            ),
        ))
    }

    fn resize(&mut self, target_width: usize, target_height: usize) -> PyResult<()> {
        if target_width == 0 || target_height == 0 {
            return Err(PyValueError::new_err(
                "Image.resize() dimensions must be positive.",
            ));
        }
        self.pixels = Arc::new(resize_rgba_nearest(
            self.pixels.as_slice(),
            self.width,
            self.height,
            target_width,
            target_height,
        ));
        self.width = target_width;
        self.height = target_height;
        self.bump_version();
        Ok(())
    }

    fn mask(&mut self, mask: PyRef<'_, CanvasImage>) -> PyResult<()> {
        apply_rgba_mask(
            Arc::make_mut(&mut self.pixels).as_mut_slice(),
            self.width,
            self.height,
            mask.pixels.as_slice(),
            mask.width,
            mask.height,
        );
        self.bump_version();
        Ok(())
    }

    #[pyo3(signature = (mode, value=None))]
    fn filter(&mut self, mode: &str, value: Option<f64>) -> PyResult<()> {
        filter_rgba(
            Arc::make_mut(&mut self.pixels).as_mut_slice(),
            self.width,
            self.height,
            mode,
            value,
        )?;
        self.bump_version();
        Ok(())
    }

    fn alpha_composite(&mut self, source: PyRef<'_, CanvasImage>, dx: i64, dy: i64) {
        alpha_composite_rgba_region(
            Arc::make_mut(&mut self.pixels).as_mut_slice(),
            self.width,
            self.height,
            source.pixels.as_slice(),
            source.width,
            source.height,
            dx,
            dy,
        );
        self.bump_version();
    }

    fn save(&self, path: &str) -> PyResult<()> {
        image::save_buffer_with_format(
            path,
            self.pixels.as_slice(),
            self.width as u32,
            self.height as u32,
            image::ColorType::Rgba8,
            image::ImageFormat::Png,
        )
        .map_err(|err| PyValueError::new_err(format!("Failed to save image {path}: {err}")))
    }

    fn to_rgba_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, self.pixels.as_slice())
    }
}

impl CanvasImage {
    pub(crate) fn from_pixels(width: usize, height: usize, pixels: Vec<u8>) -> Self {
        Self {
            key: NEXT_IMAGE_KEY.fetch_add(1, Ordering::Relaxed),
            version: 0,
            width,
            height,
            pixels: Arc::new(pixels),
        }
    }

    fn pixel_offset(&self, x: usize, y: usize) -> PyResult<usize> {
        if x >= self.width || y >= self.height {
            return Err(PyValueError::new_err(
                "Pixel coordinates are outside the image bounds.",
            ));
        }
        Ok((y * self.width + x) * 4)
    }

    pub(crate) fn replace_pixels_preserving_identity(
        &mut self,
        width: usize,
        height: usize,
        pixels: Vec<u8>,
    ) -> PyResult<()> {
        validate_rgba_buffer(pixels.len(), width, height)?;
        self.width = width;
        self.height = height;
        self.pixels = Arc::new(pixels);
        self.bump_version();
        Ok(())
    }

    pub(crate) fn bump_version(&mut self) {
        self.version = self.version.wrapping_add(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canvas_image_mutation_is_copy_on_write_and_versioned() {
        let mut image = CanvasImage::from_pixels(1, 1, vec![1, 2, 3, 4]);
        let shared = Arc::clone(&image.pixels);

        image.set_pixel(0, 0, 9, 8, 7, 6).unwrap();

        assert_eq!(shared.as_slice(), &[1, 2, 3, 4]);
        assert_eq!(image.pixels.as_slice(), &[9, 8, 7, 6]);
        assert!(!Arc::ptr_eq(&shared, &image.pixels));
        assert_eq!(image.version, 1);
    }
}

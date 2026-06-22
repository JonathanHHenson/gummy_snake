use crate::*;

mod helpers;

impl Canvas {
    pub(crate) fn draw_image_impl(
        &mut self,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.draw_image_pixels(
            &image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    pub(crate) fn draw_cached_image_impl(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let needs_upload = self
            .image_cache
            .get(&image_key)
            .map(|cached| {
                cached.version != image_version
                    || cached.width != image_width
                    || cached.height != image_height
            })
            .unwrap_or(true);
        if needs_upload {
            self.performance_counters.image_cache_misses += 1;
            let pixels = image_pixels.ok_or_else(|| {
                PyValueError::new_err(
                    "Image pixels are required the first time an image/version is drawn.",
                )
            })?;
            validate_rgba_buffer(pixels.len(), image_width, image_height)?;
            self.evict_image_cache_if_needed(image_key);
            self.image_cache.insert(
                image_key,
                CachedImage {
                    version: image_version,
                    width: image_width,
                    height: image_height,
                    pixels,
                },
            );
        } else {
            self.performance_counters.image_cache_hits += 1;
        }
        if let Some(cached) = self.image_cache.get(&image_key).cloned() {
            if self.try_draw_gpu_image(image_key, &cached, dx, dy, dw, dh, style, matrix, source)? {
                return Ok(());
            }
        }
        let cached = self
            .image_cache
            .get(&image_key)
            .ok_or_else(|| PyValueError::new_err("Cached image is not available."))?
            .clone();
        self.draw_image_pixels(
            &cached.pixels,
            cached.width,
            cached.height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    pub(crate) fn draw_canvas_image_impl(
        &mut self,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let needs_cache = self
            .image_cache
            .get(&image.key)
            .map(|cached| {
                cached.version != image.version
                    || cached.width != image.width
                    || cached.height != image.height
            })
            .unwrap_or(true);
        if needs_cache {
            self.evict_image_cache_if_needed(image.key);
            self.image_cache.insert(
                image.key,
                CachedImage {
                    version: image.version,
                    width: image.width,
                    height: image.height,
                    pixels: image.pixels.clone(),
                },
            );
        }
        if self.try_draw_gpu_image_parts(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )? {
            return Ok(());
        }
        self.draw_image_pixels(
            &image.pixels,
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }
}

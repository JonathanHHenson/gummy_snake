use crate::*;

impl Canvas {
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
        let cached = self.ensure_cached_image_for_draw(
            image_key,
            image_version,
            image_pixels,
            image_width,
            image_height,
        )?;
        let style = self.cached_style(style)?;
        if self.try_draw_gpu_image_parts(
            image_key,
            cached.version,
            cached.width,
            cached.height,
            &cached.pixels,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )? {
            return Ok(());
        }
        self.draw_image_pixels_with_style(
            &cached.pixels,
            cached.width,
            cached.height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_cached_image_current_impl(
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
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        let cached = self.ensure_cached_image_for_draw(
            image_key,
            image_version,
            image_pixels,
            image_width,
            image_height,
        )?;
        if self.try_draw_gpu_image_parts(
            image_key,
            cached.version,
            cached.width,
            cached.height,
            &cached.pixels,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )? {
            return Ok(());
        }
        self.draw_image_pixels_with_style(
            &cached.pixels,
            cached.width,
            cached.height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }

    fn ensure_cached_image_for_draw(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_pixels: Option<Vec<u8>>,
        image_width: usize,
        image_height: usize,
    ) -> PyResult<CachedImage> {
        if self
            .image_cache
            .needs_update(image_key, image_version, image_width, image_height)
        {
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
        self.image_cache
            .get(image_key)
            .cloned()
            .ok_or_else(|| PyValueError::new_err("Cached image is not available."))
    }
}

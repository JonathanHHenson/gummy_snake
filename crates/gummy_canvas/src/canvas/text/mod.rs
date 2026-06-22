use crate::runtime::style::*;
use crate::*;

mod cache;

impl Canvas {
    pub(crate) fn text_impl(
        &mut self,
        value: &str,
        x: f64,
        y: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let parsed_style = self.cached_style(style)?;
        self.text_with_style(value, x, y, &parsed_style, matrix)
    }

    pub(crate) fn text_current_impl(&mut self, value: &str, x: f64, y: f64) -> PyResult<()> {
        let style = self.current_style.clone();
        self.text_with_style(value, x, y, &style, self.current_matrix)
    }

    pub(crate) fn text_with_style(
        &mut self,
        value: &str,
        x: f64,
        y: f64,
        parsed_style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(&parsed_style)?;
        let Some(fill) = parsed_style.fill else {
            return Ok(());
        };
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        if parsed_style.text_leading <= 0.0 || !parsed_style.text_leading.is_finite() {
            return Err(PyValueError::new_err("text_leading must be positive."));
        }

        let lines: Vec<&str> = if value.is_empty() {
            vec![""]
        } else {
            value.split('\n').collect()
        };
        for (line_index, line) in lines.iter().enumerate() {
            if self.can_draw_gpu_text(parsed_style, matrix) {
                let font_size = (parsed_style.text_size * self.pixel_density)
                    .round()
                    .max(1.0) as usize;
                let metrics = self.cached_text_metrics(line, parsed_style, font_size)?;
                if metrics.width <= 0.0 {
                    continue;
                }
                let width = metrics.width / self.pixel_density;
                let height = (metrics.ascent + metrics.descent).max(font_size as f64)
                    / self.pixel_density;
                let mut dx = x;
                let mut dy = y + line_index as f64 * parsed_style.text_leading;
                if parsed_style.text_align_x == "center" {
                    dx -= width / 2.0;
                } else if parsed_style.text_align_x == "right" {
                    dx -= width;
                }
                if parsed_style.text_align_y == "center" {
                    dy -= height / 2.0;
                } else if parsed_style.text_align_y == "bottom" {
                    dy -= height;
                } else if parsed_style.text_align_y == "baseline" {
                    dy -= metrics.ascent / self.pixel_density;
                }
                self.draw_gpu_text(
                    line,
                    dx * self.pixel_density,
                    dy * self.pixel_density,
                    (width * self.pixel_density + font_size as f64).max(1.0),
                    (height * self.pixel_density + font_size as f64 * 0.5)
                        .max(parsed_style.text_leading),
                    font_size as f64,
                    (parsed_style.text_leading * self.pixel_density).max(font_size as f64),
                    fill,
                )?;
                continue;
            }
            let cached = self.cached_text_line(line, fill, &parsed_style)?;
            if cached.image.width == 0 || cached.image.height == 0 {
                continue;
            }
            let width = cached.image.width as f64 / self.pixel_density;
            let height = cached.image.height as f64 / self.pixel_density;
            let mut dx = x;
            let mut dy = y + line_index as f64 * parsed_style.text_leading;
            if parsed_style.text_align_x == "center" {
                dx -= width / 2.0;
            } else if parsed_style.text_align_x == "right" {
                dx -= width;
            }
            if parsed_style.text_align_y == "center" {
                dy -= height / 2.0;
            } else if parsed_style.text_align_y == "bottom" {
                dy -= height;
            } else if parsed_style.text_align_y == "baseline" {
                dy -= cached.ascent / self.pixel_density;
            }
            dx += cached.bbox_left as f64 / self.pixel_density;
            dy += cached.bbox_top as f64 / self.pixel_density;

            if self.try_draw_gpu_image_parts(
                cached.texture_key,
                cached.image.version,
                cached.image.width,
                cached.image.height,
                &cached.image.pixels,
                dx,
                dy,
                width,
                height,
                parsed_style,
                matrix,
                None,
            )? {
                continue;
            }
            self.draw_image_pixels_with_style(
                &cached.image.pixels,
                cached.image.width,
                cached.image.height,
                dx,
                dy,
                width,
                height,
                parsed_style,
                matrix,
                None,
            )?;
        }
        Ok(())
    }

    pub(crate) fn text_width_impl(
        &mut self,
        value: &str,
        style: &Bound<'_, PyAny>,
    ) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        self.text_width_with_style(value, &parsed_style)
    }

    pub(crate) fn text_width_current_impl(&mut self, value: &str) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let style = self.current_style.clone();
        self.text_width_with_style(value, &style)
    }

    pub(crate) fn text_width_with_style(
        &mut self,
        value: &str,
        parsed_style: &Style,
    ) -> PyResult<f64> {
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font_size = (parsed_style.text_size * self.pixel_density)
            .round()
            .max(1.0) as usize;
        let metrics = self.cached_text_metrics(value, &parsed_style, font_size)?;
        Ok(metrics.width / self.pixel_density)
    }

    pub(crate) fn text_ascent_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font_size = (parsed_style.text_size * self.pixel_density)
            .round()
            .max(1.0) as usize;
        let metrics = self.cached_text_metrics("", &parsed_style, font_size)?;
        Ok(metrics.ascent / self.pixel_density)
    }

    pub(crate) fn text_descent_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font_size = (parsed_style.text_size * self.pixel_density)
            .round()
            .max(1.0) as usize;
        let metrics = self.cached_text_metrics("", &parsed_style, font_size)?;
        Ok(metrics.descent / self.pixel_density)
    }

    fn cached_text_metrics(
        &mut self,
        value: &str,
        parsed_style: &Style,
        font_size: usize,
    ) -> PyResult<CachedTextMetrics> {
        let cache_key = self.text_metric_cache_key(value, parsed_style, font_size);
        if let Some(metrics) = self.text_metric_cache.get(&cache_key) {
            self.performance_counters.text_cache_hits += 1;
            return Ok(*metrics);
        }
        self.performance_counters.text_cache_misses += 1;
        let font = self.load_text_font(parsed_style)?;
        let metrics = CachedTextMetrics {
            width: text_width(value, &font, font_size),
            ascent: measure_text_ascent(&font, font_size),
            descent: measure_text_descent(&font, font_size),
        };
        self.text_metric_cache.insert(cache_key, metrics);
        Ok(metrics)
    }

    fn text_metric_cache_key(&self, value: &str, style: &Style, font_size: usize) -> String {
        let font_key = style
            .text_font_path
            .clone()
            .unwrap_or_else(|| format!("name:{}", style.text_font_name));
        format!("{font_key}|{font_size}|metrics|{value}")
    }
}

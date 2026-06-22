use crate::runtime::style::*;
use crate::*;
use ab_glyph::{Font, FontArc, PxScale, ScaleFont};

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

    pub(crate) fn text_batch_impl(
        &mut self,
        items: Vec<(String, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let parsed_style = self.cached_style(style)?;
        for (value, x, y) in items {
            self.text_with_style(&value, x, y, &parsed_style, matrix)?;
        }
        Ok(())
    }

    pub(crate) fn text_batch_current_impl(
        &mut self,
        items: Vec<(String, f64, f64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        for (value, x, y) in items {
            self.text_with_style(&value, x, y, &style, matrix)?;
        }
        Ok(())
    }

    pub(crate) fn text_batch_frame_impl(
        &mut self,
        items: Vec<(String, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<bool> {
        let parsed_style = self.cached_style(style)?;
        self.text_batch_frame_with_style(items, &parsed_style, matrix)
    }

    pub(crate) fn text_batch_frame_current_impl(
        &mut self,
        items: Vec<(String, f64, f64)>,
    ) -> PyResult<bool> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        self.text_batch_frame_with_style(items, &style, matrix)
    }

    fn text_batch_frame_with_style(
        &mut self,
        items: Vec<(String, f64, f64)>,
        parsed_style: &Style,
        matrix: Matrix,
    ) -> PyResult<bool> {
        if self.can_draw_gpu_text(parsed_style, matrix) {
            if let Some(signature) =
                self.reusable_text_frame_signature(&items, parsed_style, matrix)
            {
                if self.try_reuse_text_frame(&signature) {
                    return Ok(true);
                }
                self.pending_reusable_text_frame_signature = Some(signature);
            }
        }
        for (value, x, y) in items {
            self.text_with_style(&value, x, y, parsed_style, matrix)?;
        }
        Ok(false)
    }

    fn reusable_text_frame_signature(
        &self,
        items: &[(String, f64, f64)],
        parsed_style: &Style,
        matrix: Matrix,
    ) -> Option<String> {
        let clear = self.gpu.as_ref()?.only_pending_clear()?;
        let fill = parsed_style.fill?;
        let mut signature = format!(
            "clear={},{},{},{}|fill={},{},{},{}|font={}|font_path={:?}|size={:.3}|leading={:.3}|align={},{}|matrix={:.3},{:.3},{:.3},{:.3},{:.3},{:.3}|",
            clear.r,
            clear.g,
            clear.b,
            clear.a,
            fill.r,
            fill.g,
            fill.b,
            fill.a,
            parsed_style.text_font_name,
            parsed_style.text_font_path,
            parsed_style.text_size,
            parsed_style.text_leading,
            parsed_style.text_align_x,
            parsed_style.text_align_y,
            matrix.0,
            matrix.1,
            matrix.2,
            matrix.3,
            matrix.4,
            matrix.5,
        );
        for (value, x, y) in items {
            signature.push_str(value);
            signature.push('@');
            signature.push_str(&format!("{x:.3},{y:.3};"));
        }
        Some(signature)
    }

    fn try_reuse_text_frame(&mut self, signature: &str) -> bool {
        if self.last_reusable_text_frame_signature.as_deref() != Some(signature) {
            return false;
        }
        let Some(gpu) = self.gpu.as_mut() else {
            return false;
        };
        if gpu.only_pending_clear().is_none() {
            return false;
        }
        gpu.begin_frame();
        self.render_dirty = false;
        self.offscreen_dirty = true;
        self.pixels_stale = true;
        self.texture_stale = false;
        self.pending_reusable_text_frame_signature = None;
        true
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
                let height =
                    (metrics.ascent + metrics.descent).max(font_size as f64) / self.pixel_density;
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
            self.image_text_active_this_frame = true;
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
        let font_key = self.text_font_key(parsed_style);
        let font = self.load_text_font(parsed_style)?;
        let metrics = CachedTextMetrics {
            width: self.cached_text_width(value, &font_key, &font, font_size),
            ascent: measure_text_ascent(&font, font_size),
            descent: measure_text_descent(&font, font_size),
        };
        self.text_metric_cache.insert(cache_key, metrics);
        Ok(metrics)
    }

    fn text_metric_cache_key(&self, value: &str, style: &Style, font_size: usize) -> String {
        let font_key = self.text_font_key(style);
        format!("{font_key}|{font_size}|metrics|{value}")
    }

    fn text_font_key(&self, style: &Style) -> String {
        let font_key = style
            .text_font_path
            .clone()
            .unwrap_or_else(|| format!("name:{}", style.text_font_name));
        font_key
    }

    fn cached_text_width(
        &mut self,
        value: &str,
        font_key: &str,
        font: &FontArc,
        font_size: usize,
    ) -> f64 {
        let scale = PxScale::from(font_size as f32);
        let scaled_font = font.as_scaled(scale);
        let cache_font_key = font_key.to_owned();
        let mut max_width = 0.0_f32;
        for line in value.split('\n') {
            let mut caret = 0.0_f32;
            let mut previous = None;
            for ch in line.chars() {
                let glyph_key = (cache_font_key.clone(), font_size, ch);
                let (glyph_id, advance) =
                    if let Some(cached) = self.text_glyph_advance_cache.get(&glyph_key) {
                        *cached
                    } else {
                        let glyph_id = scaled_font.glyph_id(ch);
                        let advance = scaled_font.h_advance(glyph_id);
                        self.text_glyph_advance_cache
                            .insert(glyph_key, (glyph_id, advance));
                        (glyph_id, advance)
                    };
                if let Some(previous_id) = previous {
                    let kern_key = (cache_font_key.clone(), font_size, previous_id, glyph_id);
                    caret += if let Some(kern) = self.text_kern_cache.get(&kern_key) {
                        *kern
                    } else {
                        let kern = scaled_font.kern(previous_id, glyph_id);
                        self.text_kern_cache.insert(kern_key, kern);
                        kern
                    };
                }
                caret += advance;
                previous = Some(glyph_id);
            }
            max_width = max_width.max(caret);
        }
        max_width as f64
    }
}

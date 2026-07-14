use super::layout::physical_font_size;
use crate::assets::CachedTextMetrics;
use crate::canvas_state::Canvas;
use crate::text::{text_ascent as measure_text_ascent, text_descent as measure_text_descent};
use crate::types::Style;
use ab_glyph::{Font, FontArc, PxScale, ScaleFont};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;

impl Canvas {
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
        let font_size = physical_font_size(parsed_style, self.pixel_density);
        let metrics = self.cached_text_metrics(value, parsed_style, font_size)?;
        Ok(metrics.width / self.pixel_density)
    }

    pub(crate) fn text_ascent_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font_size = physical_font_size(&parsed_style, self.pixel_density);
        let metrics = self.cached_text_metrics("", &parsed_style, font_size)?;
        Ok(metrics.ascent / self.pixel_density)
    }

    pub(crate) fn text_descent_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font_size = physical_font_size(&parsed_style, self.pixel_density);
        let metrics = self.cached_text_metrics("", &parsed_style, font_size)?;
        Ok(metrics.descent / self.pixel_density)
    }

    pub(super) fn cached_text_metrics(
        &mut self,
        value: &str,
        parsed_style: &Style,
        font_size: usize,
    ) -> PyResult<CachedTextMetrics> {
        let cache_key = self.text_metric_cache_key(value, parsed_style, font_size);
        if let Some(metrics) = self.text_cache.get_metrics(&cache_key) {
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
        self.text_cache.insert_metrics(cache_key, metrics);
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
                    if let Some(cached) = self.text_cache.get_glyph_advance(&glyph_key) {
                        *cached
                    } else {
                        let glyph_id = scaled_font.glyph_id(ch);
                        let advance = scaled_font.h_advance(glyph_id);
                        self.text_cache
                            .insert_glyph_advance(glyph_key, (glyph_id, advance));
                        (glyph_id, advance)
                    };
                if let Some(previous_id) = previous {
                    let kern_key = (cache_font_key.clone(), font_size, previous_id, glyph_id);
                    caret += if let Some(kern) = self.text_cache.get_kern(&kern_key) {
                        *kern
                    } else {
                        let kern = scaled_font.kern(previous_id, glyph_id);
                        self.text_cache.insert_kern(kern_key, kern);
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

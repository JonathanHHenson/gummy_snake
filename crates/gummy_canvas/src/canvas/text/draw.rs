use super::layout::{
    layout_cached_text_line, layout_gpu_text_line, physical_font_size, text_lines,
};
use crate::prelude::*;
use crate::runtime::style::*;

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
    pub(crate) fn text_with_style(
        &mut self,
        value: &str,
        x: f64,
        y: f64,
        parsed_style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        ensure_supported_style(parsed_style)?;
        let Some(fill) = parsed_style.fill else {
            return Ok(());
        };
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        if parsed_style.text_leading <= 0.0 || !parsed_style.text_leading.is_finite() {
            return Err(PyValueError::new_err("text_leading must be positive."));
        }

        for (line_index, line) in text_lines(value).enumerate() {
            if self.can_draw_gpu_text(parsed_style, matrix) {
                let font_size = physical_font_size(parsed_style, self.pixel_density);
                let metrics = self.cached_text_metrics(line, parsed_style, font_size)?;
                let Some(layout) = layout_gpu_text_line(
                    metrics,
                    x,
                    y,
                    line_index,
                    parsed_style,
                    font_size,
                    self.pixel_density,
                ) else {
                    continue;
                };
                self.draw_gpu_text(
                    line,
                    layout.dx * self.pixel_density,
                    layout.dy * self.pixel_density,
                    layout.draw_width,
                    layout.draw_height,
                    font_size as f64,
                    layout.line_height,
                    fill,
                )?;
                continue;
            }
            self.image_text_active_this_frame = true;
            let cached = self.cached_text_line(line, fill, parsed_style)?;
            let Some(layout) = layout_cached_text_line(
                &cached,
                x,
                y,
                line_index,
                parsed_style,
                self.pixel_density,
            ) else {
                continue;
            };

            if self.try_draw_gpu_image_parts(
                cached.texture_key,
                cached.image.version,
                cached.image.width,
                cached.image.height,
                &cached.image.pixels,
                layout.dx,
                layout.dy,
                layout.width,
                layout.height,
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
                layout.dx,
                layout.dy,
                layout.width,
                layout.height,
                parsed_style,
                matrix,
                None,
            )?;
        }
        Ok(())
    }
}

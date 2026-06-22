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
        let font = self.load_text_font(&parsed_style)?;
        let font_size = (parsed_style.text_size * self.pixel_density)
            .round()
            .max(1.0) as usize;
        Ok(text_width(value, &font, font_size) / self.pixel_density)
    }

    pub(crate) fn text_ascent_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font = self.load_text_font(&parsed_style)?;
        let font_size = (parsed_style.text_size * self.pixel_density)
            .round()
            .max(1.0) as usize;
        Ok(measure_text_ascent(&font, font_size) / self.pixel_density)
    }

    pub(crate) fn text_descent_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<f64> {
        self.performance_counters.text_measurements += 1;
        let parsed_style = self.cached_style(style)?;
        if parsed_style.text_size <= 0.0 || !parsed_style.text_size.is_finite() {
            return Err(PyValueError::new_err("text_size must be positive."));
        }
        let font = self.load_text_font(&parsed_style)?;
        let font_size = (parsed_style.text_size * self.pixel_density)
            .round()
            .max(1.0) as usize;
        Ok(measure_text_descent(&font, font_size) / self.pixel_density)
    }
}

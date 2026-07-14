use super::super::images::{
    BatchCanvasImage, BatchUniqueImage, ImageBatchBuilder, IMAGE_ATLAS_MAX_UNIQUE_IMAGES,
};
use super::layout::{layout_cached_text_line, text_lines};
use crate::canvas_state::Canvas;
use crate::raster::Matrix;
use crate::types::Style;
use pyo3::prelude::*;
use pyo3::types::PyAny;

impl Canvas {
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
        if self.try_text_batch_cached_image_atlas(&items, parsed_style, matrix)? {
            return Ok(false);
        }
        for (value, x, y) in items {
            self.text_with_style(&value, x, y, parsed_style, matrix)?;
        }
        Ok(false)
    }

    fn try_text_batch_cached_image_atlas(
        &mut self,
        items: &[(String, f64, f64)],
        parsed_style: &Style,
        matrix: Matrix,
    ) -> PyResult<bool> {
        if items.is_empty()
            || self.gpu.is_none()
            || !self.can_queue_gpu_primitives(parsed_style)
            || parsed_style.fill.is_none()
        {
            return Ok(false);
        }
        let fill = parsed_style.fill.expect("fill was checked");
        let mut batch = ImageBatchBuilder::with_record_capacity(items.len());
        let mut drew_any = false;

        for (value, x, y) in items {
            for (line_index, line) in text_lines(value).enumerate() {
                let cached = self.cached_text_line(line, fill, parsed_style)?;
                let Some(layout) = layout_cached_text_line(
                    &cached,
                    *x,
                    *y,
                    line_index,
                    parsed_style,
                    self.pixel_density,
                ) else {
                    continue;
                };

                let unique_key = (cached.texture_key, cached.image.version);
                if !batch.contains_unique(unique_key)
                    && batch.unique_len() >= IMAGE_ATLAS_MAX_UNIQUE_IMAGES
                {
                    if self.draw_cached_text_image_batch(
                        batch.unique_images(),
                        batch.records(),
                        parsed_style,
                    )? {
                        drew_any = true;
                    }
                    batch.clear();
                }
                batch.push_cached_text_image(
                    &cached,
                    layout.dx,
                    layout.dy,
                    layout.width,
                    layout.height,
                    matrix,
                );
            }
        }
        if self.draw_cached_text_image_batch(
            batch.unique_images(),
            batch.records(),
            parsed_style,
        )? {
            drew_any = true;
        }
        Ok(drew_any)
    }

    fn draw_cached_text_image_batch(
        &mut self,
        unique_images: &[BatchUniqueImage],
        records: &[BatchCanvasImage],
        parsed_style: &Style,
    ) -> PyResult<bool> {
        if records.is_empty() {
            return Ok(false);
        }
        if self.try_draw_gpu_image_atlas_batch(unique_images, records, parsed_style)? {
            return Ok(true);
        }
        self.draw_image_batch_records(unique_images, records, parsed_style, true)?;
        Ok(true)
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
}

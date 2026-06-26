use crate::runtime::style::*;
use crate::*;

mod export;
mod load;
mod update;

impl Canvas {
    pub(crate) fn blend_region_impl(
        &mut self,
        source_pixels: Option<Vec<u8>>,
        source_width: Option<usize>,
        source_height: Option<usize>,
        source: (i64, i64, i64, i64),
        destination: (i64, i64, i64, i64),
        mode: &str,
    ) -> PyResult<()> {
        ensure_supported_blend_mode(mode)?;
        let (dest_x, dest_y, dest_w, dest_h) = scale_rect(destination, self.pixel_density);
        if dest_w <= 0 || dest_h <= 0 {
            return Ok(());
        }
        self.prepare_cpu_composite();
        let source_owned;
        let (source_data, source_canvas_width, source_canvas_height, source_rect) =
            if let Some(pixels) = source_pixels {
                let width = source_width.ok_or_else(|| {
                    PyValueError::new_err("External blend source width is required.")
                })?;
                let height = source_height.ok_or_else(|| {
                    PyValueError::new_err("External blend source height is required.")
                })?;
                validate_rgba_buffer(pixels.len(), width, height)?;
                source_owned = pixels;
                (&source_owned[..], width, height, source)
            } else {
                (
                    &self.pixels[..],
                    self.physical_width,
                    self.physical_height,
                    scale_rect(source, self.pixel_density),
                )
            };
        let Some((sx, sy, sw, sh)) =
            clipped_source_rect(source_rect, source_canvas_width, source_canvas_height)
        else {
            return Ok(());
        };
        let Some((dx, dy, dw, dh)) = clipped_dest_rect(
            (dest_x, dest_y, dest_w, dest_h),
            self.physical_width,
            self.physical_height,
        ) else {
            return Ok(());
        };
        let sampled = source_data.to_vec();
        blit_scaled_region(
            &mut self.pixels,
            &mut self.present_pixels,
            self.physical_width,
            &sampled,
            source_canvas_width,
            sx,
            sy,
            sw,
            sh,
            dx,
            dy,
            dw,
            dh,
            false,
            mode,
            "linear",
            self.clip_masks.last().map(Vec::as_slice),
        );
        self.upload_cpu_pixels()?;
        Ok(())
    }
}

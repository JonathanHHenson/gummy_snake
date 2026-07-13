use super::{BatchCanvasImage, BatchUniqueImage};
use crate::prelude::*;

impl Canvas {
    pub(crate) fn draw_image_batch_records(
        &mut self,
        unique_images: &[BatchUniqueImage],
        records: &[BatchCanvasImage],
        style: &Style,
        try_individual_gpu: bool,
    ) -> PyResult<()> {
        for record in records {
            let image = &unique_images[record.unique_index];

            if try_individual_gpu
                && self.try_draw_gpu_image_parts(
                    image.key,
                    image.version,
                    image.width,
                    image.height,
                    image.pixels.as_slice(),
                    record.dx,
                    record.dy,
                    record.dw,
                    record.dh,
                    style,
                    record.matrix,
                    record.source,
                )?
            {
                continue;
            }
            self.draw_image_pixels_with_style(
                image.pixels.as_slice(),
                image.width,
                image.height,
                record.dx,
                record.dy,
                record.dw,
                record.dh,
                style,
                record.matrix,
                record.source,
            )?;
        }
        Ok(())
    }
}

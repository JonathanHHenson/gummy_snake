use super::{BatchCanvasImage, BatchUniqueImage};
use crate::prelude::*;

impl Canvas {
    pub(super) fn cache_canvas_image_payload(
        &mut self,
        image_key: u64,
        image_version: u64,
        image_width: usize,
        image_height: usize,
        image_pixels: &[u8],
    ) {
        if self
            .image_cache
            .needs_update(image_key, image_version, image_width, image_height)
        {
            self.evict_image_cache_if_needed(image_key);
            self.image_cache.insert(
                image_key,
                CachedImage {
                    version: image_version,
                    width: image_width,
                    height: image_height,
                    pixels: image_pixels.to_vec(),
                },
            );
        }
    }

    pub(crate) fn draw_image_batch_records(
        &mut self,
        unique_images: &[BatchUniqueImage],
        records: &[BatchCanvasImage],
        style: &Style,
        cache_images: bool,
        try_individual_gpu: bool,
    ) -> PyResult<()> {
        for record in records {
            let image = &unique_images[record.unique_index];
            if cache_images {
                self.cache_canvas_image_payload(
                    image.key,
                    image.version,
                    image.width,
                    image.height,
                    &image.pixels,
                );
            }
            if try_individual_gpu
                && self.try_draw_gpu_image_parts(
                    image.key,
                    image.version,
                    image.width,
                    image.height,
                    &image.pixels,
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
                &image.pixels,
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

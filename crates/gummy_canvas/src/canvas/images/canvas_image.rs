use super::ImageBatchBuilder;
use crate::prelude::*;

impl Canvas {
    pub(crate) fn draw_canvas_image_impl(
        &mut self,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.cache_canvas_image_payload(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
        );
        if self.try_draw_gpu_image_parts_for_payload(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )? {
            return Ok(());
        }
        self.draw_image_pixels(
            &image.pixels,
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_canvas_image_current_impl(
        &mut self,
        image: PyRef<'_, CanvasImage>,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        self.cache_canvas_image_payload(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
        );
        if self.try_draw_gpu_image_parts(
            image.key,
            image.version,
            image.width,
            image.height,
            &image.pixels,
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
            &image.pixels,
            image.width,
            image.height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }

    pub(crate) fn batch_canvas_images_impl(
        &mut self,
        records: &Bound<'_, PyAny>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let ingest_start = std::time::Instant::now();
        let style = self.cached_style(style)?;
        let batch = ImageBatchBuilder::parse_canvas_records(records, matrix)?;
        if self.try_draw_gpu_image_atlas_batch(batch.unique_images(), batch.records(), &style)? {
            self.performance_counters.native_command_ingest_time_ms +=
                ingest_start.elapsed().as_secs_f64() * 1000.0;
            return Ok(());
        }
        let (unique_images, records) = batch.into_parts();
        let result = self.draw_image_batch_records(&unique_images, &records, &style, true, true);
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        result
    }

    pub(crate) fn batch_canvas_images_transformed_impl(
        &mut self,
        records: &Bound<'_, PyAny>,
        style: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let ingest_start = std::time::Instant::now();
        let style = self.cached_style(style)?;
        let batch = ImageBatchBuilder::parse_transformed_canvas_records(records)?;
        if self.try_draw_gpu_image_atlas_batch(batch.unique_images(), batch.records(), &style)? {
            self.performance_counters.native_command_ingest_time_ms +=
                ingest_start.elapsed().as_secs_f64() * 1000.0;
            return Ok(());
        }
        let (unique_images, records) = batch.into_parts();
        let result = self.draw_image_batch_records(&unique_images, &records, &style, false, true);
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        result
    }

    pub(crate) fn batch_canvas_image_motion_terms_impl(
        &mut self,
        records: &[u8],
        images: Vec<PyRef<'_, CanvasImage>>,
        frame: u64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let ingest_start = std::time::Instant::now();
        let style = self.cached_style(style)?;
        let batch = ImageBatchBuilder::parse_motion_records(records, &images, frame, matrix)?;
        if batch.is_empty() {
            self.performance_counters.native_command_ingest_time_ms +=
                ingest_start.elapsed().as_secs_f64() * 1000.0;
            return Ok(());
        }
        if self.try_draw_gpu_image_atlas_batch(batch.unique_images(), batch.records(), &style)? {
            self.performance_counters.native_command_ingest_time_ms +=
                ingest_start.elapsed().as_secs_f64() * 1000.0;
            return Ok(());
        }
        let (unique_images, records) = batch.into_parts();
        let result = self.draw_image_batch_records(&unique_images, &records, &style, false, false);
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        result
    }
}

use crate::prelude::*;

impl Canvas {
    pub(crate) fn prepare_cpu_composite(&mut self) -> PyResult<()> {
        self.flush_pending_3d_triangles();
        self.performance_counters.cpu_fallbacks += 1;
        Err(PyValueError::new_err(
            "CPU raster/compositing fallback is disabled in gummy_canvas. This drawing path must use a GPU implementation instead.",
        ))
    }

    pub(crate) fn upload_stale_texture(&mut self, consume_mirrored_commands: bool) -> PyResult<()> {
        self.flush_pending_3d_triangles();
        if !self.texture_stale {
            return Ok(());
        }
        if let Some(gpu) = self.gpu.as_mut() {
            self.performance_counters.pixel_uploads += 1;
            gpu.upload_pixels(&self.pixels)
                .map_err(|err| PyValueError::new_err(format!("Failed to upload pixels: {err}")))?;
            if consume_mirrored_commands {
                gpu.begin_frame();
            }
        }
        self.texture_stale = false;
        if consume_mirrored_commands {
            self.offscreen_dirty = false;
            self.pixels_stale = false;
        }
        Ok(())
    }

    pub(crate) fn render_gpu_frame(&mut self, readback: bool) {
        self.flush_pending_3d_triangles();
        if self.upload_stale_texture(false).is_err() {
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
            return;
        }
        if self.gpu.is_none() {
            self.render_dirty = false;
            self.offscreen_dirty = false;
            self.texture_stale = false;
            return;
        }
        if readback {
            let readback_result = self
                .gpu
                .as_mut()
                .expect("checked above")
                .render_and_read_pixels();
            match readback_result {
                Ok(pixels) => {
                    self.performance_counters.gpu_frames_rendered += 1;
                    self.performance_counters.pixel_readbacks += 1;
                    self.performance_counters.gpu_pixel_readbacks += 1;
                    self.pixels = pixels;
                    self.sync_present_pixels_from_rgba();
                    if let Some(gpu) = self.gpu.as_mut() {
                        gpu.begin_frame();
                    }
                    self.mark_render_clean();
                }
                Err(err) => {
                    self.gpu_error = Some(err);
                    if let Some(gpu) = self.gpu.as_mut() {
                        gpu.begin_frame();
                    }
                    self.mark_render_clean();
                }
            }
            return;
        }
        let Some(gpu) = self.gpu.as_mut() else {
            return;
        };
        let reusable_text_frame_signature = self.pending_reusable_text_frame_signature.take();
        gpu.render();
        self.performance_counters.gpu_frames_rendered += 1;
        gpu.begin_frame();
        self.last_reusable_text_frame_signature = reusable_text_frame_signature;
        self.mark_gpu_rendered_without_readback();
    }

    pub(crate) fn read_gpu_pixels(&mut self) {
        self.flush_pending_3d_triangles();
        let Some(gpu) = self.gpu.as_mut() else {
            self.pixels_stale = false;
            return;
        };
        match gpu.read_pixels() {
            Ok(pixels) => {
                self.performance_counters.pixel_readbacks += 1;
                self.performance_counters.gpu_pixel_readbacks += 1;
                self.pixels = pixels;
                self.sync_present_pixels_from_rgba();
                self.pixels_stale = false;
            }
            Err(err) => {
                self.gpu_error = Some(err);
                self.pixels_stale = false;
            }
        }
    }
}

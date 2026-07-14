use super::LIVE_RESIZE_PRESENT_COOLDOWN;
use crate::canvas_state::Canvas;
use crate::runtime::InteractiveRuntime;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

impl Canvas {
    pub(crate) fn begin_frame_impl(&mut self) {
        self.performance_counters.bridge_calls += 1;
        self.begin_frame_command_generation();
        self.cpu_compositing_active = false;
        self.image_text_active_this_frame = false;
        self.pending_reusable_text_frame_signature = None;
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.begin_frame();
        }
        self.render_dirty = false;
        self.pending_3d_triangles.clear();
    }

    pub(crate) fn end_frame_impl(&mut self) {
        self.flush_pending_3d_triangles();
        if self.render_dirty && self.offscreen_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        } else if self.runtime.is_none() {
            self.render_dirty = false;
        }
    }

    pub(crate) fn present_impl(&mut self) -> PyResult<()> {
        self.performance_counters.bridge_calls += 1;
        self.flush_pending_3d_triangles();
        if self.render_dirty && self.offscreen_dirty && self.runtime.is_none() {
            self.render_gpu_frame(false);
        } else if self.runtime.is_none() {
            self.render_dirty = false;
        }
        if let Some(runtime) = self.runtime.as_mut() {
            if runtime.should_close() {
                self.closed = true;
                return Ok(());
            }
            if runtime.resize_recently(LIVE_RESIZE_PRESENT_COOLDOWN) {
                return Ok(());
            }
        }
        if self.runtime.is_some() {
            let should_present = self.render_dirty;
            if should_present {
                if self.offscreen_dirty {
                    self.render_gpu_frame(false);
                } else if self.texture_stale {
                    self.upload_stale_texture(false)?;
                }
            }
            if should_present {
                let runtime = self.runtime.as_mut().expect("runtime checked above");
                let window = runtime.window().ok_or_else(|| {
                    PyValueError::new_err("Native canvas window is not available for presentation.")
                })?;
                let (surface_width, surface_height) = runtime.physical_size();
                let gpu = self.gpu.as_mut().ok_or_else(|| {
                    PyValueError::new_err(
                        self.gpu_error
                            .clone()
                            .unwrap_or_else(|| "GPU presentation is unavailable.".to_string()),
                    )
                })?;
                let present_start = std::time::Instant::now();
                gpu.present_texture_to_window(window, surface_width, surface_height)
                    .map_err(|err| {
                        PyValueError::new_err(format!("Failed to present native GPU frame: {err}"))
                    })?;
                self.performance_counters.gpu_present_time_ms +=
                    present_start.elapsed().as_secs_f64() * 1000.0;
                self.performance_counters.frames_presented += 1;
                self.render_dirty = false;
            }
            if self
                .runtime
                .as_ref()
                .is_some_and(InteractiveRuntime::should_close)
            {
                self.closed = true;
            }
        }
        Ok(())
    }

    pub(crate) fn close_impl(&mut self) {
        self.closed = true;
        if let Some(runtime) = self.runtime.as_mut() {
            runtime.close();
        }
        if let Some(gpu) = self.gpu.as_mut() {
            gpu.drop_surface();
        }
        self.runtime = None;
    }
}

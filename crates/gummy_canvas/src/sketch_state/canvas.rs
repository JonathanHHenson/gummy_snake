use super::SketchContextState;
use std::time::Instant;

impl SketchContextState {
    pub(super) fn begin_frame_timing_impl(&mut self) {
        let now = Instant::now();
        self.delta_time = (now - self.last_frame_time).as_secs_f64() * 1000.0;
        self.last_frame_time = now;
    }

    pub(super) fn increment_frame_count_impl(&mut self) {
        self.frame_count += 1;
    }

    pub(super) fn millis_impl(&self) -> f64 {
        (Instant::now() - self.start_time).as_secs_f64() * 1000.0
    }

    pub(super) fn sync_canvas_impl(
        &mut self,
        width: i64,
        height: i64,
        physical_width: i64,
        physical_height: i64,
        pixel_density: f64,
        renderer: String,
        created: bool,
    ) {
        self.width = width;
        self.height = height;
        self.physical_width = physical_width;
        self.physical_height = physical_height;
        self.pixel_density = pixel_density;
        self.renderer = renderer;
        self.created = created;
    }
}
